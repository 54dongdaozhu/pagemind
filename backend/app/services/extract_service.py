"""
Knowledge extraction service.

The API keeps the existing response shape used by the frontend, while the
actual decision-making is delegated to the agent workflow:
KnowledgeDiscoveryAgent -> KnowledgeFilterAgent -> KnowledgeRankAgent.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import BoundedSemaphore, RLock

from app.agents.knowledge_agents import discover_knowledge_points, finalize_knowledge_items
from app.core.config import EXTRACT_MAX_CONCURRENCY
from app.core.database import ExtractCache, get_db
from app.schemas.knowledge import ExtractBatchItem, ExtractBatchResponse, ExtractResponse, KnowledgePoint


logger = logging.getLogger(__name__)

_extract_cache = {}
_extract_cache_lock = RLock()
_extract_db_lock = RLock()
_llm_slots = BoundedSemaphore(EXTRACT_MAX_CONCURRENCY)


def _to_knowledge_points(kps_data: list[dict], text: str) -> list[KnowledgePoint]:
    finalized = finalize_knowledge_items(kps_data, text)
    return [KnowledgePoint(**kp) for kp in finalized]


def _load_from_cache(chunk_id: str, text: str) -> list[KnowledgePoint] | None:
    with get_db() as db:
        cache = db.get(ExtractCache, chunk_id)
    if cache is None:
        return None
    data = json.loads(cache.result_json)
    return _to_knowledge_points(data, text)


def _save_to_cache(chunk_id: str, knowledge_points: list[KnowledgePoint]):
    now = datetime.now(timezone.utc)
    result_json = json.dumps([kp.model_dump() for kp in knowledge_points], ensure_ascii=False)
    with _extract_db_lock:
        with get_db() as db:
            cache = db.get(ExtractCache, chunk_id)
            if cache is None:
                db.add(ExtractCache(chunk_id=chunk_id, result_json=result_json, created_at=now))
            else:
                cache.result_json = result_json
                cache.created_at = now
            db.commit()


def extract_knowledge_from_text(chunk_id: str, text: str) -> ExtractResponse:
    text = text.strip()

    with _extract_cache_lock:
        if chunk_id in _extract_cache:
            return ExtractResponse(chunk_id=chunk_id, knowledge_points=_extract_cache[chunk_id])

    cached = _load_from_cache(chunk_id, text)
    if cached is not None:
        with _extract_cache_lock:
            _extract_cache[chunk_id] = cached
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached)

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    try:
        with _llm_slots:
            kps_data = discover_knowledge_points(text)
        knowledge_points = _to_knowledge_points(kps_data, text)
    except Exception as e:
        logger.exception("Knowledge agent extraction failed: %s", e)
        knowledge_points = []

    with _extract_cache_lock:
        _extract_cache[chunk_id] = knowledge_points
    _save_to_cache(chunk_id, knowledge_points)

    return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)


def extract_knowledge_batch(chunks: list[ExtractBatchItem]) -> ExtractBatchResponse:
    if not chunks:
        return ExtractBatchResponse(results=[])

    max_workers = min(EXTRACT_MAX_CONCURRENCY, len(chunks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(
            executor.map(
                lambda chunk: extract_knowledge_from_text(chunk.chunk_id, chunk.text),
                chunks,
            )
        )

    return ExtractBatchResponse(results=results)
