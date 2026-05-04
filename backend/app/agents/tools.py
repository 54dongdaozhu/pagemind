from app.agents.knowledge_agents import discover_knowledge_points
from app.services.explain_service import stream_deep_explanation
from app.services.knowledge_service import (
    get_status_batch,
    get_stats,
    mark_known,
    record_click,
    unmark_known,
)
from app.services.rag_service import answer_with_rag, get_document_summary, retrieve_relevant_chunks


def search_document_chunks(doc_id: str, query: str, top_k: int = 4):
    return retrieve_relevant_chunks(doc_id=doc_id, question=query, top_k=top_k)


def read_document_summary(doc_id: str) -> str:
    return get_document_summary(doc_id)


def answer_with_document_context(doc_id: str, question: str, top_k: int = 4):
    reply, sources = answer_with_rag(doc_id=doc_id, question=question, top_k=top_k)
    return {"reply": reply, "sources": sources}


def extract_knowledge_from_chunk(text: str):
    return {"knowledge_points": discover_knowledge_points(text)}


def get_knowledge_status_batch(kp_texts: list[str]):
    return get_status_batch(kp_texts)


def record_knowledge_click(kp_text: str, kp_type: str):
    return record_click(kp_text=kp_text, kp_type=kp_type)


def mark_knowledge_known(kp_text: str, kp_type: str):
    return mark_known(kp_text=kp_text, kp_type=kp_type)


def unmark_knowledge_known(kp_text: str):
    return unmark_known(kp_text=kp_text)


def get_learning_stats():
    return get_stats()


def explain_knowledge_with_context(keyword: str, kp_type: str, context: str):
    return "".join(
        stream_deep_explanation(
            keyword=keyword,
            kp_type=kp_type,
            context=context,
        )
    )
