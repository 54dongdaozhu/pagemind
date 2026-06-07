import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from app.shared.cache import (
    ANALYSIS_REPORT_CACHE_TTL_SECONDS,
    get_json,
    maintain_lock,
    redis_available,
    set_json,
    stable_hash,
    try_acquire_lock,
)
from app.shared.llm import call_deepseek
from app.modules.rag.chunking import normalize_text
from app.modules.rag.prompts import FULL_DOCUMENT_CHUNK_PROMPT, FULL_DOCUMENT_MERGE_PROMPT, SUMMARY_SYSTEM_PROMPT
from app.modules.rag.repository import get_document_cache_version, get_document_summary, list_document_chunks

logger = logging.getLogger(__name__)

_FULL_SUMMARY_STATUS_TTL = 60 * 60 * 24        # 24 小时
_FULL_SUMMARY_RESULT_TTL = ANALYSIS_REPORT_CACHE_TTL_SECONDS  # 24 小时
_FULL_SUMMARY_TIMEOUT_SECONDS = 80


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _full_summary_status_key(user_id: str, doc_id: str) -> str:
    return f"summary:full:status:user:{user_id}:doc:{doc_id}"


def _full_summary_cache_key(user_id: str, doc_id: str, version_id: str, request: str) -> str:
    payload = {
        "user_id": user_id,
        "doc_id": doc_id,
        "version_id": version_id,
        "request": request,
    }
    return f"summary:full:result:{stable_hash(payload)}"


def _save_full_summary_status(user_id: str, doc_id: str, status: dict) -> None:
    try:
        set_json(_full_summary_status_key(user_id, doc_id), status, _FULL_SUMMARY_STATUS_TTL)
    except Exception as e:
        logger.warning("[FullSummary] status save failed for doc=%s: %s", doc_id, e)


def get_full_summary_status(user_id: str, doc_id: str) -> dict:
    data = get_json(_full_summary_status_key(user_id, doc_id))
    if isinstance(data, dict):
        return data
    return {"doc_id": doc_id, "status": "unknown", "chunk_count": None, "error": None, "updated_at": None}


def _build_summary_input(text: str) -> str:
    if len(text) <= 6000:
        return text

    head = text[:2500]
    middle_start = max((len(text) // 2) - 1250, 0)
    middle = text[middle_start:middle_start + 2500]
    tail = text[-1000:]
    return f"{head}\n\n[中间片段]\n{middle}\n\n[结尾片段]\n{tail}"


def _quick_document_summary(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return "空文档。"
    return _build_summary_input(text)[:800]


def summarize_document(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return "空文档。"

    summary_input = _build_summary_input(text)
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": f"请总结以下文档：\n\n{summary_input}"},
    ]
    try:
        return call_deepseek(messages, temperature=0.2, purpose="rag.summarize").strip()
    except Exception:
        return summary_input[:500]


def _batch_chunk_rows(rows, max_chars: int = 7000):
    batches = []
    current = []
    current_len = 0
    for row in rows:
        content = row["content"]
        marker_len = len(content) + 32
        if current and current_len + marker_len > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(row)
        current_len += marker_len
    if current:
        batches.append(current)
    return batches


def _summarize_chunk_batch(batch, batch_index: int, batch_count: int) -> str:
    first_chunk = batch[0]["chunk_index"] + 1
    last_chunk = batch[-1]["chunk_index"] + 1
    text = "\n\n".join(
        f"[片段 {row['chunk_index'] + 1}]\n{row['content']}"
        for row in batch
    )
    messages = [
        {"role": "system", "content": FULL_DOCUMENT_CHUNK_PROMPT},
        {
            "role": "user",
            "content": (
                f"这是全文分批整理的第 {batch_index}/{batch_count} 批，"
                f"覆盖片段 {first_chunk}-{last_chunk}。\n\n{text}"
            ),
        },
    ]
    return call_deepseek(messages, temperature=0.15, purpose="rag.chunk_summarize").strip()


def _merge_partial_summaries(partials: list[str], request: str = "") -> str:
    partial_text = "\n\n".join(
        f"【分批整理 {idx}】\n{partial}"
        for idx, partial in enumerate(partials, start=1)
        if partial
    )
    messages = [
        {"role": "system", "content": FULL_DOCUMENT_MERGE_PROMPT},
        {
            "role": "user",
            "content": f"【用户请求】\n{request or '请总结全文'}\n\n【分批整理结果】\n{partial_text}",
        },
    ]
    return call_deepseek(messages, temperature=0.15, purpose="rag.merge_summary").strip()


def summarize_full_document(user_id: str, doc_id: str, request: str = "") -> dict:
    version_id = get_document_cache_version(user_id, doc_id)
    cache_key = _full_summary_cache_key(user_id, doc_id, version_id, request)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    lock_key = f"lock:{cache_key}"
    lock_token = try_acquire_lock(lock_key, ttl_seconds=210)
    if lock_token is None and redis_available():
        deadline = time.monotonic() + 205.0
        while time.monotonic() < deadline:
            cached = get_json(cache_key)
            if isinstance(cached, dict):
                return cached
            lock_token = try_acquire_lock(lock_key, ttl_seconds=210)
            if lock_token is not None:
                break
            time.sleep(0.1)

    if lock_token is None and redis_available():
        fallback = get_document_summary(user_id, doc_id) or ""
        logger.warning("[FullSummary] same request still running for doc=%s", doc_id)
        return {"summary": fallback, "chunk_count": 0, "batch_count": 0}

    if lock_token is None:
        return _generate_full_document_summary(user_id, doc_id, request, cache_key)

    with maintain_lock(lock_key, lock_token, 210):
        return _generate_full_document_summary(user_id, doc_id, request, cache_key)


def _generate_full_document_summary(
    user_id: str,
    doc_id: str,
    request: str,
    cache_key: str,
) -> dict:
    rows = list_document_chunks(user_id, doc_id)
    if not rows:
        summary = get_document_summary(user_id, doc_id)
        return {"summary": summary, "chunk_count": 0, "batch_count": 0}

    _save_full_summary_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "running",
        "chunk_count": len(rows),
        "error": None,
        "updated_at": _now_iso(),
    })
    try:
        deadline = time.monotonic() + _FULL_SUMMARY_TIMEOUT_SECONDS
        batches = _batch_chunk_rows(rows)
        partials: list[str | None] = [None] * len(batches)

        executor = ThreadPoolExecutor(max_workers=4)
        future_to_idx = {
            executor.submit(
                _summarize_chunk_batch,
                batch=b,
                batch_index=i,
                batch_count=len(batches),
            ): i - 1
            for i, b in enumerate(batches, 1)
        }
        remaining = max(1.0, deadline - time.monotonic())
        try:
            for fut in as_completed(future_to_idx, timeout=remaining):
                partials[future_to_idx[fut]] = fut.result()
        except FuturesTimeoutError:
            done = sum(1 for p in partials if p is not None)
            logger.warning(
                "[FullSummary] deadline reached: %d/%d batches completed for doc=%s",
                done, len(batches), doc_id,
            )
        finally:
            executor.shutdown(wait=False)

        completed = [p for p in partials if p is not None]
        if not completed:
            raise RuntimeError("全文总结超时：未能完成任何批次")

        merged = _merge_partial_summaries(completed, request=request)
        result = {"summary": merged, "chunk_count": len(rows), "batch_count": len(batches)}
        set_json(cache_key, result, _FULL_SUMMARY_RESULT_TTL)
        _save_full_summary_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "completed",
            "chunk_count": len(rows),
            "error": None,
            "updated_at": _now_iso(),
        })
        return result
    except Exception as exc:
        _save_full_summary_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "failed",
            "chunk_count": len(rows),
            "error": str(exc)[:300],
            "updated_at": _now_iso(),
        })
        fallback = get_document_summary(user_id, doc_id) or ""
        logger.warning("[FullSummary] falling back to DB summary for doc=%s: %s", doc_id, exc)
        return {"summary": fallback, "chunk_count": len(rows), "batch_count": 0}
