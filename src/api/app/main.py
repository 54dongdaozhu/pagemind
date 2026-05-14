import json
import threading

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, validate_settings
from app.core.database import init_db
from app.modules.auth.service import ensure_builtin_user, get_current_user
from app.modules.agent import router as agent_router
from app.modules.assets import router as assets_router
from app.modules.auth import router as auth_router
from app.modules.explain import router as explain_router
from app.modules.extraction import router as extraction_router
from app.modules.health import router as health_router
from app.modules.knowledge import router as knowledge_router
from app.modules.rag import router as rag_router


class _ConcurrencyLimitMiddleware:
    _PROTECTED = frozenset({"/api/agent/chat", "/api/agent/chat-stream", "/api/rag/index"})

    def __init__(self, app, limit: int = 5):
        self._app = app
        self._sem = threading.Semaphore(limit)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in self._PROTECTED:
            await self._app(scope, receive, send)
            return
        if not self._sem.acquire(blocking=False):
            body = json.dumps({"detail": "服务器繁忙，请稍后重试。"}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        try:
            await self._app(scope, receive, send)
        finally:
            self._sem.release()


def create_app():
    validate_settings()
    init_db()
    ensure_builtin_user()

    _fast_api = FastAPI(title="AI 文档学习助手后端")
    _fast_api.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    protected = [Depends(get_current_user)]
    _fast_api.include_router(health_router.router)
    _fast_api.include_router(auth_router.router)
    _fast_api.include_router(assets_router.router)
    _fast_api.include_router(agent_router.router, dependencies=protected)
    _fast_api.include_router(extraction_router.router, dependencies=protected)
    _fast_api.include_router(explain_router.router, dependencies=protected)
    _fast_api.include_router(knowledge_router.router, dependencies=protected)
    _fast_api.include_router(rag_router.router, dependencies=protected)
    return _ConcurrencyLimitMiddleware(_fast_api, limit=5)


app = create_app()
