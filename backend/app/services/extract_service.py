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
from threading import BoundedSemaphore, RLock

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

    # 检查 TTL：expired_at 存在且已过期，视为缓存失效
    if cache.expired_at is not None and cache.expired_at < now:
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


def extract_knowledge_from_text(
    user_id: str,
    chunk_id: str,
    text: str,
    doc_id: str | None = None,
    chunk_index: int | None = None,
) -> ExtractResponse:
    text = text.strip()
    cache_key = _scoped_chunk_id(user_id, chunk_id)

    with _extract_cache_lock:
        if cache_key in _extract_cache:
            cached_points = _extract_cache[cache_key]
            _upsert_extracted_knowledge_points(user_id, chunk_id, cached_points, doc_id, chunk_index)
            return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached_points)

    cached = _load_from_cache(cache_key, text)
    if cached is not None:
        with _extract_cache_lock:
            _extract_cache[cache_key] = cached
        _upsert_extracted_knowledge_points(user_id, chunk_id, cached, doc_id, chunk_index)
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
    _save_to_cache(cache_key, knowledge_points)
    _upsert_extracted_knowledge_points(user_id, chunk_id, knowledge_points, doc_id, chunk_index)

    return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)


def extract_knowledge_batch(user_id: str, chunks: list[ExtractBatchItem]) -> ExtractBatchResponse:
    if not chunks:
        return ExtractBatchResponse(results=[])

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
                ),
                chunks,
            )
        )

    return ExtractBatchResponse(results=results)
