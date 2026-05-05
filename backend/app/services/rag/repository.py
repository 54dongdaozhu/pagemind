import json
from datetime import datetime

from app.core.database import get_db


def save_indexed_document(
    doc_id: str,
    chunks: list[str],
    embeddings: list[list[float]] | None,
    summary: str,
    title: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute("DELETE FROM rag_chunks WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            """
            INSERT INTO rag_chunks (doc_id, chunk_index, content, embedding_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    doc_id,
                    idx,
                    content,
                    json.dumps(embeddings[idx]) if embeddings and idx < len(embeddings) else None,
                    now,
                )
                for idx, content in enumerate(chunks)
            ],
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


def get_document_summary(doc_id: str) -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT summary FROM rag_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
    return row["summary"] if row else ""


def list_document_chunks(doc_id: str):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT chunk_index, content, embedding_json
            FROM rag_chunks
            WHERE doc_id = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id,),
        ).fetchall()
