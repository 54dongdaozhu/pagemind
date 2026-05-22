"""add email_verified to users

Revision ID: 005
Revises: 004
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("users")}
    if "email_verified" not in cols:
        # server_default='1'：现有用户默认已验证，避免升级后锁定已有账号
        op.add_column(
            "users",
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        return
    op.drop_column("users", "email_verified")
