from fastapi import APIRouter, Depends

from app.core.database import User
from app.modules.knowledge.schemas import ClickRequest, MarkKnownRequest, StatusBatchRequest, UnmarkKnownRequest
from app.modules.auth.service import get_current_user
from app.modules.knowledge import service as knowledge_service


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/click")
def record_click(request: ClickRequest, current_user: User = Depends(get_current_user)):
    return knowledge_service.record_click(current_user.user_id, request.kp_text, request.kp_type)


@router.post("/mark-known")
def mark_known(request: MarkKnownRequest, current_user: User = Depends(get_current_user)):
    return knowledge_service.mark_known(current_user.user_id, request.kp_text, request.kp_type)


@router.post("/unmark-known")
def unmark_known(request: UnmarkKnownRequest, current_user: User = Depends(get_current_user)):
    return knowledge_service.unmark_known(current_user.user_id, request.kp_text)


@router.post("/status-batch")
def get_status_batch(request: StatusBatchRequest, current_user: User = Depends(get_current_user)):
    return knowledge_service.get_status_batch(current_user.user_id, request.kp_texts)


@router.get("/stats")
def get_stats(current_user: User = Depends(get_current_user)):
    return knowledge_service.get_stats(current_user.user_id)


@router.post("/reset")
def reset_all(current_user: User = Depends(get_current_user)):
    return knowledge_service.reset_all(current_user.user_id)
