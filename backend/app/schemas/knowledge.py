from typing import List, Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class AgentChatRequest(BaseModel):
    message: str
    doc_id: str | None = None


class RagIndexRequest(BaseModel):
    doc_id: str
    text: str
    title: str | None = None
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


class KnowledgePoint(BaseModel):
    text: str
    type: str
    explanation: str
    importance: Literal["high", "medium"] = "medium"


class ExtractResponse(BaseModel):
    chunk_id: str
    knowledge_points: List[KnowledgePoint]


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
