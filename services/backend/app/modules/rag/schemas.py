from typing import List, Literal

from pydantic import BaseModel, Field


class ImageMeta(BaseModel):
    asset_id: str
    page_num: int | None = None
    alt_text: str | None = None


class DocumentOutlineItem(BaseModel):
    text: str
    level: int = 1
    page_num: int | None = None


class RagIndexRequest(BaseModel):
    doc_id: str
    text: str
    title: str | None = None
    chunks: List[str] | None = None
    chunk_size: int = 800
    chunk_overlap: int = 120
    images: List[ImageMeta] | None = None
    render_html: str | None = None
    render_outline: List[DocumentOutlineItem] | None = None


class RagIndexResponse(BaseModel):
    doc_id: str
    indexed_count: int
    enrichment_status: str = "pending"


class DocumentListItem(BaseModel):
    doc_id: str
    title: str | None = None
    summary: str = ""
    chunk_count: int = 0
    updated_at: str | None = None
    render_available: bool = False


class DocumentListResponse(BaseModel):
    documents: List[DocumentListItem]


class DocumentRenderResponse(BaseModel):
    doc_id: str
    title: str | None = None
    html: str
    plain_text: str
    outline: List[DocumentOutlineItem] = Field(default_factory=list)
    updated_at: str | None = None


class RagEnrichmentStatusResponse(BaseModel):
    doc_id: str
    status: str
    chunk_count: int | None = None
    error: str | None = None
    updated_at: str | None = None


class DocTypeStatusResponse(BaseModel):
    doc_id: str
    status: str
    doc_type: str | None = None
    confidence: float | None = None
    error: str | None = None
    updated_at: str | None = None


class RagSource(BaseModel):
    chunk_index: int
    content: str
    score: float
    retrieval_method: Literal["embedding", "keyword"] = "keyword"


class RagQueryRequest(BaseModel):
    doc_id: str
    question: str
    top_k: int = 4


class RagQueryResponse(BaseModel):
    reply: str
    sources: List[RagSource]
