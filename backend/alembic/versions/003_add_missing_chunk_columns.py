"""add missing columns to legacy chunks table

Revision ID: 003
Revises: 002
Create Date: 2026-05-11
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    return table_name in inspect(conn).get_table_names()


def _col_names(conn, table_name: str) -> set[str]:
    return {col["name"] for col in inspect(conn).get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "chunks"):
        return

    cols = _col_names(conn, "chunks")
    if "embedding_json" not in cols:
        op.execute(text("ALTER TABLE chunks ADD COLUMN embedding_json JSON"))


def downgrade() -> None:
    # SQLite cannot reliably drop columns across supported local versions, and
    # keeping this nullable compatibility column is harmless.
    pass
