import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.knowledge_base import KBDocument, KBStructuredSource, DocumentStatus, SourceType
from app.schemas.auth import CurrentUser
from app.schemas.knowledge_base import (
    KBDocumentListResponse,
    KBDocumentResponse,
    KBStructuredSourceCreate,
    KBStructuredSourceResponse,
    KBStructuredSourceUpdate,
)
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "txt", "csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads")


def _get_file_extension(filename: str) -> str:
    """Extract lowercase file extension without the dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


@router.post(
    "/documents",
    response_model=KBDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KBDocumentResponse:
    """Upload a document to the agent's knowledge base.

    Accepts PDF, TXT, and CSV files. The document is saved locally,
    then a background task chunks and embeds the content for retrieval.
    Maximum file size is 50MB.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    # Validate file extension
    filename = file.filename or "upload"
    ext = _get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file content and validate size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    # Save file to local uploads directory
    agent_upload_dir = os.path.join(UPLOAD_DIR, str(agent_id))
    os.makedirs(agent_upload_dir, exist_ok=True)
    file_path = os.path.join(agent_upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)

    # Map extension to SourceType
    source_type_map = {
        "pdf": SourceType.PDF,
        "txt": SourceType.TXT,
        "csv": SourceType.CSV,
    }

    # Create document record
    document = KBDocument(
        agent_id=agent_id,
        filename=filename,
        source_type=source_type_map[ext],
        file_size_bytes=len(file_content),
        status=DocumentStatus.PENDING,
        s3_key=file_path,
    )
    db.add(document)
    await db.flush()

    # Ingest document (parse, chunk, embed)
    service = KnowledgeBaseService(db)
    try:
        await service.ingest_document(document.id, file_content)
    except Exception:
        # ingest_document already marks the document as FAILED
        pass

    # Refresh to get latest status
    await db.refresh(document)

    return KBDocumentResponse.model_validate(document)


@router.get(
    "/documents",
    response_model=KBDocumentListResponse,
)
async def list_documents(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KBDocumentListResponse:
    """List all documents in the agent's knowledge base.

    Returns document metadata including processing status and chunk counts.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    stmt = (
        select(KBDocument)
        .where(KBDocument.agent_id == agent_id)
        .order_by(KBDocument.created_at.desc())
    )
    result = await db.execute(stmt)
    documents = result.scalars().all()

    count_stmt = select(func.count()).select_from(KBDocument).where(KBDocument.agent_id == agent_id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return KBDocumentListResponse(
        items=[KBDocumentResponse.model_validate(doc) for doc in documents],
        total=total,
    )


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    agent_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a document from the agent's knowledge base.

    Removes the document, its chunks, embeddings, and the S3 object.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    stmt = select(KBDocument).where(KBDocument.id == doc_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Document not found for this agent")

    # Delete associated chunks first
    service = KnowledgeBaseService(db)
    await service.delete_document_chunks(doc_id)

    # Delete the document record
    await db.delete(document)


@router.post(
    "/structured",
    response_model=KBStructuredSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_structured_source(
    agent_id: uuid.UUID,
    source_in: KBStructuredSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KBStructuredSourceResponse:
    """Add a structured data source to the agent's knowledge base.

    Configures an API endpoint, database connection, or spreadsheet as a
    live data source the agent can query during conversations.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    source = KBStructuredSource(agent_id=agent_id, **source_in.model_dump())
    db.add(source)
    await db.flush()

    return KBStructuredSourceResponse.model_validate(source)


@router.put(
    "/structured/{source_id}",
    response_model=KBStructuredSourceResponse,
)
async def update_structured_source(
    agent_id: uuid.UUID,
    source_id: uuid.UUID,
    source_in: KBStructuredSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> KBStructuredSourceResponse:
    """Update a structured data source configuration.

    Allows modifying connection details, query templates, and refresh intervals.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    stmt = select(KBStructuredSource).where(KBStructuredSource.id == source_id)
    result = await db.execute(stmt)
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Structured source not found")
    if source.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Structured source not found for this agent")

    update_data = source_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(source, field, value)

    await db.flush()

    return KBStructuredSourceResponse.model_validate(source)
