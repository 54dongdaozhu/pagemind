import re
from datetime import datetime

from app.core.database import get_db
from app.schemas.knowledge import RagSource
from app.services.llm_service import call_deepseek


RAG_SYSTEM_PROMPT = """你是一个严谨的文档学习助手。请只依据给定的文档片段回答学生问题。

回答要求：
1. 先直接回答问题，再补充必要解释
2. 如果文档摘要和片段不足以回答，请明确说"文档中没有足够信息"
3. 不要编造文档外的事实
4. 用简洁中文回答，必要时分点说明
5. 最多 300 字"""


SUMMARY_SYSTEM_PROMPT = """你是一个文档整理助手。请为学习型 RAG 问答生成文档摘要。

要求：
1. 概括主题、核心概念、关键结论
2. 保留重要术语
3. 不编造原文没有的信息
4. 150-300 字"""


def split_text_for_rag(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> list[str]:
    text = _normalize_text(text)
    if not text:
        return []

    chunk_size = max(200, min(chunk_size, 2000))
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]

    chunks = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_long_text(paragraph, chunk_size, chunk_overlap))
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)

    return _with_overlap(chunks, chunk_overlap)


def index_document_text(
    doc_id: str,
    text: str,
    title: str | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> int:
    normalized_text = _normalize_text(text)
    chunks = split_text_for_rag(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    now = datetime.utcnow().isoformat()
    summary = summarize_document(normalized_text)

    with get_db() as conn:
        conn.execute("DELETE FROM rag_chunks WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            """
            INSERT INTO rag_chunks (doc_id, chunk_index, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [(doc_id, idx, content, now) for idx, content in enumerate(chunks)],
        )
        conn.execute(
            """
            INSERT INTO rag_documents
                (doc_id, title, summary, chunk_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                chunk_count = excluded.chunk_count,
                updated_at = excluded.updated_at
            """,
            (doc_id, title, summary, len(chunks), now, now),
        )
        conn.commit()

    return len(chunks)


def summarize_document(text: str) -> str:
    text = _normalize_text(text)
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


def get_document_summary(doc_id: str) -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT summary FROM rag_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
    return row["summary"] if row else ""


def retrieve_relevant_chunks(doc_id: str, question: str, top_k: int = 4) -> list[RagSource]:
    top_k = max(1, min(top_k, 8))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT chunk_index, content
            FROM rag_chunks
            WHERE doc_id = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id,),
        ).fetchall()

    scored = []
    for row in rows:
        score = _score_chunk(question, row["content"])
        if score > 0:
            scored.append(
                RagSource(
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    score=round(score, 3),
                )
            )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def answer_with_rag(doc_id: str, question: str, top_k: int = 4) -> tuple[str, list[RagSource]]:
    sources = retrieve_relevant_chunks(doc_id=doc_id, question=question, top_k=top_k)
    summary = get_document_summary(doc_id)
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
            "content": f"【文档摘要】\n{summary or '无'}\n\n【检索片段】\n{context}\n\n【学生问题】\n{question}",
        },
    ]
    reply = call_deepseek(messages, temperature=0.2)
    return reply, sources


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


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_summary_input(text: str) -> str:
    if len(text) <= 6000:
        return text

    head = text[:2500]
    middle_start = max((len(text) // 2) - 1250, 0)
    middle = text[middle_start:middle_start + 2500]
    tail = text[-1000:]
    return f"{head}\n\n[中间片段]\n{middle}\n\n[结尾片段]\n{tail}"


def _split_long_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _with_overlap(chunks: list[str], chunk_overlap: int) -> list[str]:
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped = [chunks[0]]
    for idx in range(1, len(chunks)):
        prefix = chunks[idx - 1][-chunk_overlap:].strip()
        current = chunks[idx]
        overlapped.append(f"{prefix}\n\n{current}" if prefix else current)
    return overlapped


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
