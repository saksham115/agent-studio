"""Knowledge-base ingestion and vector retrieval service.

Orchestrates the full pipeline:
  parse document --> chunk text --> generate embeddings --> store in pgvector

And provides cosine-similarity search over the stored chunks.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import DocumentStatus, KBChunk, KBDocument
from app.services.document_processor import DocumentProcessor
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """High-level service for KB document ingestion and retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.embeddings = EmbeddingService()
        self.processor = DocumentProcessor()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        document_id: uuid.UUID,
        file_content: bytes,
    ) -> None:
        """Full ingestion pipeline: parse, chunk, embed, store.

        Updates the ``KBDocument`` status as it progresses.  On error the
        status is set to FAILED and the error message is persisted.
        """
        # 1. Load the document record
        stmt = select(KBDocument).where(KBDocument.id == document_id)
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()

        if document is None:
            raise ValueError(f"KBDocument with id={document_id} not found")

        # 2. Mark as processing
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        await self.db.flush()

        try:
            # 3. Parse and chunk the document
            chunks = await self.processor.process_document(
                file_content=file_content,
                filename=document.filename,
                source_type=document.source_type.value,
            )

            if not chunks:
                raise ValueError(
                    f"Document '{document.filename}' produced no text chunks"
                )

            # 4. Generate embeddings in batches
            texts = [c.content for c in chunks]
            embeddings = await self.embeddings.embed_batch(texts)

            # 5. Create KBChunk records
            chunk_records: list[KBChunk] = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_record = KBChunk(
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=embedding,
                    metadata_json={
                        "filename": document.filename,
                        "source_type": document.source_type.value,
                    },
                )
                chunk_records.append(chunk_record)

            self.db.add_all(chunk_records)

            # 6. Update document status
            document.status = DocumentStatus.COMPLETED
            document.chunk_count = len(chunk_records)
            await self.db.flush()

            logger.info(
                "Ingested document %s (%s): %d chunks created",
                document_id,
                document.filename,
                len(chunk_records),
            )

        except Exception as exc:
            # Roll back any partial chunk inserts from this method -- the
            # caller's session management will handle the actual DB rollback.
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:2000]
            await self.db.flush()

            logger.exception(
                "Failed to ingest document %s (%s)",
                document_id,
                document.filename,
            )
            raise

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def search(
        self,
        agent_id: uuid.UUID,
        query: str,
        top_k: int = 5,
    ) -> list[str]:
        """Vector similarity search across an agent's knowledge base.

        Returns a list of chunk content strings ordered by cosine similarity
        (nearest first).
        """
        if not query or not query.strip():
            return []

        # 1. Generate the query embedding
        query_embedding = await self.embeddings.embed_text(query)

        # 2. Cosine-distance search via pgvector
        stmt = (
            select(KBChunk.content)
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .where(KBDocument.agent_id == agent_id)
            .where(KBDocument.status == DocumentStatus.COMPLETED)
            .where(KBChunk.embedding.isnot(None))
            .order_by(KBChunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return list(rows)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_document_chunks(self, document_id: uuid.UUID) -> None:
        """Delete all chunks belonging to a document."""
        stmt = delete(KBChunk).where(KBChunk.document_id == document_id)
        await self.db.execute(stmt)
        await self.db.flush()

        logger.info("Deleted all chunks for document %s", document_id)
