from fastapi import APIRouter

from app.schemas.knowledge import ClickRequest, MarkKnownRequest, StatusBatchRequest, UnmarkKnownRequest
from app.services import knowledge_service


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/click")
def record_click(request: ClickRequest):
    return knowledge_service.record_click(request.kp_text, request.kp_type)


@router.post("/mark-known")
def mark_known(request: MarkKnownRequest):
    return knowledge_service.mark_known(request.kp_text, request.kp_type)


@router.post("/unmark-known")
def unmark_known(request: UnmarkKnownRequest):
    return knowledge_service.unmark_known(request.kp_text)


@router.post("/status-batch")
def get_status_batch(request: StatusBatchRequest):
    return knowledge_service.get_status_batch(request.kp_texts)


@router.get("/stats")
def get_stats():
    return knowledge_service.get_stats()


@router.post("/reset")
def reset_all():
    return knowledge_service.reset_all()
