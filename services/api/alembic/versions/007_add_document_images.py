"""add document_images table

Revision ID: 007
Revises: 006
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("vision_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("doc_id", "user_id", "asset_id", name="uq_doc_user_image"),
    )
    conn = op.get_bind()
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_document_images_doc_id ON document_images (doc_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_document_images_user_id ON document_images (user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_document_images_asset_id ON document_images (asset_id)"))


def downgrade() -> None:
    op.drop_table("document_images")
