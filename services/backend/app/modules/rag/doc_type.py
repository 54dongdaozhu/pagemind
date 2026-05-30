import logging
from datetime import datetime, timezone

from app.shared.cache import get_json, set_json

logger = logging.getLogger(__name__)

_DOC_TYPE_STATUS_TTL = 60 * 60 * 24 * 3  # 3 天


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_type_status_key(user_id: str, doc_id: str) -> str:
    return f"doc_type:status:user:{user_id}:doc:{doc_id}"


def _save_doc_type_status(user_id: str, doc_id: str, status: dict) -> None:
    try:
        set_json(_doc_type_status_key(user_id, doc_id), status, _DOC_TYPE_STATUS_TTL)
    except Exception as e:
        logger.warning("[DocType] status save failed for doc=%s: %s", doc_id, e)


def get_doc_type_status(user_id: str, doc_id: str) -> dict:
    data = get_json(_doc_type_status_key(user_id, doc_id))
    if isinstance(data, dict):
        return data
    return {"doc_id": doc_id, "status": "unknown", "doc_type": None, "confidence": None, "error": None, "updated_at": None}


def _classify_document_type_job(
    user_id: str,
    doc_id: str,
    storage_doc_id: str,
    title: str,
    chunks: list[str],
) -> None:
    """RQ job：识别文档类型并写入 DB 和 Redis。"""
    from app.core.database import RagDocument, get_db
    from app.modules.agent.doc_type_agents import classify_document_type

    _save_doc_type_status(user_id, doc_id, {
        "doc_id": doc_id,
        "status": "running",
        "doc_type": None,
        "confidence": None,
        "error": None,
        "updated_at": _now_iso(),
    })
    try:
        result = classify_document_type(title, chunks)
        doc_type = result.get("doc_type", "其他")
        confidence = result.get("confidence", 0.0)

        with get_db() as db:
            doc = db.get(RagDocument, storage_doc_id)
            if doc:
                doc.doc_type = doc_type
                doc.doc_type_confidence = confidence
                doc.updated_at = datetime.now(timezone.utc)
                db.commit()

        _save_doc_type_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "completed",
            "doc_type": doc_type,
            "confidence": confidence,
            "error": None,
            "updated_at": _now_iso(),
        })
        logger.info("[DocType] doc=%s classified as %s (confidence=%.2f)", doc_id, doc_type, confidence)
    except Exception as e:
        logger.exception("[DocType] failed for doc=%s: %s", doc_id, e)
        _save_doc_type_status(user_id, doc_id, {
            "doc_id": doc_id,
            "status": "failed",
            "doc_type": None,
            "confidence": None,
            "error": str(e),
            "updated_at": _now_iso(),
        })
        raise
