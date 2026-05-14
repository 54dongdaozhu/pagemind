import time

from fastapi import APIRouter, Depends

from app.core.database import User
from app.shared.schemas import (
    RagEnrichmentStatusResponse,
    RagIndexRequest,
    RagIndexResponse,
    RagQueryRequest,
    RagQueryResponse,
)
from app.shared import db_log
from app.modules.auth.service import get_current_user
from app.modules.rag import answer_with_rag, index_document_text
from app.modules.rag.service import get_rag_enrichment_status


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/index", response_model=RagIndexResponse)
def index_rag_document(request: RagIndexRequest, current_user: User = Depends(get_current_user)):
    user_id_token = db_log.current_user_id.set(current_user.user_id)
    try:
        result = index_document_text(
            user_id=current_user.user_id,
            doc_id=request.doc_id,
            text=request.text,
            title=request.title,
            chunks=request.chunks,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
        db_log.log_event(
            entity_type="document",
            entity_id=request.doc_id,
            event_type="document.indexed",
            user_id=current_user.user_id,
            after_state={"chunk_count": result["indexed_count"], "title": request.title},
        )
        return RagIndexResponse(
            doc_id=request.doc_id,
            indexed_count=result["indexed_count"],
            enrichment_status=result["enrichment_status"],
        )
    finally:
        db_log.current_user_id.reset(user_id_token)


@router.get("/index/status", response_model=RagEnrichmentStatusResponse)
def rag_index_status(doc_id: str, current_user: User = Depends(get_current_user)):
    data = get_rag_enrichment_status(current_user.user_id, doc_id)
    return RagEnrichmentStatusResponse(**data)


@router.post("/query", response_model=RagQueryResponse)
def query_rag_document(request: RagQueryRequest, current_user: User = Depends(get_current_user)):
    user_id_token = db_log.current_user_id.set(current_user.user_id)
    start = time.monotonic()
    try:
        reply, sources = answer_with_rag(
            user_id=current_user.user_id,
            doc_id=request.doc_id,
            question=request.question.strip(),
            top_k=request.top_k,
        )
        db_log.log_qa(
            user_id=current_user.user_id,
            doc_id=request.doc_id,
            question=request.question.strip(),
            answer=reply,
            intent="qa",
            agent="RagAgent",
            latency_ms=int((time.monotonic() - start) * 1000),
            sources=sources,
        )
        return RagQueryResponse(reply=reply, sources=sources)
    finally:
        db_log.current_user_id.reset(user_id_token)
