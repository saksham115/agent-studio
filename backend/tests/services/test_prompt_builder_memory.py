"""Tests for ``PromptBuilder.build_system_prompt`` memory + voice-style features.

The system prompt assembly is the only place where end-user memories surface
to the LLM, so these tests guard the contract that:

- The "What you remember about this user" section appears between Persona
  and Languages (positional contract — the LLM treats it as identity context
  rather than KB / state / fallback).
- An empty memory list omits the section entirely (no empty header).
- ``voice_style=True`` appends the response-style block at the end.
- Backward-compatible: callers omitting the new kwargs still work.
"""

from __future__ import annotations

import pytest

from app.services.prompt_builder import PromptBuilder


class _FakeAgent:
    """Minimal agent shim — only the fields PromptBuilder reads."""

    def __init__(
        self, *,
        persona="Aaru",
        system_prompt="You are a helpful agent.",
        languages=None,
        fallback_message="",
        escalation_message="",
        description="An agent",
    ):
        self.persona = persona
        self.name = persona
        self.description = description
        self.system_prompt = system_prompt
        self.languages = languages or []
        self.fallback_message = fallback_message
        self.escalation_message = escalation_message


@pytest.fixture
def builder():
    return PromptBuilder()


# ---------------------------------------------------------------------------
# Memory section
# ---------------------------------------------------------------------------


def test_memory_section_renders_each_fact_as_bullet(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
        user_memories=[
            "Aarti has account ACC-44219",
            "Pending refund Rs 5400",
        ],
    )
    assert "## What you remember about this user" in out
    assert "- Aarti has account ACC-44219" in out
    assert "- Pending refund Rs 5400" in out


def test_memory_section_appears_between_persona_and_languages(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(languages=["English", "Hindi"]),
        current_state=None,
        guardrails=[],
        kb_context="",
        user_memories=["Aarti has account ACC-44219"],
    )
    persona_pos = out.find("## Persona")
    memory_pos = out.find("## What you remember about this user")
    languages_pos = out.find("## Languages")
    assert persona_pos < memory_pos < languages_pos, (
        f"order mismatch: persona={persona_pos} memory={memory_pos} "
        f"languages={languages_pos}\n\n{out}"
    )


def test_empty_memories_omits_section(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
        user_memories=[],
    )
    assert "What you remember" not in out


def test_none_memories_omits_section(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
        user_memories=None,
    )
    assert "What you remember" not in out


# ---------------------------------------------------------------------------
# Voice style
# ---------------------------------------------------------------------------


def test_voice_style_appends_response_style_section(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
        voice_style=True,
    )
    assert "## Response Style" in out
    assert "voice call" in out.lower()
    assert "2-3" in out or "short" in out.lower()


def test_voice_style_section_appears_last(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(languages=["English"]),
        current_state=None,
        guardrails=[],
        kb_context="some KB content here",
        voice_style=True,
        user_memories=["fact"],
    )
    response_style_pos = out.find("## Response Style")
    # Every other section header must appear before Response Style
    for header in ("## Persona", "## What you remember", "## Languages",
                   "## Relevant Knowledge"):
        if header in out:
            assert out.find(header) < response_style_pos, (
                f"{header} should come before Response Style"
            )


def test_voice_style_default_false_omits_section(builder):
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
    )
    assert "## Response Style" not in out


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_legacy_call_without_new_kwargs_still_works(builder):
    """Pre-PR callers (orchestrator before Step 8) pass only the original 4 args."""
    out = builder.build_system_prompt(
        agent=_FakeAgent(),
        current_state=None,
        guardrails=[],
        kb_context="",
    )
    assert "Persona" in out
    assert "What you remember" not in out
    assert "Response Style" not in out
