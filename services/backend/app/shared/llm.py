import json
import logging
import time

import requests
from fastapi import HTTPException

from app.core.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    FALLBACK_LLM_API_KEY,
    FALLBACK_LLM_BASE_URL,
    FALLBACK_LLM_MODEL,
    LLM_CIRCUIT_FAILURE_THRESHOLD,
    LLM_CIRCUIT_RECOVERY_SECONDS,
    VISION_LLM_API_KEY,
    VISION_LLM_BASE_URL,
    VISION_LLM_MODEL,
)
from app.shared.cache import PROMPT_CACHE_TTL_SECONDS, get_text, set_text, stable_hash
from app.shared.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.shared import db_log

logger = logging.getLogger(__name__)

REQUEST_PROXIES = {"http": None, "https": None}

_http_session = requests.Session()

_PROVIDER = "deepseek"
_MODEL = "deepseek-chat"


_breaker = CircuitBreaker(
    name="llm",
    failure_threshold=LLM_CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=LLM_CIRCUIT_RECOVERY_SECONDS,
)


def _http_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    temperature: float,
    json_mode: bool,
) -> tuple[str, dict]:
    """Returns (content, usage). Raises requests.exceptions.RequestException on failure."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = _http_session.post(url, headers=headers, json=payload, timeout=60, proxies=REQUEST_PROXIES)
    response.raise_for_status()
    result = response.json()
    content = result["choices"][0]["message"]["content"]
    return content, result.get("usage", {})


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

    try:
        _breaker.before_call()
    except CircuitOpenError:
        raise HTTPException(status_code=503, detail="LLM 服务暂时不可用，请稍后重试。")

    start = time.monotonic()
    try:
        content, usage = _http_chat_completion(
            DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, _MODEL, messages, temperature, json_mode
        )
        if not content.strip():
            raise HTTPException(status_code=502, detail="LLM 返回了空内容，请稍后重试。")
        _breaker.record_success()
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
        _breaker.record_failure()
        if FALLBACK_LLM_API_KEY and FALLBACK_LLM_BASE_URL and FALLBACK_LLM_MODEL:
            try:
                content, usage = _http_chat_completion(
                    FALLBACK_LLM_BASE_URL, FALLBACK_LLM_API_KEY, FALLBACK_LLM_MODEL,
                    messages, temperature, json_mode,
                )
                db_log.log_llm_call(
                    provider="fallback",
                    model=FALLBACK_LLM_MODEL,
                    purpose=purpose,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    latency_ms=int((time.monotonic() - start) * 1000),
                    success=True,
                )
                set_text(cache_key, content, PROMPT_CACHE_TTL_SECONDS)
                return content
            except requests.exceptions.RequestException as fe:
                db_log.log_llm_call(
                    provider="fallback",
                    model=FALLBACK_LLM_MODEL,
                    purpose=purpose,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    success=False,
                    error_details={"error": str(fe)},
                )
        db_log.log_llm_call(
            provider=_PROVIDER,
            model=_MODEL,
            purpose=purpose,
            latency_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error_details={"error": str(e)},
        )
        raise HTTPException(status_code=503, detail=f"LLM 调用失败: {str(e)}")
    except HTTPException as e:
        if e.status_code >= 500:
            _breaker.record_failure()
        raise
    except (KeyError, IndexError) as e:
        _breaker.record_failure()
        raise HTTPException(status_code=500, detail=f"LLM 返回格式异常: {str(e)}")


def call_vision_llm(
    image_base64: str,
    content_type: str,
    prompt: str,
    purpose: str | None = None,
) -> str | None:
    """Describe an image via a vision-capable LLM. Returns None if not configured or on failure."""
    if not (VISION_LLM_API_KEY and VISION_LLM_BASE_URL and VISION_LLM_MODEL):
        return None
    data_url = f"data:{content_type};base64,{image_base64}"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    start = time.monotonic()
    try:
        content, usage = _http_chat_completion(
            VISION_LLM_BASE_URL, VISION_LLM_API_KEY, VISION_LLM_MODEL,
            messages, 0.3, False,
        )
        db_log.log_llm_call(
            provider="vision",
            model=VISION_LLM_MODEL,
            purpose=purpose,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
        return content.strip() or None
    except Exception as exc:
        logger.warning("[VisionLLM] image description failed: %s", exc)
        db_log.log_llm_call(
            provider="vision",
            model=VISION_LLM_MODEL,
            purpose=purpose,
            latency_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error_details={"error": str(exc)},
        )
        return None


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

    try:
        _breaker.before_call()
    except CircuitOpenError:
        yield "\n\n[错误] LLM 服务暂时不可用，请稍后重试。"
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
        with _http_session.post(
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
        _breaker.record_success()
    except requests.exceptions.RequestException as e:
        success = False
        error_info = {"error": str(e)}
        _breaker.record_failure()
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
