import logging

from app.shared.cache import get_json, set_json

logger = logging.getLogger(__name__)

PLAN_MEMORY_TTL = 7200
CHAT_MEMORY_TTL = 3600
MEMORY_MAX_TURNS = 10


def _plan_key(user_id: str) -> str:
    return f"plan_memory:user:{user_id}"


def _chat_key(user_id: str) -> str:
    return f"chat_memory:user:{user_id}"


def get_plan_memory(user_id: str) -> list[dict]:
    return get_json(_plan_key(user_id)) or []


def save_plan_memory(user_id: str, user_msg: str, assistant_msg: str) -> None:
    history = get_plan_memory(user_id)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    if len(history) > MEMORY_MAX_TURNS * 2:
        history = history[-(MEMORY_MAX_TURNS * 2):]
    set_json(_plan_key(user_id), history, PLAN_MEMORY_TTL)


def get_chat_memory(user_id: str) -> list[dict]:
    return get_json(_chat_key(user_id)) or []


def save_chat_memory(user_id: str, user_msg: str, assistant_msg: str) -> None:
    history = get_chat_memory(user_id)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    if len(history) > MEMORY_MAX_TURNS * 2:
        history = history[-(MEMORY_MAX_TURNS * 2):]
    set_json(_chat_key(user_id), history, CHAT_MEMORY_TTL)
