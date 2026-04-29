"""Pellet adapter — regression coverage for the OpenAI-compatible path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import LLMClient


def _mock_completion(content="hello", tool_calls=None, finish_reason="stop", model="m"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock(message=msg, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
    return MagicMock(choices=[choice], usage=usage, model=model)


def _build_pellet_client(monkeypatch, mock_create):
    monkeypatch.setattr("app.config.settings.LLM_PROVIDER", "pellet")
    monkeypatch.setattr("app.config.settings.PELLET_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    with patch("app.services.llm_client.AsyncOpenAI", return_value=mock_client):
        return LLMClient()


async def test_chat_prepends_system_prompt(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_completion())
    client = _build_pellet_client(monkeypatch, mock_create)

    await client.chat("YOU ARE", [{"role": "user", "content": "hi"}])

    kwargs = mock_create.call_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "YOU ARE"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hi"}


async def test_chat_passes_tools_with_tool_choice_auto(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_completion())
    client = _build_pellet_client(monkeypatch, mock_create)

    tools = [
        {
            "type": "function",
            "function": {"name": "x", "description": "y", "parameters": {}},
        }
    ]
    await client.chat("sys", [{"role": "user", "content": "hi"}], tools=tools)

    kwargs = mock_create.call_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


async def test_parse_extracts_text_content(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_completion(content="goodbye"))
    client = _build_pellet_client(monkeypatch, mock_create)

    response = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert response.content == "goodbye"


async def test_parse_decodes_tool_call_arguments_from_json_string(monkeypatch):
    tool = MagicMock()
    tool.id = "call_1"
    tool.function = MagicMock()
    tool.function.name = "lookup"
    tool.function.arguments = '{"q": "policy", "n": 3}'
    completion = _mock_completion(tool_calls=[tool], finish_reason="tool_calls")
    mock_create = AsyncMock(return_value=completion)
    client = _build_pellet_client(monkeypatch, mock_create)

    response = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert response.tool_calls == [
        {"id": "call_1", "name": "lookup", "input": {"q": "policy", "n": 3}}
    ]


async def test_parse_maps_usage_fields(monkeypatch):
    mock_create = AsyncMock(return_value=_mock_completion())
    client = _build_pellet_client(monkeypatch, mock_create)

    response = await client.chat("sys", [{"role": "user", "content": "hi"}])

    assert response.input_tokens == 10
    assert response.output_tokens == 20


@pytest.mark.parametrize(
    "answer_text, expected",
    [("YES", True), ("yes, definitely", True), ("NO", False), ("maybe", False)],
)
async def test_evaluate_condition_returns_bool(monkeypatch, answer_text, expected):
    mock_create = AsyncMock(return_value=_mock_completion(content=answer_text))
    client = _build_pellet_client(monkeypatch, mock_create)

    result = await client.evaluate_condition("summary", "is met")

    assert result is expected
