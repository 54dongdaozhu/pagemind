"""add doc_type to documents

Revision ID: 008
Revises: 007
Create Date: 2026-05-18
"""
import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_type", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("doc_type_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "doc_type_confidence")
    op.drop_column("documents", "doc_type")
