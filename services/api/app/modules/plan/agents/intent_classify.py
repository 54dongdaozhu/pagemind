import json
import logging

from app.shared.llm import call_deepseek

logger = logging.getLogger(__name__)

_INTENT_PROMPT = """\
你是一个意图分类器。根据用户的消息和对话历史，判断用户的意图。

用户画像：
identity: {identity}
purpose: {purpose}

对话历史（最近几轮）：
{history_text}

用户当前消息：{message}

请返回 JSON，字段：
- intent: 只能是 "need_info"（需要更多用户信息）、"gen_plan"（生成学习计划/技能树）、\
"gen_doc"（生成教学文档）、"qa"（问答/答疑）之一
- reason: 简短说明

意图判断参考：
- 用户提到"计划"、"路线图"、"技能树"、"怎么学"、"学习路径"、"规划" → gen_plan
- 用户提到"讲解"、"教我"、"文档"、"详细介绍"、"写一篇"、"介绍一下" → gen_doc
- 用户提问某个概念、原理、区别、用法 → qa
- 信息不足以理解用户目标时 → need_info

仅返回 JSON。"""

_FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "gen_plan": ["计划", "路线", "技能树", "怎么学", "学习路径", "规划"],
    "gen_doc": ["讲解", "教我", "文档", "详细介绍", "写一篇", "介绍一下"],
    "qa": ["是什么", "为什么", "区别", "怎么", "原理", "如何"],
}


def _keyword_fallback(message: str) -> str:
    for intent, keywords in _FALLBACK_KEYWORDS.items():
        if any(kw in message for kw in keywords):
            return intent
    return "qa"


def classify_intent(message: str, history: list[dict], profile: dict | None) -> str:
    identity = (profile or {}).get("identity", "")
    purpose = (profile or {}).get("purpose", "")
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-6:]
    ) or "（无）"

    prompt = _INTENT_PROMPT.format(
        identity=identity,
        purpose=purpose,
        history_text=history_text,
        message=message,
    )
    try:
        raw = call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            json_mode=True,
            purpose="plan_intent_classify",
        )
        parsed = json.loads(raw)
        intent = parsed.get("intent", "")
        if intent in ("need_info", "gen_plan", "gen_doc", "qa"):
            return intent
        logger.warning("Intent classify returned unknown value: %s", intent)
    except Exception as e:
        logger.warning("Intent classify LLM failed, using keyword fallback: %s", e)
    return _keyword_fallback(message)
