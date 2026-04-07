"""Custom Bolna LLM adapter that wraps our ConversationOrchestrator.

Bolna calls generate_stream() with the conversation history. We extract
the latest user message, pass it to our orchestrator (which handles tools,
state machine, guardrails, KB), and yield the response text in chunks
for Bolna's streaming TTS pipeline.
"""

from __future__ import annotations

import logging
import time

from bolna.llms.llm import BaseLLM

logger = logging.getLogger(__name__)


class OrchestratorLLM(BaseLLM):
    """Bridges Bolna's LLM interface to the Agent Studio orchestrator."""

    def __init__(self, max_tokens=200, buffer_size=40, **kwargs):
        super().__init__(max_tokens=max_tokens, buffer_size=buffer_size)
        self.model = "orchestrator"
        self.started_streaming = False

        # These are passed via AssistantManager kwargs
        self.conversation_id = kwargs.get("conversation_id")
        self.db_session_factory = kwargs.get("db_session_factory")

        if not self.conversation_id:
            raise ValueError("conversation_id is required for OrchestratorLLM")
        if not self.db_session_factory:
            raise ValueError("db_session_factory is required for OrchestratorLLM")

        logger.info(
            "OrchestratorLLM initialized: conversation_id=%s",
            self.conversation_id,
        )

    async def generate_stream(self, messages, synthesize=True, meta_info=None, tool_choice=None):
        """Process user transcript through the orchestrator and yield response chunks.

        Bolna passes the full message history, but our orchestrator maintains
        its own history in the DB. We only extract the latest user message.

        Yields:
            Tuples of (text, end_of_stream, latency_data, is_function_call, func_name, func_message)
        """
        from app.services.orchestrator import ConversationOrchestrator

        # Extract the last user message from Bolna's history
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        if not user_text:
            logger.warning("No user message found in Bolna history")
            return

        logger.info(
            "OrchestratorLLM: conversation_id=%s, user_text=%r",
            self.conversation_id,
            user_text[:200],
        )

        start_time = time.monotonic()
        latency_data = {
            "sequence_id": meta_info.get("sequence_id") if meta_info else None,
            "first_token_latency_ms": None,
            "total_stream_duration_ms": None,
        }

        # Call our orchestrator with a fresh DB session
        try:
            async with self.db_session_factory() as db:
                orchestrator = ConversationOrchestrator(db)
                response = await orchestrator.process_message(
                    conversation_id=self.conversation_id,
                    user_message=user_text,
                )
                await db.commit()
        except Exception:
            logger.exception("Orchestrator failed for conversation %s", self.conversation_id)
            yield "Sorry, something went wrong. Please try again.", True, latency_data, False, None, None
            return

        response_text = response.message
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        latency_data["first_token_latency_ms"] = elapsed_ms
        latency_data["total_stream_duration_ms"] = elapsed_ms

        logger.info(
            "OrchestratorLLM response: %d chars, latency=%dms",
            len(response_text),
            elapsed_ms,
        )

        self.started_streaming = True

        # Yield response in chunks for streaming TTS
        if synthesize:
            words = response_text.split()
            buffer = ""
            for word in words:
                buffer += word + " "
                if len(buffer) >= self.buffer_size:
                    split = buffer.rsplit(" ", 1)
                    yield split[0], False, latency_data, False, None, None
                    buffer = split[1] if len(split) > 1 else ""
            if buffer.strip():
                yield buffer.strip(), True, latency_data, False, None, None
            else:
                # Edge case: empty buffer after last word
                yield "", True, latency_data, False, None, None
        else:
            yield response_text, True, latency_data, False, None, None

        self.started_streaming = False

    async def generate(self, messages, stream=False, request_json=False, meta_info=None, ret_metadata=False):
        """Non-streaming generation — used for summarization tasks."""
        from app.services.orchestrator import ConversationOrchestrator

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        if not user_text:
            return ("", {}) if ret_metadata else ""

        try:
            async with self.db_session_factory() as db:
                orchestrator = ConversationOrchestrator(db)
                response = await orchestrator.process_message(
                    conversation_id=self.conversation_id,
                    user_message=user_text,
                )
                await db.commit()
        except Exception:
            logger.exception("Orchestrator failed")
            return ("Sorry, something went wrong.", {}) if ret_metadata else "Sorry, something went wrong."

        text = response.message
        return (text, {}) if ret_metadata else text
