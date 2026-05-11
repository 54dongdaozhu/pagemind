import re

from app.schemas.knowledge import RagSource
from app.services.llm_service import call_deepseek
from app.core.config import EMBEDDING_MODEL
from app.services import db_log
from app.services.rag.chunking import normalize_text, split_text_for_rag
from app.services.rag.embeddings import embed_texts
from app.services.rag.repository import (
    get_document_summary,
    list_document_chunks,
    save_indexed_document,
    scoped_doc_id,
)
from app.services.rag.vector_store import index_chunks_in_chroma, retrieve_by_chroma


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
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> int:
    normalized_text = normalize_text(text)
    chunks = split_text_for_rag(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    summary = summarize_document(normalized_text)
    embeddings = embed_texts(chunks)
    storage_doc_id = scoped_doc_id(user_id, doc_id)
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
    return len(chunks)


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
        return call_deepseek(messages, temperature=0.2).strip()
    except Exception:
        return summary_input[:500]


def retrieve_relevant_chunks(user_id: str, doc_id: str, question: str, top_k: int = 3) -> list[RagSource]:
    top_k = max(1, min(top_k, 8))
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    chroma_results = retrieve_by_chroma(storage_doc_id, question, top_k)
    if chroma_results:
        return chroma_results

    rows = list_document_chunks(user_id, doc_id)
    return _retrieve_by_keyword(rows, question, top_k)


def summarize_full_document(user_id: str, doc_id: str, request: str = "") -> dict:
    rows = list_document_chunks(user_id, doc_id)
    if not rows:
        summary = get_document_summary(user_id, doc_id)
        return {
            "summary": summary,
            "chunk_count": 0,
            "batch_count": 0,
        }

    batches = _batch_chunk_rows(rows)
    partials = [
        _summarize_chunk_batch(batch=batch, batch_index=idx, batch_count=len(batches))
        for idx, batch in enumerate(batches, start=1)
    ]
    merged = _merge_partial_summaries(partials, request=request)
    return {
        "summary": merged,
        "chunk_count": len(rows),
        "batch_count": len(batches),
    }


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
    reply = call_deepseek(messages, temperature=0.2)
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
    return call_deepseek(messages, temperature=0.15).strip()


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
    return call_deepseek(messages, temperature=0.15).strip()


def _retrieve_by_keyword(rows, question: str, top_k: int) -> list[RagSource]:
    scored = []
    for row in rows:
        score = _score_chunk(question, row["content"])
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


def _score_chunk(question: str, content: str) -> float:
    question = question.strip().lower()
    content_lower = content.lower()
    if not question:
        return 0

    score = 0.0
    if question in content_lower:
        score += 10.0

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


def _term_weight(term: str) -> float:
    if re.fullmatch(r"[\u4e00-\u9fff]+", term):
        return 1.0 + min(len(term), 6) * 0.25
    return 1.5 + min(len(term), 10) * 0.1
