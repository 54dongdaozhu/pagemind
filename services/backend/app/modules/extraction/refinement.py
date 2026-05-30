import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import RagChunk, WorkflowRun, get_db
from app.modules.agent.knowledge_agents import refine_document_knowledge
from app.modules.extraction.repository import _persist_phase2_results, save_refined_doc_kps
from app.modules.rag.repository import scoped_doc_id
from app.shared import db_log
from app.shared.cache import get_json, set_json
from app.shared.job_queue import enqueue_job

logger = logging.getLogger(__name__)

_PROGRESS_TTL_SECONDS = 60 * 60 * 24
_RAG_READY_WAIT_SECONDS = 8
_RAG_READY_POLL_SECONDS = 0.5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extraction_progress_key(run_id: str) -> str:
    return f"progress:knowledge_extraction:{run_id}"


def _refinement_progress_key(run_id: str) -> str:
    return f"progress:knowledge_refinement:{run_id}"


def _doc_refinement_progress_key(user_id: str, doc_id: str) -> str:
    return f"progress:knowledge_refinement:user:{user_id}:doc:{doc_id}"


def get_refinement_status(user_id: str, doc_id: str) -> dict | None:
    data = get_json(_doc_refinement_progress_key(user_id, doc_id))
    return data if isinstance(data, dict) else None


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
    chunks: list,
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


def _close_extraction_run(run_id: str, user_id: str, doc_id: str) -> None:
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


def run_phase2_and_save(
    user_id: str,
    doc_id: str,
    all_chunk_kps: list[dict],
    run_id: str | None = None,
) -> None:
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
        try:
            _persist_phase2_results(user_id, doc_id, refined)
        except Exception as e:
            logger.exception("[Phase2] DB persist failed (Redis result is intact): %s", e)
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
