"""initial schema — create all tables in new format

Revision ID: 001
Revises:
Create Date: 2026-05-10

策略：每张表都用 IF NOT EXISTS 语义（先 inspect 再建），使本迁移对已有旧库
也是幂等的。旧库上该版本完成后，002 负责把旧格式列升级为新格式。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables(conn) -> set:
    return set(inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    existing = _existing_tables(conn)

    # ── users ────────────────────────────────────────────────────────────
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("user_id", sa.String(64), primary_key=True),
            sa.Column("username", sa.String(128), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username", name="uq_users_username"),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )

    # ── documents ────────────────────────────────────────────────────────
    if "documents" not in existing:
        op.create_table(
            "documents",
            sa.Column("doc_id", sa.Text, primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("title", sa.Text, nullable=True),
            sa.Column("summary", sa.Text, nullable=False, server_default=""),
            sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("current_version_id", sa.Text, nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="indexed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── document_versions ────────────────────────────────────────────────
    if "document_versions" not in existing:
        op.create_table(
            "document_versions",
            sa.Column("version_id", sa.Text, primary_key=True),
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=False),
            sa.Column("version_number", sa.Integer, nullable=False),
            sa.Column("source_name", sa.Text, nullable=True),
            sa.Column("content_hash", sa.String(128), nullable=False),
            sa.Column("raw_text", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("doc_id", "version_number", name="uq_document_version_number"),
        )
        op.create_index("ix_document_versions_doc_id", "document_versions", ["doc_id"])

    # ── chunks ───────────────────────────────────────────────────────────
    if "chunks" not in existing:
        op.create_table(
            "chunks",
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=False),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("version_id", sa.Text, sa.ForeignKey("document_versions.version_id"), nullable=True),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("embedding_json", sa.JSON, nullable=True),
            sa.Column("token_count", sa.Integer, nullable=True),
            sa.Column("content_hash", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("doc_id", "chunk_index", name="pk_chunks"),
        )

    # ── knowledge_points（新格式：kp_id 为 UUID PK）─────────────────────
    if "knowledge_points" not in existing:
        op.create_table(
            "knowledge_points",
            sa.Column("kp_id", sa.String(32), primary_key=True),
            sa.Column("kp_text", sa.Text, nullable=False),
            sa.Column("kp_type", sa.String(32), nullable=False),
            sa.Column("explanation", sa.Text, nullable=True),
            sa.Column("importance", sa.String(32), nullable=False, server_default="medium"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("kp_text", name="uq_kp_text"),
        )

    # ── chunk_knowledge_points ───────────────────────────────────────────
    if "chunk_knowledge_points" not in existing:
        op.create_table(
            "chunk_knowledge_points",
            sa.Column("doc_id", sa.Text, nullable=False),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("kp_id", sa.String(32), sa.ForeignKey("knowledge_points.kp_id"), nullable=False),
            sa.Column("confidence", sa.Float, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("doc_id", "chunk_index", "kp_id", name="pk_chunk_knowledge_points"),
        )

    # ── embedding_records ────────────────────────────────────────────────
    if "embedding_records" not in existing:
        op.create_table(
            "embedding_records",
            sa.Column("embedding_id", sa.Text, primary_key=True),
            sa.Column("doc_id", sa.Text, nullable=False),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("model", sa.String(128), nullable=False),
            sa.Column("vector_store", sa.String(64), nullable=False, server_default="chroma"),
            sa.Column("vector_id", sa.Text, nullable=True),
            sa.Column("content_hash", sa.String(128), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("doc_id", "chunk_index", "model", name="uq_embedding_chunk_model"),
        )

    # ── study_records ────────────────────────────────────────────────────
    if "study_records" not in existing:
        op.create_table(
            "study_records",
            sa.Column("record_id", sa.Text, primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=True),
            sa.Column("kp_id", sa.String(32), sa.ForeignKey("knowledge_points.kp_id"), nullable=True),
            sa.Column("kp_text", sa.Text, nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("click_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_clicked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("marked_known_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "kp_text", name="uq_study_user_knowledge"),
        )

    # ── study_status_history ─────────────────────────────────────────────
    if "study_status_history" not in existing:
        op.create_table(
            "study_status_history",
            sa.Column("history_id", sa.String(32), primary_key=True),
            sa.Column("record_id", sa.Text, sa.ForeignKey("study_records.record_id"), nullable=False),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("kp_id", sa.String(32), sa.ForeignKey("knowledge_points.kp_id"), nullable=True),
            sa.Column("kp_text", sa.Text, nullable=False),
            sa.Column("old_status", sa.String(32), nullable=True),
            sa.Column("new_status", sa.String(32), nullable=False),
            sa.Column("trigger", sa.String(64), nullable=True),
            sa.Column("click_count_snapshot", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ssh_user_time", "study_status_history", ["user_id", "created_at"])

    # ── review_records ───────────────────────────────────────────────────
    if "review_records" not in existing:
        op.create_table(
            "review_records",
            sa.Column("review_id", sa.Text, primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=True),
            sa.Column("kp_id", sa.String(32), sa.ForeignKey("knowledge_points.kp_id"), nullable=True),
            sa.Column("kp_text", sa.Text, nullable=True),
            sa.Column("review_type", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("result", sa.String(32), nullable=True),
            sa.Column("note", sa.Text, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── qa_records ───────────────────────────────────────────────────────
    if "qa_records" not in existing:
        op.create_table(
            "qa_records",
            sa.Column("qa_id", sa.Text, primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=True),
            sa.Column("question", sa.Text, nullable=False),
            sa.Column("answer", sa.Text, nullable=False),
            sa.Column("intent", sa.String(32), nullable=True),
            sa.Column("agent", sa.String(64), nullable=True),
            sa.Column("tools_used", sa.JSON, nullable=True),
            sa.Column("latency_ms", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_qa_records_doc_id", "qa_records", ["doc_id"])

    # ── qa_references ────────────────────────────────────────────────────
    if "qa_references" not in existing:
        op.create_table(
            "qa_references",
            sa.Column("qa_id", sa.Text, sa.ForeignKey("qa_records.qa_id"), nullable=False),
            sa.Column("doc_id", sa.Text, nullable=False),
            sa.Column("chunk_index", sa.Integer, nullable=False),
            sa.Column("score", sa.Float, nullable=True),
            sa.Column("retrieval_method", sa.String(32), nullable=False, server_default="keyword"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("qa_id", "doc_id", "chunk_index", name="pk_qa_references"),
        )

    # ── workflow_runs ────────────────────────────────────────────────────
    if "workflow_runs" not in existing:
        op.create_table(
            "workflow_runs",
            sa.Column("run_id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("doc_id", sa.Text, sa.ForeignKey("documents.doc_id"), nullable=True),
            sa.Column("workflow_type", sa.String(64), nullable=False),
            sa.Column("trigger_source", sa.String(32), nullable=False, server_default="api"),
            sa.Column("trigger_ref", sa.Text, nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("input_data", sa.JSON, nullable=True),
            sa.Column("output_data", sa.JSON, nullable=True),
            sa.Column("error_details", sa.JSON, nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id", "created_at"])
        op.create_index(
            "ix_workflow_runs_active",
            "workflow_runs",
            ["status"],
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )

    # ── workflow_steps ───────────────────────────────────────────────────
    if "workflow_steps" not in existing:
        op.create_table(
            "workflow_steps",
            sa.Column("step_id", sa.String(32), primary_key=True),
            sa.Column("run_id", sa.String(32), sa.ForeignKey("workflow_runs.run_id"), nullable=False),
            sa.Column("step_name", sa.String(100), nullable=False),
            sa.Column("step_order", sa.Integer, nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("input_data", sa.JSON, nullable=True),
            sa.Column("output_data", sa.JSON, nullable=True),
            sa.Column("error_details", sa.JSON, nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_workflow_steps_run_id", "workflow_steps", ["run_id"])

    # ── llm_call_logs ────────────────────────────────────────────────────
    if "llm_call_logs" not in existing:
        op.create_table(
            "llm_call_logs",
            sa.Column("call_id", sa.Text, primary_key=True),
            sa.Column("run_id", sa.String(32), sa.ForeignKey("workflow_runs.run_id"), nullable=True),
            sa.Column("step_id", sa.String(32), sa.ForeignKey("workflow_steps.step_id"), nullable=True),
            sa.Column("qa_id", sa.Text, sa.ForeignKey("qa_records.qa_id"), nullable=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("model", sa.String(128), nullable=False),
            sa.Column("purpose", sa.String(100), nullable=True),
            sa.Column("prompt_tokens", sa.Integer, nullable=True),
            sa.Column("completion_tokens", sa.Integer, nullable=True),
            sa.Column("total_tokens", sa.Integer, nullable=True),
            sa.Column("cost_usd", sa.Float, nullable=True),
            sa.Column("latency_ms", sa.Integer, nullable=True),
            sa.Column("success", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("error_details", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_llm_call_logs_user_time", "llm_call_logs", ["user_id", "created_at"])
        op.create_index("ix_llm_call_logs_run_id", "llm_call_logs", ["run_id"])

    # ── tool_call_logs ───────────────────────────────────────────────────
    if "tool_call_logs" not in existing:
        op.create_table(
            "tool_call_logs",
            sa.Column("call_id", sa.Text, primary_key=True),
            sa.Column("run_id", sa.String(32), sa.ForeignKey("workflow_runs.run_id"), nullable=True),
            sa.Column("step_id", sa.String(32), sa.ForeignKey("workflow_steps.step_id"), nullable=True),
            sa.Column("qa_id", sa.Text, sa.ForeignKey("qa_records.qa_id"), nullable=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("tool_name", sa.String(128), nullable=False),
            sa.Column("args", sa.JSON, nullable=True),
            sa.Column("result", sa.JSON, nullable=True),
            sa.Column("latency_ms", sa.Integer, nullable=True),
            sa.Column("success", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("error_details", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── event_log ────────────────────────────────────────────────────────
    if "event_log" not in existing:
        op.create_table(
            "event_log",
            sa.Column("event_id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("entity_type", sa.String(64), nullable=False),
            sa.Column("entity_id", sa.Text, nullable=False),
            sa.Column("event_type", sa.String(128), nullable=False),
            sa.Column("before_state", sa.JSON, nullable=True),
            sa.Column("after_state", sa.JSON, nullable=True),
            sa.Column("meta", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_event_log_entity", "event_log", ["entity_type", "entity_id"])
        op.create_index("ix_event_log_user_time", "event_log", ["user_id", "created_at"])

    # ── extract_caches ───────────────────────────────────────────────────
    if "extract_caches" not in existing:
        op.create_table(
            "extract_caches",
            sa.Column("chunk_id", sa.Text, primary_key=True),
            sa.Column("result", sa.JSON, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # 按 FK 依赖的逆序删表
    for table in [
        "extract_caches",
        "event_log",
        "tool_call_logs",
        "llm_call_logs",
        "workflow_steps",
        "workflow_runs",
        "qa_references",
        "qa_records",
        "review_records",
        "study_status_history",
        "study_records",
        "embedding_records",
        "chunk_knowledge_points",
        "knowledge_points",
        "chunks",
        "document_versions",
        "documents",
        "users",
    ]:
        op.drop_table(table)
