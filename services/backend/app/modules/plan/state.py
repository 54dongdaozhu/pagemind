from typing import TypedDict


class PlanConvState(TypedDict):
    user_id: str
    message: str
    history: list[dict]
    profile: dict | None

    intent: str
    missing_fields: list[str]
    research_context: str
    generated_content: str

    question_to_user: str | None

    stop_reason: str
