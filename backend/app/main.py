from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, validate_settings
from app.core.database import init_db
from app.routers import agent, explain, extract, health, knowledge, rag


def create_app() -> FastAPI:
    validate_settings()
    init_db()

    app = FastAPI(title="AI 文档学习助手后端")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(agent.router)
    app.include_router(extract.router)
    app.include_router(explain.router)
    app.include_router(knowledge.router)
    app.include_router(rag.router)
    return app


app = create_app()
