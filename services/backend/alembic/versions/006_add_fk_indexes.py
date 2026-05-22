"""add indexes to FK columns

Revision ID: 006
Revises: 005
Create Date: 2026-05-16
"""
import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_INDEXES = [
    # (index_name, table, column)
    ("ix_documents_user_id", "documents", "user_id"),
    ("ix_study_records_user_id", "study_records", "user_id"),
    ("ix_study_records_doc_id", "study_records", "doc_id"),
    ("ix_study_records_kp_id", "study_records", "kp_id"),
    ("ix_study_status_history_record_id", "study_status_history", "record_id"),
    ("ix_study_status_history_user_id", "study_status_history", "user_id"),
    ("ix_review_records_user_id", "review_records", "user_id"),
    ("ix_review_records_doc_id", "review_records", "doc_id"),
    ("ix_qa_records_user_id", "qa_records", "user_id"),
    ("ix_workflow_runs_user_id", "workflow_runs", "user_id"),
    ("ix_workflow_runs_doc_id", "workflow_runs", "doc_id"),
    ("ix_llm_call_logs_run_id", "llm_call_logs", "run_id"),
    ("ix_llm_call_logs_step_id", "llm_call_logs", "step_id"),
    ("ix_llm_call_logs_qa_id", "llm_call_logs", "qa_id"),
    ("ix_llm_call_logs_user_id", "llm_call_logs", "user_id"),
    ("ix_tool_call_logs_run_id", "tool_call_logs", "run_id"),
    ("ix_tool_call_logs_step_id", "tool_call_logs", "step_id"),
    ("ix_tool_call_logs_qa_id", "tool_call_logs", "qa_id"),
    ("ix_tool_call_logs_user_id", "tool_call_logs", "user_id"),
    ("ix_event_log_user_id", "event_log", "user_id"),
    ("ix_event_log_entity_id", "event_log", "entity_id"),
    ("ix_chunks_version_id", "chunks", "version_id"),
    ("ix_workflow_steps_run_id", "workflow_steps", "run_id"),
    ("ix_study_status_history_kp_id", "study_status_history", "kp_id"),
    ("ix_review_records_kp_id", "review_records", "kp_id"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, table, col in _INDEXES:
        conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})"))


def downgrade() -> None:
    conn = op.get_bind()
    for name, _table, _col in _INDEXES:
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
