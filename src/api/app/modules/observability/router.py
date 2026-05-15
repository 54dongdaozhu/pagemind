from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.core.database import get_db

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _since(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


@router.get("/llm-stats")
def llm_stats(hours: int = Query(default=24, ge=1, le=8760)):
    """LLM 调用按 purpose + model 聚合：次数、延迟、token、成本、失败率。"""
    since = _since(hours)
    sql = text("""
        SELECT
            COALESCE(purpose, 'unknown') AS purpose,
            model,
            provider,
            COUNT(*) AS calls,
            ROUND(AVG(latency_ms)) AS avg_ms,
            MAX(latency_ms) AS max_ms,
            SUM(total_tokens) AS total_tokens,
            ROUND(SUM(cost_usd), 6) AS total_cost_usd,
            ROUND(AVG(CASE WHEN success = 0 THEN 1.0 ELSE 0.0 END), 4) AS error_rate
        FROM llm_call_logs
        WHERE created_at >= :since
        GROUP BY purpose, model, provider
        ORDER BY total_cost_usd DESC
    """)
    with get_db() as db:
        rows = db.execute(sql, {"since": since}).mappings().all()
    return {"hours": hours, "rows": [dict(r) for r in rows]}


@router.get("/slow-steps")
def slow_steps(hours: int = Query(default=24, ge=1, le=8760), threshold_ms: int = Query(default=3000, ge=0)):
    """慢步骤排名：workflow_steps 按平均耗时降序。"""
    since = _since(hours)
    sql = text("""
        SELECT
            step_name,
            COUNT(*) AS count,
            ROUND(AVG(
                (JULIANDAY(finished_at) - JULIANDAY(started_at)) * 86400000
            )) AS avg_ms,
            ROUND(MAX(
                (JULIANDAY(finished_at) - JULIANDAY(started_at)) * 86400000
            )) AS max_ms
        FROM workflow_steps
        WHERE started_at >= :since AND finished_at IS NOT NULL
        GROUP BY step_name
        HAVING avg_ms >= :threshold_ms
        ORDER BY avg_ms DESC
    """)
    with get_db() as db:
        rows = db.execute(sql, {"since": since, "threshold_ms": threshold_ms}).mappings().all()
    return {"hours": hours, "threshold_ms": threshold_ms, "rows": [dict(r) for r in rows]}


@router.get("/error-summary")
def error_summary(hours: int = Query(default=24, ge=1, le=8760)):
    """失败汇总：LLM 失败 + Tool 失败，按出错次数降序。"""
    since = _since(hours)
    sql_llm = text("""
        SELECT 'llm' AS source, COALESCE(purpose, model) AS name, COUNT(*) AS errors
        FROM llm_call_logs
        WHERE created_at >= :since AND success = 0
        GROUP BY purpose, model
    """)
    sql_tool = text("""
        SELECT 'tool' AS source, tool_name AS name, COUNT(*) AS errors
        FROM tool_call_logs
        WHERE created_at >= :since AND success = 0
        GROUP BY tool_name
    """)
    with get_db() as db:
        llm_rows = db.execute(sql_llm, {"since": since}).mappings().all()
        tool_rows = db.execute(sql_tool, {"since": since}).mappings().all()

    rows = sorted(
        [dict(r) for r in llm_rows] + [dict(r) for r in tool_rows],
        key=lambda r: r["errors"],
        reverse=True,
    )
    return {"hours": hours, "rows": rows}


@router.get("/cost-breakdown")
def cost_breakdown(hours: int = Query(default=168, ge=1, le=8760)):
    """按 model + purpose 的成本分解，含每次调用平均成本。"""
    since = _since(hours)
    sql = text("""
        SELECT
            model,
            COALESCE(purpose, 'unknown') AS purpose,
            COUNT(*) AS calls,
            ROUND(SUM(cost_usd), 6) AS total_cost_usd,
            ROUND(AVG(cost_usd), 8) AS avg_cost_usd,
            SUM(total_tokens) AS total_tokens
        FROM llm_call_logs
        WHERE created_at >= :since AND cost_usd IS NOT NULL
        GROUP BY model, purpose
        ORDER BY total_cost_usd DESC
    """)
    with get_db() as db:
        rows = db.execute(sql, {"since": since}).mappings().all()
    return {"hours": hours, "rows": [dict(r) for r in rows]}
