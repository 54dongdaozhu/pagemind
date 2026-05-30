from typing import List

from pydantic import BaseModel


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
