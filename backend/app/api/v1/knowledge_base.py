import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.knowledge_base import (
    KBDocumentListResponse,
    KBDocumentResponse,
    KBStructuredSourceCreate,
    KBStructuredSourceResponse,
    KBStructuredSourceUpdate,
)

router = APIRouter()


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

    Accepts PDF, DOCX, TXT, and CSV files. The document is uploaded to S3,
    then a background task chunks and embeds the content for retrieval.
    Maximum file size is 50MB.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")
