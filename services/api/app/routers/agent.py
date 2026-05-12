import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.database import User
from app.agents.learning_agents import run_learning_agents, stream_learning_agents
from app.agents.tool_registry import list_tools
from app.schemas.knowledge import AgentChatRequest, AgentChatResponse
from app.services import db_log
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/tools")
def agent_tools():
    return {"tools": list_tools()}


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest, current_user: User = Depends(get_current_user)):
    user_id_token = db_log.current_user_id.set(current_user.user_id)
    start = time.monotonic()
    try:
        state = run_learning_agents(
            user_id=current_user.user_id,
            message=request.message.strip(),
            doc_id=request.doc_id,
            history=request.history,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        db_log.log_qa(
            user_id=current_user.user_id,
            doc_id=request.doc_id,
            question=request.message.strip(),
            answer=state["answer"],
            intent=state["intent"],
            agent=state["active_agent"],
            tools_used=state["tools_used"],
            latency_ms=latency_ms,
            sources=state["sources"],
        )
        return AgentChatResponse(
            reply=state["answer"],
            agent=state["active_agent"],
            intent=state["intent"],
            tools_used=state["tools_used"],
            stop_reason=state["stop_reason"],
            sources=state["sources"],
        )
    finally:
        db_log.current_user_id.reset(user_id_token)


@router.post("/chat-stream")
def agent_chat_stream(request: AgentChatRequest, current_user: User = Depends(get_current_user)):
    def generate():
        user_id_token = db_log.current_user_id.set(current_user.user_id)
        try:
            yield from stream_learning_agents(
                user_id=current_user.user_id,
                message=request.message.strip(),
                doc_id=request.doc_id,
                history=request.history,
            )
        finally:
            db_log.current_user_id.reset(user_id_token)

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
