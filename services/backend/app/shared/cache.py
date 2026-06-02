import hashlib
import json
import logging
import random
import time
import uuid
from functools import lru_cache
from typing import Any, Callable

from redis import Redis

from app.core.config import REDIS_URL


logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300
DEFAULT_NULL_TTL_SECONDS = 60
DEFAULT_LOCK_TTL_SECONDS = 10
DEFAULT_CACHE_WAIT_TIMEOUT_SECONDS = 0.2
DEFAULT_CACHE_RETRY_INTERVAL_SECONDS = 0.03
DEFAULT_TTL_JITTER_RATIO = 0.1
NULL_JSON_CACHE_VALUE = {"__cache_null__": True}
NULL_TEXT_CACHE_VALUE = "__cache_null__"

PROMPT_CACHE_TTL_SECONDS = 60 * 60
EMBEDDING_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
RAG_QUERY_CACHE_TTL_SECONDS = 60 * 10
USER_CACHE_TTL_SECONDS = 60 * 5
CONTENT_CACHE_TTL_SECONDS = 60 * 30
ANALYSIS_REPORT_CACHE_TTL_SECONDS = 60 * 60 * 24
EMAIL_TOKEN_TTL_SECONDS = 60 * 60 * 24
RESET_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
IMAGE_VISION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
USER_PROFILE_TTL_SECONDS = 60 * 60 * 24 * 7
AGENT_MEMORY_TTL_SECONDS = 60 * 60 * 4
SKILL_TREE_TTL_SECONDS = 60 * 60 * 24 * 7


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


def jitter_ttl(ttl_seconds: int, jitter_ratio: float = DEFAULT_TTL_JITTER_RATIO) -> int:
    if ttl_seconds <= 1 or jitter_ratio <= 0:
        return ttl_seconds
    spread = max(1, int(ttl_seconds * jitter_ratio))
    return max(1, ttl_seconds + random.randint(-spread, spread))


def _effective_ttl(ttl_seconds: int, jitter: bool) -> int:
    return jitter_ttl(ttl_seconds) if jitter else ttl_seconds


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def is_null_cache_value(value: Any) -> bool:
    return value == NULL_JSON_CACHE_VALUE or value == NULL_TEXT_CACHE_VALUE


def _decode_json_cache(raw: str) -> tuple[bool, Any | None]:
    value = json.loads(raw)
    if is_null_cache_value(value):
        return True, None
    return True, value


def _get_json_cached_value(key: str) -> tuple[bool, Any | None]:
    try:
        raw = get_redis().get(key)
        if raw is None:
            return False, None
        return _decode_json_cache(raw)
    except Exception as exc:
        logger.debug("Redis JSON cache read failed for %s: %s", key, exc)
        return False, None


def _get_text_cached_value(key: str) -> tuple[bool, str | None]:
    try:
        raw = get_redis().get(key)
        if raw is None:
            return False, None
        if is_null_cache_value(raw):
            return True, None
        return True, raw
    except Exception as exc:
        logger.debug("Redis text cache read failed for %s: %s", key, exc)
        return False, None


def get_json(key: str) -> Any | None:
    hit, value = _get_json_cached_value(key)
    return value if hit else None


def get_json_many(keys: list[str]) -> list[Any | None]:
    if not keys:
        return []
    try:
        values = get_redis().mget(keys)
        result: list[Any | None] = []
        for raw in values:
            if raw is None:
                result.append(None)
                continue
            _, value = _decode_json_cache(raw)
            result.append(value)
        return result
    except Exception as exc:
        logger.debug("Redis JSON cache batch read failed for %s keys: %s", len(keys), exc)
        return [None] * len(keys)


def set_json(key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS, *, jitter: bool = True) -> bool:
    try:
        get_redis().setex(
            key,
            _effective_ttl(ttl_seconds, jitter),
            _json_dumps(value),
        )
        return True
    except Exception as exc:
        logger.debug("Redis JSON cache write failed for %s: %s", key, exc)
        return False


def set_json_many(items: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS, *, jitter: bool = True) -> bool:
    if not items:
        return True
    try:
        pipe = get_redis().pipeline(transaction=False)
        for key, value in items.items():
            pipe.setex(
                key,
                _effective_ttl(ttl_seconds, jitter),
                _json_dumps(value),
            )
        pipe.execute()
        return True
    except Exception as exc:
        logger.debug("Redis JSON cache batch write failed for %s keys: %s", len(items), exc)
        return False


def get_text(key: str) -> str | None:
    hit, value = _get_text_cached_value(key)
    return value if hit else None


def set_text(key: str, value: str, ttl_seconds: int = DEFAULT_TTL_SECONDS, *, jitter: bool = True) -> bool:
    try:
        get_redis().setex(key, _effective_ttl(ttl_seconds, jitter), value)
        return True
    except Exception as exc:
        logger.debug("Redis text cache write failed for %s: %s", key, exc)
        return False


def set_json_null(key: str, ttl_seconds: int = DEFAULT_NULL_TTL_SECONDS, *, jitter: bool = True) -> bool:
    return set_json(key, NULL_JSON_CACHE_VALUE, ttl_seconds, jitter=jitter)


def set_text_null(key: str, ttl_seconds: int = DEFAULT_NULL_TTL_SECONDS, *, jitter: bool = True) -> bool:
    return set_text(key, NULL_TEXT_CACHE_VALUE, ttl_seconds, jitter=jitter)


def try_acquire_lock(lock_key: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> str | None:
    token = uuid.uuid4().hex
    try:
        acquired = get_redis().set(lock_key, token, nx=True, ex=ttl_seconds)
        return token if acquired else None
    except Exception as exc:
        logger.debug("Redis cache lock acquire failed for %s: %s", lock_key, exc)
        return None


def release_lock(lock_key: str, token: str) -> bool:
    script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """
    try:
        return bool(get_redis().eval(script, 1, lock_key, token))
    except Exception as exc:
        logger.debug("Redis cache lock release failed for %s: %s", lock_key, exc)
        return False


def get_or_set_json(
    key: str,
    loader: Callable[[], Any],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    *,
    null_ttl_seconds: int = DEFAULT_NULL_TTL_SECONDS,
    lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    wait_timeout_seconds: float = DEFAULT_CACHE_WAIT_TIMEOUT_SECONDS,
    retry_interval_seconds: float = DEFAULT_CACHE_RETRY_INTERVAL_SECONDS,
    cache_null: bool = True,
    jitter: bool = True,
    lock_key: str | None = None,
) -> Any | None:
    hit, value = _get_json_cached_value(key)
    if hit:
        return value

    lock_name = lock_key or f"lock:{key}"
    token = try_acquire_lock(lock_name, lock_ttl_seconds)
    if token:
        try:
            hit, value = _get_json_cached_value(key)
            if hit:
                return value
            value = loader()
            if value is None and cache_null:
                set_json_null(key, null_ttl_seconds, jitter=jitter)
            elif value is not None:
                set_json(key, value, ttl_seconds, jitter=jitter)
            return value
        finally:
            release_lock(lock_name, token)

    deadline = time.monotonic() + wait_timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(retry_interval_seconds)
        hit, value = _get_json_cached_value(key)
        if hit:
            return value

    value = loader()
    if value is None and cache_null:
        set_json_null(key, null_ttl_seconds, jitter=jitter)
    elif value is not None:
        set_json(key, value, ttl_seconds, jitter=jitter)
    return value


def get_or_set_text(
    key: str,
    loader: Callable[[], str | None],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    *,
    null_ttl_seconds: int = DEFAULT_NULL_TTL_SECONDS,
    lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    wait_timeout_seconds: float = DEFAULT_CACHE_WAIT_TIMEOUT_SECONDS,
    retry_interval_seconds: float = DEFAULT_CACHE_RETRY_INTERVAL_SECONDS,
    cache_null: bool = True,
    jitter: bool = True,
    lock_key: str | None = None,
) -> str | None:
    hit, value = _get_text_cached_value(key)
    if hit:
        return value

    lock_name = lock_key or f"lock:{key}"
    token = try_acquire_lock(lock_name, lock_ttl_seconds)
    if token:
        try:
            hit, value = _get_text_cached_value(key)
            if hit:
                return value
            value = loader()
            if value is None and cache_null:
                set_text_null(key, null_ttl_seconds, jitter=jitter)
            elif value is not None:
                set_text(key, value, ttl_seconds, jitter=jitter)
            return value
        finally:
            release_lock(lock_name, token)

    deadline = time.monotonic() + wait_timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(retry_interval_seconds)
        hit, value = _get_text_cached_value(key)
        if hit:
            return value

    value = loader()
    if value is None and cache_null:
        set_text_null(key, null_ttl_seconds, jitter=jitter)
    elif value is not None:
        set_text(key, value, ttl_seconds, jitter=jitter)
    return value


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
