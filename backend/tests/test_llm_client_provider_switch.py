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


