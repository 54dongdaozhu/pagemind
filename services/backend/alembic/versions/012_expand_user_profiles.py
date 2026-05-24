"""expand user_profiles with extended fields

Revision ID: 012
Revises: 011
Create Date: 2026-05-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

_NEW_COLS = [
    ("skill_level",      sa.Text()),
    ("tech_stack",       sa.JSON()),
    ("knowledge_gaps",   sa.JSON()),
    ("learning_style",   sa.Text()),
    ("depth_preference", sa.Text()),
    ("urgency",          sa.Text()),
    ("domain_focus",     sa.JSON()),
]


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = {c["name"] for c in inspect(conn).get_columns("user_profiles")}
    for col_name, col_type in _NEW_COLS:
        if col_name not in existing_cols:
            op.add_column("user_profiles", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    for col_name, _ in _NEW_COLS:
        op.drop_column("user_profiles", col_name)
