import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

from redis import Redis

from app.core.config import REDIS_URL


logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300
PROMPT_CACHE_TTL_SECONDS = 60 * 60
EMBEDDING_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
RAG_QUERY_CACHE_TTL_SECONDS = 60 * 10
USER_CACHE_TTL_SECONDS = 60 * 5
CONTENT_CACHE_TTL_SECONDS = 60 * 30
ANALYSIS_REPORT_CACHE_TTL_SECONDS = 60 * 60 * 24
EMAIL_TOKEN_TTL_SECONDS = 60 * 60 * 24
RESET_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def redis_available() -> bool:
    try:
        get_redis().ping()
        return True
    except Exception:
        return False


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_json(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Redis JSON cache read failed for %s: %s", key, exc)
        return None


def get_json_many(keys: list[str]) -> list[Any | None]:
    if not keys:
        return []
    try:
        values = get_redis().mget(keys)
        return [json.loads(raw) if raw is not None else None for raw in values]
    except Exception as exc:
        logger.debug("Redis JSON cache batch read failed for %s keys: %s", len(keys), exc)
        return [None] * len(keys)


def set_json(key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    try:
        get_redis().setex(
            key,
            ttl_seconds,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )
        return True
    except Exception as exc:
        logger.debug("Redis JSON cache write failed for %s: %s", key, exc)
        return False


def set_json_many(items: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    if not items:
        return True
    try:
        pipe = get_redis().pipeline(transaction=False)
        for key, value in items.items():
            pipe.setex(
                key,
                ttl_seconds,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            )
        pipe.execute()
        return True
    except Exception as exc:
        logger.debug("Redis JSON cache batch write failed for %s keys: %s", len(items), exc)
        return False


def get_text(key: str) -> str | None:
    try:
        return get_redis().get(key)
    except Exception as exc:
        logger.debug("Redis text cache read failed for %s: %s", key, exc)
        return None


def set_text(key: str, value: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    try:
        get_redis().setex(key, ttl_seconds, value)
        return True
    except Exception as exc:
        logger.debug("Redis text cache write failed for %s: %s", key, exc)
        return False


def delete_key(key: str) -> None:
    try:
        get_redis().delete(key)
    except Exception as exc:
        logger.debug("Redis cache delete failed for %s: %s", key, exc)


def delete_pattern(pattern: str) -> None:
    try:
        redis = get_redis()
        for key in redis.scan_iter(match=pattern, count=200):
            redis.delete(key)
    except Exception as exc:
        logger.debug("Redis cache invalidation failed for %s: %s", pattern, exc)
