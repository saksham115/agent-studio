"""LLM client with switchable backend (Pellet or Anthropic).

`LLMClient` is a thin facade that picks one of two adapters at init time
based on ``settings.LLM_PROVIDER``:

- ``_PelletAdapter`` — OpenAI SDK pointed at Pellet (Llama 3.3 70B, default)
- ``_AnthropicAdapter`` — Anthropic SDK direct (Claude Sonnet 4.6 by default)

The OpenAI/Pellet message and tool-call shape is the canonical wire format
throughout the codebase. The Anthropic adapter translates outbound requests
and inbound responses internally; callers don't change.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from anthropic import (
    APIConnectionError as AnthropicAPIConnectionError,
    APIStatusError as AnthropicAPIStatusError,
    AsyncAnthropic,
)
from openai import (
    APIConnectionError as OpenAIAPIConnectionError,
    APIStatusError as OpenAIAPIStatusError,
    AsyncOpenAI,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level model defaults. Code constants — not env vars — to keep the
# config surface small. Override by editing this file.
_PELLET_DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
_PELLET_EVAL_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
_ANTHROPIC_EVAL_MODEL = "claude-haiku-4-5-20251001"

# Backward-compat: callers that import DEFAULT_MODEL still work.
DEFAULT_MODEL = _PELLET_DEFAULT_MODEL


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool-use request extracted from an LLM response."""

    id: str
    name: str
    input: dict


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Structured representation of an LLM API response."""

    content: str
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Pellet adapter (OpenAI-compatible)
# ---------------------------------------------------------------------------


class _PelletAdapter:
    """OpenAI SDK pointed at the Pellet inference gateway."""

    default_model = _PELLET_DEFAULT_MODEL
    default_eval_model = _PELLET_EVAL_MODEL

    def __init__(self) -> None:
        api_key = settings.PELLET_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "Pellet adapter requires PELLET_API_KEY (or OPENAI_API_KEY)."
            )
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=settings.PELLET_BASE_URL
        )

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int,
        model: str,
        temperature: float | None,
    ) -> LLMResponse:
        api_messages = [{"role": "system", "content": system_prompt}, *messages]
        kwargs: dict = {
            "model": model,
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
        except OpenAIAPIStatusError as exc:
            logger.error(
                "Pellet API error: status=%s message=%s",
                exc.status_code,
                exc.message,
            )
            raise
        except OpenAIAPIConnectionError:
            logger.error("Failed to connect to Pellet API")
            raise

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None

        content = message.content or "" if message else ""
        stop_reason = choice.finish_reason or "stop" if choice else "stop"

        tool_calls: list[dict] = []
        if message and message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = (
                        json.loads(tc.function.arguments)
                        if tc.function.arguments
                        else {}
                    )
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    {"id": tc.id, "name": tc.function.name, "input": args}
                )

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=response.model or _PELLET_DEFAULT_MODEL,
        )


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


class _AnthropicAdapter:
    """Direct Anthropic API client.

    Translates OpenAI-canonical messages and tools to Anthropic format on
    the way out, and Anthropic responses back to ``LLMResponse`` on the
    way in.
    """

    default_eval_model = _ANTHROPIC_EVAL_MODEL

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("Anthropic adapter requires ANTHROPIC_API_KEY.")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.default_model = settings.ANTHROPIC_MODEL

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int,
        model: str,
        temperature: float | None,
    ) -> LLMResponse:
        anthropic_messages = self._translate_messages(messages)
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": anthropic_messages,
        }
        if tools:
            kwargs["tools"] = self._translate_tools(tools)
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)
        except AnthropicAPIStatusError as exc:
            logger.error(
                "Anthropic API error: status=%s message=%s",
                exc.status_code,
                getattr(exc, "message", str(exc)),
            )
            raise
        except AnthropicAPIConnectionError:
            logger.error("Failed to connect to Anthropic API")
            raise

        return self._parse_response(response)

    @staticmethod
    def _translate_tools(tools: list[dict]) -> list[dict]:
        """OpenAI envelope → Anthropic input_schema format."""
        out: list[dict] = []
        for t in tools:
            fn = t.get("function", t)
            out.append(
                {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                }
            )
        return out

    @staticmethod
    def _translate_messages(messages: list[dict]) -> list[dict]:
        """Convert OpenAI-canonical messages to Anthropic format.

        Coalesces consecutive ``role:"tool"`` messages into one user turn
        with multiple ``tool_result`` content blocks. Skips system messages
        (system prompt is passed via ``system=`` kwarg, not in messages).
        """
        out: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                tool_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }
                if (
                    out
                    and out[-1]["role"] == "user"
                    and isinstance(out[-1].get("content"), list)
                ):
                    out[-1]["content"].append(tool_block)
                else:
                    out.append({"role": "user", "content": [tool_block]})
            elif role == "assistant":
                content_blocks: list[dict] = []
                text = msg.get("content")
                if text:
                    content_blocks.append({"type": "text", "text": text})
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    args = fn.get("arguments") or tc.get("input") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name") or tc.get("name", ""),
                            "input": args,
                        }
                    )
                # Anthropic requires non-empty assistant content; fall back
                # to an empty text block in the rare case of neither text
                # nor tool_calls.
                if not content_blocks:
                    content_blocks = [{"type": "text", "text": ""}]
                out.append({"role": "assistant", "content": content_blocks})
            elif role == "user":
                out.append({"role": "user", "content": msg.get("content", "")})
            elif role == "system":
                continue
            else:
                out.append(msg)
        # Anthropic rejects conversations that end with an assistant turn
        # (no prefill on these models). Pellet/OpenAI is lenient. Drop
        # trailing assistant turns so Claude always sees a user-last history.
        while out and out[-1].get("role") == "assistant":
            out.pop()
        # Sanitize tool_use/tool_result pairing: Anthropic enforces that
        # every ``tool_result`` block must have a matching ``tool_use``
        # in the immediately preceding assistant message, AND every
        # ``tool_use`` must be followed by a user turn whose first content
        # block is the matching ``tool_result``. Pellet/OpenAI is lenient
        # and our DB-row history can drift out of pairing across
        # interrupted turns (orphan tool_use after a fast-fail, or
        # orphan tool_result after a truncation). Drop orphans before
        # sending — better than 400-ing the whole turn.
        return _AnthropicAdapter._sanitize_tool_pairing(out)

    @staticmethod
    def _sanitize_tool_pairing(messages: list[dict]) -> list[dict]:
        """Drop orphan tool_use / tool_result blocks for Anthropic.

        Walks the message list left-to-right with this state machine:
        - When an assistant message has tool_use blocks, peek at the
          *next* user message: keep only tool_use blocks whose ID appears
          as a tool_result.tool_use_id in that next message; drop the rest.
        - When a user message has tool_result blocks, keep only those whose
          tool_use_id was emitted by the *previous* assistant message; drop
          orphans.
        Empty messages (all blocks dropped) are removed entirely.
        """
        if not messages:
            return messages

        # First pass: collect, per assistant index, the set of tool_use ids
        # that have a matching tool_result in the *next* user message.
        n = len(messages)
        kept_tool_use_ids: list[set[str]] = [set() for _ in range(n)]
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            asst_tool_use_ids = {
                b.get("id")
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id")
            }
            if not asst_tool_use_ids:
                continue
            # Look at next user message for tool_result blocks
            next_idx = i + 1
            if next_idx >= n or messages[next_idx].get("role") != "user":
                # No following user → all tool_use are orphans
                continue
            next_content = messages[next_idx].get("content")
            if not isinstance(next_content, list):
                continue
            next_tool_result_ids = {
                b.get("tool_use_id")
                for b in next_content
                if isinstance(b, dict) and b.get("type") == "tool_result"
            }
            kept_tool_use_ids[i] = asst_tool_use_ids & next_tool_result_ids

        # Second pass: rebuild messages dropping orphan tool_use and
        # orphan tool_result blocks.
        out: list[dict] = []
        for i, msg in enumerate(messages):
            role = msg.get("role")
            content = msg.get("content")
            if role == "assistant" and isinstance(content, list):
                kept_ids = kept_tool_use_ids[i]
                new_content = []
                for b in content:
                    if (
                        isinstance(b, dict)
                        and b.get("type") == "tool_use"
                        and b.get("id") not in kept_ids
                    ):
                        continue  # orphan
                    new_content.append(b)
                if not new_content:
                    new_content = [{"type": "text", "text": ""}]
                out.append({**msg, "content": new_content})
            elif role == "user" and isinstance(content, list):
                # Build allowed tool_use_ids from previous assistant
                allowed: set[str] = set()
                if i > 0 and messages[i - 1].get("role") == "assistant":
                    prev_content = messages[i - 1].get("content")
                    if isinstance(prev_content, list):
                        allowed = {
                            b.get("id")
                            for b in prev_content
                            if isinstance(b, dict)
                            and b.get("type") == "tool_use"
                            and b.get("id")
                        } & kept_tool_use_ids[i - 1]
                new_content = []
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        if b.get("tool_use_id") in allowed:
                            new_content.append(b)
                        # else: drop orphan
                    else:
                        new_content.append(b)
                if new_content:
                    out.append({**msg, "content": new_content})
                # else: skip empty user message
            else:
                out.append(msg)
        return out

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        text_chunks: list[str] = []
        tool_calls: list[dict] = []
        for block in response.content or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_chunks.append(getattr(block, "text", "") or "")
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}) or {},
                    }
                )

        content = "".join(text_chunks)

        # Normalize stop_reason vocabulary to OpenAI/Pellet's so downstream
        # consumers don't need to special-case the provider.
        raw_stop = getattr(response, "stop_reason", None)
        stop_map = {
            "end_turn": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
        }
        stop_reason = stop_map.get(raw_stop, raw_stop or "stop")

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=getattr(response, "model", "") or settings.ANTHROPIC_MODEL,
        )


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------


class LLMClient:
    """Async LLM client. Picks an adapter from ``settings.LLM_PROVIDER``.

    Usage::

        client = LLMClient()
        response = await client.chat(
            system_prompt="You are a helpful agent.",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.content)
    """

    def __init__(self) -> None:
        if settings.LLM_PROVIDER == "anthropic":
            self._adapter: _PelletAdapter | _AnthropicAdapter = _AnthropicAdapter()
        else:
            self._adapter = _PelletAdapter()

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        model: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a conversation to the configured LLM and return a parsed response."""
        if not messages:
            raise ValueError("At least one message is required.")

        chosen_model = model or self._adapter.default_model

        start = time.monotonic()
        response = await self._adapter.chat(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            model=chosen_model,
            temperature=temperature,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "LLM call provider=%s model=%s tool_count=%d msg_count=%d "
            "latency_ms=%d input_tokens=%d output_tokens=%d",
            settings.LLM_PROVIDER,
            chosen_model,
            len(tools or []),
            len(messages),
            latency_ms,
            response.input_tokens,
            response.output_tokens,
        )
        return response
