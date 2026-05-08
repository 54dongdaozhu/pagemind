import json
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.database import RagChunk, RagDocument, get_db


def save_indexed_document(
    doc_id: str,
    chunks: list[str],
    embeddings: list[list[float]] | None,
    summary: str,
    title: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    with get_db() as db:
        db.execute(delete(RagChunk).where(RagChunk.doc_id == doc_id))
        db.add_all(
            [
                RagChunk(
                    doc_id=doc_id,
                    chunk_index=idx,
                    content=content,
                    embedding_json=json.dumps(embeddings[idx]) if embeddings and idx < len(embeddings) else None,
                    created_at=now,
                )
                for idx, content in enumerate(chunks)
            ]
        )

        document = db.get(RagDocument, doc_id)
        if document is None:
            db.add(
                RagDocument(
                    doc_id=doc_id,
                    title=title,
                    summary=summary,
                    chunk_count=len(chunks),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            document.title = title
            document.summary = summary
            document.chunk_count = len(chunks)
            document.updated_at = now

        db.commit()


def get_document_summary(doc_id: str) -> str:
    with get_db() as db:
        document = db.get(RagDocument, doc_id)
    return document.summary if document else ""


def list_document_chunks(doc_id: str):
    with get_db() as db:
        chunks = db.execute(
            select(RagChunk)
            .where(RagChunk.doc_id == doc_id)
            .order_by(RagChunk.chunk_index.asc())
        ).scalars()
        return [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "embedding_json": chunk.embedding_json,
            }
            for chunk in chunks
        ]
