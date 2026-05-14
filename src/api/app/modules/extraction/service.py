"""
Knowledge extraction service.

The API keeps the existing response shape used by the frontend, while the
actual decision-making is delegated to the agent workflow:
KnowledgeDiscoveryAgent -> ChunkCriticAgent.
"""
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore, RLock

from sqlalchemy import select

from app.modules.agent.knowledge_agents import discover_knowledge_points, finalize_knowledge_items, refine_document_knowledge
from app.core.config import EXTRACT_MAX_CONCURRENCY
from app.core.database import ChunkKnowledgePoint, ExtractCache, KnowledgePoint as KnowledgePointRow, RagChunk, WorkflowRun, get_db
from app.shared.schemas import ExtractBatchItem, ExtractBatchResponse, ExtractResponse, KnowledgePoint
from app.shared import db_log
from app.shared.cache import ANALYSIS_REPORT_CACHE_TTL_SECONDS, get_json, set_json, stable_hash
from app.shared.job_queue import enqueue_job
from app.modules.rag.repository import list_document_chunks, scoped_doc_id
from app.modules.rag.service import index_document_text


logger = logging.getLogger(__name__)

_extract_cache: dict = {}
_extract_cache_lock = RLock()
_extract_db_lock = RLock()
_llm_slots = BoundedSemaphore(EXTRACT_MAX_CONCURRENCY)

# 缓存 TTL：7 天（同一 chunk 内容不会频繁变动）
_CACHE_TTL_DAYS = 7
_DOC_KP_CACHE_TTL = ANALYSIS_REPORT_CACHE_TTL_SECONDS  # 24h
_PROGRESS_TTL_SECONDS = 60 * 60 * 24
_RAG_READY_WAIT_SECONDS = 8
_RAG_READY_POLL_SECONDS = 0.5


def _doc_kp_redis_key(user_id: str, doc_id: str) -> str:
    return f"doc_kps:user:{user_id}:doc:{doc_id}"


def _extraction_progress_key(run_id: str) -> str:
    return f"progress:knowledge_extraction:{run_id}"


def _refinement_progress_key(run_id: str) -> str:
    return f"progress:knowledge_refinement:{run_id}"


def _doc_refinement_progress_key(user_id: str, doc_id: str) -> str:
    return f"progress:knowledge_refinement:user:{user_id}:doc:{doc_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_refined_doc_kps(user_id: str, doc_id: str) -> list[dict] | None:
    """读取 Phase 2 精炼后的文档级知识点（来自 Redis）。"""
    data = get_json(_doc_kp_redis_key(user_id, doc_id))
    if isinstance(data, list):
        return data
    return None


def get_refinement_status(user_id: str, doc_id: str) -> dict | None:
    data = get_json(_doc_refinement_progress_key(user_id, doc_id))
    return data if isinstance(data, dict) else None


def save_refined_doc_kps(user_id: str, doc_id: str, kps: list[dict]) -> None:
    """将 Phase 2 精炼结果写入 Redis。"""
    set_json(_doc_kp_redis_key(user_id, doc_id), kps, _DOC_KP_CACHE_TTL)


def _wait_for_rag_ready(user_id: str, doc_id: str) -> bool:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    deadline = time.monotonic() + _RAG_READY_WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            with get_db() as db:
                chunk_exists = db.execute(
                    select(RagChunk.chunk_index)
                    .where(RagChunk.doc_id == storage_doc_id)
                    .limit(1)
                ).first()
                if chunk_exists is not None:
                    return True
        except Exception as e:
            logger.warning("[Phase2] RAG readiness check failed for doc=%s: %s", doc_id, e)
            return False
        time.sleep(_RAG_READY_POLL_SECONDS)
    return False


def _enrich_refined_kp_metadata(refined: list[dict], source_kps: list[dict]) -> list[dict]:
    source_by_text = {}
    for kp in source_kps:
        text = kp.get("text")
        if text and text not in source_by_text:
            source_by_text[text] = kp

    enriched = []
    for kp in refined:
        if not isinstance(kp, dict):
            continue
        item = dict(kp)
        source = source_by_text.get(item.get("text"))
        if source:
            item.setdefault("chunk_id", source.get("chunk_id"))
            item.setdefault("chunk_index", source.get("chunk_index"))
        enriched.append(item)
    return enriched


def _load_progress(key: str) -> dict:
    progress = get_json(key)
    return progress if isinstance(progress, dict) else {}


def _public_progress(progress: dict) -> dict:
    return {
        "run_id": progress.get("run_id", ""),
        "doc_id": progress.get("doc_id"),
        "workflow_type": progress.get("workflow_type", "knowledge_extraction"),
        "status": progress.get("status", "unknown"),
        "total": int(progress.get("total", 0) or 0),
        "done": int(progress.get("done", 0) or 0),
        "failed": int(progress.get("failed", 0) or 0),
        "knowledge_count": int(progress.get("knowledge_count", 0) or 0),
        "refinement_run_id": progress.get("refinement_run_id"),
        "errors": list(progress.get("errors", []) or []),
        "updated_at": progress.get("updated_at"),
    }


def _save_refinement_progress(user_id: str, doc_id: str, run_id: str, progress: dict) -> None:
    set_json(_refinement_progress_key(run_id), progress, _PROGRESS_TTL_SECONDS)
    set_json(_doc_refinement_progress_key(user_id, doc_id), progress, _PROGRESS_TTL_SECONDS)


def _record_extraction_chunk_success(
    run_id: str | None,
    doc_id: str | None,
    chunk_index: int | None,
    knowledge_count: int,
) -> None:
    if not run_id or chunk_index is None:
        return
    key = _extraction_progress_key(run_id)
    progress = _load_progress(key)
    if not progress:
        return
    chunk_counts = progress.get("chunk_counts")
    if not isinstance(chunk_counts, dict):
        chunk_counts = {}
    chunk_key = str(chunk_index)
    chunk_counts[chunk_key] = knowledge_count
    progress["chunk_counts"] = chunk_counts
    progress["done"] = len(chunk_counts)
    progress["knowledge_count"] = sum(int(value or 0) for value in chunk_counts.values())
    progress["doc_id"] = progress.get("doc_id") or doc_id
    progress["status"] = "running"
    progress["updated_at"] = _now_iso()
    set_json(key, progress, _PROGRESS_TTL_SECONDS)


def _record_extraction_chunk_error(
    run_id: str | None,
    doc_id: str | None,
    chunk_index: int | None,
    message: str,
) -> None:
    if not run_id or chunk_index is None:
        return
    key = _extraction_progress_key(run_id)
    progress = _load_progress(key)
    if not progress:
        return
    errors = progress.get("errors")
    if not isinstance(errors, list):
        errors = []
    errors = [item for item in errors if item.get("chunk_index") != chunk_index]
    errors.append({"chunk_index": chunk_index, "message": message})
    progress["errors"] = errors[-20:]
    progress["failed"] = len(errors)
    progress["doc_id"] = progress.get("doc_id") or doc_id
    progress["updated_at"] = _now_iso()
    set_json(key, progress, _PROGRESS_TTL_SECONDS)


def start_knowledge_extraction_run(
    user_id: str,
    doc_id: str,
    chunks: list[ExtractBatchItem],
    title: str | None = None,
    source: str = "frontend_chunks",
) -> dict:
    total = len(chunks)
    run_id = db_log.create_workflow_run(
        workflow_type="knowledge_extraction",
        user_id=user_id,
        doc_id=scoped_doc_id(user_id, doc_id),
        input_data={"doc_id": doc_id, "title": title, "chunk_count": total, "source": source},
    )
    progress = {
        "run_id": run_id,
        "doc_id": doc_id,
        "workflow_type": "knowledge_extraction",
        "status": "running",
        "total": total,
        "done": 0,
        "failed": 0,
        "knowledge_count": 0,
        "chunk_counts": {},
        "errors": [],
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    set_json(_extraction_progress_key(run_id), progress, _PROGRESS_TTL_SECONDS)
    db_log.log_event(
        entity_type="workflow_run",
        entity_id=run_id,
        event_type="knowledge.extraction.started",
        user_id=user_id,
        after_state={"doc_id": doc_id, "chunk_count": total},
    )
    return {"run_id": run_id, "status": "running", "total": total}


def get_extraction_status(run_id: str) -> dict:
    progress = get_json(_extraction_progress_key(run_id))
    if isinstance(progress, dict):
        return _public_progress(progress)

    with get_db() as db:
        run = db.get(WorkflowRun, run_id)
    if run is None:
        return {
            "run_id": run_id,
            "workflow_type": "knowledge_extraction",
            "status": "unknown",
            "total": 0,
            "done": 0,
            "failed": 0,
            "knowledge_count": 0,
            "errors": [],
            "updated_at": None,
        }
    output = run.output_data if isinstance(run.output_data, dict) else {}
    return {
        "run_id": run_id,
        "doc_id": run.doc_id,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "total": output.get("total", 0),
        "done": output.get("done", 0),
        "failed": output.get("failed", 0),
        "knowledge_count": output.get("knowledge_count", 0),
        "refinement_run_id": output.get("refinement_run_id"),
        "errors": output.get("errors", []),
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def finalize_knowledge_extraction(
    user_id: str,
    run_id: str,
    doc_id: str,
    chunks: list[ExtractBatchItem],
) -> dict:
    all_chunk_kps: list[dict] = []
    for chunk in chunks:
        cache_key = _scoped_chunk_id(user_id, chunk.chunk_id)
        knowledge_points = _load_from_cache(cache_key, chunk.text)
        if knowledge_points is None:
            response = extract_knowledge_from_text(
                user_id,
                chunk.chunk_id,
                chunk.text,
                doc_id=chunk.doc_id or doc_id,
                chunk_index=chunk.chunk_index,
                run_id=run_id,
            )
            knowledge_points = response.knowledge_points
        else:
            _record_extraction_chunk_success(run_id, doc_id, chunk.chunk_index, len(knowledge_points))
        for kp in knowledge_points:
            all_chunk_kps.append({
                **kp.model_dump(),
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
            })

    progress = _load_progress(_extraction_progress_key(run_id))
    failed = int(progress.get("failed", 0))
    done = int(progress.get("done", 0))
    total = int(progress.get("total", len(chunks)))
    status = "failed" if done == 0 and failed > 0 else "degraded" if failed > 0 else "completed"
    refinement_run_id = None
    if all_chunk_kps:
        refinement_run_id = start_refinement_run(user_id, doc_id, all_chunk_kps, parent_run_id=run_id)
        if not enqueue_job(run_phase2_and_save, user_id, doc_id, all_chunk_kps, refinement_run_id):
            try:
                run_phase2_and_save(user_id, doc_id, all_chunk_kps, refinement_run_id)
            except Exception as e:
                logger.exception("[Phase2] finalize fallback failed: %s", e)

    output_data = {
        "total": total,
        "done": done,
        "failed": failed,
        "knowledge_count": int(progress.get("knowledge_count", len(all_chunk_kps))),
        "errors": progress.get("errors", []),
        "refinement_run_id": refinement_run_id,
    }
    progress.update({"status": status, "refinement_run_id": refinement_run_id, "updated_at": _now_iso()})
    set_json(_extraction_progress_key(run_id), progress, _PROGRESS_TTL_SECONDS)
    db_log.finish_workflow_run(
        run_id,
        success=status != "failed",
        status=status,
        output_data=output_data,
        error_details={"errors": progress.get("errors", [])} if status == "failed" else None,
    )
    db_log.log_event(
        entity_type="workflow_run",
        entity_id=run_id,
        event_type=f"knowledge.extraction.{status}",
        user_id=user_id,
        after_state=output_data,
    )
    return _public_progress(progress)


def start_refinement_run(
    user_id: str,
    doc_id: str,
    all_chunk_kps: list[dict],
    parent_run_id: str | None = None,
) -> str:
    run_id = db_log.create_workflow_run(
        workflow_type="knowledge_refinement",
        user_id=user_id,
        doc_id=scoped_doc_id(user_id, doc_id),
        input_data={
            "doc_id": doc_id,
            "parent_run_id": parent_run_id,
            "knowledge_count": len(all_chunk_kps),
        },
    )
    progress = {
        "run_id": run_id,
        "doc_id": doc_id,
        "workflow_type": "knowledge_refinement",
        "status": "running",
        "total": len(all_chunk_kps),
        "done": 0,
        "failed": 0,
        "knowledge_count": len(all_chunk_kps),
        "refined_count": 0,
        "parent_run_id": parent_run_id,
        "errors": [],
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _save_refinement_progress(user_id, doc_id, run_id, progress)
    db_log.log_event(
        entity_type="workflow_run",
        entity_id=run_id,
        event_type="knowledge.refinement.started",
        user_id=user_id,
        after_state={"doc_id": doc_id, "knowledge_count": len(all_chunk_kps), "parent_run_id": parent_run_id},
    )
    return run_id


def run_phase2_and_save(
    user_id: str,
    doc_id: str,
    all_chunk_kps: list[dict],
    run_id: str | None = None,
) -> None:
    """Phase 2 任务入口（由 job_queue 异步执行）。"""
    if run_id is None:
        run_id = start_refinement_run(user_id, doc_id, all_chunk_kps)
    progress = _load_progress(_refinement_progress_key(run_id))
    progress.update({"status": "running", "updated_at": _now_iso()})
    _save_refinement_progress(user_id, doc_id, run_id, progress)
    try:
        rag_ready = _wait_for_rag_ready(user_id, doc_id)
        progress.update({"rag_ready": rag_ready, "updated_at": _now_iso()})
        _save_refinement_progress(user_id, doc_id, run_id, progress)

        refined = refine_document_knowledge(user_id, doc_id, all_chunk_kps)
        refined = _enrich_refined_kp_metadata(refined, all_chunk_kps)
        save_refined_doc_kps(user_id, doc_id, refined)
        status = "completed" if rag_ready else "degraded"
        progress.update({
            "status": status,
            "done": len(all_chunk_kps),
            "refined_count": len(refined),
            "updated_at": _now_iso(),
        })
        _save_refinement_progress(user_id, doc_id, run_id, progress)
        db_log.finish_workflow_run(
            run_id,
            status=status,
            output_data={"input_count": len(all_chunk_kps), "refined_count": len(refined), "rag_ready": rag_ready},
        )
        db_log.log_event(
            entity_type="workflow_run",
            entity_id=run_id,
            event_type=f"knowledge.refinement.{status}",
            user_id=user_id,
            after_state={"doc_id": doc_id, "refined_count": len(refined), "rag_ready": rag_ready},
        )
        logger.info("[Phase2] saved %s refined KPs for doc=%s", len(refined), doc_id)
    except Exception as e:
        progress.update({
            "status": "failed",
            "failed": 1,
            "errors": [{"message": str(e)}],
            "updated_at": _now_iso(),
        })
        _save_refinement_progress(user_id, doc_id, run_id, progress)
        db_log.finish_workflow_run(
            run_id,
            success=False,
            status="failed",
            output_data={"input_count": len(all_chunk_kps), "refined_count": 0},
            error_details={"error": str(e)},
        )
        logger.exception("[Phase2] failed for doc=%s: %s", doc_id, e)


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
    run_id: str | None = None,
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
            _record_extraction_chunk_success(run_id, doc_id, chunk_index, len(cached_points))
            return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=cached_points)

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
        _record_extraction_chunk_success(run_id, doc_id, chunk_index, len(cached))
        return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=cached)

    if len(text) < 30:
        _record_extraction_chunk_success(run_id, doc_id, chunk_index, 0)
        return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=[])

    try:
        with _llm_slots:
            kps_data = discover_knowledge_points(text)
        knowledge_points = _to_knowledge_points(kps_data, text)
    except Exception as e:
        logger.exception("Knowledge agent extraction failed: %s", e)
        _record_extraction_chunk_error(run_id, doc_id, chunk_index, str(e))
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
    _record_extraction_chunk_success(run_id, doc_id, chunk_index, len(knowledge_points))

    return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=knowledge_points)


def extract_knowledge_batch(
    user_id: str,
    chunks: list[ExtractBatchItem],
    run_id: str | None = None,
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
                    run_id=run_id,
                ),
                chunks,
            )
        )

    # 触发 Phase 2：跨块去重 + 全局重要性 + RAG 验证（异步）
    doc_id = next((c.doc_id for c in chunks if c.doc_id), None)
    if doc_id:
        all_chunk_kps = [
            {**kp.model_dump(), "chunk_id": r.chunk_id, "chunk_index": r.chunk_index}
            for r in results
            for kp in r.knowledge_points
        ]
        if all_chunk_kps:
            refinement_run_id = start_refinement_run(user_id, doc_id, all_chunk_kps, parent_run_id=run_id)
            if run_id:
                key = _extraction_progress_key(run_id)
                p = _load_progress(key)
                if p:
                    p["refinement_run_id"] = refinement_run_id
                    p["updated_at"] = _now_iso()
                    set_json(key, p, _PROGRESS_TTL_SECONDS)
            if not enqueue_job(run_phase2_and_save, user_id, doc_id, all_chunk_kps, refinement_run_id):
                # Redis/RQ 不可用时同步执行（仅 dev 环境）
                try:
                    run_phase2_and_save(user_id, doc_id, all_chunk_kps, refinement_run_id)
                except Exception as e:
                    logger.exception("[Phase2] sync fallback failed: %s", e)

    return ExtractBatchResponse(results=results)


def _close_extraction_run(run_id: str, user_id: str, doc_id: str) -> None:
    """结束 Phase 1 run，不触发 Phase 2（Phase 2 已由 extract_knowledge_batch 启动）。"""
    key = _extraction_progress_key(run_id)
    progress = _load_progress(key)
    if not progress:
        return
    failed = int(progress.get("failed", 0))
    done = int(progress.get("done", 0))
    status = "failed" if done == 0 and failed > 0 else "degraded" if failed > 0 else "completed"
    output_data = {
        "total": int(progress.get("total", 0)),
        "done": done,
        "failed": failed,
        "knowledge_count": int(progress.get("knowledge_count", 0)),
        "refinement_run_id": progress.get("refinement_run_id"),
        "errors": progress.get("errors", []),
    }
    progress.update({"status": status, "updated_at": _now_iso()})
    set_json(key, progress, _PROGRESS_TTL_SECONDS)
    db_log.finish_workflow_run(
        run_id,
        success=status != "failed",
        status=status,
        output_data=output_data,
        error_details={"errors": output_data["errors"]} if status == "failed" else None,
    )
    db_log.log_event(
        entity_type="workflow_run",
        entity_id=run_id,
        event_type=f"knowledge.extraction.{status}",
        user_id=user_id,
        after_state={"doc_id": doc_id, **output_data},
    )


def extract_knowledge_for_document(
    user_id: str,
    doc_id: str,
    text: str | None = None,
    title: str | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> ExtractBatchResponse:
    """Extract knowledge from the backend canonical document chunks.

    RAG indexing owns the canonical chunking strategy. Knowledge extraction
    reuses those persisted chunks so chunk_knowledge_points references the
    same doc_id/chunk_index coordinate system as retrieval.
    """
    rows = list_document_chunks(user_id, doc_id)
    if not rows and text and text.strip():
        index_document_text(
            user_id=user_id,
            doc_id=doc_id,
            text=text,
            title=title,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        rows = list_document_chunks(user_id, doc_id)

    canonical_chunks = [
        ExtractBatchItem(
            text=row["content"],
            chunk_id=_canonical_extract_chunk_id(user_id, doc_id, row),
            doc_id=doc_id,
            chunk_index=row["chunk_index"],
        )
        for row in rows
        if isinstance(row.get("content"), str) and row["content"].strip()
    ]
    if not canonical_chunks:
        return ExtractBatchResponse(results=[])

    run_info = start_knowledge_extraction_run(
        user_id, doc_id, canonical_chunks, title=title, source="backend_document"
    )
    run_id = run_info["run_id"]
    result = extract_knowledge_batch(user_id, canonical_chunks, run_id=run_id)
    _close_extraction_run(run_id, user_id, doc_id)
    return result


def _canonical_extract_chunk_id(user_id: str, doc_id: str, row: dict) -> str:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    return stable_hash({
        "doc_id": storage_doc_id,
        "chunk_index": row.get("chunk_index"),
        "content": row.get("content", ""),
    })
