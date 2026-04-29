import sqlite3
from contextlib import contextmanager

from app.core.config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_knowledge (
                kp_text TEXT PRIMARY KEY,
                kp_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unknown',
                click_count INTEGER NOT NULL DEFAULT 0,
                last_clicked_at TEXT,
                marked_known_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
