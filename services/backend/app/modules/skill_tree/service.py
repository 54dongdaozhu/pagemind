import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SkillTreeSnapshot, get_db
from app.modules.skill_tree.aggregator import (
    aggregate_user_signals,
    build_profile_section,
    build_signals_section,
)
from app.modules.skill_tree.prompts import SKILL_TREE_ANALYZE_PROMPT, SKILL_TREE_FINALIZE_PROMPT
from app.shared import db_log
from app.shared.cache import SKILL_TREE_TTL_SECONDS, delete_key, get_json, set_json
from app.shared.llm import call_deepseek


logger = logging.getLogger(__name__)

_CACHE_KEY = "skill_tree:user:{user_id}"
_ACTIVITY_KEY = "skill_tree:activity:{user_id}"


def _cache_key(user_id: str) -> str:
    return _CACHE_KEY.format(user_id=user_id)


def _activity_key(user_id: str) -> str:
    return _ACTIVITY_KEY.format(user_id=user_id)


def get_latest_snapshot(user_id: str) -> dict | None:
    cached = get_json(_cache_key(user_id))
    if cached is not None:
        return cached

    with get_db() as db:
        row = db.execute(
            select(SkillTreeSnapshot)
            .where(
                SkillTreeSnapshot.user_id == user_id,
                SkillTreeSnapshot.status == "ready",
            )
            .order_by(SkillTreeSnapshot.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if row is None:
        return None

    result = _snapshot_to_dict(row)
    set_json(_cache_key(user_id), result, SKILL_TREE_TTL_SECONDS)
    return result


def get_snapshot_status(snapshot_id: str) -> dict | None:
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
    if row is None:
        return None
    return {
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "error_detail": row.error_detail,
    }


def create_snapshot(user_id: str, trigger: str = "manual") -> str:
    now = datetime.now(timezone.utc)
    snapshot_id = uuid.uuid4().hex
    with get_db() as db:
        db.add(SkillTreeSnapshot(
            snapshot_id=snapshot_id,
            user_id=user_id,
            status="generating",
            trigger=trigger,
            web_search_used=False,
            created_at=now,
            updated_at=now,
        ))
        db.commit()
    return snapshot_id


def get_generating_snapshot(user_id: str) -> str | None:
    with get_db() as db:
        row = db.execute(
            select(SkillTreeSnapshot)
            .where(
                SkillTreeSnapshot.user_id == user_id,
                SkillTreeSnapshot.status == "generating",
            )
            .order_by(SkillTreeSnapshot.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    return row.snapshot_id if row else None


def generate_skill_tree_job(user_id: str, snapshot_id: str) -> None:
    run_id = db_log.create_workflow_run(
        workflow_type="skill_tree_generation",
        user_id=user_id,
        trigger_source="rq",
    )
    try:
        _do_generate(user_id, snapshot_id, run_id)
        db_log.finish_workflow_run(run_id, success=True)
    except Exception as exc:
        logger.exception("[SkillTree] generation failed for user %s snapshot %s", user_id, snapshot_id)
        _mark_failed(snapshot_id, str(exc), run_id)
        db_log.finish_workflow_run(run_id, success=False, error_details={"error": str(exc)})


def _do_generate(user_id: str, snapshot_id: str, run_id: str) -> None:
    step1_id = db_log.create_workflow_step(run_id=run_id, step_name="aggregate_signals", step_order=1)
    signals = aggregate_user_signals(user_id)
    input_summary = {
        "doc_count": len(signals["docs"]),
        "deep_kp_count": signals.get("deep_kp_count", 0),
        "learning_kp_count": len(signals["learning_kps"]),
        "known_kp_count": len(signals["known_kps"]),
        "qa_count": len(signals["qa_topics"]),
    }
    db_log.finish_workflow_step(step1_id, success=True, output_data=input_summary)

    profile_section = build_profile_section(signals["profile"])
    signals_section = build_signals_section(signals)

    web_snippets: dict[str, str] = {}
    web_search_used = False

    tavily_key = _get_tavily_key()
    skill_level = (signals["profile"].get("skill_level") or "").strip()
    if tavily_key and skill_level != "高级":
        step2_id = db_log.create_workflow_step(run_id=run_id, step_name="web_search", step_order=2)
        web_snippets, web_search_used = _run_web_search(signals, tavily_key)
        db_log.finish_workflow_step(step2_id, success=True, output_data={"skills_searched": len(web_snippets)})

    if web_search_used:
        step3_id = db_log.create_workflow_step(run_id=run_id, step_name="llm_finalize", step_order=3)
        tree_json = _llm_finalize(profile_section, signals_section, web_snippets, run_id)
        db_log.finish_workflow_step(step3_id, success=True)
    else:
        step3_id = db_log.create_workflow_step(run_id=run_id, step_name="llm_analyze", step_order=3)
        tree_json = _llm_analyze(profile_section, signals_section, run_id)
        db_log.finish_workflow_step(step3_id, success=True)

    now = datetime.now(timezone.utc)
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
        if row:
            row.status = "ready"
            row.input_summary = input_summary
            row.tree_json = tree_json
            row.web_search_used = web_search_used
            row.run_id = run_id
            row.updated_at = now
            db.commit()

    delete_key(_cache_key(user_id))

    db_log.log_event(
        entity_type="skill_tree_snapshot",
        entity_id=snapshot_id,
        event_type="skill_tree.ready",
        user_id=user_id,
        meta=input_summary,
    )


def _llm_analyze(profile_section: str, signals_section: str, run_id: str) -> dict:
    prompt = SKILL_TREE_ANALYZE_PROMPT.format(
        profile_section=profile_section,
        signals_section=signals_section,
    )
    raw = call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        json_mode=True,
        purpose="skill_tree_analyze",
    )
    return json.loads(raw)


def _llm_finalize(profile_section: str, signals_section: str, web_snippets: dict, run_id: str) -> dict:
    web_section = "\n".join(f"- {skill}: {snippet}" for skill, snippet in web_snippets.items())
    prompt = SKILL_TREE_FINALIZE_PROMPT.format(
        profile_section=profile_section,
        signals_section=signals_section,
        web_section=web_section,
    )
    raw = call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        json_mode=True,
        purpose="skill_tree_finalize",
    )
    return json.loads(raw)


def _run_web_search(signals: dict, tavily_key: str) -> tuple[dict, bool]:
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError:
        logger.debug("[SkillTree] tavily-python not installed, skipping web search")
        return {}, False

    domain_focus = signals["profile"].get("domain_focus") or []
    user_domain = domain_focus[0] if domain_focus else "技术开发"

    learning_kp_texts = [k["text"] for k in signals["learning_kps"][:5]]
    if not learning_kp_texts:
        return {}, False

    client = TavilyClient(api_key=tavily_key)
    snippets: dict[str, str] = {}
    for kp in learning_kp_texts:
        try:
            result = client.search(
                f"{kp} 学习路线 {user_domain}",
                max_results=2,
                search_depth="basic",
            )
            first = (result.get("results") or [{}])[0]
            content = first.get("content", "").strip()[:300]
            if content:
                snippets[kp] = content
        except Exception as exc:
            logger.debug("[SkillTree] web search failed for '%s': %s", kp, exc)

    return snippets, bool(snippets)


def _mark_failed(snapshot_id: str, error: str, run_id: str | None) -> None:
    now = datetime.now(timezone.utc)
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
        if row:
            row.status = "failed"
            row.error_detail = error[:1000]
            row.run_id = run_id
            row.updated_at = now
            db.commit()


def _get_tavily_key() -> str:
    from app.core.config import TAVILY_API_KEY
    return TAVILY_API_KEY or ""


def _snapshot_to_dict(row: SkillTreeSnapshot) -> dict:
    return {
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "trigger": row.trigger,
        "web_search_used": row.web_search_used,
        "input_summary": row.input_summary,
        "tree": row.tree_json,
        "generated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def increment_activity_counter(user_id: str) -> None:
    from app.core.config import SKILL_TREE_ACTIVITY_THRESHOLD
    from app.shared.cache import get_redis
    from app.shared.job_queue import enqueue_job

    try:
        redis = get_redis()
        key = _activity_key(user_id)
        count = redis.incr(key)
        redis.expire(key, 60 * 60 * 24 * 7)
        if count >= SKILL_TREE_ACTIVITY_THRESHOLD:
            redis.delete(key)
            existing = get_generating_snapshot(user_id)
            if not existing:
                snapshot_id = create_snapshot(user_id, trigger="auto_threshold")
                enqueued = enqueue_job(generate_skill_tree_job, user_id, snapshot_id)
                if enqueued:
                    db_log.log_event(
                        entity_type="skill_tree_snapshot",
                        entity_id=snapshot_id,
                        event_type="skill_tree.auto_triggered",
                        user_id=user_id,
                        meta={"activity_count": count},
                    )
                else:
                    _mark_failed(snapshot_id, "RQ not available for auto-trigger", None)
    except Exception as exc:
        logger.debug("[SkillTree] activity counter failed: %s", exc)
