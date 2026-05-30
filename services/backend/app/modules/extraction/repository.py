import uuid
from datetime import datetime, timedelta, timezone
from threading import RLock

from sqlalchemy import select, update

from app.modules.agent.knowledge_agents import finalize_knowledge_items
from app.core.database import ChunkKnowledgePoint, ExtractCache, KnowledgePoint as KnowledgePointRow, RagChunk, get_db
from app.modules.extraction.schemas import KnowledgePoint
from app.shared import db_log
from app.shared.cache import ANALYSIS_REPORT_CACHE_TTL_SECONDS, get_json, set_json, stable_hash
from app.shared.job_queue import enqueue_job
from app.modules.rag.repository import list_document_chunks, scoped_doc_id

import logging

logger = logging.getLogger(__name__)

_extract_db_lock = RLock()

_CACHE_TTL_DAYS = 7
_DOC_KP_CACHE_TTL = ANALYSIS_REPORT_CACHE_TTL_SECONDS  # 24h


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Chunk ID helpers ───────────────────────────────────────────────────────────

def _scoped_chunk_id(user_id: str, chunk_id: str) -> str:
    return f"user:{user_id}:chunk:{chunk_id}"


def _canonical_extract_chunk_id(user_id: str, doc_id: str, row: dict) -> str:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    return stable_hash({
        "doc_id": storage_doc_id,
        "chunk_index": row.get("chunk_index"),
        "content": row.get("content", ""),
    })


def _frontend_extract_chunk_id(doc_id: str, chunk_index: int, text: str) -> str:
    return _js_hash_string(f"{doc_id}:{chunk_index}:{text}")


def _js_hash_string(value: str) -> str:
    hash_value = 0
    utf16 = value.encode("utf-16-le", "surrogatepass")
    for idx in range(0, len(utf16), 2):
        char = int.from_bytes(utf16[idx:idx + 2], "little")
        hash_value = ((hash_value << 5) - hash_value) + char
        hash_value = _to_int32(hash_value)
    return _to_base36(abs(hash_value))


def _to_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _to_base36(value: int) -> str:
    if value == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while value:
        value, remainder = divmod(value, 36)
        out = digits[remainder] + out
    return out


# ── KP schema conversion ───────────────────────────────────────────────────────

def _to_knowledge_points(kps_data: list[dict], text: str) -> list[KnowledgePoint]:
    finalized = finalize_knowledge_items(kps_data, text)
    return [KnowledgePoint(**kp) for kp in finalized]


# ── SQLite extract cache ───────────────────────────────────────────────────────

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


# ── Redis KP cache ─────────────────────────────────────────────────────────────

def _doc_kp_redis_key(user_id: str, doc_id: str) -> str:
    return f"doc_kps:user:{user_id}:doc:{doc_id}"


def get_refined_doc_kps(user_id: str, doc_id: str) -> list[dict] | None:
    """读取 Phase 2 精炼后的文档级知识点（来自 Redis）。"""
    data = get_json(_doc_kp_redis_key(user_id, doc_id))
    if isinstance(data, list):
        return data
    return None


def save_refined_doc_kps(user_id: str, doc_id: str, kps: list[dict]) -> None:
    """将 Phase 2 精炼结果写入 Redis。"""
    set_json(_doc_kp_redis_key(user_id, doc_id), kps, _DOC_KP_CACHE_TTL)


def get_persisted_doc_kps(user_id: str, doc_id: str) -> list[dict]:
    """Load document knowledge points from persisted DB links, then extract cache."""
    linked = _load_doc_kps_from_db(user_id, doc_id)
    if linked:
        return linked

    cached = _load_doc_kps_from_extract_cache(user_id, doc_id)
    return cached


def _load_doc_kps_from_db(user_id: str, doc_id: str) -> list[dict]:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    with get_db() as db:
        rows = db.execute(
            select(ChunkKnowledgePoint, KnowledgePointRow)
            .join(KnowledgePointRow, KnowledgePointRow.kp_id == ChunkKnowledgePoint.kp_id)
            .where(ChunkKnowledgePoint.doc_id == storage_doc_id)
            .order_by(ChunkKnowledgePoint.chunk_index.asc(), ChunkKnowledgePoint.confidence.desc())
        ).all()

    return _dedupe_doc_kps([
        {
            "text": kp.kp_text,
            "type": kp.kp_type,
            "explanation": kp.explanation or "",
            "importance": kp.importance or "medium",
            "chunk_index": link.chunk_index,
            "has_explanation": link.has_explanation,
        }
        for link, kp in rows
        if kp.kp_text
    ])


def _load_doc_kps_from_extract_cache(user_id: str, doc_id: str) -> list[dict]:
    rows = list_document_chunks(user_id, doc_id)
    all_items: list[dict] = []
    for row in rows:
        content = row.get("content")
        chunk_index = row.get("chunk_index")
        if not isinstance(content, str) or chunk_index is None:
            continue
        chunk_ids = list(dict.fromkeys([
            _frontend_extract_chunk_id(doc_id, int(chunk_index), content),
            _canonical_extract_chunk_id(user_id, doc_id, row),
        ]))
        chunk_id = ""
        cache_key = ""
        knowledge_points = None
        for candidate in chunk_ids:
            if not candidate:
                continue
            candidate_cache_key = _scoped_chunk_id(user_id, candidate)
            knowledge_points = _load_from_cache(candidate_cache_key, content)
            if knowledge_points is not None:
                chunk_id = candidate
                cache_key = candidate_cache_key
                break
        if knowledge_points is None or not chunk_id or not cache_key:
            continue
        _persist_or_enqueue(
            user_id,
            chunk_id,
            cache_key,
            knowledge_points,
            doc_id,
            int(chunk_index),
        )
        all_items.extend({
            **kp.model_dump(),
            "chunk_index": int(chunk_index),
        } for kp in knowledge_points)

    return _dedupe_doc_kps(all_items)


def _dedupe_doc_kps(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
        existing = merged.get(text)
        if existing is None:
            merged[text] = {
                "text": text,
                "type": item.get("type") or "term",
                "explanation": item.get("explanation") or "",
                "importance": item.get("importance") or "medium",
                "chunk_index": item.get("chunk_index"),
                "has_explanation": item.get("has_explanation"),
            }
        else:
            if existing.get("importance") != "high" and item.get("importance") == "high":
                existing["importance"] = "high"
                if item.get("explanation"):
                    existing["explanation"] = item["explanation"]
                if item.get("chunk_index") is not None:
                    existing["chunk_index"] = item["chunk_index"]
            if existing.get("has_explanation") is None and item.get("has_explanation") is not None:
                existing["has_explanation"] = item["has_explanation"]

    result = []
    for item in merged.values():
        item["chunk_count"] = counts.get(item["text"], 1)
        result.append(item)
    return result


# ── DB KP persistence ──────────────────────────────────────────────────────────

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


# ── Phase 2 DB update ──────────────────────────────────────────────────────────

def _persist_phase2_results(user_id: str, doc_id: str, refined: list[dict]) -> None:
    """将 Phase 2 精炼结果回写 DB：importance 只升级不降级，has_explanation 按文档更新。"""
    if not refined:
        return

    storage_doc_id = scoped_doc_id(user_id, doc_id)
    now = datetime.now(timezone.utc)

    high_texts = [kp["text"] for kp in refined if kp.get("importance") == "high" and kp.get("text")]
    has_expl_items = [
        (kp["text"], kp["has_explanation"])
        for kp in refined
        if kp.get("text") and kp.get("has_explanation") is not None
    ]

    with _extract_db_lock:
        with get_db() as db:
            if high_texts:
                db.execute(
                    update(KnowledgePointRow)
                    .where(KnowledgePointRow.kp_text.in_(high_texts))
                    .where(KnowledgePointRow.importance != "high")
                    .values(importance="high", updated_at=now)
                )

            if has_expl_items:
                texts = [text for text, _ in has_expl_items]
                kp_rows = db.execute(
                    select(KnowledgePointRow.kp_id, KnowledgePointRow.kp_text)
                    .where(KnowledgePointRow.kp_text.in_(texts))
                ).all()
                text_to_id = {row.kp_text: row.kp_id for row in kp_rows}

                for text, has_expl in has_expl_items:
                    kp_id = text_to_id.get(text)
                    if kp_id is None:
                        continue
                    link_row = db.execute(
                        select(ChunkKnowledgePoint)
                        .where(ChunkKnowledgePoint.doc_id == storage_doc_id)
                        .where(ChunkKnowledgePoint.kp_id == kp_id)
                        .limit(1)
                    ).scalar_one_or_none()
                    if link_row is not None:
                        link_row.has_explanation = has_expl

            db.commit()


# ── Public RQ job & helper ─────────────────────────────────────────────────────

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
