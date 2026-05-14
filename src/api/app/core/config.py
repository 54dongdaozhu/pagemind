import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
FALLBACK_LLM_API_KEY = os.getenv("FALLBACK_LLM_API_KEY", "")
FALLBACK_LLM_BASE_URL = os.getenv("FALLBACK_LLM_BASE_URL", "")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EXTRACT_MAX_CONCURRENCY = max(1, int(os.getenv("EXTRACT_MAX_CONCURRENCY", "3")))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RQ_QUEUE_NAME = os.getenv("RQ_QUEUE_NAME", "pagemind")
RQ_JOB_TIMEOUT_SECONDS = int(os.getenv("RQ_JOB_TIMEOUT_SECONDS", "300"))
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BACKEND_DIR / 'user_data.db'}",
)
CHROMA_PATH = DATA_DIR / "chroma_store"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-auth-secret-change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
BUILTIN_USERNAME = os.getenv("BUILTIN_USERNAME", "meng")
BUILTIN_PASSWORD = os.getenv("BUILTIN_PASSWORD", "200311")
BUILTIN_EMAIL = os.getenv("BUILTIN_EMAIL", "meng@local")


def validate_settings():
    if not DEEPSEEK_API_KEY:
        raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")
