import json
import logging
from collections.abc import Generator

from app.shared.llm import call_deepseek

logger = logging.getLogger(__name__)

_RESEARCH_PROMPT = """\
你是一位学习规划专家。请基于以下信息，分析这个学习目标所需的核心知识领域和学习路径。

用户身份：{identity}
学习目的：{purpose}
用户请求：{message}

请分析：
1. 核心知识领域（3-5个）
2. 必要前置知识
3. 推荐学习路径的逻辑顺序
4. 典型项目和应用场景

用中文简洁回答，这将作为后续计划生成的参考依据。"""


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def research(state: dict) -> Generator[str, None, None]:
    yield _encode("status", "正在分析学习目标...")
    profile = state.get("profile") or {}
    prompt = _RESEARCH_PROMPT.format(
        identity=profile.get("identity", "未知"),
        purpose=profile.get("purpose", "未知"),
        message=state["message"],
    )
    try:
        context = call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            purpose="plan_research",
        )
        state["research_context"] = context
    except Exception as e:
        logger.warning("Research LLM failed: %s", e)
        state["research_context"] = ""
