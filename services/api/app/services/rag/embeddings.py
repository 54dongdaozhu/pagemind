import logging

import requests

from app.core.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
from app.services.cache_service import EMBEDDING_CACHE_TTL_SECONDS, get_json_many, set_json_many, stable_hash
from app.services.llm_service import REQUEST_PROXIES


logger = logging.getLogger(__name__)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not EMBEDDING_API_KEY:
        logger.warning("Embedding skipped: EMBEDDING_API_KEY is not configured")
        return None

    cleaned = [text.strip() for text in texts if isinstance(text, str) and text.strip()]
    if not cleaned:
        return []

    keys = [
        f"cache:embedding:{EMBEDDING_MODEL}:{stable_hash(text)}"
        for text in cleaned
    ]
    cached_embeddings = get_json_many(keys)
    missing_indexes = [idx for idx, value in enumerate(cached_embeddings) if value is None]
    if not missing_indexes:
        if any(value is None for value in cached_embeddings):
            return None
        return cached_embeddings

    missing_texts = [cleaned[idx] for idx in missing_indexes]

    url = f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": missing_texts,
    }

    try:
        logger.info(
            "Requesting embeddings: url=%s model=%s input_count=%s",
            url,
            EMBEDDING_MODEL,
            len(missing_texts),
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
        embeddings_to_cache = {}
        for original_idx, embedding in zip(missing_indexes, embeddings):
            cached_embeddings[original_idx] = embedding
            embeddings_to_cache[keys[original_idx]] = embedding
        set_json_many(embeddings_to_cache, EMBEDDING_CACHE_TTL_SECONDS)
        logger.info(
            "Embedding request succeeded: input_count=%s embedding_count=%s dimension=%s",
            len(missing_texts),
            len(cached_embeddings),
            len(cached_embeddings[0]) if cached_embeddings else 0,
        )
        return cached_embeddings
    except Exception as exc:
        logger.exception("Embedding request exception: %s", exc)
        return None
