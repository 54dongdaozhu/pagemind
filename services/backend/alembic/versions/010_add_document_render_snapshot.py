"""add document render snapshot columns

Revision ID: 010
Revises: 009
Create Date: 2026-05-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = {c["name"] for c in inspect(conn).get_columns("document_versions")}
    if "render_html" not in columns:
        op.add_column("document_versions", sa.Column("render_html", sa.Text(), nullable=True))
    if "render_outline" not in columns:
        op.add_column("document_versions", sa.Column("render_outline", sa.JSON(), nullable=True))


def downgrade() -> None:
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("document_versions")}
    if "render_outline" in columns:
        op.drop_column("document_versions", "render_outline")
    if "render_html" in columns:
        op.drop_column("document_versions", "render_html")
