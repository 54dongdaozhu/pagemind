from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.knowledge import ExplainDeepRequest
from app.services.explain_service import stream_deep_explanation


router = APIRouter(prefix="/api", tags=["explain"])


@router.post("/explain-deep")
async def explain_deep(request: ExplainDeepRequest):
    async def generate():
        for chunk in stream_deep_explanation(
            keyword=request.keyword.strip(),
            kp_type=request.kp_type,
            context=request.context.strip(),
        ):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
