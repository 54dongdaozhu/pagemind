from datetime import datetime

from app.core.database import get_db
from app.models.knowledge import LEARNING_THRESHOLD, STATUS_KNOWN, STATUS_LEARNING, STATUS_UNKNOWN


def record_click(kp_text: str, kp_type: str):
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            conn.execute("""
                INSERT INTO user_knowledge
                (kp_text, kp_type, status, click_count, last_clicked_at, created_at)
                VALUES (?, ?, 'unknown', 1, ?, ?)
            """, (kp_text, kp_type, now, now))
            new_count = 1
            new_status = STATUS_UNKNOWN
        else:
            new_count = row["click_count"] + 1
            if row["status"] == STATUS_KNOWN:
                new_status = STATUS_KNOWN
            elif new_count >= LEARNING_THRESHOLD:
                new_status = STATUS_LEARNING
            else:
                new_status = STATUS_UNKNOWN

            conn.execute("""
                UPDATE user_knowledge
                SET click_count = ?, last_clicked_at = ?, status = ?
                WHERE kp_text = ?
            """, (new_count, now, new_status, kp_text))

        conn.commit()

    return {"kp_text": kp_text, "status": new_status, "click_count": new_count}


def mark_known(kp_text: str, kp_type: str):
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            conn.execute("""
                INSERT INTO user_knowledge
                (kp_text, kp_type, status, click_count, marked_known_at, created_at)
                VALUES (?, ?, 'known', 0, ?, ?)
            """, (kp_text, kp_type, now, now))
        else:
            conn.execute("""
                UPDATE user_knowledge
                SET status = 'known', marked_known_at = ?
                WHERE kp_text = ?
            """, (now, kp_text))

        conn.commit()

    return {"kp_text": kp_text, "status": STATUS_KNOWN}


def unmark_known(kp_text: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            return {"kp_text": kp_text, "status": STATUS_UNKNOWN}

        new_status = STATUS_LEARNING if row["click_count"] >= LEARNING_THRESHOLD else STATUS_UNKNOWN
        conn.execute("""
            UPDATE user_knowledge
            SET status = ?, marked_known_at = NULL
            WHERE kp_text = ?
        """, (new_status, kp_text))
        conn.commit()

    return {"kp_text": kp_text, "status": new_status}


def get_status_batch(kp_texts: list[str]):
    if not kp_texts:
        return {"items": []}

    with get_db() as conn:
        placeholders = ",".join(["?"] * len(kp_texts))
        rows = conn.execute(
            f"SELECT kp_text, status, click_count FROM user_knowledge WHERE kp_text IN ({placeholders})",
            kp_texts,
        ).fetchall()

    items = [
        {"kp_text": row["kp_text"], "status": row["status"], "click_count": row["click_count"]}
        for row in rows
    ]
    return {"items": items}


def get_stats():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM user_knowledge
            GROUP BY status
        """).fetchall()

    stats = {STATUS_UNKNOWN: 0, STATUS_LEARNING: 0, STATUS_KNOWN: 0}
    for row in rows:
        stats[row["status"]] = row["count"]
    return stats


def reset_all():
    with get_db() as conn:
        conn.execute("DELETE FROM user_knowledge")
        conn.commit()
    return {"message": "已重置所有学习记录"}
