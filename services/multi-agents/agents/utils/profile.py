from typing import Any


def build_profile_hint(user_profile: dict[str, Any] | None, label: str = "Learner profile") -> str:
    if not user_profile:
        return ""

    parts: list[str] = []

    level = str(user_profile.get("level") or "").strip()
    if level:
        parts.append(f"level={level}")

    identity = str(user_profile.get("identity") or "").strip()
    if identity:
        parts.append(f"identity={identity}")

    purpose = str(user_profile.get("purpose") or "").strip()
    if purpose:
        parts.append(f"purpose={purpose}")

    goals = user_profile.get("learning_goals") or user_profile.get("goals") or []
    if isinstance(goals, str):
        goals_text = goals.strip()
    elif isinstance(goals, list):
        goals_text = "; ".join(str(goal).strip() for goal in goals if str(goal).strip())
    else:
        goals_text = ""
    if goals_text:
        parts.append(f"goals={goals_text}")

    if not parts:
        return ""
    return f"\n{label}: " + " | ".join(parts)
