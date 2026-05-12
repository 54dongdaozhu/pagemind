"""rebuild legacy SQLite knowledge tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-12

The 002 migration can only add compatibility columns on SQLite. It cannot
change primary keys in place, so old local databases may still have
knowledge_points keyed by kp_text and chunk_knowledge_points requiring kp_text.
The ORM now writes chunk links by kp_id, so rebuild those tables on SQLite.
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    return table_name in inspect(conn).get_table_names()


def _col_names(conn, table_name: str) -> set[str]:
    return {col["name"] for col in inspect(conn).get_columns(table_name)}


def _pk_cols(conn, table_name: str) -> list[str]:
    return inspect(conn).get_pk_constraint(table_name).get("constrained_columns") or []


def _rebuild_knowledge_points(conn) -> None:
    if not _table_exists(conn, "knowledge_points"):
        return

    cols = _col_names(conn, "knowledge_points")
    if "kp_id" not in cols:
        op.execute(text("ALTER TABLE knowledge_points ADD COLUMN kp_id VARCHAR(32)"))

    conn.execute(text("""
        UPDATE knowledge_points
        SET kp_id = lower(hex(randomblob(16)))
        WHERE kp_id IS NULL OR kp_id = ''
    """))

    if _pk_cols(conn, "knowledge_points") == ["kp_id"]:
        return

    op.execute(text("""
        CREATE TABLE knowledge_points_new (
            kp_id VARCHAR(32) NOT NULL,
            kp_text TEXT NOT NULL,
            kp_type VARCHAR(32) NOT NULL,
            explanation TEXT,
            importance VARCHAR(32) NOT NULL DEFAULT 'medium',
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            PRIMARY KEY (kp_id),
            CONSTRAINT uq_kp_text UNIQUE (kp_text)
        )
    """))
    op.execute(text("""
        INSERT OR IGNORE INTO knowledge_points_new
            (kp_id, kp_text, kp_type, explanation, importance, created_at, updated_at)
        SELECT
            kp_id,
            kp_text,
            kp_type,
            explanation,
            COALESCE(importance, 'medium'),
            created_at,
            updated_at
        FROM knowledge_points
    """))
    op.execute(text("DROP TABLE knowledge_points"))
    op.execute(text("ALTER TABLE knowledge_points_new RENAME TO knowledge_points"))


def _rebuild_chunk_knowledge_points(conn) -> None:
    if not _table_exists(conn, "chunk_knowledge_points"):
        return

    cols = _col_names(conn, "chunk_knowledge_points")
    pk_cols = _pk_cols(conn, "chunk_knowledge_points")
    if "kp_text" not in cols and pk_cols == ["doc_id", "chunk_index", "kp_id"]:
        return

    if "kp_id" not in cols:
        op.execute(text("ALTER TABLE chunk_knowledge_points ADD COLUMN kp_id VARCHAR(32)"))
        cols = _col_names(conn, "chunk_knowledge_points")

    if "kp_text" in cols:
        conn.execute(text("""
            UPDATE chunk_knowledge_points
            SET kp_id = (
                SELECT kp.kp_id
                FROM knowledge_points kp
                WHERE kp.kp_text = chunk_knowledge_points.kp_text
                LIMIT 1
            )
            WHERE kp_id IS NULL OR kp_id = ''
        """))

    op.execute(text("""
        CREATE TABLE chunk_knowledge_points_new (
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            kp_id VARCHAR(32) NOT NULL,
            confidence FLOAT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (doc_id, chunk_index, kp_id),
            FOREIGN KEY(kp_id) REFERENCES knowledge_points (kp_id)
        )
    """))
    op.execute(text("""
        INSERT OR IGNORE INTO chunk_knowledge_points_new
            (doc_id, chunk_index, kp_id, confidence, created_at)
        SELECT doc_id, chunk_index, kp_id, confidence, created_at
        FROM chunk_knowledge_points
        WHERE kp_id IS NOT NULL AND kp_id != ''
    """))
    op.execute(text("DROP TABLE chunk_knowledge_points"))
    op.execute(text("ALTER TABLE chunk_knowledge_points_new RENAME TO chunk_knowledge_points"))


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return

    op.execute(text("PRAGMA foreign_keys=OFF"))
    _rebuild_knowledge_points(conn)
    _rebuild_chunk_knowledge_points(conn)
    op.execute(text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Keep the upgraded schema. Rebuilding back to the legacy kp_text primary
    # key would risk losing kp_id-only relationships.
    pass
