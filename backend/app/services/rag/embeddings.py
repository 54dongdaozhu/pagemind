import requests

from app.core.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
from app.services.llm_service import REQUEST_PROXIES


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not EMBEDDING_API_KEY:
        return None

    cleaned = [text.strip() for text in texts if isinstance(text, str) and text.strip()]
    if not cleaned:
        return []

    url = f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": cleaned,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
            proxies=REQUEST_PROXIES,
        )
        response.raise_for_status()
        data = response.json()
        ordered = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]
    except Exception:
        return None
