"""add generated_documents table

Revision ID: 011
Revises: 010
Create Date: 2026-05-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = set(inspect(conn).get_table_names())
    if "generated_documents" not in existing:
        op.create_table(
            "generated_documents",
            sa.Column("generated_doc_id", sa.Text(), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("source_task_id", sa.String(64), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("topic", sa.Text(), nullable=False),
            sa.Column("requirements", sa.Text(), nullable=False, server_default=""),
            sa.Column("html_snapshot", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "source_task_id", name="uq_generated_doc_user_task"),
        )
        op.create_index("ix_generated_documents_user_id", "generated_documents", ["user_id"])
        op.create_index("ix_generated_documents_source_task_id", "generated_documents", ["source_task_id"])


def downgrade() -> None:
    conn = op.get_bind()
    existing = set(inspect(conn).get_table_names())
    if "generated_documents" in existing:
        op.drop_index("ix_generated_documents_source_task_id", table_name="generated_documents")
        op.drop_index("ix_generated_documents_user_id", table_name="generated_documents")
        op.drop_table("generated_documents")
