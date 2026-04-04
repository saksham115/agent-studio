"""Claude API wrapper for the Agent Studio conversation orchestrator.

Provides an async interface to the Anthropic Claude API with structured
response types. Used by the orchestrator to drive agent conversations
and evaluate state-machine transition conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# Default model used across the application.
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Lightweight model for cheap evaluation calls (condition checks, etc.).
EVAL_MODEL = "claude-sonnet-4-20250514"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool-use request extracted from a Claude response."""

    id: str
    name: str
    input: dict


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Structured representation of a Claude API response.

    Attributes:
        content: The concatenated text blocks from the response.
        tool_calls: Any tool_use blocks the model produced.
        stop_reason: Why the model stopped generating (e.g. "end_turn",
            "tool_use", "max_tokens").
        input_tokens: Number of tokens in the request.
        output_tokens: Number of tokens in the response.
        model: The model identifier that served the request.
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL


class LLMClient:
    """Async wrapper around the Anthropic Python SDK.

    Usage::

        client = LLMClient()
        response = await client.chat(
            system_prompt="You are a helpful agent.",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.content)
    """

    def __init__(self, api_key: str | None = None, default_model: str = DEFAULT_MODEL) -> None:
        resolved_key = api_key or settings.ANTHROPIC_API_KEY
        if not resolved_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY in the "
                "environment or pass it explicitly."
            )
        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)
        self._default_model = default_model

    # ------------------------------------------------------------------
    # Primary conversation method
    # ------------------------------------------------------------------

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        model: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a conversation to Claude and return a structured response.

        Parameters
        ----------
        system_prompt:
            The system-level instructions for the model.
        messages:
            A list of message dicts in the Anthropic messages-API format
            (``{"role": "user"|"assistant", "content": ...}``).
        tools:
            Optional list of tool definitions (Claude tool-use format).
        max_tokens:
            Maximum tokens the model may generate.
        model:
            Override the default model for this call.
        temperature:
            Sampling temperature override.

        Returns
        -------
        LLMResponse
            Parsed response with text content, tool calls, and usage stats.
        """
        if not messages:
            raise ValueError("At least one message is required.")

        kwargs: dict = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            logger.error(
                "Anthropic API error: status=%s message=%s",
                exc.status_code,
                exc.message,
            )
            raise
        except anthropic.APIConnectionError:
            logger.error("Failed to connect to Anthropic API")
            raise

        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Lightweight condition evaluator
    # ------------------------------------------------------------------

    async def evaluate_condition(
        self,
        conversation_summary: str,
        condition: str,
    ) -> bool:
        """Evaluate whether a natural-language condition is met.

        Uses a small, focused prompt to get a YES/NO answer from Claude.
        Intended for state-machine transition checks where we need a
        boolean decision based on conversation context.

        Parameters
        ----------
        conversation_summary:
            A brief summary of the recent conversation turns.
        condition:
            The natural-language condition to evaluate (e.g.
            "The customer has provided their policy number").

        Returns
        -------
        bool
            True if the condition is considered met, False otherwise.
        """
        system = (
            "You evaluate whether a condition has been met in a conversation. "
            "Reply with only YES or NO."
        )
        user_message = (
            f"## Conversation Summary\n{conversation_summary}\n\n"
            f"## Condition to Evaluate\n{condition}\n\n"
            "Has this condition been met? Answer YES or NO only."
        )

        response = await self.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=8,
            model=EVAL_MODEL,
            temperature=0.0,
        )

        answer = response.content.strip().upper()
        # Be lenient: accept answers that start with YES/NO even if the
        # model adds a period or brief explanation.
        if answer.startswith("YES"):
            return True
        if answer.startswith("NO"):
            return False

        # Fallback: if the model gave an unexpected answer, log and
        # default to False (safer — don't transition on ambiguity).
        logger.warning(
            "Unexpected condition-evaluation answer: %r (condition=%r). "
            "Defaulting to False.",
            response.content,
            condition,
        )
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: anthropic.types.Message) -> LLMResponse:
        """Convert an Anthropic Message object to our LLMResponse dataclass."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return LLMResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )
