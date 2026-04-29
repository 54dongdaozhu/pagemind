from fastapi import APIRouter

from app.schemas.knowledge import ExtractRequest, ExtractResponse
from app.services.extract_service import extract_knowledge_from_text


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(request: ExtractRequest):
    return extract_knowledge_from_text(request.chunk_id, request.text)
