"""Embedding generation service using OpenAI's text-embedding-3-small model.

Calls the OpenAI embeddings API directly via httpx -- no OpenAI SDK required.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
_MAX_BATCH_SIZE = 100
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0


class EmbeddingError(Exception):
    """Raised when the OpenAI embeddings API returns an error."""


class EmbeddingService:
    """Generate vector embeddings via the OpenAI API."""

    def __init__(self) -> None:
        self.api_key: str = settings.OPENAI_API_KEY
        self.model: str = "text-embedding-3-small"
        self.dimensions: int = 1536

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding for a single piece of text."""
        results = await self._call_api([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        The OpenAI API allows at most 100 inputs per request, so larger
        batches are automatically split into multiple calls.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), _MAX_BATCH_SIZE):
            chunk = texts[start : start + _MAX_BATCH_SIZE]
            embeddings = await self._call_api(chunk)
            all_embeddings.extend(embeddings)
        return all_embeddings

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings endpoint with retry + exponential backoff."""
        if not self.api_key:
            raise EmbeddingError(
                "OPENAI_API_KEY is not configured. Set it in your environment or .env file."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "input": texts,
            "model": self.model,
            "dimensions": self.dimensions,
        }

        last_exception: Exception | None = None
        backoff = _INITIAL_BACKOFF_SECONDS

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        _OPENAI_EMBEDDINGS_URL,
                        headers=headers,
                        json=payload,
                    )

                if response.status_code == 200:
                    data = response.json()
                    # The API returns objects sorted by index; sort explicitly
                    # to be safe.
                    sorted_data = sorted(data["data"], key=lambda d: d["index"])
                    return [item["embedding"] for item in sorted_data]

                # Rate-limit or transient server error -- retry
                if response.status_code in (429, 500, 502, 503, 504):
                    last_exception = EmbeddingError(
                        f"OpenAI API returned {response.status_code}: {response.text}"
                    )
                    logger.warning(
                        "OpenAI embeddings API attempt %d/%d failed with %d, retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        response.status_code,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                # Non-retryable error
                raise EmbeddingError(
                    f"OpenAI embeddings API error {response.status_code}: {response.text}"
                )

            except httpx.HTTPError as exc:
                last_exception = exc
                logger.warning(
                    "OpenAI embeddings API attempt %d/%d raised %s, retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2

        raise EmbeddingError(
            f"OpenAI embeddings API failed after {_MAX_RETRIES} retries"
        ) from last_exception
