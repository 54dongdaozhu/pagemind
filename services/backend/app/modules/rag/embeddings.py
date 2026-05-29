import logging

import requests

from app.core.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_CIRCUIT_FAILURE_THRESHOLD,
    EMBEDDING_CIRCUIT_RECOVERY_SECONDS,
    EMBEDDING_MODEL,
)
from app.shared.cache import EMBEDDING_CACHE_TTL_SECONDS, get_json_many, set_json_many, stable_hash
from app.shared.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.shared.llm import REQUEST_PROXIES


logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 100
_embedding_breaker = CircuitBreaker(
    name="embedding",
    failure_threshold=EMBEDDING_CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=EMBEDDING_CIRCUIT_RECOVERY_SECONDS,
)


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

    try:
        _embedding_breaker.before_call()
    except CircuitOpenError as exc:
        logger.warning(
            "Embedding skipped: circuit is open retry_after=%.1fs missing=%d",
            exc.retry_after_seconds,
            len(missing_indexes),
        )
        return None

    missing_texts = [cleaned[idx] for idx in missing_indexes]

    url = f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"
    try:
        all_new_embeddings: list[list[float]] = []
        for batch_start in range(0, len(missing_texts), _EMBED_BATCH_SIZE):
            batch = missing_texts[batch_start:batch_start + _EMBED_BATCH_SIZE]
            logger.info(
                "Requesting embeddings: url=%s model=%s batch=%d-%d total=%d",
                url, EMBEDDING_MODEL,
                batch_start, batch_start + len(batch) - 1, len(missing_texts),
            )
            response = requests.post(
                url,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {EMBEDDING_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": batch},
                timeout=60,
                proxies=REQUEST_PROXIES,
            )
            if not response.ok:
                logger.error(
                    "Embedding request failed: status=%s body=%s",
                    response.status_code, response.text[:1000],
                )
            response.raise_for_status()
            items = sorted(response.json().get("data", []), key=lambda x: x.get("index", 0))
            all_new_embeddings.extend(item["embedding"] for item in items)

        embeddings_to_cache = {}
        for original_idx, embedding in zip(missing_indexes, all_new_embeddings):
            cached_embeddings[original_idx] = embedding
            embeddings_to_cache[keys[original_idx]] = embedding
        set_json_many(embeddings_to_cache, EMBEDDING_CACHE_TTL_SECONDS)
        logger.info(
            "Embedding succeeded: total=%d dimension=%s",
            len(missing_texts),
            len(all_new_embeddings[0]) if all_new_embeddings else 0,
        )
        _embedding_breaker.record_success()
        return cached_embeddings
    except Exception as exc:
        _embedding_breaker.record_failure()
        logger.exception("Embedding request exception: %s", exc)
        return None
