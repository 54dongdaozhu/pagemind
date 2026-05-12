"""
Knowledge extraction service.

The API keeps the existing response shape used by the frontend, while the
actual decision-making is delegated to the agent workflow:
KnowledgeDiscoveryAgent -> KnowledgeFilterAgent -> KnowledgeRankAgent.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore, Lock, RLock
from typing import Any, Protocol

from sqlalchemy import select

from app.agents.knowledge_agents import discover_knowledge_points, finalize_knowledge_items
from app.core.config import EXTRACT_MAX_CONCURRENCY
from app.core.database import ChunkKnowledgePoint, ExtractCache, KnowledgePoint as KnowledgePointRow, RagChunk, get_db
from app.schemas.knowledge import ExtractBatchItem, ExtractBatchResponse, ExtractResponse, KnowledgePoint
from app.services import db_log
from app.services.rag.repository import scoped_doc_id


logger = logging.getLogger(__name__)

_extract_cache: dict = {}
_extract_cache_lock = RLock()
_extract_db_lock = RLock()
_llm_slots = BoundedSemaphore(EXTRACT_MAX_CONCURRENCY)

# 缓存 TTL：7 天（同一 chunk 内容不会频繁变动）
_CACHE_TTL_DAYS = 7


class PersistTaskScheduler(Protocol):
    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None:
        ...


class _PersistTaskCollector:
    def __init__(self):
        self._lock = Lock()
        self._tasks: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            self._tasks.append((func, args, kwargs))

    def flush_to(self, scheduler: PersistTaskScheduler) -> None:
        with self._lock:
            tasks = list(self._tasks)
            self._tasks.clear()
        for func, args, kwargs in tasks:
            scheduler.add_task(func, *args, **kwargs)


def _to_knowledge_points(kps_data: list[dict], text: str) -> list[KnowledgePoint]:
    finalized = finalize_knowledge_items(kps_data, text)
    return [KnowledgePoint(**kp) for kp in finalized]


def _scoped_chunk_id(user_id: str, chunk_id: str) -> str:
    return f"user:{user_id}:chunk:{chunk_id}"


def _load_from_cache(cache_key: str, text: str) -> list[KnowledgePoint] | None:
    now = datetime.now(timezone.utc)
    with get_db() as db:
        cache = db.get(ExtractCache, cache_key)

    if cache is None:
        return None

    # 检查 TTL：SQLite 会丢失 timezone 信息，比较前统一按 UTC 处理。
    expired_at = cache.expired_at
    if expired_at is not None and expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)
    if expired_at is not None and expired_at < now:
        return None

    # result 字段已是 JSON 类型，SQLAlchemy 自动反序列化为 list/dict
    data = cache.result
    if not isinstance(data, list):
        return None
    return _to_knowledge_points(data, text)


def _save_to_cache(cache_key: str, knowledge_points: list[KnowledgePoint]):
    now = datetime.now(timezone.utc)
    expired_at = now + timedelta(days=_CACHE_TTL_DAYS)
    result_data = [kp.model_dump() for kp in knowledge_points]

    with _extract_db_lock:
        with get_db() as db:
            cache = db.get(ExtractCache, cache_key)
            if cache is None:
                db.add(ExtractCache(
                    chunk_id=cache_key,
                    result=result_data,
                    created_at=now,
                    expired_at=expired_at,
                ))
            else:
                cache.result = result_data
                cache.created_at = now
                cache.expired_at = expired_at
            db.commit()


def _upsert_extracted_knowledge_points(
    user_id: str,
    chunk_id: str,
    knowledge_points: list[KnowledgePoint],
    doc_id: str | None = None,
    chunk_index: int | None = None,
) -> None:
    if not knowledge_points:
        return

    now = datetime.now(timezone.utc)
    storage_doc_id = scoped_doc_id(user_id, doc_id) if doc_id else None
    with _extract_db_lock:
        with get_db() as db:
            resolved_chunk_index = _resolve_chunk_index(db, storage_doc_id, chunk_index) if storage_doc_id else None
            for item in knowledge_points:
                row = db.execute(
                    select(KnowledgePointRow).where(KnowledgePointRow.kp_text == item.text)
                ).scalar_one_or_none()
                if row is None:
                    kp_id = uuid.uuid4().hex
                    db.add(KnowledgePointRow(
                        kp_id=kp_id,
                        kp_text=item.text,
                        kp_type=item.type,
                        explanation=item.explanation,
                        importance=item.importance,
                        created_at=now,
                        updated_at=now,
                    ))
                else:
                    kp_id = row.kp_id
                    row.kp_type = item.type
                    row.explanation = item.explanation
                    row.importance = item.importance
                    row.updated_at = now

                if storage_doc_id is not None and resolved_chunk_index is not None:
                    existing_link = db.get(
                        ChunkKnowledgePoint,
                        (storage_doc_id, resolved_chunk_index, kp_id),
                    )
                    if existing_link is None:
                        db.add(ChunkKnowledgePoint(
                            doc_id=storage_doc_id,
                            chunk_index=resolved_chunk_index,
                            kp_id=kp_id,
                            confidence=_confidence_for_importance(item.importance),
                            created_at=now,
                        ))
                    else:
                        existing_link.confidence = _confidence_for_importance(item.importance)
            db.commit()

    db_log.log_event(
        entity_type="extract_cache",
        entity_id=chunk_id,
        event_type="knowledge.extracted",
        user_id=user_id,
        after_state={"knowledge_count": len(knowledge_points), "doc_id": doc_id, "chunk_index": chunk_index},
    )


def _resolve_chunk_index(db, storage_doc_id: str | None, chunk_index: int | None) -> int | None:
    if storage_doc_id is None or chunk_index is None:
        return None
    return chunk_index if db.get(RagChunk, (storage_doc_id, chunk_index)) is not None else None


def _confidence_for_importance(importance: str) -> float:
    return 0.95 if importance == "high" else 0.75


def _persist_extraction_result(
    user_id: str,
    chunk_id: str,
    cache_key: str,
    knowledge_points: list[KnowledgePoint],
    doc_id: str | None = None,
    chunk_index: int | None = None,
    save_cache: bool = False,
) -> None:
    try:
        if save_cache:
            _save_to_cache(cache_key, knowledge_points)
        _upsert_extracted_knowledge_points(user_id, chunk_id, knowledge_points, doc_id, chunk_index)
    except Exception as e:
        logger.exception("Persisting extracted knowledge failed for chunk %s: %s", chunk_id, e)


def _persist_or_schedule(
    scheduler: PersistTaskScheduler | None,
    user_id: str,
    chunk_id: str,
    cache_key: str,
    knowledge_points: list[KnowledgePoint],
    doc_id: str | None = None,
    chunk_index: int | None = None,
    save_cache: bool = False,
) -> None:
    args = (user_id, chunk_id, cache_key, knowledge_points, doc_id, chunk_index, save_cache)
    if scheduler is None:
        _persist_extraction_result(*args)
        return
    scheduler.add_task(_persist_extraction_result, *args)


def extract_knowledge_from_text(
    user_id: str,
    chunk_id: str,
    text: str,
    doc_id: str | None = None,
    chunk_index: int | None = None,
    background_tasks: PersistTaskScheduler | None = None,
) -> ExtractResponse:
    text = text.strip()
    cache_key = _scoped_chunk_id(user_id, chunk_id)

    with _extract_cache_lock:
        if cache_key in _extract_cache:
            cached_points = _extract_cache[cache_key]
            _persist_or_schedule(
                background_tasks,
                user_id,
                chunk_id,
                cache_key,
                cached_points,
                doc_id,
                chunk_index,
            )
            return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached_points)

    cached = _load_from_cache(cache_key, text)
    if cached is not None:
        with _extract_cache_lock:
            _extract_cache[cache_key] = cached
        _persist_or_schedule(
            background_tasks,
            user_id,
            chunk_id,
            cache_key,
            cached,
            doc_id,
            chunk_index,
        )
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached)

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    try:
        with _llm_slots:
            kps_data = discover_knowledge_points(text)
        knowledge_points = _to_knowledge_points(kps_data, text)
    except Exception as e:
        logger.exception("Knowledge agent extraction failed: %s", e)
        knowledge_points = []

    with _extract_cache_lock:
        _extract_cache[cache_key] = knowledge_points
    _persist_or_schedule(
        background_tasks,
        user_id,
        chunk_id,
        cache_key,
        knowledge_points,
        doc_id,
        chunk_index,
        save_cache=True,
    )

    return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)


def extract_knowledge_batch(
    user_id: str,
    chunks: list[ExtractBatchItem],
    background_tasks: PersistTaskScheduler | None = None,
) -> ExtractBatchResponse:
    if not chunks:
        return ExtractBatchResponse(results=[])

    task_scheduler = _PersistTaskCollector() if background_tasks is not None else None
    max_workers = min(EXTRACT_MAX_CONCURRENCY, len(chunks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(
            executor.map(
                lambda chunk: extract_knowledge_from_text(
                    user_id,
                    chunk.chunk_id,
                    chunk.text,
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    background_tasks=task_scheduler,
                ),
                chunks,
            )
        )

    if task_scheduler is not None and background_tasks is not None:
        task_scheduler.flush_to(background_tasks)

    return ExtractBatchResponse(results=results)
