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
from app.shared.cache import USER_PROFILE_TTL_SECONDS, get_or_set_json, get_redis, set_json
from app.shared.llm import call_deepseek


logger = logging.getLogger(__name__)

_ANALYZE_PROMPT = """\
请根据以下用户提供的技术学习背景信息，提取结构化的用户画像。产品默认面向技术自学者，例如开发者、转行者、工程实践者。

背景信息：
{background_text}

请以 JSON 格式返回，字段说明：
- identity: 用户的身份角色（如"AI应用开发者"、"后端开发者"、"转行软件工程师"，简洁一句话）
- purpose: 用户的学习目的（简洁一句话）
- learning_goals: 具体学习目标列表（最多5条，每条简洁一句话）
- skill_level: "入门"/"初级"/"中级"/"高级" 之一，无法判断则返回 null
- tech_stack: 已知技术列表（JSON 数组），无则返回 []
- knowledge_gaps: 用户明确提及的薄弱领域（JSON 数组），无则返回 []
- learning_style: "实践导向"/"理论导向"/"系统学习"/"项目驱动" 之一，无法判断则返回 null
- depth_preference: "快速概览"/"适中深度"/"深度系统" 之一，无法判断则返回 null
- urgency: "快速入门"/"按部就班"/"长期规划" 之一，无法判断则返回 null
- domain_focus: 关注领域列表（JSON 数组），无则返回 []

仅返回 JSON，不要有其他文字。"""


class ProfileState(TypedDict):
    user_id: str
    background_text: str
    identity: str
    purpose: str
    learning_goals: list[str]
    skill_level: str | None
    tech_stack: list[str]
    knowledge_gaps: list[str]
    learning_style: str | None
    depth_preference: str | None
    urgency: str | None
    domain_focus: list[str]


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
            "learning_goals": parsed.get("learning_goals") or [],
            "skill_level": parsed.get("skill_level"),
            "tech_stack": parsed.get("tech_stack") or [],
            "knowledge_gaps": parsed.get("knowledge_gaps") or [],
            "learning_style": parsed.get("learning_style"),
            "depth_preference": parsed.get("depth_preference"),
            "urgency": parsed.get("urgency"),
            "domain_focus": parsed.get("domain_focus") or [],
        }
    except Exception as e:
        logger.warning("Profile analysis LLM failed, using fallback: %s", e)
        snippet = state["background_text"][:100]
        return {
            **state,
            "identity": snippet,
            "purpose": snippet,
            "learning_goals": [],
            "skill_level": None,
            "tech_stack": [],
            "knowledge_gaps": [],
            "learning_style": None,
            "depth_preference": None,
            "urgency": None,
            "domain_focus": [],
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
            if data.get("skill_level") is not None:
                existing.skill_level = data["skill_level"]
            if data.get("tech_stack") is not None:
                existing.tech_stack = data["tech_stack"]
            if data.get("knowledge_gaps") is not None:
                existing.knowledge_gaps = data["knowledge_gaps"]
            if data.get("learning_style") is not None:
                existing.learning_style = data["learning_style"]
            if data.get("depth_preference") is not None:
                existing.depth_preference = data["depth_preference"]
            if data.get("urgency") is not None:
                existing.urgency = data["urgency"]
            if data.get("domain_focus") is not None:
                existing.domain_focus = data["domain_focus"]
            existing.updated_at = now
        else:
            db.add(UserProfile(
                user_id=user_id,
                background_text=data["background_text"],
                identity=data["identity"],
                purpose=data["purpose"],
                learning_goals=data["learning_goals"],
                skill_level=data.get("skill_level"),
                tech_stack=data.get("tech_stack"),
                knowledge_gaps=data.get("knowledge_gaps"),
                learning_style=data.get("learning_style"),
                depth_preference=data.get("depth_preference"),
                urgency=data.get("urgency"),
                domain_focus=data.get("domain_focus"),
                created_at=now,
                updated_at=now,
            ))
        db.commit()


def patch_profile(user_id: str, patches: dict) -> None:
    """RQ job: 增量更新 UserProfile，不覆盖已有单值字段；列表字段做并集合并。"""
    _LIST_FIELDS = {"tech_stack", "knowledge_gaps", "domain_focus"}
    now = datetime.now(timezone.utc)
    with get_db() as db:
        existing = db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        ).scalar_one_or_none()
        if existing is None:
            return

        changed = False
        for key, value in patches.items():
            if not hasattr(existing, key):
                continue
            if value is None or value == "" or value == []:
                continue
            current = getattr(existing, key)
            if key in _LIST_FIELDS:
                merged = list({*(current or []), *value})[:20]
                setattr(existing, key, merged)
                changed = True
            elif current is None:
                setattr(existing, key, value)
                changed = True

        if changed:
            existing.updated_at = now
            db.commit()

    try:
        get_redis().delete(_profile_cache_key(user_id))
    except Exception:
        pass


def analyze_and_save(user_id: str, background_text: str) -> dict:
    """Run profile analysis workflow, cache in Redis, write to DB."""
    initial: ProfileState = {
        "user_id": user_id,
        "background_text": background_text,
        "identity": "",
        "purpose": "",
        "learning_goals": [],
        "skill_level": None,
        "tech_stack": [],
        "knowledge_gaps": [],
        "learning_style": None,
        "depth_preference": None,
        "urgency": None,
        "domain_focus": [],
    }
    result = _get_graph().invoke(initial)
    profile = {
        "background_text": background_text,
        "identity": result["identity"],
        "purpose": result["purpose"],
        "learning_goals": result["learning_goals"],
        "skill_level": result["skill_level"],
        "tech_stack": result["tech_stack"],
        "knowledge_gaps": result["knowledge_gaps"],
        "learning_style": result["learning_style"],
        "depth_preference": result["depth_preference"],
        "urgency": result["urgency"],
        "domain_focus": result["domain_focus"],
    }
    persist_user_profile(user_id, profile)
    set_json(_profile_cache_key(user_id), profile, USER_PROFILE_TTL_SECONDS)
    return profile


def get_profile(user_id: str) -> dict | None:
    """Return cached profile or load from DB."""
    def load_profile() -> dict | None:
        with get_db() as db:
            row = db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            ).scalar_one_or_none()

        if row is None:
            return None

        return {
            "background_text": row.background_text,
            "identity": row.identity,
            "purpose": row.purpose,
            "learning_goals": row.learning_goals or [],
            "skill_level": row.skill_level,
            "tech_stack": row.tech_stack or [],
            "knowledge_gaps": row.knowledge_gaps or [],
            "learning_style": row.learning_style,
            "depth_preference": row.depth_preference,
            "urgency": row.urgency,
            "domain_focus": row.domain_focus or [],
        }

    return get_or_set_json(
        _profile_cache_key(user_id),
        load_profile,
        USER_PROFILE_TTL_SECONDS,
        wait_timeout_seconds=1.0,
    )
