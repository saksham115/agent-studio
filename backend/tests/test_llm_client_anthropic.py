"""Anthropic adapter — translation coverage (OpenAI canonical ⇄ Anthropic API)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import LLMClient


def _mock_response(text="hi", tool_uses=None, stop_reason="end_turn", model="m"):
    blocks: list = []
    if text is not None:
        blocks.append(SimpleNamespace(type="text", text=text))
    for tu in tool_uses or []:
        blocks.append(SimpleNamespace(type="tool_use", **tu))
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        model=model,
    )


def _build_anthropic_client(monkeypatch, mock_create):
    monkeypatch.setattr("app.config.settings.LLM_PROVIDER", "anthropic")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_MODEL", "claude-sonnet-4-6")
    mock_client = MagicMock()
    mock_client.messages.create = mock_create
    with patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client):
        return LLMClient()


async def test_system_prompt_routed_to_kwarg_not_messages(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_response())
    client = _build_anthropic_client(monkeypatch, mock_create)

    await client.chat("YOU ARE", [{"role": "user", "content": "hi"}])

    kwargs = mock_create.call_args.kwargs
    assert kwargs["system"] == "YOU ARE"
    assert all(m.get("role") != "system" for m in kwargs["messages"])
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


async def test_tool_def_translation(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_response())
    client = _build_anthropic_client(monkeypatch, mock_create)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "find a policy",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        }
    ]
    await client.chat("sys", [{"role": "user", "content": "hi"}], tools=tools)

    kwargs = mock_create.call_args.kwargs
    assert kwargs["tools"] == [
        {
            "name": "lookup",
            "description": "find a policy",
            "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
    ]


async def test_outbound_tool_call_translation(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_response())
    client = _build_anthropic_client(monkeypatch, mock_create)

    history = [
        {"role": "user", "content": "what's the price"},
        {
            "role": "assistant",
            "content": "let me check",
            "tool_calls": [
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q":"price"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc_1", "content": "$100"},
    ]
    await client.chat("sys", history)

    out = mock_create.call_args.kwargs["messages"]
    # Assistant turn carries text + tool_use blocks; arguments parsed to dict.
    assistant_turn = next(m for m in out if m["role"] == "assistant")
    assert assistant_turn["content"] == [
        {"type": "text", "text": "let me check"},
        {"type": "tool_use", "id": "tc_1", "name": "lookup", "input": {"q": "price"}},
    ]
    # Tool reply becomes a user turn with a tool_result block.
    last_user = out[-1]
    assert last_user["role"] == "user"
    assert last_user["content"] == [
        {"type": "tool_result", "tool_use_id": "tc_1", "content": "$100"}
    ]


async def test_consecutive_tool_results_coalesced(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_response())
    client = _build_anthropic_client(monkeypatch, mock_create)

    history = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "g", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": "first"},
        {"role": "tool", "tool_call_id": "b", "content": "second"},
    ]
    await client.chat("sys", history)

    out = mock_create.call_args.kwargs["messages"]
    user_turns = [m for m in out if m["role"] == "user"]
    # Both tool_results should land in ONE user turn.
    assert len(user_turns) == 1
    assert user_turns[0]["content"] == [
        {"type": "tool_result", "tool_use_id": "a", "content": "first"},
        {"type": "tool_result", "tool_use_id": "b", "content": "second"},
    ]


async def test_inbound_text_blocks_concatenated(monkeypatch):
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hi"),
            SimpleNamespace(type="text", text=" there"),
        ],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
        model="m",
    )
    mock_create = AsyncMock(return_value=response)
    client = _build_anthropic_client(monkeypatch, mock_create)

    result = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert result.content == "hi there"


async def test_inbound_tool_use_parsed_as_dict(monkeypatch):
    response = _mock_response(
        text=None,
        tool_uses=[{"id": "t_1", "name": "lookup", "input": {"q": "policy"}}],
        stop_reason="tool_use",
    )
    mock_create = AsyncMock(return_value=response)
    client = _build_anthropic_client(monkeypatch, mock_create)

    result = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert result.tool_calls == [
        {"id": "t_1", "name": "lookup", "input": {"q": "policy"}}
    ]


@pytest.mark.parametrize(
    "raw, normalized",
    [
        ("end_turn", "stop"),
        ("tool_use", "tool_calls"),
        ("max_tokens", "length"),
        ("stop_sequence", "stop_sequence"),
    ],
)
async def test_stop_reason_normalization(monkeypatch, raw, normalized):
    mock_create = AsyncMock(return_value=_mock_response(stop_reason=raw))
    client = _build_anthropic_client(monkeypatch, mock_create)

    result = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert result.stop_reason == normalized


async def test_usage_field_mapping(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_response())
    client = _build_anthropic_client(monkeypatch, mock_create)

    result = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert result.input_tokens == 10
    assert result.output_tokens == 20
