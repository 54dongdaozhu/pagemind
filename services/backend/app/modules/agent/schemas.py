from typing import List, Literal

from pydantic import BaseModel, Field

from app.modules.rag.schemas import RagSource


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    message: str
    doc_id: str | None = None
    history: List[ChatMessage] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    reply: str
    agent: str
    intent: str
    tools_used: List[str] = []
    stop_reason: str
    sources: List[RagSource] = []
