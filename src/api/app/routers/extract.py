from fastapi import APIRouter, Depends

from app.core.database import User
from app.schemas.knowledge import (
    DocKPResponse,
    ExtractBatchRequest,
    ExtractBatchResponse,
    ExtractRequest,
    ExtractResponse,
    KnowledgePoint,
)
from app.services.auth_service import get_current_user
from app.services.extract_service import (
    extract_knowledge_batch,
    extract_knowledge_from_text,
    get_refined_doc_kps,
)


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(
    request: ExtractRequest,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_from_text(
        current_user.user_id,
        request.chunk_id,
        request.text,
        doc_id=request.doc_id,
        chunk_index=request.chunk_index,
    )


@router.post("/extract-knowledge-batch", response_model=ExtractBatchResponse)
def extract_knowledge_batch_route(
    request: ExtractBatchRequest,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_batch(current_user.user_id, request.chunks)


@router.get("/doc-kps", response_model=DocKPResponse)
def get_doc_knowledge_points(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取文档级精炼知识点（Phase 2 完成后可用）。
    Phase 2 仍在运行时返回 is_refined=False 和空列表，前端可轮询。
    """
    refined = get_refined_doc_kps(current_user.user_id, doc_id)
    if refined is not None:
        kps = [KnowledgePoint(**kp) for kp in refined if isinstance(kp, dict)]
        return DocKPResponse(doc_id=doc_id, knowledge_points=kps, is_refined=True)
    return DocKPResponse(doc_id=doc_id, knowledge_points=[], is_refined=False)
