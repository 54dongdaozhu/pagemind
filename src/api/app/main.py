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


def create_app() -> FastAPI:
    validate_settings()
    init_db()
    ensure_builtin_user()

    app = FastAPI(title="AI 文档学习助手后端")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    protected = [Depends(get_current_user)]
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(assets_router.router)
    app.include_router(agent_router.router, dependencies=protected)
    app.include_router(extraction_router.router, dependencies=protected)
    app.include_router(explain_router.router, dependencies=protected)
    app.include_router(knowledge_router.router, dependencies=protected)
    app.include_router(rag_router.router, dependencies=protected)
    return app


app = create_app()
