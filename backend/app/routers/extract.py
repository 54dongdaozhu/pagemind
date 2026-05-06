from fastapi import APIRouter

from app.schemas.knowledge import ExtractBatchRequest, ExtractBatchResponse, ExtractRequest, ExtractResponse
from app.services.extract_service import extract_knowledge_batch, extract_knowledge_from_text


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(request: ExtractRequest):
    return extract_knowledge_from_text(request.chunk_id, request.text)


@router.post("/extract-knowledge-batch", response_model=ExtractBatchResponse)
def extract_knowledge_batch_route(request: ExtractBatchRequest):
    return extract_knowledge_batch(request.chunks)
