import os
from functools import lru_cache

_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.3):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=_MODEL,
        api_key=_API_KEY,
        base_url=_BASE_URL,
        temperature=temperature,
        timeout=120,
        max_retries=1,
    )


def call_llm(prompt: str, temperature: float = 0.3) -> str:
    """Synchronous LLM call, returns content string."""
    from langchain_core.messages import HumanMessage
    llm = get_llm(temperature)
    resp = llm.invoke([HumanMessage(content=prompt)])
    return resp.content


async def call_llm_async(prompt: str, temperature: float = 0.3) -> str:
    """Async LLM call."""
    from langchain_core.messages import HumanMessage
    llm = get_llm(temperature)
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    return resp.content
