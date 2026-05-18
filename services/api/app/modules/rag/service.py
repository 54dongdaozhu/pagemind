import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from app.shared.schemas import RagSource
from app.shared.llm import call_deepseek
from app.core.config import EMBEDDING_MODEL
from app.shared.cache import ANALYSIS_REPORT_CACHE_TTL_SECONDS, RAG_QUERY_CACHE_TTL_SECONDS, get_json, set_json, stable_hash
from app.shared import db_log
from app.shared.job_queue import enqueue_job
from app.modules.rag.chunking import normalize_text, split_text_for_rag
from app.modules.rag.embeddings import embed_texts
from app.modules.rag.repository import (
    get_document_summary,
    list_document_chunks,
    save_indexed_document,
    scoped_doc_id,
)
from app.modules.rag.vector_store import index_chunks_in_chroma, retrieve_by_chroma


logger = logging.getLogger(__name__)
_rag_enrichment_executor = ThreadPoolExecutor(max_workers=2)

_RAG_ENRICHMENT_STATUS_TTL = 60 * 60 * 24 * 3  # 3 天
_FULL_SUMMARY_STATUS_TTL = 60 * 60 * 24        # 24 小时
_FULL_SUMMARY_RESULT_TTL = ANALYSIS_REPORT_CACHE_TTL_SECONDS  # 24 小时
# 全文总结单次执行预算：每批最多 60s（LLM timeout），超出此时间后不再启动新批次
_FULL_SUMMARY_TIMEOUT_SECONDS = 80


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rag_enrichment_status_key(user_id: str, doc_id: str) -> str:
    return f"rag:enrichment:user:{user_id}:doc:{doc_id}"


def _save_enrichment_status(user_id: str, doc_id: str, status: dict) -> None:
    try:
        set_json(_rag_enrichment_status_key(user_id, doc_id), status, _RAG_ENRICHMENT_STATUS_TTL)
    except Exception as e:
        logger.warning("[RAGEnrichment] status save failed for doc=%s: %s", doc_id, e)


def get_rag_enrichment_status(user_id: str, doc_id: str) -> dict:
    data = get_json(_rag_enrichment_status_key(user_id, doc_id))
    if isinstance(data, dict):
        return data
    return {"doc_id": doc_id, "status": "unknown", "chunk_count": None, "error": None, "updated_at": None}


def _full_summary_status_key(user_id: str, doc_id: str) -> str:
    return f"summary:full:status:user:{user_id}:doc:{doc_id}"


def _full_summary_cache_key(user_id: str, doc_id: str, request: str) -> str:
    return f"summary:full:result:{stable_hash({'user_id': user_id, 'doc_id': doc_id, 'request': request})}"


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


def _doc_type_status_key(user_id: str, doc_id: str) -> str:
    return f"doc_type:status:user:{user_id}:doc:{doc_id}"


def _save_doc_type_status(user_id: str, doc_id: str, status: dict) -> None:
    try:
        set_json(_doc_type_status_key(user_id, doc_id), status, _RAG_ENRICHMENT_STATUS_TTL)
    except Exception as e:
        logger.warning("[DocType] status save failed for doc=%s: %s", doc_id, e)


def get_doc_type_status(user_id: str, doc_id: str) -> dict:
    data = get_json(_doc_type_status_key(user_id, doc_id))
    if isinstance(data, dict):
        return data
    return {"doc_id": doc_id, "status": "unknown", "doc_type": None, "confidence": None, "error": None, "updated_at": None}


def _classify_document_type_job(
    user_id: str,
    doc_id: str,
    storage_doc_id: str,
    title: str,
    chunks: list[str],
) -> None:
    """RQ job：识别文档类型并写入 DB 和 Redis。"""
    from app.core.database import RagDocument, get_db
    from app.modules.agent.doc_type_agents import classify_document_type

    _save_doc_type_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "running",
        "doc_type": None,
        "confidence": None,
        "error": None,
        "updated_at": _now_iso(),
    })
    try:
        result = classify_document_type(title, chunks)
        doc_type = result.get("doc_type", "其他")
        confidence = result.get("confidence", 0.0)

        with get_db() as db:
            doc = db.get(RagDocument, storage_doc_id)
            if doc:
                doc.doc_type = doc_type
                doc.doc_type_confidence = confidence
                doc.updated_at = datetime.now(timezone.utc)
                db.commit()

        _save_doc_type_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "completed",
            "doc_type": doc_type,
            "confidence": confidence,
            "error": None,
            "updated_at": _now_iso(),
        })
        logger.info("[DocType] doc=%s classified as %s (confidence=%.2f)", doc_id, doc_type, confidence)
    except Exception as e:
        logger.exception("[DocType] failed for doc=%s: %s", doc_id, e)
        _save_doc_type_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "failed",
            "doc_type": None,
            "confidence": None,
            "error": str(e),
            "updated_at": _now_iso(),
        })
        raise


RAG_SYSTEM_PROMPT = """你是一个严谨的文档问答助手。请只依据给定的文档片段回答用户问题。

回答要求：
1. 先直接回答问题，再补充必要解释
2. 如果文档摘要和片段不足以回答，请明确说"文档中没有足够信息"
3. 不要编造文档外的事实
4. 用简洁中文回答，必要时分点说明
5. 最多 300 字"""


SUMMARY_SYSTEM_PROMPT = """你是一个文档整理助手。请为文档 RAG 问答生成文档摘要。

要求：
1. 概括主题、核心概念、关键结论
2. 保留重要术语
3. 不编造原文没有的信息
4. 150-300 字"""


FULL_DOCUMENT_CHUNK_PROMPT = """你是一个严谨的学习资料整理助手。请只依据当前文档片段做阶段性整理。

要求：
1. 覆盖本批片段中的主题、关键概念、重要结论和结构线索
2. 保留原文中的重要术语
3. 不编造片段外信息
4. 用中文分点输出，控制在 300-500 字"""


FULL_DOCUMENT_MERGE_PROMPT = """你是一个严谨的学习资料整理助手。请把分批整理结果合并成面向学习的全文总结。

要求：
1. 尽量覆盖全文，不只挑选和用户问题相关的片段
2. 按主题或章节组织，体现整体脉络
3. 保留关键概念、方法、结论、例子或公式
4. 不编造文档外信息
5. 中文输出，结构清晰"""


def index_document_text(
    user_id: str,
    doc_id: str,
    text: str,
    title: str | None = None,
    chunks: list[str] | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    images: list[dict] | None = None,
) -> dict:
    # 幂等性：已完成的文档跳过重新索引，避免前端重传时 status 倒退回 pending
    existing = get_rag_enrichment_status(user_id, doc_id)
    if existing.get("status") == "completed":
        return {"indexed_count": existing.get("chunk_count") or 0, "enrichment_status": "completed"}

    canonical_chunks = _normalize_input_chunks(chunks)
    if canonical_chunks:
        normalized_text = normalize_text(text or "\n\n".join(canonical_chunks))
    else:
        normalized_text = normalize_text(text)
        canonical_chunks = split_text_for_rag(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    save_indexed_document(
        user_id=user_id,
        doc_id=doc_id,
        chunks=canonical_chunks,
        embeddings=None,
        summary=_quick_document_summary(normalized_text),
        title=title,
    )

    _save_enrichment_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "pending",
        "chunk_count": len(canonical_chunks),
        "error": None,
        "updated_at": _now_iso(),
    })

    enqueued = enqueue_job(
        _enrich_indexed_document_job,
        user_id=user_id,
        doc_id=doc_id,
        storage_doc_id=storage_doc_id,
        chunks=canonical_chunks,
        normalized_text=normalized_text,
        title=title,
    )
    if not enqueued:
        # RQ 不可用时降级到 ThreadPool（保持原有行为）
        _rag_enrichment_executor.submit(
            _enrich_indexed_document,
            user_id=user_id,
            doc_id=doc_id,
            storage_doc_id=storage_doc_id,
            chunks=canonical_chunks,
            normalized_text=normalized_text,
            title=title,
        )

    if images:
        enqueued = enqueue_job(_analyze_images_job, user_id=user_id, doc_id=doc_id, images=images)
        if not enqueued:
            _rag_enrichment_executor.submit(_analyze_images_job, user_id=user_id, doc_id=doc_id, images=images)

    _save_doc_type_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "pending",
        "doc_type": None,
        "confidence": None,
        "error": None,
        "updated_at": _now_iso(),
    })
    enqueued = enqueue_job(
        _classify_document_type_job,
        user_id=user_id,
        doc_id=doc_id,
        storage_doc_id=storage_doc_id,
        title=title or "",
        chunks=canonical_chunks[:10],
    )
    if not enqueued:
        _rag_enrichment_executor.submit(
            _classify_document_type_job,
            user_id=user_id,
            doc_id=doc_id,
            storage_doc_id=storage_doc_id,
            title=title or "",
            chunks=canonical_chunks[:10],
        )

    return {"indexed_count": len(canonical_chunks), "enrichment_status": "pending"}


def _normalize_input_chunks(chunks: list[str] | None) -> list[str]:
    if not chunks:
        return []
    return [chunk.strip() for chunk in chunks if isinstance(chunk, str) and chunk.strip()]


_VISION_PROMPT = "请用中文简洁描述这张图片的内容，用于学习文档的图片注解，不超过100字。"
_IMAGE_PER_DOC_LIMIT = 20
_IMAGE_TIMEOUT_SECONDS = 60


def _analyze_images_job(user_id: str, doc_id: str, images: list[dict]) -> None:
    """RQ job: run vision LLM on each image, cache result, persist to document_images."""
    import base64
    from datetime import datetime, timezone

    from app.core.database import DocumentImage, get_db
    from app.modules.assets.service import ALLOWED_IMAGE_TYPES, IMAGE_ASSET_DIR
    from app.shared.cache import IMAGE_VISION_CACHE_TTL_SECONDS, get_json, set_json
    from app.shared.llm import call_vision_llm

    now = datetime.now(timezone.utc)
    limited = images[:_IMAGE_PER_DOC_LIMIT]
    records = []

    for img in limited:
        asset_id = img.get("asset_id", "")
        if not asset_id:
            continue

        cache_key = f"img:vision:asset:{asset_id}"
        cached = get_json(cache_key)
        if cached is not None:
            description = cached.get("description")
        else:
            description = None
            for content_type, ext in ALLOWED_IMAGE_TYPES.items():
                if content_type == "image/svg+xml":
                    continue
                path = IMAGE_ASSET_DIR / f"{asset_id}{ext}"
                if not path.is_file():
                    continue
                try:
                    image_bytes = path.read_bytes()
                    if len(image_bytes) > 8 * 1024 * 1024:
                        break
                    b64 = base64.b64encode(image_bytes).decode("utf-8")
                    description = call_vision_llm(b64, content_type, _VISION_PROMPT, purpose="image_vision")
                except Exception as exc:
                    logger.warning("[ImageVision] asset=%s failed: %s", asset_id, exc)
                break
            if description:
                set_json(cache_key, {"description": description}, IMAGE_VISION_CACHE_TTL_SECONDS)

        records.append({
            "doc_id": doc_id,
            "user_id": user_id,
            "asset_id": asset_id,
            "page_num": img.get("page_num"),
            "alt_text": img.get("alt_text") or "",
            "vision_description": description,
            "created_at": now,
        })

    if not records:
        return

    import sqlalchemy as _sa

    with get_db() as db:
        for rec in records:
            existing = db.execute(
                _sa.select(DocumentImage).where(
                    DocumentImage.doc_id == rec["doc_id"],
                    DocumentImage.user_id == rec["user_id"],
                    DocumentImage.asset_id == rec["asset_id"],
                )
            ).scalar_one_or_none()
            if existing:
                if rec["vision_description"]:
                    existing.vision_description = rec["vision_description"]
            else:
                db.add(DocumentImage(**rec))
        db.commit()
    logger.info("[ImageVision] persisted %d image records for doc=%s", len(records), doc_id)


def _enrich_indexed_document_job(
    user_id: str,
    doc_id: str,
    storage_doc_id: str,
    chunks: list[str],
    normalized_text: str,
    title: str | None,
) -> None:
    """RQ Job 入口：更新状态后执行富化，异常时标记 failed 并 re-raise（触发 RQ 重试）。"""
    _save_enrichment_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "running",
        "chunk_count": len(chunks),
        "error": None,
        "updated_at": _now_iso(),
    })
    try:
        _enrich_indexed_document(user_id, doc_id, storage_doc_id, chunks, normalized_text, title)
        _save_enrichment_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "completed",
            "chunk_count": len(chunks),
            "error": None,
            "updated_at": _now_iso(),
        })
        logger.info("[RAGEnrichment] completed for doc=%s chunks=%s", doc_id, len(chunks))
    except Exception as exc:
        _save_enrichment_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "failed",
            "chunk_count": len(chunks),
            "error": str(exc)[:300],
            "updated_at": _now_iso(),
        })
        raise  # 让 RQ 捕获并触发重试


def _enrich_indexed_document(
    user_id: str,
    doc_id: str,
    storage_doc_id: str,
    chunks: list[str],
    normalized_text: str,
    title: str | None,
) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        summary_future = executor.submit(summarize_document, normalized_text)
        embeddings_future = executor.submit(embed_texts, chunks)
        summary = summary_future.result()
        embeddings = embeddings_future.result()
    index_chunks_in_chroma(storage_doc_id, chunks, embeddings)
    save_indexed_document(
        user_id=user_id,
        doc_id=doc_id,
        chunks=chunks,
        embeddings=embeddings,
        summary=summary,
        title=title,
    )
    if embeddings:
        db_log.log_embedding_records(
            storage_doc_id=storage_doc_id,
            model=EMBEDDING_MODEL,
            chunk_count=len(chunks),
        )


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


def retrieve_relevant_chunks(user_id: str, doc_id: str, question: str, top_k: int = 3) -> list[RagSource]:
    top_k = max(1, min(top_k, 8))
    cache_key = f"cache:rag_query:u:{user_id}:d:{doc_id}:{stable_hash({'question': question, 'top_k': top_k})}"
    cached = get_json(cache_key)
    if cached is not None:
        return [RagSource(**item) for item in cached]

    storage_doc_id = scoped_doc_id(user_id, doc_id)
    chroma_results = retrieve_by_chroma(storage_doc_id, question, top_k)
    if chroma_results:
        set_json(cache_key, [_source_to_dict(item) for item in chroma_results], RAG_QUERY_CACHE_TTL_SECONDS)
        return chroma_results

    rows = list_document_chunks(user_id, doc_id)
    sources = _retrieve_by_keyword(rows, question, top_k)
    set_json(cache_key, [_source_to_dict(item) for item in sources], RAG_QUERY_CACHE_TTL_SECONDS)
    return sources


def summarize_full_document(user_id: str, doc_id: str, request: str = "") -> dict:
    cache_key = _full_summary_cache_key(user_id, doc_id, request)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

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
        # 降级：返回 DB 中已有的快速摘要，而不是向上抛 500
        fallback = get_document_summary(user_id, doc_id) or ""
        logger.warning("[FullSummary] falling back to DB summary for doc=%s: %s", doc_id, exc)
        return {"summary": fallback, "chunk_count": len(rows), "batch_count": 0}


def answer_with_rag(user_id: str, doc_id: str, question: str, top_k: int = 3) -> tuple[str, list[RagSource]]:
    sources = retrieve_relevant_chunks(user_id=user_id, doc_id=doc_id, question=question, top_k=top_k)
    summary = get_document_summary(user_id, doc_id)
    if not sources and not summary:
        return "当前文档中没有检索到足够相关的内容。", []

    context = "\n\n".join(
        f"[片段 {source.chunk_index + 1}]\n{source.content}"
        for source in sources
    ) if sources else "未检索到高相关片段，请优先依据文档摘要回答。"
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"【文档摘要】\n{summary or '无'}\n\n【检索片段】\n{context}\n\n【用户问题】\n{question}",
        },
    ]
    reply = call_deepseek(messages, temperature=0.2, purpose="rag.qa")
    if not reply.strip():
        reply = "抱歉，暂时无法基于文档生成回答，请换一种提问方式。"
    return reply, sources


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


def _retrieve_by_keyword(rows, question: str, top_k: int) -> list[RagSource]:
    question_lower = question.strip().lower()
    if not question_lower:
        return []
    terms = _extract_terms(question_lower)

    scored = []
    for row in rows:
        score = _score_chunk(question_lower, row["content"], terms)
        if score > 0:
            scored.append(
                RagSource(
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    score=round(score, 3),
                    retrieval_method="keyword",
                )
            )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def _score_chunk(question: str, content: str, terms: list[str] | None = None) -> float:
    content_lower = content.lower()
    if not question:
        return 0.0

    score = 0.0
    if question in content_lower:
        score += 10.0

    if terms is None:
        terms = _extract_terms(question)
    for term in terms:
        count = content_lower.count(term)
        if count:
            score += min(count, 5) * _term_weight(term)

    return score


def _build_summary_input(text: str) -> str:
    if len(text) <= 6000:
        return text

    head = text[:2500]
    middle_start = max((len(text) // 2) - 1250, 0)
    middle = text[middle_start:middle_start + 2500]
    tail = text[-1000:]
    return f"{head}\n\n[中间片段]\n{middle}\n\n[结尾片段]\n{tail}"


def _extract_terms(text: str) -> list[str]:
    text = text.lower()
    terms = set(re.findall(r"[a-z0-9_]{2,}", text))
    chinese_parts = re.findall(r"[\u4e00-\u9fff]+", text)
    for part in chinese_parts:
        if len(part) >= 2:
            terms.add(part)
        for size in (2, 3, 4):
            for idx in range(0, max(len(part) - size + 1, 0)):
                terms.add(part[idx:idx + size])
    return sorted(terms, key=len, reverse=True)


def _source_to_dict(source: RagSource) -> dict:
    if hasattr(source, "model_dump"):
        return source.model_dump()
    return {
        "chunk_index": source.chunk_index,
        "content": source.content,
        "score": source.score,
        "retrieval_method": source.retrieval_method,
    }


def _term_weight(term: str) -> float:
    if re.fullmatch(r"[\u4e00-\u9fff]+", term):
        return 1.0 + min(len(term), 6) * 0.25
    return 1.5 + min(len(term), 10) * 0.1
