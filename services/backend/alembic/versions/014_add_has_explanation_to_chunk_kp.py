"""add has_explanation to chunk_knowledge_points

Revision ID: 014
Revises: 013
Create Date: 2026-05-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [c["name"] for c in inspect(conn).get_columns("chunk_knowledge_points")]
    if "has_explanation" not in cols:
        op.add_column(
            "chunk_knowledge_points",
            sa.Column("has_explanation", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chunk_knowledge_points", "has_explanation")
