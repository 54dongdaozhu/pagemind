from typing import List, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    message: str
    doc_id: str | None = None
    history: List[ChatMessage] = Field(default_factory=list)


class RagIndexRequest(BaseModel):
    doc_id: str
    text: str
    title: str | None = None
    chunks: List[str] | None = None
    chunk_size: int = 800
    chunk_overlap: int = 120


class RagSource(BaseModel):
    chunk_index: int
    content: str
    score: float
    retrieval_method: Literal["embedding", "keyword"] = "keyword"


class AgentChatResponse(BaseModel):
    reply: str
    agent: str
    intent: str
    tools_used: List[str] = []
    stop_reason: str
    sources: List[RagSource] = []


class RagQueryRequest(BaseModel):
    doc_id: str
    question: str
    top_k: int = 4


class RagQueryResponse(BaseModel):
    reply: str
    sources: List[RagSource]


class ExtractRequest(BaseModel):
    text: str
    chunk_id: str
    doc_id: str | None = None
    chunk_index: int | None = None
    run_id: str | None = None


class ExtractBatchItem(BaseModel):
    text: str
    chunk_id: str
    doc_id: str | None = None
    chunk_index: int | None = None


class ExtractBatchRequest(BaseModel):
    chunks: List[ExtractBatchItem]
    run_id: str | None = None


class ExtractStartRequest(BaseModel):
    doc_id: str
    chunks: List[ExtractBatchItem]
    title: str | None = None
    source: str = "frontend_chunks"


class ExtractStartResponse(BaseModel):
    run_id: str
    status: str
    total: int


class ExtractFinalizeRequest(BaseModel):
    run_id: str
    doc_id: str
    chunks: List[ExtractBatchItem]


class ExtractStatusResponse(BaseModel):
    run_id: str
    doc_id: str | None = None
    workflow_type: str = "knowledge_extraction"
    status: str
    total: int = 0
    done: int = 0
    failed: int = 0
    knowledge_count: int = 0
    refinement_run_id: str | None = None
    errors: List[dict] = []
    updated_at: str | None = None


class ExtractDocumentRequest(BaseModel):
    doc_id: str
    text: str | None = None
    title: str | None = None
    chunk_size: int = 800
    chunk_overlap: int = 120


class KnowledgePoint(BaseModel):
    text: str
    type: str
    explanation: str
    importance: Literal["high", "medium"] = "medium"


class ExtractResponse(BaseModel):
    chunk_id: str
    chunk_index: int | None = None
    knowledge_points: List[KnowledgePoint]


class ExtractBatchResponse(BaseModel):
    results: List[ExtractResponse]


class DocKPResponse(BaseModel):
    doc_id: str
    knowledge_points: List[KnowledgePoint]
    is_refined: bool = False
    refinement_status: str = "not_started"
    refinement_run_id: str | None = None


class ExplainDeepRequest(BaseModel):
    keyword: str
    kp_type: str
    context: str


class ClickRequest(BaseModel):
    kp_text: str
    kp_type: str


class MarkKnownRequest(BaseModel):
    kp_text: str
    kp_type: str


class UnmarkKnownRequest(BaseModel):
    kp_text: str


class KnowledgeStatus(BaseModel):
    kp_text: str
    status: str
    click_count: int


class StatusBatchRequest(BaseModel):
    kp_texts: List[str]
