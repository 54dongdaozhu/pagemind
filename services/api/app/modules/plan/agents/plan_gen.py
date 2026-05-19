import json
import logging
from collections.abc import Generator

from app.shared.llm import call_deepseek_stream

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """\
你是一位学习规划专家。请为用户生成一份详细的学习计划和技能树。

用户身份：{identity}
学习目的：{purpose}
用户请求：{message}

背景研究：
{research_context}

请生成一份结构清晰的 Markdown 格式学习计划，包含：
1. 学习目标概述
2. 技能树（层级结构）
3. 分阶段学习路径（每阶段2-4周）
4. 每阶段重点内容和里程碑
5. 推荐学习资源类型

使用中文，格式美观，内容实用。"""


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def generate_plan(state: dict) -> Generator[str, None, None]:
    yield _encode("status", "正在生成学习计划...")
    profile = state.get("profile") or {}
    prompt = _PLAN_PROMPT.format(
        identity=profile.get("identity", "未知"),
        purpose=profile.get("purpose", "未知"),
        message=state["message"],
        research_context=state.get("research_context", ""),
    )
    try:
        accumulated = ""
        for chunk in call_deepseek_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            purpose="plan_generation",
        ):
            accumulated += chunk
            yield _encode("content", chunk)
        state["generated_content"] = accumulated
    except Exception as e:
        logger.warning("Plan generation failed: %s", e)
        yield _encode("error", f"计划生成失败：{e}")
