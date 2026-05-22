from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.database import User
from app.modules.auth.service import get_current_user
from app.modules.plan.service import stream_plan_agent
from app.modules.profile.service import get_profile
from app.shared import db_log


router = APIRouter(prefix="/api/plan", tags=["plan"])


class PlanChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("/chat")
def plan_chat(request: PlanChatRequest, current_user: User = Depends(get_current_user)):
    user_id = current_user.user_id
    profile = get_profile(user_id)

    def stream():
        user_id_token = db_log.current_user_id.set(user_id)
        try:
            yield from stream_plan_agent(
                user_id=user_id,
                message=request.message,
                history=request.history,
                profile=profile,
            )
        finally:
            db_log.current_user_id.reset(user_id_token)

    return StreamingResponse(
        stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
