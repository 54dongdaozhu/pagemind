"""add skill_tree_snapshots table

Revision ID: 013
Revises: 012
Create Date: 2026-05-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if "skill_tree_snapshots" in inspect(conn).get_table_names():
        return
    op.create_table(
        "skill_tree_snapshots",
        sa.Column("snapshot_id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("input_summary", sa.JSON(), nullable=True),
        sa.Column("tree_json", sa.JSON(), nullable=True),
        sa.Column("web_search_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("workflow_runs.run_id"), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_skill_tree_snapshots_user_id", "skill_tree_snapshots", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_skill_tree_snapshots_user_id", table_name="skill_tree_snapshots")
    op.drop_table("skill_tree_snapshots")
