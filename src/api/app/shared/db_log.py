"""
Non-blocking database logging helpers.

Fire-and-forget writes submit to a shared thread pool and swallow all
exceptions so callers are never blocked or affected by log failures.

create_workflow_run / create_workflow_step return IDs immediately and enqueue
the insert in the same ordered worker as follow-up log writes. This keeps
workflow IDs available to callers without putting database commits in the
request's critical path.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete

from app.core.database import (
    EmbeddingRecord,
    EventLog,
    LLMCallLog,
    QARecord,
    QAReference,
    ReviewRecord,
    ToolCallLog,
    WorkflowRun,
    WorkflowStep,
    get_db,
)

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db_log")
LOG_STREAM_NAME = "stream:db_log"
LOG_CONSUMER_GROUP = "db_log_writers"
LOG_MAX_LEN = 100_000

# Per-request context — set at request boundary, read by all write helpers.
# Callers should use var.set(value) / var.reset(token) to avoid stale values.
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_step_id: ContextVar[str | None] = ContextVar("current_step_id", default=None)
current_qa_id: ContextVar[str | None] = ContextVar("current_qa_id", default=None)


_STREAM_WRITE_MAP = {
    "_write_llm_call": "_write_llm_call",
    "_write_tool_call": "_write_tool_call",
    "_write_event": "_write_event",
    "_write_workflow_run": "_write_workflow_run",
    "_write_finish_run": "_write_finish_run",
    "_write_workflow_step": "_write_workflow_step",
    "_write_finish_step": "_write_finish_step",
    "_write_qa": "_write_qa",
    "_write_embedding_records": "_write_embedding_records",
    "_write_review_records": "_write_review_records",
}


def _submit(fn, **kwargs) -> None:
    if _enqueue_stream(fn, kwargs):
        return
    _pool.submit(_safe_run, fn, **kwargs)


def _safe_run(fn, **kwargs):
    try:
        fn(**kwargs)
    except Exception:
        logger.exception("[db_log] background write failed: %s", fn.__name__)


def _json_default(value):
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_object_hook(value):
    marker = value.get("__datetime__") if isinstance(value, dict) else None
    if marker:
        return datetime.fromisoformat(marker)
    return value


def _enqueue_stream(fn, kwargs: dict) -> bool:
    kind = _STREAM_WRITE_MAP.get(fn.__name__)
    if not kind:
        return False
    try:
        from app.shared.cache import get_redis

        get_redis().xadd(
            LOG_STREAM_NAME,
            {"kind": kind, "payload": json_dumps(kwargs)},
            maxlen=LOG_MAX_LEN,
            approximate=True,
        )
        return True
    except Exception as exc:
        logger.debug("[db_log] Redis stream enqueue failed, falling back to thread pool: %s", exc)
        return False


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def json_loads(value: str) -> Any:
    import json

    return json.loads(value, object_hook=_json_object_hook)


def process_stream_entry(kind: str, payload: dict) -> None:
    fn = globals().get(kind)
    if fn is None or kind not in _STREAM_WRITE_MAP.values():
        raise ValueError(f"Unknown db_log stream entry kind: {kind}")
    fn(**payload)


# ── LLM call log ──────────────────────────────────────────────────────────────

def log_llm_call(
    *,
    provider: str,
    model: str,
    purpose: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    success: bool = True,
    error_details: Any = None,
    user_id: str | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    qa_id: str | None = None,
) -> None:
    _submit(
        _write_llm_call,
        provider=provider,
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        success=success,
        error_details=error_details,
        user_id=user_id if user_id is not None else current_user_id.get(),
        run_id=run_id if run_id is not None else current_run_id.get(),
        step_id=step_id if step_id is not None else current_step_id.get(),
        qa_id=qa_id if qa_id is not None else current_qa_id.get(),
    )


def _write_llm_call(
    *, provider, model, purpose, prompt_tokens, completion_tokens, total_tokens,
    cost_usd, latency_ms, success, error_details, user_id, run_id, step_id, qa_id,
):
    with get_db() as db:
        db.add(LLMCallLog(
            call_id=uuid.uuid4().hex,
            run_id=run_id,
            step_id=step_id,
            qa_id=qa_id,
            user_id=user_id,
            provider=provider,
            model=model,
            purpose=purpose,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error_details=error_details,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()


# ── Tool call log ──────────────────────────────────────────────────────────────

def log_tool_call(
    *,
    tool_name: str,
    args: Any = None,
    result_summary: Any = None,
    latency_ms: int | None = None,
    success: bool = True,
    error_details: Any = None,
    user_id: str | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    qa_id: str | None = None,
) -> None:
    _submit(
        _write_tool_call,
        tool_name=tool_name,
        args=args,
        result_summary=result_summary,
        latency_ms=latency_ms,
        success=success,
        error_details=error_details,
        user_id=user_id if user_id is not None else current_user_id.get(),
        run_id=run_id if run_id is not None else current_run_id.get(),
        step_id=step_id if step_id is not None else current_step_id.get(),
        qa_id=qa_id if qa_id is not None else current_qa_id.get(),
    )


def _write_tool_call(
    *, tool_name, args, result_summary, latency_ms, success, error_details,
    user_id, run_id, step_id, qa_id,
):
    with get_db() as db:
        db.add(ToolCallLog(
            call_id=uuid.uuid4().hex,
            run_id=run_id,
            step_id=step_id,
            qa_id=qa_id,
            user_id=user_id,
            tool_name=tool_name,
            args=args,
            result=result_summary,
            latency_ms=latency_ms,
            success=success,
            error_details=error_details,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()


# ── Event log ─────────────────────────────────────────────────────────────────

def log_event(
    *,
    entity_type: str,
    entity_id: str,
    event_type: str,
    user_id: str | None = None,
    before_state: Any = None,
    after_state: Any = None,
    meta: Any = None,
) -> None:
    _submit(
        _write_event,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        user_id=user_id if user_id is not None else current_user_id.get(),
        before_state=before_state,
        after_state=after_state,
        meta=meta,
    )


def _write_event(
    *, entity_type, entity_id, event_type, user_id, before_state, after_state, meta,
):
    with get_db() as db:
        db.add(EventLog(
            event_id=uuid.uuid4().hex,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            before_state=before_state,
            after_state=after_state,
            meta=meta,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()


# ── WorkflowRun ────────────────────────────────────────────────────────────────

def create_workflow_run(
    *,
    workflow_type: str,
    user_id: str | None = None,
    doc_id: str | None = None,
    trigger_source: str = "api",
    input_data: Any = None,
) -> str:
    """Returns a WorkflowRun ID immediately and enqueues the insert."""
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    _submit(
        _write_workflow_run,
        run_id=run_id,
        user_id=user_id if user_id is not None else current_user_id.get(),
        doc_id=doc_id,
        workflow_type=workflow_type,
        trigger_source=trigger_source,
        input_data=input_data,
        now=now,
    )
    return run_id


def _write_workflow_run(
    *, run_id, user_id, doc_id, workflow_type, trigger_source, input_data, now,
):
    try:
        with get_db() as db:
            db.add(WorkflowRun(
                run_id=run_id,
                user_id=user_id,
                doc_id=doc_id,
                workflow_type=workflow_type,
                trigger_source=trigger_source,
                status="running",
                input_data=input_data,
                started_at=now,
                created_at=now,
                updated_at=now,
            ))
            db.commit()
    except Exception:
        logger.exception("[db_log] create_workflow_run failed")


def finish_workflow_run(
    run_id: str,
    *,
    success: bool = True,
    status: str | None = None,
    output_data: Any = None,
    error_details: Any = None,
) -> None:
    _submit(
        _write_finish_run,
        run_id=run_id,
        success=success,
        status=status,
        output_data=output_data,
        error_details=error_details,
    )


def _write_finish_run(*, run_id, success, output_data, error_details, status=None):
    now = datetime.now(timezone.utc)
    with get_db() as db:
        run = db.get(WorkflowRun, run_id)
        if run is None:
            return
        run.status = status or ("completed" if success else "failed")
        run.output_data = output_data
        run.error_details = error_details
        run.finished_at = now
        run.updated_at = now
        db.commit()


# ── WorkflowStep ───────────────────────────────────────────────────────────────

def create_workflow_step(
    *,
    run_id: str,
    step_name: str,
    step_order: int,
    input_data: Any = None,
) -> str:
    """Returns a WorkflowStep ID immediately and enqueues the insert."""
    step_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    _submit(
        _write_workflow_step,
        step_id=step_id,
        run_id=run_id,
        step_name=step_name,
        step_order=step_order,
        input_data=input_data,
        now=now,
    )
    return step_id


def _write_workflow_step(*, step_id, run_id, step_name, step_order, input_data, now):
    try:
        with get_db() as db:
            db.add(WorkflowStep(
                step_id=step_id,
                run_id=run_id,
                step_name=step_name,
                step_order=step_order,
                status="running",
                input_data=input_data,
                started_at=now,
                created_at=now,
            ))
            db.commit()
    except Exception:
        logger.exception("[db_log] create_workflow_step failed")


def finish_workflow_step(
    step_id: str,
    *,
    success: bool = True,
    status: str | None = None,
    output_data: Any = None,
    error_details: Any = None,
) -> None:
    _submit(
        _write_finish_step,
        step_id=step_id,
        success=success,
        status=status,
        output_data=output_data,
        error_details=error_details,
    )


def _write_finish_step(*, step_id, success, output_data, error_details, status=None):
    now = datetime.now(timezone.utc)
    with get_db() as db:
        step = db.get(WorkflowStep, step_id)
        if step is None:
            return
        step.status = status or ("completed" if success else "failed")
        step.output_data = output_data
        step.error_details = error_details
        step.finished_at = now
        db.commit()


# ── QA log ────────────────────────────────────────────────────────────────────

def log_qa(
    *,
    user_id: str,
    doc_id: str | None = None,
    question: str,
    answer: str,
    intent: str | None = None,
    agent: str | None = None,
    tools_used: list | None = None,
    latency_ms: int | None = None,
    sources: list | None = None,
) -> None:
    """Fire-and-forget. Writes QARecord + QAReference rows."""
    _submit(
        _write_qa,
        user_id=user_id,
        doc_id=doc_id,
        question=question,
        answer=answer,
        intent=intent,
        agent=agent,
        tools_used=tools_used,
        latency_ms=latency_ms,
        sources=[_source_to_dict(s) for s in (sources or [])],
    )


def _source_to_dict(source) -> dict:
    if isinstance(source, dict):
        return source
    return {
        "chunk_index": getattr(source, "chunk_index", None),
        "score": getattr(source, "score", None),
        "retrieval_method": getattr(source, "retrieval_method", "semantic"),
    }


def _write_qa(
    *, user_id, doc_id, question, answer, intent, agent, tools_used, latency_ms, sources,
):
    qa_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with get_db() as db:
        db.add(QARecord(
            qa_id=qa_id,
            user_id=user_id,
            doc_id=doc_id,
            question=question,
            answer=answer,
            intent=intent,
            agent=agent,
            tools_used=tools_used,
            latency_ms=latency_ms,
            created_at=now,
        ))
        for s in sources:
            ci = s.get("chunk_index")
            if doc_id is not None and ci is not None:
                db.add(QAReference(
                    qa_id=qa_id,
                    doc_id=doc_id,
                    chunk_index=ci,
                    score=s.get("score"),
                    retrieval_method=s.get("retrieval_method", "semantic"),
                    created_at=now,
                ))
        db.commit()


# ── Embedding records ──────────────────────────────────────────────────────────

def log_embedding_records(
    *,
    storage_doc_id: str,
    model: str,
    chunk_count: int,
) -> None:
    """Fire-and-forget. Replaces all embedding records for this doc+model."""
    _submit(
        _write_embedding_records,
        storage_doc_id=storage_doc_id,
        model=model,
        chunk_count=chunk_count,
    )


def _write_embedding_records(*, storage_doc_id, model, chunk_count):
    now = datetime.now(timezone.utc)
    with get_db() as db:
        db.execute(
            delete(EmbeddingRecord).where(
                EmbeddingRecord.doc_id == storage_doc_id,
                EmbeddingRecord.model == model,
            )
        )
        db.add_all([
            EmbeddingRecord(
                embedding_id=uuid.uuid4().hex,
                doc_id=storage_doc_id,
                chunk_index=i,
                model=model,
                vector_store="chroma",
                vector_id=f"{storage_doc_id}:{i}",
                is_active=True,
                created_at=now,
            )
            for i in range(chunk_count)
        ])
        db.commit()


# ── Review records ────────────────────────────────────────────────────────────

def log_review_records(
    *,
    user_id: str,
    doc_id: str | None = None,
    review_items: list | None = None,
    review_type: str = "agent_schedule",
) -> None:
    _submit(
        _write_review_records,
        user_id=user_id,
        doc_id=doc_id,
        review_items=review_items or [],
        review_type=review_type,
    )


def _write_review_records(*, user_id, doc_id, review_items, review_type):
    now = datetime.now(timezone.utc)
    rows = []
    for item in review_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("kp_text") or "").strip()
        if not text:
            continue
        rows.append(ReviewRecord(
            review_id=uuid.uuid4().hex,
            user_id=user_id,
            doc_id=doc_id,
            kp_text=text,
            review_type=review_type,
            result=item.get("priority"),
            note=item.get("reason") or item.get("next_action"),
            reviewed_at=now,
            created_at=now,
        ))
    if not rows:
        return
    with get_db() as db:
        db.add_all(rows)
        db.commit()
