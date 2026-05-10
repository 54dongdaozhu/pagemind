import time

from fastapi import APIRouter, Depends

from app.core.database import User
from app.schemas.knowledge import RagIndexRequest, RagQueryRequest, RagQueryResponse
from app.services import db_log
from app.services.auth_service import get_current_user
from app.services.rag_service import answer_with_rag, index_document_text


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/index")
def index_rag_document(request: RagIndexRequest, current_user: User = Depends(get_current_user)):
    user_id_token = db_log.current_user_id.set(current_user.user_id)
    try:
        indexed_count = index_document_text(
            user_id=current_user.user_id,
            doc_id=request.doc_id,
            text=request.text,
            title=request.title,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
        db_log.log_event(
            entity_type="document",
            entity_id=request.doc_id,
            event_type="document.indexed",
            user_id=current_user.user_id,
            after_state={"chunk_count": indexed_count, "title": request.title},
        )
        return {"doc_id": request.doc_id, "indexed_count": indexed_count}
    finally:
        db_log.current_user_id.reset(user_id_token)


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
