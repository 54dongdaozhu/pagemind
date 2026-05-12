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
from app.services.job_queue import enqueue_job
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
            if not _upsert_extract_cache_row(db, cache_key, result_data, now, expired_at):
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
                kp_id = _upsert_knowledge_point_row(db, item, now)

                if storage_doc_id is not None and resolved_chunk_index is not None:
                    _upsert_chunk_knowledge_link(db, storage_doc_id, resolved_chunk_index, kp_id, item, now)
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


def _upsert_extract_cache_row(
    db,
    cache_key: str,
    result_data: list[dict],
    now: datetime,
    expired_at: datetime,
) -> bool:
    dialect = db.bind.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        return False

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    stmt = insert(ExtractCache).values(
        chunk_id=cache_key,
        result=result_data,
        created_at=now,
        expired_at=expired_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["chunk_id"],
        set_={
            "result": result_data,
            "created_at": now,
            "expired_at": expired_at,
        },
    )
    db.execute(stmt)
    return True


def _upsert_knowledge_point_row(db, item: KnowledgePoint, now: datetime) -> str:
    dialect = db.bind.dialect.name
    values = {
        "kp_text": item.text,
        "kp_type": item.type,
        "explanation": item.explanation,
        "importance": item.importance,
        "updated_at": now,
    }

    if dialect in {"postgresql", "sqlite"}:
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert

        stmt = insert(KnowledgePointRow).values(kp_id=uuid.uuid4().hex, created_at=now, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["kp_text"],
            set_=values,
        )
        if dialect == "postgresql":
            return db.execute(stmt.returning(KnowledgePointRow.kp_id)).scalar_one()
        db.execute(stmt)
        return db.execute(
            select(KnowledgePointRow.kp_id).where(KnowledgePointRow.kp_text == item.text)
        ).scalar_one()

    row = db.execute(
        select(KnowledgePointRow).where(KnowledgePointRow.kp_text == item.text)
    ).scalar_one_or_none()
    if row is None:
        kp_id = uuid.uuid4().hex
        db.add(KnowledgePointRow(kp_id=kp_id, created_at=now, **values))
        return kp_id

    row.kp_type = item.type
    row.explanation = item.explanation
    row.importance = item.importance
    row.updated_at = now
    return row.kp_id


def _upsert_chunk_knowledge_link(
    db,
    storage_doc_id: str,
    chunk_index: int,
    kp_id: str,
    item: KnowledgePoint,
    now: datetime,
) -> None:
    confidence = _confidence_for_importance(item.importance)
    dialect = db.bind.dialect.name

    if dialect in {"postgresql", "sqlite"}:
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert

        stmt = insert(ChunkKnowledgePoint).values(
            doc_id=storage_doc_id,
            chunk_index=chunk_index,
            kp_id=kp_id,
            confidence=confidence,
            created_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["doc_id", "chunk_index", "kp_id"],
            set_={"confidence": confidence},
        )
        db.execute(stmt)
        return

    existing_link = db.get(ChunkKnowledgePoint, (storage_doc_id, chunk_index, kp_id))
    if existing_link is None:
        db.add(ChunkKnowledgePoint(
            doc_id=storage_doc_id,
            chunk_index=chunk_index,
            kp_id=kp_id,
            confidence=confidence,
            created_at=now,
        ))
    else:
        existing_link.confidence = confidence


def _confidence_for_importance(importance: str) -> float:
    return 0.95 if importance == "high" else 0.75


def persist_extraction_result(
    user_id: str,
    chunk_id: str,
    cache_key: str,
    knowledge_points_data: list[dict],
    doc_id: str | None = None,
    chunk_index: int | None = None,
    save_cache: bool = False,
) -> None:
    knowledge_points = [KnowledgePoint(**item) for item in knowledge_points_data]
    if save_cache:
        _save_to_cache(cache_key, knowledge_points)
    _upsert_extracted_knowledge_points(user_id, chunk_id, knowledge_points, doc_id, chunk_index)


def _persist_or_enqueue(
    user_id: str,
    chunk_id: str,
    cache_key: str,
    knowledge_points: list[KnowledgePoint],
    doc_id: str | None = None,
    chunk_index: int | None = None,
    save_cache: bool = False,
) -> None:
    payload = [kp.model_dump() for kp in knowledge_points]
    args = (user_id, chunk_id, cache_key, payload, doc_id, chunk_index, save_cache)
    if enqueue_job(persist_extraction_result, *args):
        return
    try:
        persist_extraction_result(*args)
    except Exception as e:
        logger.exception("Persisting extracted knowledge failed for chunk %s: %s", chunk_id, e)


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
            _persist_or_enqueue(
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
        _persist_or_enqueue(
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
    _persist_or_enqueue(
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
) -> ExtractBatchResponse:
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
