"""Pellet / OpenAI-compatible API wrapper for the Agent Studio orchestrator.

Provides an async interface via the OpenAI Python SDK pointed at the
Pellet inference gateway. Used by the orchestrator to drive agent
conversations and evaluate state-machine transition conditions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI, APIStatusError, APIConnectionError

from app.config import settings

logger = logging.getLogger(__name__)

# Default model — auto-route via Pellet when set to empty string.
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

# Lightweight model for cheap evaluation calls (condition checks, etc.).
EVAL_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool-use request extracted from an LLM response."""

    id: str
    name: str
    input: dict


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Structured representation of an LLM API response.

    Attributes:
        content: The text content from the response.
        tool_calls: Any tool calls the model produced (as dicts for
            backward compatibility with the orchestrator).
        stop_reason: Why the model stopped generating.
        input_tokens: Number of tokens in the request.
        output_tokens: Number of tokens in the response.
        model: The model identifier that served the request.
    """

    content: str
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL


class LLMClient:
    """Async wrapper around the OpenAI Python SDK pointed at Pellet.

    Usage::

        client = LLMClient()
        response = await client.chat(
            system_prompt="You are a helpful agent.",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.content)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = DEFAULT_MODEL,
    ) -> None:
        resolved_key = api_key or settings.PELLET_API_KEY or settings.OPENAI_API_KEY
        if not resolved_key:
            raise ValueError(
                "API key is required. Set PELLET_API_KEY in the "
                "environment or pass it explicitly."
            )
        resolved_base_url = base_url or settings.PELLET_BASE_URL
        self._client = AsyncOpenAI(api_key=resolved_key, base_url=resolved_base_url)
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
        """Send a conversation to the LLM and return a structured response.

        Parameters
        ----------
        system_prompt:
            The system-level instructions for the model.
        messages:
            A list of message dicts in the OpenAI messages-API format.
        tools:
            Optional list of tool definitions (OpenAI function-calling format).
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

        # Prepend system prompt as a system message.
        api_messages = [{"role": "system", "content": system_prompt}, *messages]

        kwargs: dict = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except APIStatusError as exc:
            logger.error(
                "LLM API error: status=%s message=%s",
                exc.status_code,
                exc.message,
            )
            raise
        except APIConnectionError:
            logger.error("Failed to connect to LLM API")
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

        Uses a small, focused prompt to get a YES/NO answer.
        Intended for state-machine transition checks where we need a
        boolean decision based on conversation context.
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
        if answer.startswith("YES"):
            return True
        if answer.startswith("NO"):
            return False

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
    def _parse_response(response) -> LLMResponse:
        """Convert an OpenAI ChatCompletion to our LLMResponse dataclass."""
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None

        content = message.content or "" if message else ""
        stop_reason = choice.finish_reason or "stop" if choice else "stop"

        # Parse tool calls into dicts matching the format the orchestrator expects:
        # {"id": "...", "name": "...", "input": {...}}
        tool_calls: list[dict] = []
        if message and message.tool_calls:
            for tc in message.tool_calls:
                # Parse arguments from JSON string to dict
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (json.JSONDecodeError, TypeError):
                    args = {}

                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                })

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=response.model or DEFAULT_MODEL,
        )
