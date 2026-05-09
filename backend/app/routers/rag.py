from fastapi import APIRouter, Depends

from app.core.database import User
from app.schemas.knowledge import RagIndexRequest, RagQueryRequest, RagQueryResponse
from app.services.auth_service import get_current_user
from app.services.rag_service import answer_with_rag, index_document_text


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/index")
def index_rag_document(request: RagIndexRequest, current_user: User = Depends(get_current_user)):
    indexed_count = index_document_text(
        user_id=current_user.user_id,
        doc_id=request.doc_id,
        text=request.text,
        title=request.title,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    return {"doc_id": request.doc_id, "indexed_count": indexed_count}


@router.post("/query", response_model=RagQueryResponse)
def query_rag_document(request: RagQueryRequest, current_user: User = Depends(get_current_user)):
    reply, sources = answer_with_rag(
        user_id=current_user.user_id,
        doc_id=request.doc_id,
        question=request.question.strip(),
        top_k=request.top_k,
    )
    return RagQueryResponse(reply=reply, sources=sources)
