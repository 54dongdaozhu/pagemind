import logging
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, RLock

from app.core.config import EXTRACT_MAX_CONCURRENCY
from app.modules.agent.knowledge_agents import discover_knowledge_points
from app.modules.extraction.repository import (
    _canonical_extract_chunk_id,
    _load_from_cache,
    _persist_or_enqueue,
    _scoped_chunk_id,
    _to_knowledge_points,
    get_persisted_doc_kps,
    get_refined_doc_kps,
)
from app.modules.extraction.refinement import (
    _close_extraction_run,
    _extraction_progress_key,
    _load_progress,
    _now_iso,
    _PROGRESS_TTL_SECONDS,
    _public_progress,
    _record_extraction_chunk_error,
    _record_extraction_chunk_success,
    get_extraction_status,
    get_refinement_status,
    run_phase2_and_save,
    start_knowledge_extraction_run,
    start_refinement_run,
)
from app.modules.extraction.schemas import ExtractBatchItem, ExtractBatchResponse, ExtractResponse
from app.modules.rag.repository import list_document_chunks
from app.modules.rag.service import index_document_text
from app.shared import db_log
from app.shared.cache import set_json
from app.shared.job_queue import enqueue_job

logger = logging.getLogger(__name__)

_extract_cache: dict = {}
_extract_cache_lock = RLock()
_llm_slots = BoundedSemaphore(EXTRACT_MAX_CONCURRENCY)
_extraction_executor = ThreadPoolExecutor(max_workers=EXTRACT_MAX_CONCURRENCY)


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
            _persist_or_enqueue(user_id, chunk_id, cache_key, cached_points, doc_id, chunk_index)
            _record_extraction_chunk_success(run_id, doc_id, chunk_index, len(cached_points))
            return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=cached_points)

    cached = _load_from_cache(cache_key, text)
    if cached is not None:
        with _extract_cache_lock:
            _extract_cache[cache_key] = cached
        _persist_or_enqueue(user_id, chunk_id, cache_key, cached, doc_id, chunk_index)
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
    _persist_or_enqueue(user_id, chunk_id, cache_key, knowledge_points, doc_id, chunk_index, save_cache=True)
    _record_extraction_chunk_success(run_id, doc_id, chunk_index, len(knowledge_points))

    return ExtractResponse(chunk_id=chunk_id, chunk_index=chunk_index, knowledge_points=knowledge_points)


def extract_knowledge_batch(
    user_id: str,
    chunks: list[ExtractBatchItem],
    run_id: str | None = None,
) -> ExtractBatchResponse:
    if not chunks:
        return ExtractBatchResponse(results=[])

    results = list(
        _extraction_executor.map(
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
                try:
                    run_phase2_and_save(user_id, doc_id, all_chunk_kps, refinement_run_id)
                except Exception as e:
                    logger.exception("[Phase2] sync fallback failed: %s", e)

    return ExtractBatchResponse(results=results)


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


def extract_knowledge_for_document(
    user_id: str,
    doc_id: str,
    text: str | None = None,
    title: str | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> ExtractBatchResponse:
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
