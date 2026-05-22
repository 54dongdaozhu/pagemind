import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_INPUT_PRICE_PER_M = float(os.getenv("DEEPSEEK_INPUT_PRICE_PER_M", "0.14"))
DEEPSEEK_OUTPUT_PRICE_PER_M = float(os.getenv("DEEPSEEK_OUTPUT_PRICE_PER_M", "0.28"))
FALLBACK_LLM_API_KEY = os.getenv("FALLBACK_LLM_API_KEY", "")
FALLBACK_LLM_BASE_URL = os.getenv("FALLBACK_LLM_BASE_URL", "")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "")
VISION_LLM_API_KEY = os.getenv("VISION_LLM_API_KEY", "")
VISION_LLM_BASE_URL = os.getenv("VISION_LLM_BASE_URL", "")
VISION_LLM_MODEL = os.getenv("VISION_LLM_MODEL", "")
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
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost")
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
BUILTIN_USERNAME = os.getenv("BUILTIN_USERNAME", "meng")
BUILTIN_PASSWORD = os.getenv("BUILTIN_PASSWORD", "")
BUILTIN_EMAIL = os.getenv("BUILTIN_EMAIL", "meng@local")

_WEAK_SECRET_KEYS = {"dev-auth-secret-change-me", "change-me", "secret", ""}


def validate_settings():
    if not DEEPSEEK_API_KEY:
        raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")
    if AUTH_SECRET_KEY in _WEAK_SECRET_KEYS or len(AUTH_SECRET_KEY) < 32:
        raise ValueError(
            "AUTH_SECRET_KEY 不安全，请设置长度 ≥ 32 的随机字符串（可用 openssl rand -hex 32 生成）"
        )
    if not BUILTIN_PASSWORD or len(BUILTIN_PASSWORD) < 8:
        raise ValueError("请在 .env 中设置 BUILTIN_PASSWORD（长度 ≥ 8 位）")
