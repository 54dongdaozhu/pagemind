import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.database import User
from app.modules.agent.learning_agents import run_learning_agents, stream_learning_agents
from app.modules.agent.tool_registry import list_tools
from app.shared.schemas import AgentChatRequest, AgentChatResponse
from app.shared import db_log
from app.modules.auth.service import get_current_user

_AGENT_CHAT_TIMEOUT_SECONDS = 180

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/tools")
def agent_tools():
    return {"tools": list_tools()}


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest, current_user: User = Depends(get_current_user)):
    user_id_token = db_log.current_user_id.set(current_user.user_id)
    start = time.monotonic()
    try:
        # 拷贝当前 ContextVar（含 user_id），确保子线程中的 db_log 能正确关联
        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                ctx.run,
                run_learning_agents,
                user_id=current_user.user_id,
                message=request.message.strip(),
                doc_id=request.doc_id,
                history=request.history,
            )
            try:
                state = future.result(timeout=_AGENT_CHAT_TIMEOUT_SECONDS)
            except FuturesTimeout:
                raise HTTPException(
                    status_code=408,
                    detail="请求处理超时，请尝试更简短的问题或较小的文档。",
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
        except Exception as exc:
            logger.exception("Unhandled error in agent_chat_stream")
            yield f"对话服务暂时不可用：{str(exc)}"
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
