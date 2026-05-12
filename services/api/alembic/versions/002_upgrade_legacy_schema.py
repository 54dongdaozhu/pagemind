"""upgrade legacy schema — migrate pre-Alembic databases to new format

Revision ID: 002
Revises: 001
Create Date: 2026-05-10

处理三类旧库问题：
1. knowledge_points 的主键从 kp_text(TEXT) 改为 kp_id(UUID)
   - 添加 kp_id 列、填充 UUID、在 PostgreSQL 上完成 PK 切换
   - 同步更新 study_records / chunk_knowledge_points / review_records 的 FK 列
2. 字段重命名（result_json→result, tools_used_json→tools_used, error_message→error_details）
3. 补充新增列（llm_call_logs/tool_call_logs 的上下文关联列、extract_caches.expired_at 等）

在新库（001 刚建好）上运行时所有操作均检测列存在性后跳过，完全幂等。
"""
import uuid as _uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _col_names(conn, table: str) -> set:
    return {c["name"] for c in inspect(conn).get_columns(table)}


def _table_exists(conn, table: str) -> bool:
    return table in set(inspect(conn).get_table_names())


def _is_postgres(conn) -> bool:
    return conn.dialect.name == "postgresql"


def _add_col_if_missing(table: str, col_name: str, col_type: str, cols: set) -> None:
    """跳过已存在列，避免重复 ALTER TABLE。"""
    if col_name not in cols:
        op.add_column(table, sa.Column(col_name, sa.Text))  # placeholder
        # 使用原生 SQL 精确控制类型（op.add_column 的类型映射在混合 DB 下不够精确）
        op.execute(text(f"ALTER TABLE {table} DROP COLUMN {col_name}"))
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))


def upgrade() -> None:
    conn = op.get_bind()
    pg = _is_postgres(conn)

    # ═══════════════════════════════════════════════════════════════════════
    # 1. knowledge_points：kp_text PK → kp_id UUID PK
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "knowledge_points"):
        kp_cols = _col_names(conn, "knowledge_points")

        if "kp_id" not in kp_cols:
            # ── 1a. 添加 kp_id 列并用 Python 生成 UUID 回填 ──────────────
            op.execute(text("ALTER TABLE knowledge_points ADD COLUMN kp_id VARCHAR(32)"))
            rows = conn.execute(text("SELECT kp_text FROM knowledge_points")).fetchall()
            for (kp_text,) in rows:
                new_id = _uuid.uuid4().hex
                conn.execute(
                    text("UPDATE knowledge_points SET kp_id = :id WHERE kp_text = :t"),
                    {"id": new_id, "t": kp_text},
                )

            if pg:
                # ── 1b. 删除子表中指向 knowledge_points(kp_text) 的 FK ────
                for child in ("study_records", "chunk_knowledge_points", "review_records"):
                    if not _table_exists(conn, child):
                        continue
                    for fk in inspect(conn).get_foreign_keys(child):
                        if fk.get("referred_table") == "knowledge_points" and fk.get("name"):
                            op.execute(text(
                                f"ALTER TABLE {child} DROP CONSTRAINT IF EXISTS {fk['name']}"
                            ))

                # ── 1c. 切换 knowledge_points 主键 ───────────────────────
                op.execute(text("ALTER TABLE knowledge_points ALTER COLUMN kp_id SET NOT NULL"))
                op.execute(text("ALTER TABLE knowledge_points DROP CONSTRAINT knowledge_points_pkey"))
                op.execute(text(
                    "ALTER TABLE knowledge_points "
                    "ADD CONSTRAINT uq_kp_text UNIQUE (kp_text)"
                ))
                op.execute(text("ALTER TABLE knowledge_points ADD PRIMARY KEY (kp_id)"))

    # ═══════════════════════════════════════════════════════════════════════
    # 2. study_records：添加 kp_id FK 列并回填
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "study_records") and _table_exists(conn, "knowledge_points"):
        sr_cols = _col_names(conn, "study_records")

        if "kp_id" not in sr_cols:
            op.execute(text("ALTER TABLE study_records ADD COLUMN kp_id VARCHAR(32)"))

        # 修复历史遗留问题：study_records 中存在 knowledge_points 里没有的 kp_text
        # （旧版 SQLite 不强制 FK，导致出现孤立记录）
        ts = "now()" if pg else "datetime('now')"
        orphans = conn.execute(text("""
            SELECT DISTINCT sr.kp_text
            FROM study_records sr
            LEFT JOIN knowledge_points kp ON sr.kp_text = kp.kp_text
            WHERE kp.kp_text IS NULL
        """)).fetchall()
        for (kp_text,) in orphans:
            new_id = _uuid.uuid4().hex
            conn.execute(
                text(f"""
                    INSERT INTO knowledge_points
                        (kp_id, kp_text, kp_type, importance, created_at, updated_at)
                    VALUES (:id, :t, 'term', 'medium', {ts}, {ts})
                """),
                {"id": new_id, "t": kp_text},
            )

        # 回填 kp_id
        if pg:
            conn.execute(text("""
                UPDATE study_records sr
                SET kp_id = kp.kp_id
                FROM knowledge_points kp
                WHERE sr.kp_text = kp.kp_text
                  AND sr.kp_id IS NULL
            """))
        else:
            conn.execute(text("""
                UPDATE study_records
                SET kp_id = (
                    SELECT kp_id FROM knowledge_points
                    WHERE knowledge_points.kp_text = study_records.kp_text
                    LIMIT 1
                )
                WHERE kp_id IS NULL
            """))

    # ═══════════════════════════════════════════════════════════════════════
    # 3. chunk_knowledge_points：添加 kp_id 列并回填
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "chunk_knowledge_points") and _table_exists(conn, "knowledge_points"):
        ckp_cols = _col_names(conn, "chunk_knowledge_points")
        if "kp_id" not in ckp_cols:
            op.execute(text("ALTER TABLE chunk_knowledge_points ADD COLUMN kp_id VARCHAR(32)"))
            if pg:
                conn.execute(text("""
                    UPDATE chunk_knowledge_points ckp
                    SET kp_id = kp.kp_id
                    FROM knowledge_points kp
                    WHERE ckp.kp_text = kp.kp_text
                """))
            else:
                conn.execute(text("""
                    UPDATE chunk_knowledge_points
                    SET kp_id = (
                        SELECT kp_id FROM knowledge_points
                        WHERE knowledge_points.kp_text = chunk_knowledge_points.kp_text
                        LIMIT 1
                    )
                """))

    # ═══════════════════════════════════════════════════════════════════════
    # 4. review_records：添加 kp_id 列并回填
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "review_records") and _table_exists(conn, "knowledge_points"):
        rr_cols = _col_names(conn, "review_records")
        if "kp_id" not in rr_cols:
            op.execute(text("ALTER TABLE review_records ADD COLUMN kp_id VARCHAR(32)"))
            if pg:
                conn.execute(text("""
                    UPDATE review_records rr
                    SET kp_id = kp.kp_id
                    FROM knowledge_points kp
                    WHERE rr.kp_text = kp.kp_text
                """))
            else:
                conn.execute(text("""
                    UPDATE review_records
                    SET kp_id = (
                        SELECT kp_id FROM knowledge_points
                        WHERE knowledge_points.kp_text = review_records.kp_text
                        LIMIT 1
                    )
                """))

    # ═══════════════════════════════════════════════════════════════════════
    # 5. extract_caches：重命名 result_json → result，添加 expired_at
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "extract_caches"):
        ec_cols = _col_names(conn, "extract_caches")
        if "result_json" in ec_cols and "result" not in ec_cols:
            # SQLite 3.25+ 和 PostgreSQL 均支持 RENAME COLUMN
            op.execute(text("ALTER TABLE extract_caches RENAME COLUMN result_json TO result"))
        if "expired_at" not in _col_names(conn, "extract_caches"):
            ts_type = "TIMESTAMP WITH TIME ZONE" if pg else "TIMESTAMP"
            op.execute(text(f"ALTER TABLE extract_caches ADD COLUMN expired_at {ts_type}"))

    # ═══════════════════════════════════════════════════════════════════════
    # 6. llm_call_logs：补充新列，重命名 error_message → error_details
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "llm_call_logs"):
        llm_cols = _col_names(conn, "llm_call_logs")

        # 重命名（仅 PostgreSQL；SQLite 3.25+ 也支持，但旧 llm_call_logs 列名在 SQLite 不一致）
        if "error_message" in llm_cols and "error_details" not in llm_cols:
            op.execute(text("ALTER TABLE llm_call_logs RENAME COLUMN error_message TO error_details"))
            llm_cols = _col_names(conn, "llm_call_logs")  # 刷新

        new_llm_cols = [
            ("run_id",            "VARCHAR(32)"),
            ("step_id",           "VARCHAR(32)"),
            ("qa_id",             "TEXT"),
            ("user_id",           "VARCHAR(64)"),
            ("total_tokens",      "INTEGER"),
            ("cost_usd",          "FLOAT"),
            ("error_details",     "TEXT"),  # 如果 rename 未执行（老列名不存在），兜底创建
        ]
        for col_name, col_type in new_llm_cols:
            if col_name not in llm_cols:
                op.execute(text(f"ALTER TABLE llm_call_logs ADD COLUMN {col_name} {col_type}"))

    # ═══════════════════════════════════════════════════════════════════════
    # 7. tool_call_logs：补充新列，重命名字段
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "tool_call_logs"):
        tcl_cols = _col_names(conn, "tool_call_logs")

        if "error_message" in tcl_cols and "error_details" not in tcl_cols:
            op.execute(text("ALTER TABLE tool_call_logs RENAME COLUMN error_message TO error_details"))
            tcl_cols = _col_names(conn, "tool_call_logs")

        # 旧列名 args_json/result_json → args/result
        if "args_json" in tcl_cols and "args" not in tcl_cols:
            op.execute(text("ALTER TABLE tool_call_logs RENAME COLUMN args_json TO args"))
            tcl_cols = _col_names(conn, "tool_call_logs")
        if "result_json" in tcl_cols and "result" not in tcl_cols:
            op.execute(text("ALTER TABLE tool_call_logs RENAME COLUMN result_json TO result"))
            tcl_cols = _col_names(conn, "tool_call_logs")

        new_tcl_cols = [
            ("run_id",        "VARCHAR(32)"),
            ("step_id",       "VARCHAR(32)"),
            ("qa_id",         "TEXT"),
            ("user_id",       "VARCHAR(64)"),
            ("args",          "TEXT"),
            ("result",        "TEXT"),
            ("error_details", "TEXT"),
        ]
        for col_name, col_type in new_tcl_cols:
            if col_name not in tcl_cols:
                op.execute(text(f"ALTER TABLE tool_call_logs ADD COLUMN {col_name} {col_type}"))

    # ═══════════════════════════════════════════════════════════════════════
    # 8. qa_records：重命名 tools_used_json → tools_used
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "qa_records"):
        qa_cols = _col_names(conn, "qa_records")
        if "tools_used_json" in qa_cols and "tools_used" not in qa_cols:
            op.execute(text("ALTER TABLE qa_records RENAME COLUMN tools_used_json TO tools_used"))

    # ═══════════════════════════════════════════════════════════════════════
    # 9. users：补充 password_hash（最早期版本可能没有）
    # ═══════════════════════════════════════════════════════════════════════
    if _table_exists(conn, "users"):
        if "password_hash" not in _col_names(conn, "users"):
            op.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))


def downgrade() -> None:
    """
    逆向迁移：移除本版本添加的列。
    注意：kp_text PK → kp_id PK 的切换不可逆（数据已回填，旧 PK 约束无法完全还原）。
    建议在生产环境回退时使用数据库备份，而非依赖此 downgrade。
    """
    conn = op.get_bind()
    pg = _is_postgres(conn)

    # 移除 llm_call_logs 新列
    if _table_exists(conn, "llm_call_logs"):
        for col in ("run_id", "step_id", "qa_id", "user_id", "total_tokens", "cost_usd"):
            if col in _col_names(conn, "llm_call_logs"):
                op.drop_column("llm_call_logs", col)

    # 移除 tool_call_logs 新列
    if _table_exists(conn, "tool_call_logs"):
        for col in ("run_id", "step_id", "qa_id", "user_id"):
            if col in _col_names(conn, "tool_call_logs"):
                op.drop_column("tool_call_logs", col)

    # 移除 study_records.kp_id
    if _table_exists(conn, "study_records"):
        if "kp_id" in _col_names(conn, "study_records"):
            op.drop_column("study_records", "kp_id")

    # 移除 extract_caches.expired_at
    if _table_exists(conn, "extract_caches"):
        if "expired_at" in _col_names(conn, "extract_caches"):
            op.drop_column("extract_caches", "expired_at")
