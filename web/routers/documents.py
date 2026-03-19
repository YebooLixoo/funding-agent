from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.config import get_settings
from web.database import get_db, async_session as default_async_session
from web.dependencies import get_current_user
from web.models.document import UserDocument
from web.models.user import User
from web.schemas.document import DocumentDetailResponse, DocumentResponse
from web.services.document_processor import extract_text_from_file

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

# Configurable session factory for background tasks (allows test override)
_session_factory = None


def set_session_factory(factory):
    global _session_factory
    _session_factory = factory


def _get_session_factory():
    return _session_factory or default_async_session


async def _process_document(doc_id: uuid.UUID) -> None:
    """Background task: extract text and keywords from document."""
    session_factory = _get_session_factory()
    async with session_factory() as db:
        result = await db.execute(select(UserDocument).where(UserDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        doc.upload_status = "processing"
        await db.commit()

        try:
            # Extract text
            text = extract_text_from_file(doc.file_path, doc.file_type)
            doc.extracted_text = text

            # Extract keywords via LLM (optional — skip if no API key)
            try:
                from web.services.keyword_extractor import extract_keywords_from_text
                keywords = await extract_keywords_from_text(text)
                doc.extracted_keywords = keywords
            except Exception:
                doc.extracted_keywords = {"error": "Keyword extraction unavailable"}

            doc.upload_status = "completed"
        except Exception as e:
            doc.upload_status = "failed"
            doc.extracted_keywords = {"error": str(e)}

        await db.commit()


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_type: str = Form("resume"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file_type not in ("resume", "paper", "cv"):
        raise HTTPException(status_code=400, detail="file_type must be resume, paper, or cv")

    # Create upload directory
    upload_dir = Path(settings.upload_dir) / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_id = uuid.uuid4()
    ext = Path(file.filename or "upload").suffix or ".pdf"
    file_path = upload_dir / f"{file_id}{ext}"

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_size_mb}MB limit")

    file_path.write_bytes(content)

    doc = UserDocument(
        id=file_id,
        user_id=current_user.id,
        filename=file.filename or "upload",
        file_path=str(file_path),
        file_type=file_type,
        upload_status="pending",
    )
    db.add(doc)
    await db.flush()

    # Process in background
    background_tasks.add_task(_process_document, doc.id)

    return doc


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserDocument)
        .where(UserDocument.user_id == current_user.id)
        .order_by(UserDocument.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserDocument).where(
            UserDocument.id == doc_id,
            UserDocument.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserDocument).where(
            UserDocument.id == doc_id,
            UserDocument.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception:
        pass

    await db.delete(doc)


@router.post("/{doc_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserDocument).where(
            UserDocument.id == doc_id,
            UserDocument.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.upload_status = "pending"
    await db.flush()

    background_tasks.add_task(_process_document, doc.id)
    return doc
