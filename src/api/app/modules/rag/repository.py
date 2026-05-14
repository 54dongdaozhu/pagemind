from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy import delete, func, select

from app.core.database import DocumentVersion, RagChunk, RagDocument, get_db
from app.shared.cache import CONTENT_CACHE_TTL_SECONDS, delete_pattern, get_json, get_text, set_json, set_text


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
    raw_text = "\n\n".join(chunks)
    content_hash = _hash_text(raw_text)
    with get_db() as db:
        document = db.get(RagDocument, storage_doc_id)
        if document is None:
            document = RagDocument(
                doc_id=storage_doc_id,
                user_id=user_id,
                title=title,
                summary=summary,
                chunk_count=0,
                current_version_id=None,
                created_at=now,
                updated_at=now,
            )
            db.add(document)
            db.flush()

        current_version = (
            db.get(DocumentVersion, document.current_version_id)
            if document.current_version_id
            else None
        )
        if current_version is not None and current_version.content_hash == content_hash:
            version_id = current_version.version_id
        else:
            max_version = db.execute(
                select(func.max(DocumentVersion.version_number))
                .where(DocumentVersion.doc_id == storage_doc_id)
            ).scalar_one()
            version_id = uuid.uuid4().hex
            db.add(
                DocumentVersion(
                    version_id=version_id,
                    doc_id=storage_doc_id,
                    version_number=(max_version or 0) + 1,
                    source_name=title,
                    content_hash=content_hash,
                    raw_text=raw_text,
                    created_at=now,
                )
            )
            db.flush()

        db.execute(delete(RagChunk).where(RagChunk.doc_id == storage_doc_id))
        db.add_all(
            [
                RagChunk(
                    doc_id=storage_doc_id,
                    chunk_index=idx,
                    version_id=version_id,
                    content=content,
                    # embedding_json 字段为 JSON 类型，直接传 list，无需 json.dumps
                    embedding_json=embeddings[idx] if embeddings and idx < len(embeddings) else None,
                    content_hash=_hash_text(content),
                    created_at=now,
                )
                for idx, content in enumerate(chunks)
            ]
        )

        document.user_id = user_id
        document.title = title
        document.summary = summary
        document.chunk_count = len(chunks)
        document.current_version_id = version_id
        document.updated_at = now

        db.commit()
    delete_pattern(f"cache:content:{storage_doc_id}:*")
    delete_pattern("cache:rag_query:*")


def get_document_summary(user_id: str, doc_id: str) -> str:
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    cache_key = f"cache:content:{storage_doc_id}:summary"
    cached = get_text(cache_key)
    if cached is not None:
        return cached

    with get_db() as db:
        document = db.get(RagDocument, storage_doc_id)
    summary = document.summary if document else ""
    set_text(cache_key, summary, CONTENT_CACHE_TTL_SECONDS)
    return summary


def list_document_chunks(user_id: str, doc_id: str):
    storage_doc_id = scoped_doc_id(user_id, doc_id)
    cache_key = f"cache:content:{storage_doc_id}:chunks"
    cached = get_json(cache_key)
    if cached is not None:
        return cached

    with get_db() as db:
        chunks = db.execute(
            select(RagChunk)
            .where(RagChunk.doc_id == storage_doc_id)
            .order_by(RagChunk.chunk_index.asc())
        ).scalars()
        rows = [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                # JSON 类型字段，已由 SQLAlchemy 反序列化为 list（或 None）
                "embedding": chunk.embedding_json,
            }
            for chunk in chunks
        ]
    set_json(cache_key, rows, CONTENT_CACHE_TTL_SECONDS)
    return rows


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
