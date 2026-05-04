from typing import Literal, TypedDict

from app.schemas.knowledge import RagSource


class KnowledgeAgentState(TypedDict):
    original_text: str
    current_text: str
    discovered_kps: list[dict]
    filtered_kps: list[dict]
    ranked_kps: list[dict]
    retry_count: int
    stop_reason: str


Intent = Literal["qa", "explain", "summarize", "compare", "unknown"]


class LearningAgentState(TypedDict):
    doc_id: str | None
    message: str
    intent: Intent
    query: str
    summary: str
    sources: list[RagSource]
    answer: str
    tools_used: list[str]
    active_agent: str
    stop_reason: str
