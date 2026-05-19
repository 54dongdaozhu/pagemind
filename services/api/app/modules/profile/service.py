import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = None
    StateGraph = None

from sqlalchemy import select

from app.core.database import UserProfile, get_db
from app.shared.cache import USER_PROFILE_TTL_SECONDS, get_json, set_json
from app.shared.llm import call_deepseek


logger = logging.getLogger(__name__)

_ANALYZE_PROMPT = """\
请根据以下用户提供的学习背景信息，提取结构化的用户画像。

背景信息：
{background_text}

请以 JSON 格式返回，字段说明：
- identity: 用户的身份角色（如"AI应用开发者"、"在校学生"，简洁一句话）
- purpose: 用户的学习目的（简洁一句话）
- learning_goals: 具体学习目标列表（最多5条，每条简洁一句话）

仅返回 JSON，不要有其他文字。"""


class ProfileState(TypedDict):
    user_id: str
    background_text: str
    identity: str
    purpose: str
    learning_goals: list[str]


def _analyze_node(state: ProfileState) -> ProfileState:
    prompt = _ANALYZE_PROMPT.format(background_text=state["background_text"])
    try:
        raw = call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            purpose="user_profile_analysis",
        )
        parsed = json.loads(raw)
        return {
            **state,
            "identity": parsed.get("identity", ""),
            "purpose": parsed.get("purpose", ""),
            "learning_goals": parsed.get("learning_goals", []),
        }
    except Exception as e:
        logger.warning("Profile analysis LLM failed, using fallback: %s", e)
        snippet = state["background_text"][:100]
        return {
            **state,
            "identity": snippet,
            "purpose": snippet,
            "learning_goals": [],
        }


def _build_graph():
    if StateGraph is None:
        raise RuntimeError("langgraph 未安装，请运行 pip install langgraph")
    g = StateGraph(ProfileState)
    g.add_node("analyze", _analyze_node)
    g.set_entry_point("analyze")
    g.add_edge("analyze", END)
    return g.compile()


_profile_graph = None


def _get_graph():
    global _profile_graph
    if _profile_graph is None:
        _profile_graph = _build_graph()
    return _profile_graph


def _profile_cache_key(user_id: str) -> str:
    return f"user_profile:user:{user_id}"


def persist_user_profile(user_id: str, data: dict) -> None:
    """RQ job: write/update user_profiles table."""
    now = datetime.now(timezone.utc)
    with get_db() as db:
        existing = db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        ).scalar_one_or_none()

        if existing:
            existing.background_text = data["background_text"]
            existing.identity = data["identity"]
            existing.purpose = data["purpose"]
            existing.learning_goals = data["learning_goals"]
            existing.updated_at = now
        else:
            db.add(UserProfile(
                user_id=user_id,
                background_text=data["background_text"],
                identity=data["identity"],
                purpose=data["purpose"],
                learning_goals=data["learning_goals"],
                created_at=now,
                updated_at=now,
            ))
        db.commit()


def analyze_and_save(user_id: str, background_text: str) -> dict:
    """Run profile analysis workflow, cache in Redis, enqueue DB write."""
    initial: ProfileState = {
        "user_id": user_id,
        "background_text": background_text,
        "identity": "",
        "purpose": "",
        "learning_goals": [],
    }
    result = _get_graph().invoke(initial)
    profile = {
        "background_text": background_text,
        "identity": result["identity"],
        "purpose": result["purpose"],
        "learning_goals": result["learning_goals"],
    }
    persist_user_profile(user_id, profile)
    set_json(_profile_cache_key(user_id), profile, USER_PROFILE_TTL_SECONDS)
    return profile


def get_profile(user_id: str) -> dict | None:
    """Return cached profile or load from DB."""
    cached = get_json(_profile_cache_key(user_id))
    if cached is not None:
        return cached

    with get_db() as db:
        row = db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        ).scalar_one_or_none()

    if row is None:
        return None

    profile = {
        "background_text": row.background_text,
        "identity": row.identity,
        "purpose": row.purpose,
        "learning_goals": row.learning_goals or [],
    }
    set_json(_profile_cache_key(user_id), profile, USER_PROFILE_TTL_SECONDS)
    return profile
