from contextlib import contextmanager

from sqlalchemy import (
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
    inspect,
    text,
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
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"))
    title = Column(Text)
    summary = Column(Text, nullable=False, default="")
    chunk_count = Column(Integer, nullable=False, default=0)
    current_version_id = Column(Text)
    status = Column(String(32), nullable=False, default="indexed")
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
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_id", "version_number", name="uq_document_version_number"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    doc_id = Column(Text, ForeignKey("documents.doc_id"), primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    version_id = Column(Text, ForeignKey("document_versions.version_id"))
    content = Column(Text, nullable=False)
    embedding_json = Column(Text)
    token_count = Column(Integer)
    content_hash = Column(String(128))
    created_at = Column(DateTime(timezone=True), nullable=False)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    kp_text = Column(Text, primary_key=True)
    kp_type = Column(String(32), nullable=False)
    explanation = Column(Text)
    importance = Column(String(32), nullable=False, default="medium")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))


class UserKnowledge(Base):
    __tablename__ = "user_knowledge"

    kp_text = Column(Text, primary_key=True)
    kp_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="unknown")
    click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime(timezone=True))
    marked_known_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)


class ChunkKnowledgePoint(Base):
    __tablename__ = "chunk_knowledge_points"

    doc_id = Column(Text, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    kp_text = Column(Text, ForeignKey("knowledge_points.kp_text"), primary_key=True)
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
    embedding_json = Column(Text)
    content_hash = Column(String(128))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", "model", name="uq_embedding_chunk_model"),
    )


class StudyRecord(Base):
    __tablename__ = "study_records"

    record_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
    kp_text = Column(Text, ForeignKey("knowledge_points.kp_text"), nullable=False)
    status = Column(String(32), nullable=False, default="unknown")
    click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime(timezone=True))
    marked_known_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "kp_text", name="uq_study_user_knowledge"),
    )


class ReviewRecord(Base):
    __tablename__ = "review_records"

    review_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
    kp_text = Column(Text, ForeignKey("knowledge_points.kp_text"))
    review_type = Column(String(32), nullable=False, default="manual")
    result = Column(String(32))
    note = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    next_review_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)


class QARecord(Base):
    __tablename__ = "qa_records"

    qa_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"), index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    intent = Column(String(32))
    agent = Column(String(64))
    tools_used_json = Column(Text)
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


class AITask(Base):
    __tablename__ = "ai_tasks"

    task_id = Column(Text, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
    task_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    input_json = Column(Text)
    output_json = Column(Text)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    call_id = Column(Text, primary_key=True)
    task_id = Column(Text, ForeignKey("ai_tasks.task_id"))
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    purpose = Column(String(64))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    latency_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ToolCallLog(Base):
    __tablename__ = "tool_call_logs"

    call_id = Column(Text, primary_key=True)
    task_id = Column(Text, ForeignKey("ai_tasks.task_id"))
    tool_name = Column(String(128), nullable=False)
    args_json = Column(Text)
    result_json = Column(Text)
    latency_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ExtractCache(Base):
    __tablename__ = "extract_caches"

    chunk_id = Column(Text, primary_key=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


RagChunk = Chunk
RagDocument = Document


engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_db()


def migrate_db():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        if "password_hash" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
