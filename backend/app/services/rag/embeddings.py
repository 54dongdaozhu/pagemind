import logging

import requests

from app.core.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
from app.services.llm_service import REQUEST_PROXIES


logger = logging.getLogger(__name__)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not EMBEDDING_API_KEY:
        logger.warning("Embedding skipped: EMBEDDING_API_KEY is not configured")
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
        logger.info(
            "Requesting embeddings: url=%s model=%s input_count=%s",
            url,
            EMBEDDING_MODEL,
            len(cleaned),
        )
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
            proxies=REQUEST_PROXIES,
        )
        if not response.ok:
            logger.error(
                "Embedding request failed: status=%s body=%s",
                response.status_code,
                response.text[:1000],
            )
        response.raise_for_status()
        data = response.json()
        items = data.get("data", [])
        ordered = sorted(items, key=lambda item: item.get("index", 0))
        embeddings = [item["embedding"] for item in ordered]
        logger.info(
            "Embedding request succeeded: input_count=%s embedding_count=%s dimension=%s",
            len(cleaned),
            len(embeddings),
            len(embeddings[0]) if embeddings else 0,
        )
        return embeddings
    except Exception as exc:
        logger.exception("Embedding request exception: %s", exc)
        return None
