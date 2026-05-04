from app.services.rag_service import get_document_summary, retrieve_relevant_chunks


def search_document(doc_id: str, query: str, top_k: int = 4):
    return retrieve_relevant_chunks(doc_id=doc_id, question=query, top_k=top_k)


def read_document_summary(doc_id: str) -> str:
    return get_document_summary(doc_id)
