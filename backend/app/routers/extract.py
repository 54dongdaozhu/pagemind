from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.database import User
from app.schemas.knowledge import ExtractBatchRequest, ExtractBatchResponse, ExtractRequest, ExtractResponse
from app.services.auth_service import get_current_user
from app.services.extract_service import extract_knowledge_batch, extract_knowledge_from_text


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(
    request: ExtractRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_from_text(
        current_user.user_id,
        request.chunk_id,
        request.text,
        doc_id=request.doc_id,
        chunk_index=request.chunk_index,
        background_tasks=background_tasks,
    )


@router.post("/extract-knowledge-batch", response_model=ExtractBatchResponse)
def extract_knowledge_batch_route(
    request: ExtractBatchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return extract_knowledge_batch(current_user.user_id, request.chunks, background_tasks=background_tasks)
