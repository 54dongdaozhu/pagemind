from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, validate_settings
from app.core.database import init_db
from app.routers import agent, auth, explain, extract, health, knowledge, rag
from app.services.auth_service import ensure_builtin_user, get_current_user


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
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(agent.router, dependencies=protected)
    app.include_router(extract.router, dependencies=protected)
    app.include_router(explain.router, dependencies=protected)
    app.include_router(knowledge.router, dependencies=protected)
    app.include_router(rag.router, dependencies=protected)
    return app


app = create_app()
