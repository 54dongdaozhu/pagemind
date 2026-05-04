from fastapi import APIRouter

from app.schemas.knowledge import RagIndexRequest, RagQueryRequest, RagQueryResponse
from app.services.rag_service import answer_with_rag, index_document_text


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/index")
def index_rag_document(request: RagIndexRequest):
    indexed_count = index_document_text(
        doc_id=request.doc_id,
        text=request.text,
        title=request.title,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    return {"doc_id": request.doc_id, "indexed_count": indexed_count}


@router.post("/query", response_model=RagQueryResponse)
def query_rag_document(request: RagQueryRequest):
    reply, sources = answer_with_rag(
        doc_id=request.doc_id,
        question=request.question.strip(),
        top_k=request.top_k,
    )
    return RagQueryResponse(reply=reply, sources=sources)
