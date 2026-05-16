import chromadb

from app.core.config import CHROMA_PATH
from app.shared.schemas import RagSource
from app.modules.rag.embeddings import embed_texts


_chroma_client = None
_chroma_collection = None


def index_chunks_in_chroma(doc_id: str, chunks: list[str], embeddings: list[list[float]] | None):
    if not embeddings or len(embeddings) != len(chunks):
        return

    collection = _get_chroma_collection()
    existing = collection.get(where={"doc_id": doc_id}, include=[])
    existing_ids = existing.get("ids", [])
    if existing_ids:
        collection.delete(ids=existing_ids)

    ids = [_chunk_id(doc_id, idx) for idx in range(len(chunks))]
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=[
            {"doc_id": doc_id, "chunk_index": idx}
            for idx in range(len(chunks))
        ],
    )


def retrieve_by_chroma(doc_id: str, question: str, top_k: int) -> list[RagSource]:
    query_embeddings = embed_texts([question])
    if not query_embeddings:
        return []

    try:
        result = _get_chroma_collection().query(
            query_embeddings=query_embeddings,
            n_results=top_k,
            where={"doc_id": doc_id},
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    sources = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        sources.append(
            RagSource(
                chunk_index=metadata["chunk_index"],
                content=document,
                score=round(max(0.0, 1.0 - float(distance)), 4),
                retrieval_method="embedding",
            )
        )
    return sources


def _get_chroma_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    _chroma_collection = _chroma_client.get_or_create_collection(
        name="rag_chunks",
        metadata={"hnsw:space": "cosine"},
    )
    return _chroma_collection


def _chunk_id(doc_id: str, chunk_index: int) -> str:
    return f"{doc_id}:{chunk_index}"
