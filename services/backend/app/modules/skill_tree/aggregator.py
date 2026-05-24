from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import Document, LLMCallLog, QARecord, StudyRecord, get_db
from app.modules.profile.service import get_profile


def aggregate_user_signals(user_id: str, days: int = 60) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    with get_db() as db:
        docs = db.execute(
            select(Document.title, Document.doc_type, Document.summary)
            .where(Document.user_id == user_id)
            .order_by(Document.updated_at.desc())
            .limit(10)
        ).all()

        deep_kp_count = db.execute(
            select(LLMCallLog.call_id)
            .where(
                LLMCallLog.user_id == user_id,
                LLMCallLog.purpose == "deep_explain",
                LLMCallLog.created_at >= since,
            )
            .limit(50)
        ).fetchall()

        learning_kps = db.execute(
            select(StudyRecord.kp_text, StudyRecord.click_count)
            .where(
                StudyRecord.user_id == user_id,
                StudyRecord.status == "learning",
            )
            .order_by(StudyRecord.click_count.desc())
            .limit(30)
        ).all()

        known_kps = db.execute(
            select(StudyRecord.kp_text)
            .where(
                StudyRecord.user_id == user_id,
                StudyRecord.status == "known",
            )
            .limit(50)
        ).all()

        qa_topics = db.execute(
            select(QARecord.question)
            .where(
                QARecord.user_id == user_id,
                QARecord.created_at >= since,
            )
            .order_by(QARecord.created_at.desc())
            .limit(20)
        ).all()

    profile = get_profile(user_id)

    return {
        "docs": [
            {"title": r.title, "doc_type": r.doc_type, "summary": (r.summary or "")[:200]}
            for r in docs
        ],
        "deep_kp_count": len(deep_kp_count),
        "learning_kps": [{"text": r.kp_text, "clicks": r.click_count} for r in learning_kps],
        "known_kps": [r.kp_text for r in known_kps],
        "qa_topics": [r.question for r in qa_topics],
        "profile": profile if profile else {},
    }


def build_signals_section(signals: dict) -> str:
    parts = []

    if signals["docs"]:
        titles = [d["title"] for d in signals["docs"] if d["title"]]
        parts.append(f"近期上传文档（{len(signals['docs'])}份）：{', '.join(titles[:5])}")

    if signals.get("deep_kp_count"):
        parts.append(f"深入讲解次数：{signals['deep_kp_count']} 次（强兴趣信号）")

    if signals["learning_kps"]:
        kp_texts = [f"{k['text']}（点击{k['clicks']}次）" for k in signals["learning_kps"][:10]]
        parts.append(f"学习中知识点：{', '.join(kp_texts)}")

    if signals["known_kps"]:
        parts.append(f"已掌握知识点（{len(signals['known_kps'])}个）：{', '.join(signals['known_kps'][:8])}")

    if signals["qa_topics"]:
        parts.append(f"最近提问（{len(signals['qa_topics'])}条）：{'; '.join(signals['qa_topics'][:5])}")

    return "\n".join(parts) if parts else "暂无行为数据"


def build_profile_section(profile: dict) -> str:
    if not profile:
        return "无用户画像"
    parts = []
    if profile.get("identity"):
        parts.append(f"身份：{profile['identity']}")
    if profile.get("skill_level"):
        parts.append(f"技能水平：{profile['skill_level']}")
    if profile.get("domain_focus"):
        domains = profile["domain_focus"]
        if isinstance(domains, list):
            parts.append(f"关注领域：{', '.join(str(d) for d in domains[:5])}")
    if profile.get("knowledge_gaps"):
        gaps = profile["knowledge_gaps"]
        if isinstance(gaps, list):
            parts.append(f"已知盲区：{', '.join(str(g) for g in gaps[:5])}")
    return "\n".join(parts) if parts else "无详细画像"
