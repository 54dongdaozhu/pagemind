import logging
from datetime import datetime, timezone

from app.modules.agent.prompts import MEMORY_SUMMARIZE_PROMPT
from app.modules.agent.utils import format_history, safe_parse_json, sanitize_history
from app.shared import cache
from app.shared.llm import call_deepseek

logger = logging.getLogger(__name__)

SUMMARIZE_THRESHOLD = 16  # history 消息数（约 8 轮对话）


def _memory_key(user_id: str) -> str:
    return f"agent:memory:user:{user_id}"


def get_agent_memory(user_id: str) -> dict | None:
    return cache.get_json(_memory_key(user_id))


def save_agent_memory(user_id: str, memory: dict) -> None:
    cache.set_json(_memory_key(user_id), memory, cache.AGENT_MEMORY_TTL_SECONDS)


def summarize_and_patch(user_id: str, history: list[dict]) -> None:
    """RQ job：压缩对话历史存 Redis，提取画像线索增量更新 UserProfile。模块级函数，可 pickle。"""
    try:
        history_text = format_history(sanitize_history(history))
        prompt = MEMORY_SUMMARIZE_PROMPT.format(history_text=history_text)
        raw = call_deepseek(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            json_mode=True,
            purpose="memory_summarize",
        )
        parsed = safe_parse_json(raw)
        summary = parsed.get("summary", "")
        patches = parsed.get("profile_patches", {})

        memory = {
            "summary": summary,
            "turn_count": len(history) // 2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        save_agent_memory(user_id, memory)

        if any(v for v in patches.values() if v):
            from app.modules.profile.service import patch_profile
            patch_profile(user_id, patches)
    except Exception:
        logger.exception("[memory] summarize_and_patch failed for user=%s", user_id)
