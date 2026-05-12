from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.knowledge import ExplainDeepRequest
from app.services.explain_service import stream_deep_explanation


router = APIRouter(prefix="/api", tags=["explain"])
STREAM_DONE_MARKER = "\n[STREAM_DONE]\n"


@router.post("/explain-deep")
async def explain_deep(request: ExplainDeepRequest):
    async def generate():
        for chunk in stream_deep_explanation(
            keyword=request.keyword.strip(),
            kp_type=request.kp_type,
            context=request.context.strip(),
        ):
            yield chunk
        yield STREAM_DONE_MARKER

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
