from typing import List, Literal

from pydantic import BaseModel


class KnowledgePoint(BaseModel):
    text: str
    type: str
    explanation: str
    importance: Literal["high", "medium"] = "medium"
    chunk_index: int | None = None
    chunk_count: int | None = None
    has_explanation: bool | None = None


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
