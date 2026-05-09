import json
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.database import RagChunk, RagDocument, get_db


def scoped_doc_id(user_id: str, doc_id: str) -> str:
    return f"user:{user_id}:doc:{doc_id}"


def save_indexed_document(
    user_id: str,
    doc_id: str,
    chunks: list[str],
    embeddings: list[list[float]] | None,
    summary: str,
    title: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    with get_db() as db:
        db.execute(delete(RagChunk).where(RagChunk.doc_id == storage_doc_id))
        db.add_all(
            [
                RagChunk(
                    doc_id=storage_doc_id,
                    chunk_index=idx,
                    content=content,
                    embedding_json=json.dumps(embeddings[idx]) if embeddings and idx < len(embeddings) else None,
                    created_at=now,
                )
                for idx, content in enumerate(chunks)
            ]
        )

        document = db.get(RagDocument, storage_doc_id)
        if document is None:
            db.add(
                RagDocument(
                    doc_id=storage_doc_id,
                    user_id=user_id,
                    title=title,
                    summary=summary,
                    chunk_count=len(chunks),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            document.user_id = user_id
            document.title = title
            document.summary = summary
            document.chunk_count = len(chunks)
            document.updated_at = now

        db.commit()


def get_document_summary(user_id: str, doc_id: str) -> str:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    with get_db() as db:
        document = db.get(RagDocument, storage_doc_id)
    return document.summary if document else ""


def list_document_chunks(user_id: str, doc_id: str):
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    with get_db() as db:
        chunks = db.execute(
            select(RagChunk)
            .where(RagChunk.doc_id == storage_doc_id)
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
