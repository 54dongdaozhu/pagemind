from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.core.database import UserKnowledge, get_db
from app.models.knowledge import LEARNING_THRESHOLD, STATUS_KNOWN, STATUS_LEARNING, STATUS_UNKNOWN


def record_click(kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        knowledge = db.get(UserKnowledge, kp_text)

        if knowledge is None:
            knowledge = UserKnowledge(
                kp_text=kp_text,
                kp_type=kp_type,
                status=STATUS_UNKNOWN,
                click_count=1,
                last_clicked_at=now,
                created_at=now,
            )
            db.add(knowledge)
            new_count = 1
            new_status = STATUS_UNKNOWN
        else:
            new_count = knowledge.click_count + 1
            if knowledge.status == STATUS_KNOWN:
                new_status = STATUS_KNOWN
            elif new_count >= LEARNING_THRESHOLD:
                new_status = STATUS_LEARNING
            else:
                new_status = STATUS_UNKNOWN

            knowledge.click_count = new_count
            knowledge.last_clicked_at = now
            knowledge.status = new_status

        db.commit()

    return {"kp_text": kp_text, "status": new_status, "click_count": new_count}


def mark_known(kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        knowledge = db.get(UserKnowledge, kp_text)

        if knowledge is None:
            db.add(
                UserKnowledge(
                    kp_text=kp_text,
                    kp_type=kp_type,
                    status=STATUS_KNOWN,
                    click_count=0,
                    marked_known_at=now,
                    created_at=now,
                )
            )
        else:
            knowledge.status = STATUS_KNOWN
            knowledge.marked_known_at = now

        db.commit()

    return {"kp_text": kp_text, "status": STATUS_KNOWN}


def unmark_known(kp_text: str):
    with get_db() as db:
        knowledge = db.get(UserKnowledge, kp_text)

        if knowledge is None:
            return {"kp_text": kp_text, "status": STATUS_UNKNOWN}

        new_status = STATUS_LEARNING if knowledge.click_count >= LEARNING_THRESHOLD else STATUS_UNKNOWN
        knowledge.status = new_status
        knowledge.marked_known_at = None
        db.commit()

    return {"kp_text": kp_text, "status": new_status}


def get_status_batch(kp_texts: list[str]):
    if not kp_texts:
        return {"items": []}

    with get_db() as db:
        rows = db.execute(
            select(UserKnowledge).where(UserKnowledge.kp_text.in_(kp_texts))
        ).scalars().all()

    items = [
        {"kp_text": row.kp_text, "status": row.status, "click_count": row.click_count}
        for row in rows
    ]
    return {"items": items}


def get_stats():
    with get_db() as db:
        rows = db.execute(
            select(UserKnowledge.status, func.count())
            .select_from(UserKnowledge)
            .group_by(UserKnowledge.status)
        ).all()

    stats = {STATUS_UNKNOWN: 0, STATUS_LEARNING: 0, STATUS_KNOWN: 0}
    for status, count in rows:
        stats[status] = count
    return stats


def reset_all():
    with get_db() as db:
        db.execute(delete(UserKnowledge))
        db.commit()
    return {"message": "已重置所有掌握记录"}
