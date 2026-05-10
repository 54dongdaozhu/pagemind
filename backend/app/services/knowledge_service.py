from datetime import datetime, timezone

import uuid

from sqlalchemy import delete, func, select

from app.core.database import KnowledgePoint, StudyRecord, StudyStatusHistory, get_db
from app.models.knowledge import LEARNING_THRESHOLD, STATUS_KNOWN, STATUS_LEARNING, STATUS_UNKNOWN


def _upsert_knowledge_point(db, kp_text: str, kp_type: str) -> str:
    """确保 knowledge_points 中存在该知识点，返回 kp_id。"""
    existing = db.execute(
        select(KnowledgePoint).where(KnowledgePoint.kp_text == kp_text)
    ).scalar_one_or_none()

    if existing is not None:
        return existing.kp_id

    now = datetime.now(timezone.utc)
    kp = KnowledgePoint(
        kp_id=uuid.uuid4().hex,
        kp_text=kp_text,
        kp_type=kp_type,
        importance="medium",
        created_at=now,
        updated_at=now,
    )
    db.add(kp)
    db.flush()
    return kp.kp_id


def _write_status_history(
    db,
    record_id: str,
    user_id: str,
    kp_id: str | None,
    kp_text: str,
    old_status: str | None,
    new_status: str,
    trigger: str,
    click_count: int,
) -> None:
    """写一条状态变更历史，只在状态实际发生变化时调用。"""
    db.add(
        StudyStatusHistory(
            history_id=uuid.uuid4().hex,
            record_id=record_id,
            user_id=user_id,
            kp_id=kp_id,
            kp_text=kp_text,
            old_status=old_status,
            new_status=new_status,
            trigger=trigger,
            click_count_snapshot=click_count,
            created_at=datetime.now(timezone.utc),
        )
    )


def record_click(user_id: str, kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        kp_id = _upsert_knowledge_point(db, kp_text, kp_type)

        record = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if record is None:
            new_count = 1
            new_status = STATUS_UNKNOWN
            record_id = uuid.uuid4().hex
            record = StudyRecord(
                record_id=record_id,
                user_id=user_id,
                kp_id=kp_id,
                kp_text=kp_text,
                status=new_status,
                click_count=new_count,
                last_clicked_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(record)
            db.flush()
            _write_status_history(
                db, record_id, user_id, kp_id, kp_text,
                old_status=None, new_status=new_status,
                trigger="click", click_count=new_count,
            )
        else:
            old_status = record.status
            new_count = record.click_count + 1

            if record.status == STATUS_KNOWN:
                new_status = STATUS_KNOWN
            elif new_count >= LEARNING_THRESHOLD:
                new_status = STATUS_LEARNING
            else:
                new_status = STATUS_UNKNOWN

            record.kp_id = kp_id
            record.click_count = new_count
            record.last_clicked_at = now
            record.status = new_status
            record.updated_at = now

            if old_status != new_status:
                _write_status_history(
                    db, record.record_id, user_id, kp_id, kp_text,
                    old_status=old_status, new_status=new_status,
                    trigger="click", click_count=new_count,
                )

        db.commit()

    return {"kp_text": kp_text, "status": new_status, "click_count": new_count}


def mark_known(user_id: str, kp_text: str, kp_type: str):
    now = datetime.now(timezone.utc)

    with get_db() as db:
        kp_id = _upsert_knowledge_point(db, kp_text, kp_type)

        record = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if record is None:
            record_id = uuid.uuid4().hex
            record = StudyRecord(
                record_id=record_id,
                user_id=user_id,
                kp_id=kp_id,
                kp_text=kp_text,
                status=STATUS_KNOWN,
                click_count=0,
                marked_known_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(record)
            db.flush()
            _write_status_history(
                db, record_id, user_id, kp_id, kp_text,
                old_status=None, new_status=STATUS_KNOWN,
                trigger="mark_known", click_count=0,
            )
        else:
            old_status = record.status
            record.kp_id = kp_id
            record.status = STATUS_KNOWN
            record.marked_known_at = now
            record.updated_at = now

            if old_status != STATUS_KNOWN:
                _write_status_history(
                    db, record.record_id, user_id, kp_id, kp_text,
                    old_status=old_status, new_status=STATUS_KNOWN,
                    trigger="mark_known", click_count=record.click_count,
                )

        db.commit()

    return {"kp_text": kp_text, "status": STATUS_KNOWN}


def unmark_known(user_id: str, kp_text: str):
    now = datetime.now(timezone.utc)
    with get_db() as db:
        record = db.execute(
            select(StudyRecord).where(
                StudyRecord.user_id == user_id,
                StudyRecord.kp_text == kp_text,
            )
        ).scalar_one_or_none()

        if record is None:
            return {"kp_text": kp_text, "status": STATUS_UNKNOWN}

        old_status = record.status
        new_status = STATUS_LEARNING if record.click_count >= LEARNING_THRESHOLD else STATUS_UNKNOWN
        record.status = new_status
        record.marked_known_at = None
        record.updated_at = now

        if old_status != new_status:
            _write_status_history(
                db, record.record_id, user_id, record.kp_id, kp_text,
                old_status=old_status, new_status=new_status,
                trigger="unmark_known", click_count=record.click_count,
            )

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
