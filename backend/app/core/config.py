import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EXTRACT_MAX_CONCURRENCY = max(1, int(os.getenv("EXTRACT_MAX_CONCURRENCY", "3")))
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


def validate_settings():
    if not DEEPSEEK_API_KEY:
        raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")
