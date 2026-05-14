from fastapi import APIRouter

from app.shared.schemas import ChatRequest, ChatResponse
from app.shared.llm import call_deepseek


router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"status": "ok", "message": "AI 文档学习助手后端运行中"}


@router.get("/api/health")
def health_check():
    return {"status": "ok"}


@router.post("/api/test-llm", response_model=ChatResponse)
def test_llm(request: ChatRequest):
    messages = [{"role": "user", "content": request.message}]
    reply = call_deepseek(messages)
    return ChatResponse(reply=reply)
