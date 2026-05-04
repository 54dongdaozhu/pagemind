from fastapi import APIRouter

from app.agents.learning_agents import run_learning_agents
from app.schemas.knowledge import AgentChatRequest, AgentChatResponse


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest):
    state = run_learning_agents(
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
