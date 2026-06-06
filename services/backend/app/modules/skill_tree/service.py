import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SkillTreeSnapshot, WorkflowRun, WorkflowStep, get_db
from app.modules.skill_tree.aggregator import (
    aggregate_user_signals,
    build_profile_section,
    build_signals_section,
)
from app.modules.skill_tree.prompts import SKILL_TREE_ANALYZE_PROMPT, SKILL_TREE_FINALIZE_PROMPT
from app.shared import db_log
from app.shared.cache import SKILL_TREE_TTL_SECONDS, delete_key, get_or_set_json
from app.shared.llm import call_deepseek


logger = logging.getLogger(__name__)

_CACHE_KEY = "skill_tree:user:{user_id}"
_ACTIVITY_KEY = "skill_tree:activity:{user_id}"
_STEP_TTL_SECONDS = 300
_WEB_SEARCH_MAX_SKILLS = 3
_WEB_SEARCH_TIMEOUT_SECONDS = 8


def _cache_key(user_id: str) -> str:
    return _CACHE_KEY.format(user_id=user_id)


def _activity_key(user_id: str) -> str:
    return _ACTIVITY_KEY.format(user_id=user_id)


def get_latest_snapshot(user_id: str) -> dict | None:
    def load_snapshot() -> dict | None:
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

        return _snapshot_to_dict(row) if row is not None else None

    return get_or_set_json(
        _cache_key(user_id),
        load_snapshot,
        SKILL_TREE_TTL_SECONDS,
        wait_timeout_seconds=1.0,
    )


_GENERATING_TIMEOUT_SECONDS = 300  # worker restart leaves snapshots stuck forever


def _is_generation_stale(row: SkillTreeSnapshot, now: datetime | None = None) -> bool:
    if row.status != "generating" or not row.created_at:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - row.created_at).total_seconds() > _GENERATING_TIMEOUT_SECONDS


def _mark_stale_generating(snapshot_id: str) -> bool:
    now = datetime.now(timezone.utc)
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
        if not row or not _is_generation_stale(row, now):
            return False
        row.status = "failed"
        row.error_detail = "timeout: worker did not complete within 5 minutes"
        row.updated_at = now
        db.commit()
        return True


def get_snapshot_status(snapshot_id: str) -> dict | None:
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
    if row is None:
        return None

    if _mark_stale_generating(snapshot_id):
        with get_db() as db:
            row = db.get(SkillTreeSnapshot, snapshot_id)

    current_step = None
    try:
        from app.shared.cache import get_redis
        val = get_redis().get(f"skill_tree:step:{snapshot_id}")
        current_step = val.decode() if isinstance(val, bytes) else val
    except Exception:
        pass
    return {
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "current_step": current_step,
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
        rows = db.execute(
            select(SkillTreeSnapshot)
            .where(
                SkillTreeSnapshot.user_id == user_id,
                SkillTreeSnapshot.status == "generating",
            )
            .order_by(SkillTreeSnapshot.created_at.desc())
            .limit(10)
        ).scalars().all()

    for row in rows:
        if _mark_stale_generating(row.snapshot_id):
            continue
        return row.snapshot_id
    return None


class _WorkflowTracker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.run_id: str | None = None

    def start(self) -> str | None:
        run_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        try:
            with get_db() as db:
                db.add(WorkflowRun(
                    run_id=run_id,
                    user_id=self.user_id,
                    workflow_type="skill_tree_generation",
                    trigger_source="rq",
                    status="running",
                    started_at=now,
                    created_at=now,
                    updated_at=now,
                ))
                db.commit()
            self.run_id = run_id
        except Exception as exc:
            logger.warning("[SkillTree] workflow run logging skipped: %s", exc)
        return self.run_id

    def start_step(self, step_name: str, step_order: int, input_data: dict | None = None) -> str | None:
        if not self.run_id:
            return None
        step_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        try:
            with get_db() as db:
                db.add(WorkflowStep(
                    step_id=step_id,
                    run_id=self.run_id,
                    step_name=step_name,
                    step_order=step_order,
                    status="running",
                    input_data=input_data,
                    started_at=now,
                    created_at=now,
                ))
                db.commit()
            return step_id
        except Exception as exc:
            logger.warning("[SkillTree] workflow step logging skipped: %s", exc)
            return None

    def finish_step(
        self,
        step_id: str | None,
        *,
        success: bool = True,
        output_data: dict | None = None,
        error_details: dict | None = None,
    ) -> None:
        if not step_id:
            return
        now = datetime.now(timezone.utc)
        try:
            with get_db() as db:
                step = db.get(WorkflowStep, step_id)
                if not step:
                    return
                step.status = "completed" if success else "failed"
                step.output_data = output_data
                step.error_details = error_details
                step.finished_at = now
                db.commit()
        except Exception as exc:
            logger.debug("[SkillTree] workflow step finish skipped: %s", exc)

    def finish(
        self,
        *,
        success: bool = True,
        output_data: dict | None = None,
        error_details: dict | None = None,
    ) -> None:
        if not self.run_id:
            return
        now = datetime.now(timezone.utc)
        try:
            with get_db() as db:
                run = db.get(WorkflowRun, self.run_id)
                if not run:
                    return
                run.status = "completed" if success else "failed"
                run.output_data = output_data
                run.error_details = error_details
                run.finished_at = now
                run.updated_at = now
                db.commit()
        except Exception as exc:
            logger.debug("[SkillTree] workflow run finish skipped: %s", exc)


def generate_skill_tree_job(user_id: str, snapshot_id: str) -> None:
    tracker = _WorkflowTracker(user_id)
    run_id = tracker.start()
    user_token = db_log.current_user_id.set(user_id)
    run_token = db_log.current_run_id.set(run_id) if run_id else None
    try:
        output_data = _do_generate(user_id, snapshot_id, tracker)
        tracker.finish(success=True, output_data=output_data)
    except BaseException as exc:
        logger.exception("[SkillTree] generation failed for user %s snapshot %s", user_id, snapshot_id)
        _mark_failed(snapshot_id, str(exc), run_id)
        tracker.finish(success=False, error_details={"error": str(exc)})
        raise
    finally:
        if run_token is not None:
            db_log.current_run_id.reset(run_token)
        db_log.current_user_id.reset(user_token)


def _set_step(snapshot_id: str, step: str) -> None:
    try:
        from app.shared.cache import get_redis
        get_redis().set(f"skill_tree:step:{snapshot_id}", step, ex=_STEP_TTL_SECONDS)
    except Exception:
        pass


def _do_generate(user_id: str, snapshot_id: str, tracker: _WorkflowTracker) -> dict:
    _set_step(snapshot_id, "aggregate")
    step1_id = tracker.start_step("aggregate_signals", 1)
    signals = aggregate_user_signals(user_id)
    input_summary = {
        "doc_count": len(signals["docs"]),
        "deep_kp_count": signals.get("deep_kp_count", 0),
        "learning_kp_count": len(signals["learning_kps"]),
        "known_kp_count": len(signals["known_kps"]),
        "qa_count": len(signals["qa_topics"]),
    }
    tracker.finish_step(step1_id, success=True, output_data=input_summary)

    profile_section = build_profile_section(signals["profile"])
    signals_section = build_signals_section(signals)

    web_snippets: dict[str, str] = {}
    web_search_used = False

    tavily_key = _get_tavily_key()
    skill_level = (signals["profile"].get("skill_level") or "").strip()
    if tavily_key and skill_level != "高级":
        _set_step(snapshot_id, "web_search")
        step2_id = tracker.start_step("web_search", 2)
        web_snippets, web_search_used = _run_web_search(signals, tavily_key)
        tracker.finish_step(step2_id, success=True, output_data={"skills_searched": len(web_snippets)})

    if web_search_used:
        _set_step(snapshot_id, "llm_finalize")
        step3_id = tracker.start_step("llm_finalize", 3)
        tree_json = _llm_finalize(profile_section, signals_section, web_snippets)
        tracker.finish_step(step3_id, success=True)
    else:
        _set_step(snapshot_id, "llm_analyze")
        step3_id = tracker.start_step("llm_analyze", 3)
        tree_json = _llm_analyze(profile_section, signals_section)
        tracker.finish_step(step3_id, success=True)

    _set_step(snapshot_id, "persist")
    now = datetime.now(timezone.utc)
    with get_db() as db:
        row = db.get(SkillTreeSnapshot, snapshot_id)
        if row:
            row.status = "ready"
            row.input_summary = input_summary
            row.tree_json = tree_json
            row.web_search_used = web_search_used
            row.run_id = tracker.run_id
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
    return input_summary


def _llm_analyze(profile_section: str, signals_section: str) -> dict:
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


def _llm_finalize(profile_section: str, signals_section: str, web_snippets: dict) -> dict:
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

    learning_kp_texts = [k["text"] for k in signals["learning_kps"][:_WEB_SEARCH_MAX_SKILLS]]
    if not learning_kp_texts:
        return {}, False

    client = TavilyClient(api_key=tavily_key)

    def search_one(kp: str) -> tuple[str, str | None]:
        result = client.search(
            f"{kp} 学习路线 {user_domain}",
            max_results=2,
            search_depth="basic",
        )
        first = (result.get("results") or [{}])[0]
        content = first.get("content", "").strip()[:300]
        return kp, content or None

    snippets: dict[str, str] = {}
    executor = ThreadPoolExecutor(max_workers=min(_WEB_SEARCH_MAX_SKILLS, len(learning_kp_texts)))
    futures = {executor.submit(search_one, kp): kp for kp in learning_kp_texts}
    try:
        for future in as_completed(futures, timeout=_WEB_SEARCH_TIMEOUT_SECONDS):
            kp = futures[future]
            try:
                skill, content = future.result()
                if content:
                    snippets[skill] = content
            except Exception as exc:
                logger.debug("[SkillTree] web search failed for '%s': %s", kp, exc)
    except TimeoutError:
        logger.debug("[SkillTree] web search timed out after %s seconds", _WEB_SEARCH_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

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
