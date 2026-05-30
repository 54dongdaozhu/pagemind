from fastapi import APIRouter, Depends

from app.core.database import User
from app.modules.extraction.schemas import (
    DocKPResponse,
    ExtractBatchRequest,
    ExtractBatchResponse,
    ExtractDocumentRequest,
    ExtractFinalizeRequest,
    ExtractRequest,
    ExtractResponse,
    ExtractStartRequest,
    ExtractStartResponse,
    ExtractStatusResponse,
    KnowledgePoint,
)
from app.modules.auth.service import get_current_user
from app.modules.extraction.repository import get_persisted_doc_kps, get_refined_doc_kps
from app.modules.extraction.refinement import get_extraction_status, get_refinement_status, start_knowledge_extraction_run
from app.modules.extraction.service import (
    extract_knowledge_batch,
    extract_knowledge_for_document,
    extract_knowledge_from_text,
    finalize_knowledge_extraction,
)


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge/start", response_model=ExtractStartResponse)
def start_extract_knowledge(
    request: ExtractStartRequest,
    current_user: User = Depends(get_current_user),
):
    return start_knowledge_extraction_run(
        current_user.user_id,
        request.doc_id,
        request.chunks,
        title=request.title,
        source=request.source,
    )


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
        run_id=request.run_id,
    )


@router.post("/extract-knowledge-batch", response_model=ExtractBatchResponse)
def extract_knowledge_batch_route(
    request: ExtractBatchRequest,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_batch(current_user.user_id, request.chunks, run_id=request.run_id)


@router.post("/extract-knowledge/finalize", response_model=ExtractStatusResponse)
def finalize_extract_knowledge(
    request: ExtractFinalizeRequest,
    current_user: User = Depends(get_current_user),
):
    return finalize_knowledge_extraction(
        current_user.user_id,
        request.run_id,
        request.doc_id,
        request.chunks,
    )


@router.get("/extract-knowledge/status", response_model=ExtractStatusResponse)
def get_extract_knowledge_status(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    return get_extraction_status(run_id)


@router.post("/extract-knowledge-document", response_model=ExtractBatchResponse)
def extract_knowledge_document_route(
    request: ExtractDocumentRequest,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_for_document(
        current_user.user_id,
        request.doc_id,
        text=request.text,
        title=request.title,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )


@router.get("/doc-kps", response_model=DocKPResponse)
def get_doc_knowledge_points(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取文档知识点。
    优先返回 Phase 2 Redis 精炼结果；缓存未命中时回退到数据库关联和提取缓存。
    """
    refined = get_refined_doc_kps(current_user.user_id, doc_id)
    refinement = get_refinement_status(current_user.user_id, doc_id) or {}
    if refined is not None:
        kps = [KnowledgePoint(**kp) for kp in refined if isinstance(kp, dict)]
        return DocKPResponse(
            doc_id=doc_id,
            knowledge_points=kps,
            is_refined=True,
            refinement_status=refinement.get("status", "completed"),
            refinement_run_id=refinement.get("run_id"),
        )
    persisted = get_persisted_doc_kps(current_user.user_id, doc_id)
    if persisted:
        kps = [KnowledgePoint(**kp) for kp in persisted if isinstance(kp, dict)]
        return DocKPResponse(
            doc_id=doc_id,
            knowledge_points=kps,
            is_refined=False,
            refinement_status=refinement.get("status", "degraded"),
            refinement_run_id=refinement.get("run_id"),
        )
    return DocKPResponse(
        doc_id=doc_id,
        knowledge_points=[],
        is_refined=False,
        refinement_status=refinement.get("status", "not_started"),
        refinement_run_id=refinement.get("run_id"),
    )
