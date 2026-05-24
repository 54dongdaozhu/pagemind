import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.core.database import GeneratedDocument, User, get_db
from app.modules.auth.service import get_current_user


router = APIRouter(prefix="/api/generated-documents", tags=["generated-documents"])


class GeneratedDocumentCreateRequest(BaseModel):
    source_task_id: str | None = None
    title: str | None = None
    topic: str
    requirements: str = ""
    html_snapshot: str = Field(min_length=1)


class GeneratedDocumentListItem(BaseModel):
    generated_doc_id: str
    title: str
    topic: str
    requirements: str = ""
    source_task_id: str | None = None
    created_at: str
    updated_at: str


class GeneratedDocumentResponse(GeneratedDocumentListItem):
    html_snapshot: str


class GeneratedDocumentListResponse(BaseModel):
    documents: list[GeneratedDocumentListItem]


def _to_list_item(doc: GeneratedDocument) -> GeneratedDocumentListItem:
    return GeneratedDocumentListItem(
        generated_doc_id=doc.generated_doc_id,
        title=doc.title,
        topic=doc.topic,
        requirements=doc.requirements or "",
        source_task_id=doc.source_task_id,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )


def _to_response(doc: GeneratedDocument) -> GeneratedDocumentResponse:
    return GeneratedDocumentResponse(
        **_to_list_item(doc).model_dump(),
        html_snapshot=doc.html_snapshot,
    )


@router.post("", response_model=GeneratedDocumentResponse)
def save_generated_document(
    request: GeneratedDocumentCreateRequest,
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    title = (request.title or request.topic or "生成文档").strip() or "生成文档"
    source_task_id = request.source_task_id.strip() if request.source_task_id else None

    with get_db() as db:
        existing = None
        if source_task_id:
            existing = db.scalar(
                select(GeneratedDocument).where(
                    GeneratedDocument.user_id == current_user.user_id,
                    GeneratedDocument.source_task_id == source_task_id,
                )
            )

        if existing:
            existing.title = title
            existing.topic = request.topic.strip()
            existing.requirements = request.requirements.strip()
            existing.html_snapshot = request.html_snapshot
            existing.updated_at = now
            doc = existing
        else:
            doc = GeneratedDocument(
                generated_doc_id=uuid.uuid4().hex,
                user_id=current_user.user_id,
                source_task_id=source_task_id,
                title=title,
                topic=request.topic.strip(),
                requirements=request.requirements.strip(),
                html_snapshot=request.html_snapshot,
                created_at=now,
                updated_at=now,
            )
            db.add(doc)

        db.commit()
        db.refresh(doc)
        return _to_response(doc)


@router.get("", response_model=GeneratedDocumentListResponse)
def list_generated_documents(current_user: User = Depends(get_current_user)):
    with get_db() as db:
        docs = db.scalars(
            select(GeneratedDocument)
            .where(GeneratedDocument.user_id == current_user.user_id)
            .order_by(desc(GeneratedDocument.updated_at))
        ).all()
        return GeneratedDocumentListResponse(documents=[_to_list_item(doc) for doc in docs])


@router.get("/{generated_doc_id}", response_model=GeneratedDocumentResponse)
def get_generated_document(generated_doc_id: str, current_user: User = Depends(get_current_user)):
    with get_db() as db:
        doc = db.get(GeneratedDocument, generated_doc_id)
        if doc is None or doc.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成文档不存在")
        return _to_response(doc)

