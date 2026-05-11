"""Tests for force_pick_transition (max_turns_exceeded backstop).

Mocks both the state_machine and the LLM client. Verifies the helper:
- Routes the LLM-suggested target when valid.
- Falls back to first-by-priority when the LLM picks an invalid target.
- Falls back to first-by-priority when the LLM call raises.
- Returns None when there are no outgoing transitions.
- Always commits via state_machine.transition_to with reason="max_turns_exceeded".
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.transition_picker import force_pick_transition


def _state(name: str, *, outgoing: list | None = None, is_terminal: bool = False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        is_terminal=is_terminal,
        outgoing_transitions=outgoing or [],
    )


def _transition(target: SimpleNamespace, *, condition: str = "", description: str = ""):
    return SimpleNamespace(
        id=uuid.uuid4(),
        to_state=target,
        condition=condition,
        description=description,
    )


def _message(role: str, content: str):
    return SimpleNamespace(role=SimpleNamespace(value=role), content=content)


def _mock_llm(*, content: str | None = "Pitch", raises: BaseException | None = None):
    chat = AsyncMock()
    if raises is not None:
        chat.side_effect = raises
    else:
        chat.return_value = SimpleNamespace(content=content)
    return SimpleNamespace(chat=chat)


def _mock_state_machine():
    sm = SimpleNamespace()
    sm.transition_to = AsyncMock()
    return sm


@pytest.mark.asyncio
async def test_returns_none_when_no_outgoing_transitions():
    current = _state("Stuck", outgoing=[])
    sm = _mock_state_machine()
    llm = _mock_llm(content="anything")
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[],
        llm=llm,
    )
    assert result is None
    sm.transition_to.assert_not_called()
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_routes_to_llm_picked_target_when_valid():
    pitch = _state("Pitch")
    escalation = _state("Escalation")
    current = _state(
        "Need Discovery",
        outgoing=[_transition(pitch, condition="ready"), _transition(escalation, condition="frustrated")],
    )
    llm = _mock_llm(content="Escalation")
    sm = _mock_state_machine()
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[_message("user", "I want a human")],
        llm=llm,
    )
    assert result is escalation
    sm.transition_to.assert_awaited_once()
    kwargs = sm.transition_to.await_args.kwargs
    assert kwargs["new_state"] is escalation
    assert kwargs["reason"] == "max_turns_exceeded"


@pytest.mark.asyncio
async def test_falls_back_to_first_when_llm_returns_invalid_target():
    pitch = _state("Pitch")
    escalation = _state("Escalation")
    current = _state(
        "Need Discovery",
        outgoing=[_transition(pitch), _transition(escalation)],
    )
    llm = _mock_llm(content="NonExistentState")
    sm = _mock_state_machine()
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[],
        llm=llm,
    )
    # First-by-priority is the first item in outgoing_transitions
    # (StateMachine.get_transitions sorts ascending by priority).
    assert result is pitch
    sm.transition_to.assert_awaited_once()


@pytest.mark.asyncio
async def test_falls_back_to_first_when_llm_call_raises():
    """Regression guard: helper must not propagate the LLM exception —
    the deterministic fallback is the whole point of force-pick."""
    pitch = _state("Pitch")
    escalation = _state("Escalation")
    current = _state(
        "Need Discovery",
        outgoing=[_transition(pitch), _transition(escalation)],
    )
    llm = _mock_llm(raises=RuntimeError("Pellet outage"))
    sm = _mock_state_machine()
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[],
        llm=llm,
    )
    assert result is pitch
    sm.transition_to.assert_awaited_once()


@pytest.mark.asyncio
async def test_falls_back_to_first_when_llm_returns_empty_string():
    pitch = _state("Pitch")
    current = _state("Need Discovery", outgoing=[_transition(pitch)])
    llm = _mock_llm(content="")
    sm = _mock_state_machine()
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[],
        llm=llm,
    )
    assert result is pitch
    sm.transition_to.assert_awaited_once()


@pytest.mark.asyncio
async def test_skips_outgoing_with_no_to_state():
    """Defence in depth: corrupted transitions (to_state=None) are ignored."""
    pitch = _state("Pitch")
    current = _state(
        "Need Discovery",
        outgoing=[
            SimpleNamespace(id=uuid.uuid4(), to_state=None, condition="bad", description="bad"),
            _transition(pitch),
        ],
    )
    llm = _mock_llm(content="Pitch")
    sm = _mock_state_machine()
    result = await force_pick_transition(
        state_machine=sm,
        conversation=SimpleNamespace(id=uuid.uuid4()),
        current_state=current,
        recent_messages=[],
        llm=llm,
    )
    assert result is pitch
