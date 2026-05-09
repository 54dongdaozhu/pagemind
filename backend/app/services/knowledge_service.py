from datetime import datetime, timezone

import uuid

from sqlalchemy import delete, func, select

from app.core.database import StudyRecord, get_db
from app.models.knowledge import LEARNING_THRESHOLD, STATUS_KNOWN, STATUS_LEARNING, STATUS_UNKNOWN


def record_click(user_id: str, kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        knowledge = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if knowledge is None:
            knowledge = StudyRecord(
                record_id=uuid.uuid4().hex,
                user_id=user_id,
                kp_text=kp_text,
                status=STATUS_UNKNOWN,
                click_count=1,
                last_clicked_at=now,
                created_at=now,
                updated_at=now,
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
            knowledge.updated_at = now

        db.commit()

    return {"kp_text": kp_text, "status": new_status, "click_count": new_count}


def mark_known(user_id: str, kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        knowledge = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if knowledge is None:
            db.add(
                StudyRecord(
                    record_id=uuid.uuid4().hex,
                    user_id=user_id,
                    kp_text=kp_text,
                    status=STATUS_KNOWN,
                    click_count=0,
                    marked_known_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            knowledge.status = STATUS_KNOWN
            knowledge.marked_known_at = now
            knowledge.updated_at = now

        db.commit()

    return {"kp_text": kp_text, "status": STATUS_KNOWN}


def unmark_known(user_id: str, kp_text: str):
    now = datetime.now(timezone.utc)
    with get_db() as db:
        knowledge = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if knowledge is None:
            return {"kp_text": kp_text, "status": STATUS_UNKNOWN}

        new_status = STATUS_LEARNING if knowledge.click_count >= LEARNING_THRESHOLD else STATUS_UNKNOWN
        knowledge.status = new_status
        knowledge.marked_known_at = None
        knowledge.updated_at = now
        db.commit()

    return {"kp_text": kp_text, "status": new_status}


def get_status_batch(user_id: str, kp_texts: list[str]):
    if not kp_texts:
        return {"items": []}

    with get_db() as db:
        rows = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text.in_(kp_texts),
            )
        ).scalars().all()

    items = [
        {"kp_text": row.kp_text, "status": row.status, "click_count": row.click_count}
        for row in rows
    ]
    return {"items": items}


def get_stats(user_id: str):
    with get_db() as db:
        rows = db.execute(
            select(StudyRecord.status, func.count())
            .select_from(StudyRecord)
            .where(StudyRecord.user_id == user_id)
            .group_by(StudyRecord.status)
        ).all()

    stats = {STATUS_UNKNOWN: 0, STATUS_LEARNING: 0, STATUS_KNOWN: 0}
    for status, count in rows:
        stats[status] = count
    return stats


def reset_all(user_id: str):
    with get_db() as db:
        db.execute(delete(StudyRecord).where(StudyRecord.user_id == user_id))
        db.commit()
    return {"message": "已重置所有掌握记录"}
