"""Celery tasks for background processing."""

import asyncio
import logging
import uuid

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_document_task(self, document_id: str):
    """Background task: parse, chunk, embed, and store a KB document.

    Args:
        document_id: UUID string of the KBDocument to process.
    """
    logger.info("Starting document ingestion for %s", document_id)

    async def _ingest():
        from app.database import async_session_factory
        from app.services.knowledge_base_service import KnowledgeBaseService
        from app.services.storage import StorageService
        from app.models.knowledge_base import KBDocument

        async with async_session_factory() as db:
            try:
                doc = await db.get(KBDocument, uuid.UUID(document_id))
                if not doc:
                    logger.error("Document %s not found", document_id)
                    return

                # Download file from S3
                storage = StorageService()
                file_content = storage.download_file(doc.s3_key)

                # Run ingestion pipeline
                kb_service = KnowledgeBaseService(db)
                await kb_service.ingest_document(doc.id, file_content)

                await db.commit()
                logger.info("Document %s ingestion completed (%d chunks)", document_id, doc.chunk_count)
            except Exception as e:
                await db.rollback()
                logger.error("Document %s ingestion failed: %s", document_id, str(e))
                raise

    try:
        _run_async(_ingest())
    except Exception as exc:
        logger.error("Task failed for document %s: %s", document_id, str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def process_media_task(self, agent_id: str, media_key: str, media_type: str):
    """Background task: process uploaded media (images, voice notes).

    Args:
        agent_id: UUID string of the agent.
        media_key: S3 key of the media file.
        media_type: Type of media (image, document, voice_note).
    """
    logger.info("Processing media %s (type: %s) for agent %s", media_key, media_type, agent_id)

    async def _process():
        from app.services.storage import StorageService

        storage = StorageService()
        file_content = storage.download_file(media_key)

        if media_type == "voice_note":
            # Transcribe voice note via Sarvam STT
            from app.services.channels.voice.sarvam import SarvamSTT
            stt = SarvamSTT()
            result = await stt.transcribe(file_content)
            logger.info("Transcribed voice note: %s", result.text[:100])
            return {"transcript": result.text, "language": result.language}

        elif media_type == "image":
            # For MVP, just log that we received the image
            logger.info("Image received: %s (%d bytes)", media_key, len(file_content))
            return {"status": "received", "size_bytes": len(file_content)}

        elif media_type == "document":
            # Parse document content
            from app.services.document_processor import DocumentProcessor
            processor = DocumentProcessor()
            filename = media_key.rsplit("/", 1)[-1]
            source_type = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
            chunks = await processor.process_document(file_content, filename, source_type)
            logger.info("Processed document: %d chunks", len(chunks))
            return {"chunk_count": len(chunks)}

        return {"status": "unknown_type"}

    try:
        return _run_async(_process())
    except Exception as exc:
        logger.error("Media processing failed: %s", str(exc))
        raise self.retry(exc=exc)
