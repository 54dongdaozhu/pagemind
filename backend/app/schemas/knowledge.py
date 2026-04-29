from typing import List

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class ExtractRequest(BaseModel):
    text: str
    chunk_id: str


class KnowledgePoint(BaseModel):
    text: str
    type: str
    explanation: str


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
