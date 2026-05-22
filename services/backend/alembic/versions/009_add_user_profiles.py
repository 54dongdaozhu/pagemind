"""add user_profiles table

Revision ID: 009
Revises: 008
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = set(inspect(conn).get_table_names())
    if "user_profiles" not in existing:
        op.create_table(
            "user_profiles",
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.user_id"), primary_key=True),
            sa.Column("background_text", sa.Text, nullable=False),
            sa.Column("identity", sa.Text, nullable=True),
            sa.Column("purpose", sa.Text, nullable=True),
            sa.Column("learning_goals", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("user_profiles")
