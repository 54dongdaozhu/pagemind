from fastapi import APIRouter, Depends

from app.core.database import User
from app.agents.learning_agents import run_learning_agents
from app.agents.tool_registry import list_tools
from app.schemas.knowledge import AgentChatRequest, AgentChatResponse
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/tools")
def agent_tools():
    return {"tools": list_tools()}


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest, current_user: User = Depends(get_current_user)):
    state = run_learning_agents(
        user_id=current_user.user_id,
        message=request.message.strip(),
        doc_id=request.doc_id,
    )
    return AgentChatResponse(
        reply=state["answer"],
        agent=state["active_agent"],
        intent=state["intent"],
        tools_used=state["tools_used"],
        stop_reason=state["stop_reason"],
        sources=state["sources"],
    )
