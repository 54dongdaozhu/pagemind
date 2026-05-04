import json

import requests
from fastapi import HTTPException

from app.core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL


REQUEST_PROXIES = {"http": None, "https": None}


def call_deepseek(messages: list, temperature: float = 0.3, json_mode: bool = False) -> str:
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

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
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {str(e)}")
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回格式异常: {str(e)}")


def call_deepseek_stream(messages: list, temperature: float = 0.5):
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }

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
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except requests.exceptions.RequestException as e:
        yield f"\n\n[错误] LLM 调用失败: {str(e)}"


def get_llm(temperature: float = 0.2):
    """获取 LangChain ChatOpenAI 实例，供 LangGraph 节点使用。"""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(
            "缺少 LangGraph 提取依赖，请安装 langgraph langchain-openai langchain"
        ) from e

    return ChatOpenAI(
        model="deepseek-chat",
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
        timeout=60,
    )
