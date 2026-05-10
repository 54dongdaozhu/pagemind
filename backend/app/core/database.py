from contextlib import contextmanager
import uuid

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
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"))
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
    record_id = Column(Text, ForeignKey("study_records.record_id"), nullable=False)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"))
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
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
    kp_id = Column(String(32), ForeignKey("knowledge_points.kp_id"))
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
    user_id = Column(String(64), ForeignKey("users.user_id"))
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
    user_id = Column(String(64), ForeignKey("users.user_id"))
    doc_id = Column(Text, ForeignKey("documents.doc_id"))
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
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"), nullable=False)
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
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"))
    step_id = Column(String(32), ForeignKey("workflow_steps.step_id"))
    qa_id = Column(Text, ForeignKey("qa_records.qa_id"))
    user_id = Column(String(64), ForeignKey("users.user_id"))
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
    run_id = Column(String(32), ForeignKey("workflow_runs.run_id"))
    step_id = Column(String(32), ForeignKey("workflow_steps.step_id"))
    qa_id = Column(Text, ForeignKey("qa_records.qa_id"))
    user_id = Column(String(64), ForeignKey("users.user_id"))
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
    user_id = Column(String(64), ForeignKey("users.user_id"))
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Text, nullable=False)
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


RagChunk = Chunk
RagDocument = Document


# ── 引擎 & 会话────────────────────────────────────────────────────────────
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


def _col_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def migrate_db():
    """
    幂等迁移函数：检测并补齐已有数据库中缺失的列和结构。
    新表由 create_all 自动创建，此函数只处理已有表的列变更。
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if not table_names:
        return

    is_sqlite = DATABASE_URL.startswith("sqlite")
    is_postgres = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")

    with engine.begin() as conn:
        # ── 1. users: 补充 password_hash 列 ─────────────────────────────
        if "users" in table_names:
            if "password_hash" not in _col_names(inspector, "users"):
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))

        # ── 2. knowledge_points: kp_text PK → kp_id PK ──────────────────
        # 检测旧 schema（kp_text 为 PK，kp_id 不存在）并完成迁移
        if "knowledge_points" in table_names:
            kp_cols = _col_names(inspector, "knowledge_points")

            if "kp_id" not in kp_cols:
                # Step A: 添加 kp_id 列并填充 UUID
                conn.execute(text("ALTER TABLE knowledge_points ADD COLUMN kp_id VARCHAR(32)"))
                rows = conn.execute(text("SELECT kp_text FROM knowledge_points")).fetchall()
                for (kp_text,) in rows:
                    new_id = uuid.uuid4().hex
                    conn.execute(
                        text("UPDATE knowledge_points SET kp_id = :id WHERE kp_text = :t"),
                        {"id": new_id, "t": kp_text},
                    )

                if is_postgres:
                    # Step B: 删除子表中指向 knowledge_points(kp_text) 的 FK 约束
                    for child_table in ("study_records", "chunk_knowledge_points", "review_records"):
                        if child_table not in table_names:
                            continue
                        fks = inspector.get_foreign_keys(child_table)
                        for fk in fks:
                            if fk.get("referred_table") == "knowledge_points" and fk.get("name"):
                                conn.execute(text(
                                    f"ALTER TABLE {child_table} DROP CONSTRAINT IF EXISTS {fk['name']}"
                                ))

                    # Step C: 切换 knowledge_points 主键
                    conn.execute(text("ALTER TABLE knowledge_points ALTER COLUMN kp_id SET NOT NULL"))
                    conn.execute(text("ALTER TABLE knowledge_points DROP CONSTRAINT knowledge_points_pkey"))
                    conn.execute(text(
                        "ALTER TABLE knowledge_points ADD CONSTRAINT uq_kp_text UNIQUE (kp_text)"
                    ))
                    conn.execute(text("ALTER TABLE knowledge_points ADD PRIMARY KEY (kp_id)"))

        # ── 3. study_records: 新增 kp_id 列并回填 ───────────────────────
        if "study_records" in table_names:
            sr_cols = _col_names(inspector, "study_records")

            if "kp_id" not in sr_cols:
                conn.execute(text("ALTER TABLE study_records ADD COLUMN kp_id VARCHAR(32)"))

            if "kp_id" in _col_names(inspector, "study_records") and "knowledge_points" in table_names:
                # 确保 study_records 中的 kp_text 在 knowledge_points 中存在（修复旧 FK 缺失问题）
                orphaned = conn.execute(text("""
                    SELECT DISTINCT sr.kp_text
                    FROM study_records sr
                    LEFT JOIN knowledge_points kp ON sr.kp_text = kp.kp_text
                    WHERE kp.kp_text IS NULL
                """)).fetchall()

                now_str = "now()" if is_postgres else "datetime('now')"
                for (kp_text,) in orphaned:
                    new_id = uuid.uuid4().hex
                    conn.execute(
                        text(f"""
                            INSERT INTO knowledge_points (kp_id, kp_text, kp_type, importance, created_at, updated_at)
                            VALUES (:id, :t, 'term', 'medium', {now_str}, {now_str})
                        """),
                        {"id": new_id, "t": kp_text},
                    )

                # 回填 kp_id
                if is_postgres:
                    conn.execute(text("""
                        UPDATE study_records sr
                        SET kp_id = kp.kp_id
                        FROM knowledge_points kp
                        WHERE sr.kp_text = kp.kp_text
                          AND sr.kp_id IS NULL
                    """))
                else:
                    conn.execute(text("""
                        UPDATE study_records
                        SET kp_id = (
                            SELECT kp_id FROM knowledge_points
                            WHERE knowledge_points.kp_text = study_records.kp_text
                            LIMIT 1
                        )
                        WHERE kp_id IS NULL
                    """))

        # ── 4. chunk_knowledge_points: 新增 kp_id 列并回填 ──────────────
        if "chunk_knowledge_points" in table_names and "knowledge_points" in table_names:
            ckp_cols = _col_names(inspector, "chunk_knowledge_points")
            if "kp_id" not in ckp_cols:
                conn.execute(text("ALTER TABLE chunk_knowledge_points ADD COLUMN kp_id VARCHAR(32)"))
                if is_postgres:
                    conn.execute(text("""
                        UPDATE chunk_knowledge_points ckp
                        SET kp_id = kp.kp_id
                        FROM knowledge_points kp
                        WHERE ckp.kp_text = kp.kp_text
                    """))
                else:
                    conn.execute(text("""
                        UPDATE chunk_knowledge_points
                        SET kp_id = (
                            SELECT kp_id FROM knowledge_points
                            WHERE knowledge_points.kp_text = chunk_knowledge_points.kp_text
                            LIMIT 1
                        )
                    """))

        # ── 5. review_records: 新增 kp_id 列并回填 ──────────────────────
        if "review_records" in table_names and "knowledge_points" in table_names:
            rr_cols = _col_names(inspector, "review_records")
            if "kp_id" not in rr_cols:
                conn.execute(text("ALTER TABLE review_records ADD COLUMN kp_id VARCHAR(32)"))
                if is_postgres:
                    conn.execute(text("""
                        UPDATE review_records rr
                        SET kp_id = kp.kp_id
                        FROM knowledge_points kp
                        WHERE rr.kp_text = kp.kp_text
                    """))
                else:
                    conn.execute(text("""
                        UPDATE review_records
                        SET kp_id = (
                            SELECT kp_id FROM knowledge_points
                            WHERE knowledge_points.kp_text = review_records.kp_text
                            LIMIT 1
                        )
                    """))

        # ── 6. extract_caches: result_json → result，新增 expired_at ────
        if "extract_caches" in table_names:
            ec_cols = _col_names(inspector, "extract_caches")
            if "result_json" in ec_cols and "result" not in ec_cols:
                # SQLite 3.25+ 和 PostgreSQL 均支持 RENAME COLUMN
                conn.execute(text("ALTER TABLE extract_caches RENAME COLUMN result_json TO result"))
            if "expired_at" not in _col_names(inspector, "extract_caches"):
                ts_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "TIMESTAMP"
                conn.execute(text(
                    f"ALTER TABLE extract_caches ADD COLUMN expired_at {ts_type}"
                ))

        # ── 7. llm_call_logs: 新增上下文关联列 ──────────────────────────
        if "llm_call_logs" in table_names:
            llm_cols = _col_names(inspector, "llm_call_logs")
            new_cols = [
                ("run_id", "VARCHAR(32)"),
                ("step_id", "VARCHAR(32)"),
                ("qa_id", "TEXT"),
                ("user_id", "VARCHAR(64)"),
                ("total_tokens", "INTEGER"),
                ("cost_usd", "FLOAT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in llm_cols:
                    conn.execute(text(
                        f"ALTER TABLE llm_call_logs ADD COLUMN {col_name} {col_type}"
                    ))
            # error_message 重命名为 error_details（只做 PostgreSQL，SQLite 跳过）
            if is_postgres and "error_message" in llm_cols and "error_details" not in llm_cols:
                conn.execute(text(
                    "ALTER TABLE llm_call_logs RENAME COLUMN error_message TO error_details"
                ))

        # ── 8. tool_call_logs: 新增上下文关联列 ─────────────────────────
        if "tool_call_logs" in table_names:
            tcl_cols = _col_names(inspector, "tool_call_logs")
            new_cols = [
                ("run_id", "VARCHAR(32)"),
                ("step_id", "VARCHAR(32)"),
                ("qa_id", "TEXT"),
                ("user_id", "VARCHAR(64)"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in tcl_cols:
                    conn.execute(text(
                        f"ALTER TABLE tool_call_logs ADD COLUMN {col_name} {col_type}"
                    ))
            if is_postgres and "error_message" in tcl_cols and "error_details" not in tcl_cols:
                conn.execute(text(
                    "ALTER TABLE tool_call_logs RENAME COLUMN error_message TO error_details"
                ))

        # ── 9. qa_records: tools_used_json → tools_used ──────────────────
        if "qa_records" in table_names:
            qa_cols = _col_names(inspector, "qa_records")
            if "tools_used_json" in qa_cols and "tools_used" not in qa_cols:
                conn.execute(text("ALTER TABLE qa_records RENAME COLUMN tools_used_json TO tools_used"))
