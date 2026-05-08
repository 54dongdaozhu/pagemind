from contextlib import contextmanager

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL


Base = declarative_base()


class UserKnowledge(Base):
    __tablename__ = "user_knowledge"

    kp_text = Column(Text, primary_key=True)
    kp_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="unknown")
    click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime(timezone=True))
    marked_known_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)


class ExtractCache(Base):
    __tablename__ = "extract_cache"

    chunk_id = Column(Text, primary_key=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    doc_id = Column(Text, primary_key=True)
    chunk_index = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    embedding_json = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)


class RagDocument(Base):
    __tablename__ = "rag_documents"

    doc_id = Column(Text, primary_key=True)
    title = Column(Text)
    summary = Column(Text, nullable=False)
    chunk_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
