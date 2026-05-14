import json
import time

import requests
from fastapi import HTTPException

from app.core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from app.shared.cache import PROMPT_CACHE_TTL_SECONDS, get_text, set_text, stable_hash
from app.shared import db_log


REQUEST_PROXIES = {"http": None, "https": None}

_PROVIDER = "deepseek"
_MODEL = "deepseek-chat"


def _stream_cached_text(text: str, chunk_size: int = 12):
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
        time.sleep(0.01)


def call_deepseek(
    messages: list,
    temperature: float = 0.3,
    json_mode: bool = False,
    purpose: str | None = None,
) -> str:
    cache_key = f"cache:prompt:{stable_hash({'model': _MODEL, 'messages': messages, 'temperature': temperature, 'json_mode': json_mode})}"
    cached = get_text(cache_key)
    if cached is not None:
        return cached

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": _MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    start = time.monotonic()
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
            proxies=REQUEST_PROXIES,
        )
        response.raise_for_status()
        result = response.json()
        usage = result.get("usage", {})
        content = result["choices"][0]["message"]["content"]
        db_log.log_llm_call(
            provider=_PROVIDER,
            model=_MODEL,
            purpose=purpose,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
        set_text(cache_key, content, PROMPT_CACHE_TTL_SECONDS)
        return content
    except requests.exceptions.RequestException as e:
        db_log.log_llm_call(
            provider=_PROVIDER,
            model=_MODEL,
            purpose=purpose,
            latency_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error_details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {str(e)}")
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回格式异常: {str(e)}")


def call_deepseek_stream(
    messages: list,
    temperature: float = 0.5,
    purpose: str | None = None,
):
    cache_key = f"cache:prompt:{stable_hash({'model': _MODEL, 'messages': messages, 'temperature': temperature, 'stream': True})}"
    cached = get_text(cache_key)
    if cached is not None:
        yield from _stream_cached_text(cached)
        return

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": _MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }

    # Capture context vars before first yield so finally block uses correct values
    _user_id = db_log.current_user_id.get()
    _run_id = db_log.current_run_id.get()
    _step_id = db_log.current_step_id.get()
    _qa_id = db_log.current_qa_id.get()

    start = time.monotonic()
    success = True
    error_info = None
    answer_parts = []
    try:
        with requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=60,
            proxies=REQUEST_PROXIES,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        answer_parts.append(content)
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except requests.exceptions.RequestException as e:
        success = False
        error_info = {"error": str(e)}
        yield f"\n\n[错误] LLM 调用失败: {str(e)}"
    finally:
        db_log.log_llm_call(
            provider=_PROVIDER,
            model=_MODEL,
            purpose=purpose,
            latency_ms=int((time.monotonic() - start) * 1000),
            success=success,
            error_details=error_info,
            user_id=_user_id,
            run_id=_run_id,
            step_id=_step_id,
            qa_id=_qa_id,
        )
        if success and answer_parts:
            set_text(cache_key, "".join(answer_parts), PROMPT_CACHE_TTL_SECONDS)


def get_llm(temperature: float = 0.2):
    """获取 LangChain ChatOpenAI 实例，供 LangGraph 节点使用。"""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(
            "缺少 LangGraph 提取依赖，请安装 langgraph langchain-openai langchain"
        ) from e

    return ChatOpenAI(
        model=_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
        timeout=60,
    )
