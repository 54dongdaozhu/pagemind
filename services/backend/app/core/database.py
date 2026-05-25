from contextlib import contextmanager

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL


Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    username = Column(String(128), unique=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    email_verified = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String(64), ForeignKey("users.user_id"), primary_key=True)
    background_text = Column(Text, nullable=False)
    identity = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)
    learning_goals = Column(JSON, nullable=True)
    skill_level = Column(Text, nullable=True)
    tech_stack = Column(JSON, nullable=True)
    knowledge_gaps = Column(JSON, nullable=True)
    learning_style = Column(Text, nullable=True)
    depth_preference = Column(Text, nullable=True)
    urgency = Column(Text, nullable=True)
    domain_focus = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    title = Column(Text)
    summary = Column(Text, nullable=False, default="")
    chunk_count = Column(Integer, nullable=False, default=0)
    current_version_id = Column(Text)
    status = Column(String(32), nullable=False, default="indexed")
    doc_type = Column(String(64), nullable=True)
    doc_type_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    version_id = Column(Text, primary_key=True)
    doc_id = Column(Text, ForeignKey("documents.doc_id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    source_name = Column(Text)
    content_hash = Column(String(128), nullable=False)
    raw_text = Column(Text)
    render_html = Column(Text, nullable=True)
    render_outline = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_id", "version_number", name="uq_document_version_number"),
    )


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    generated_doc_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    source_task_id = Column(String(64), nullable=True, index=True)
    title = Column(Text, nullable=False)
    topic = Column(Text, nullable=False)
    requirements = Column(Text, nullable=False, default="")
    html_snapshot = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "source_task_id", name="uq_generated_doc_user_task"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    doc_id = Column(Text, ForeignKey("documents.doc_id"), primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    version_id = Column(Text, ForeignKey("document_versions.version_id"), index=True)
    content = Column(Text, nullable=False)
    # JSON 类型：SQLAlchemy 在 PostgreSQL 上映射为 JSON，在 SQLite 上映射为 TEXT
    # 旧数据库中该列为 TEXT，JSON 类型会自动 json.loads，兼容无缝
    embedding_json = Column(JSON)
    token_count = Column(Integer)
    content_hash = Column(String(128))
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── 全局知识点（Global Knowledge Points）────────────────────────────────────
# kp_id 为 UUID 主键，kp_text 降为 UNIQUE 约束
# 旧版本以 kp_text 作为 PK，migrate_db 负责切换
class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    kp_id = Column(String(32), primary_key=True)
    kp_text = Column(Text, nullable=False)
    kp_type = Column(String(32), nullable=False)
    explanation = Column(Text)
    importance = Column(String(32), nullable=False, default="medium")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("kp_text", name="uq_kp_text"),
    )


# ── 分块-知识点关联（M:N）────────────────────────────────────────────────────
class ChunkKnowledgePoint(Base):
    __tablename__ = "chunk_knowledge_points"

    doc_id = Column(Text, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"), primary_key=True)
    confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), nullable=False)


class EmbeddingRecord(Base):
    __tablename__ = "embedding_records"

    embedding_id = Column(Text, primary_key=True)
    doc_id = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    model = Column(String(128), nullable=False)
    vector_store = Column(String(64), nullable=False, default="chroma")
    vector_id = Column(Text)
    content_hash = Column(String(128))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", "model", name="uq_embedding_chunk_model"),
    )


# ── 用户学习记录（当前状态快照）────────────────────────────────────────────
# kp_id：关联 knowledge_points UUID PK（nullable 兼容旧数据迁移过渡期）
# kp_text：非 FK 的冗余列，供 API 层直接查询，无需 JOIN
class StudyRecord(Base):
    __tablename__ = "study_records"

    record_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    doc_id = Column(Text, ForeignKey("documents.doc_id"), index=True)
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"), index=True)
    kp_text = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="unknown")
    click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime(timezone=True))
    marked_known_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "kp_text", name="uq_study_user_knowledge"),
    )


# ── 学习状态历史（Append-only，每次状态变更追加一行）────────────────────────
class StudyStatusHistory(Base):
    __tablename__ = "study_status_history"

    history_id = Column(String(32), primary_key=True)
    record_id = Column(Text, ForeignKey("study_records.record_id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"), index=True)
    kp_text = Column(Text, nullable=False)
    old_status = Column(String(32))
    new_status = Column(String(32), nullable=False)
    # 'click' | 'mark_known' | 'unmark_known' | 'reset'
    trigger = Column(String(64))
    click_count_snapshot = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ReviewRecord(Base):
    __tablename__ = "review_records"

    review_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    doc_id = Column(Text, ForeignKey("documents.doc_id"), index=True)
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"), index=True)
    kp_text = Column(Text)
    review_type = Column(String(32), nullable=False, default="manual")
    result = Column(String(32))
    note = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    next_review_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)


class QARecord(Base):
    __tablename__ = "qa_records"

    qa_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    doc_id = Column(Text, ForeignKey("documents.doc_id"), index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    intent = Column(String(32))
    agent = Column(String(64))
    tools_used = Column(JSON)
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False)


class QAReference(Base):
    __tablename__ = "qa_references"

    qa_id = Column(Text, ForeignKey("qa_records.qa_id"), primary_key=True)
    doc_id = Column(Text, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    score = Column(Float)
    retrieval_method = Column(String(32), nullable=False, default="keyword")
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── 工作流追踪（WorkflowRun 替代原 AITask）──────────────────────────────────
# 一次完整工作流执行的顶层记录
# workflow_type: 'knowledge_extraction' | 'rag_indexing' | 'agent_chat'
# trigger_source: 'api' | 'cron' | 'webhook'
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    run_id = Column(String(32), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    doc_id = Column(Text, ForeignKey("documents.doc_id"), index=True)
    workflow_type = Column(String(64), nullable=False)
    trigger_source = Column(String(32), nullable=False, default="api")
    trigger_ref = Column(Text)
    status = Column(String(32), nullable=False, default="pending")
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_details = Column(JSON)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


# 工作流内部子步骤（discover / filter / rank / embed 等）
class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    step_id = Column(String(32), primary_key=True)
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    step_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_details = Column(JSON)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── LLM 调用日志（增加 run_id/step_id/qa_id 上下文关联）──────────────────
# task_id 旧列在 DB 中保留但不在模型中管理（已废弃）
class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    call_id = Column(Text, primary_key=True)
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"), index=True)
    step_id = Column(String(32), ForeignKey("workflow_steps.step_id"), index=True)
    qa_id = Column(Text, ForeignKey("qa_records.qa_id"), index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    purpose = Column(String(100))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    cost_usd = Column(Float)
    latency_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)
    error_details = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── Agent 工具调用日志────────────────────────────────────────────────────────
class ToolCallLog(Base):
    __tablename__ = "tool_call_logs"

    call_id = Column(Text, primary_key=True)
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"), index=True)
    step_id = Column(String(32), ForeignKey("workflow_steps.step_id"), index=True)
    qa_id = Column(Text, ForeignKey("qa_records.qa_id"), index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    tool_name = Column(String(128), nullable=False)
    args = Column(JSON)
    result = Column(JSON)
    latency_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)
    error_details = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── 通用事件审计日志（Append-only）──────────────────────────────────────────
# entity_type: 'document' | 'knowledge_point' | 'study_record' | ...
# event_type:  'document.uploaded' | 'kp.marked_known' | 'study.reset' | ...
class EventLog(Base):
    __tablename__ = "event_log"

    event_id = Column(String(32), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Text, nullable=False, index=True)
    event_type = Column(String(128), nullable=False)
    before_state = Column(JSON)
    after_state = Column(JSON)
    meta = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False)


# ── 知识提取缓存────────────────────────────────────────────────────────────
# result 字段存储提取结果（JSON），expired_at 为 TTL 过期时间
class ExtractCache(Base):
    __tablename__ = "extract_caches"

    chunk_id = Column(Text, primary_key=True)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expired_at = Column(DateTime(timezone=True))


class DocumentImage(Base):
    __tablename__ = "document_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Text, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    asset_id = Column(String(64), nullable=False, index=True)
    page_num = Column(Integer, nullable=True)
    alt_text = Column(Text, nullable=True)
    vision_description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_id", "user_id", "asset_id", name="uq_doc_user_image"),
    )


class SkillTreeSnapshot(Base):
    __tablename__ = "skill_tree_snapshots"

    snapshot_id = Column(String(32), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    status = Column(String(32), nullable=False)        # generating | ready | failed
    trigger = Column(String(32), nullable=False)       # manual | auto_threshold
    input_summary = Column(JSON, nullable=True)
    tree_json = Column(JSON, nullable=True)
    web_search_used = Column(Boolean, nullable=False, default=False)
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


RagChunk = Chunk
RagDocument = Document


# ── 引擎 & 会话────────────────────────────────────────────────────────────
engine_options = {"pool_pre_ping": True, "pool_recycle": 1800}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    engine_options["connect_args"] = {
        "connect_timeout": 10,
        "options": "-c statement_timeout=60000",
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


from sqlalchemy import event as _sa_event  # noqa: E402


@_sa_event.listens_for(engine, "handle_error")
def _invalidate_on_db_error(context):
    """Discard connections that hit a DBAPI-level error (e.g. PGRES_TUPLES_OK corruption)."""
    if context.connection is not None:
        context.connection.invalidate()


@contextmanager
def get_db():
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """启动时运行所有 Alembic 迁移（等价于 `alembic upgrade head`）。"""
    import os
    from alembic.config import Config
    from alembic import command

    # alembic.ini 与本文件的相对位置：services/backend/app/core/ → services/backend/
    _backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(_backend_dir, "alembic.ini"))
    command.upgrade(cfg, "head")
