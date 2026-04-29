from fastapi import APIRouter

from app.schemas.knowledge import ChatRequest, ChatResponse
from app.services.llm_service import call_deepseek


router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"status": "ok", "message": "AI 学习助手后端运行中"}


@router.post("/api/test-llm", response_model=ChatResponse)
def test_llm(request: ChatRequest):
    messages = [{"role": "user", "content": request.message}]
    reply = call_deepseek(messages)
    return ChatResponse(reply=reply)
