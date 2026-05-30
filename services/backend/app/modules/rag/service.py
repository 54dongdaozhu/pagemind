import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.modules.rag.schemas import RagSource
from app.shared.llm import call_deepseek
from app.core.config import EMBEDDING_MODEL
from app.shared.cache import RAG_QUERY_CACHE_TTL_SECONDS, get_json, set_json, stable_hash
from app.shared import db_log
from app.shared.job_queue import enqueue_job
from app.modules.rag.chunking import normalize_text, split_text_for_rag
from app.modules.rag.embeddings import embed_texts
from app.modules.rag.repository import (
    get_document_summary,
    list_document_chunks,
    save_indexed_document,
    scoped_doc_id,
    update_document_render_snapshot,
)
from app.modules.rag.vector_store import index_chunks_in_chroma, retrieve_by_chroma
from app.modules.rag.prompts import RAG_SYSTEM_PROMPT
from app.modules.rag.summarization import _quick_document_summary, summarize_document
from app.modules.rag.doc_type import _classify_document_type_job, _save_doc_type_status


logger = logging.getLogger(__name__)
_rag_enrichment_executor = ThreadPoolExecutor(max_workers=2)

_RAG_ENRICHMENT_STATUS_TTL = 60 * 60 * 24 * 3  # 3 天


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


def index_document_text(
    user_id: str,
    doc_id: str,
    text: str,
    title: str | None = None,
    chunks: list[str] | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    images: list[dict] | None = None,
    render_html: str | None = None,
    render_outline: list[dict] | None = None,
) -> dict:
    canonical_chunks = _normalize_input_chunks(chunks)
    if canonical_chunks:
        normalized_text = normalize_text(text or "\n\n".join(canonical_chunks))
    else:
        normalized_text = normalize_text(text)
        canonical_chunks = split_text_for_rag(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    # 幂等性：已完成的文档跳过重新索引，避免前端重传时 status 倒退回 pending；
    # 但仍写入/刷新渲染快照，保证老文档再次打开后也能被持久恢复。
    existing = get_rag_enrichment_status(user_id, doc_id)
    if existing.get("status") == "completed":
        if render_html is not None:
            update_document_render_snapshot(
                user_id=user_id,
                doc_id=doc_id,
                render_html=render_html,
                render_outline=render_outline,
                title=title,
            )
        return {"indexed_count": existing.get("chunk_count") or len(canonical_chunks), "enrichment_status": "completed"}

    storage_doc_id = scoped_doc_id(user_id, doc_id)
    save_indexed_document(
        user_id=user_id,
        doc_id=doc_id,
        chunks=canonical_chunks,
        embeddings=None,
        summary=_quick_document_summary(normalized_text),
        title=title,
        render_html=render_html,
        render_outline=render_outline,
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


def _extract_terms(text: str) -> list[str]:
    text = text.lower()
    terms = set(re.findall(r"[a-z0-9_]{2,}", text))
    chinese_parts = re.findall(r"[一-鿿]+", text)
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
    if re.fullmatch(r"[一-鿿]+", term):
        return 1.0 + min(len(term), 6) * 0.25
    return 1.5 + min(len(term), 10) * 0.1
