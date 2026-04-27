"""Provider selection + boot-time validation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.llm_client import LLMClient, _AnthropicAdapter, _PelletAdapter


def test_pellet_adapter_selected(monkeypatch):
    monkeypatch.setattr("app.config.settings.LLM_PROVIDER", "pellet")
    monkeypatch.setattr("app.config.settings.PELLET_API_KEY", "k")

    with patch("app.services.llm_client.AsyncOpenAI", return_value=MagicMock()):
        client = LLMClient()

    assert isinstance(client._adapter, _PelletAdapter)


def test_anthropic_adapter_selected(monkeypatch):
    monkeypatch.setattr("app.config.settings.LLM_PROVIDER", "anthropic")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_MODEL", "claude-sonnet-4-6")

    with patch("app.services.llm_client.AsyncAnthropic", return_value=MagicMock()):
        client = LLMClient()

    assert isinstance(client._adapter, _AnthropicAdapter)


def test_anthropic_provider_requires_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")


def test_pellet_provider_requires_api_key():
    with pytest.raises(ValueError, match="PELLET_API_KEY"):
        Settings(
            LLM_PROVIDER="pellet",
            PELLET_API_KEY="",
            OPENAI_API_KEY="",
            ANTHROPIC_API_KEY="",
        )


async def test_evaluate_condition_uses_anthropic_eval_model(monkeypatch):
    """Facade routes evaluate_condition through adapter.default_eval_model."""
    monkeypatch.setattr("app.config.settings.LLM_PROVIDER", "anthropic")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("app.config.settings.ANTHROPIC_MODEL", "claude-sonnet-4-6")

    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="YES")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        model="m",
    )
    mock_create = AsyncMock(return_value=response)
    mock_client = MagicMock()
    mock_client.messages.create = mock_create

    with patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client):
        client = LLMClient()

    result = await client.evaluate_condition("summary", "is met")

    assert result is True
    assert mock_create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"
