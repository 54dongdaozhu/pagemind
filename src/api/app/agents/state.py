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


class DocumentKPState(TypedDict):
    doc_id: str
    user_id: str
    all_chunk_kps: list[dict]      # 所有 chunk 的原始 KPs（带 chunk_id 字段）
    global_registry: dict          # text → KP，跨块去重记忆
    deduped_kps: list[dict]        # CrossChunkDedup 输出
    doc_summary: str               # DocImportance 从工具读取的文档摘要
    scored_kps: list[dict]         # DocImportance 输出
    verified_kps: list[dict]       # RAGVerify 输出
    stop_reason: str


Intent = Literal[
    "qa",
    "explain",
    "summarize",
    "compare",
    "practice",
    "grade",
    "relation",
    "structure",
    "review",
    "unknown",
]


class LearningAgentState(TypedDict):
    user_id: str
    doc_id: str | None
    message: str
    history: list[dict[str, str]]
    intent: Intent
    query: str
    summary: str
    sources: list[RagSource]
    answer: str
    tools_used: list[str]
    active_agent: str
    stop_reason: str
