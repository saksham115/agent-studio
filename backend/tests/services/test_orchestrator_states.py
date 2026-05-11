"""Unit tests for the orchestrator's __transition_to_state dispatch.

Focused on the seams that surfaced in the plan-review process:
- tool_result dict is JSON-serializable (no ORM-leak)
- _handle_transition_tool returns (dict, State|None) tuple
- invalid target_name → error result + None state, no transition committed
- terminal target → conversation marked COMPLETED + ended_at
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.conversation import Conversation, ConversationStatus
from app.services.orchestrator import ConversationOrchestrator


def _state(name: str, *, is_terminal: bool = False, outgoing: list | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        is_terminal=is_terminal,
        outgoing_transitions=outgoing or [],
    )


def _transition(target: SimpleNamespace):
    return SimpleNamespace(
        id=uuid.uuid4(),
        to_state=target,
        to_state_id=target.id,
        condition="x",
        description="x",
    )


def _build_orchestrator():
    """Construct an orchestrator with a stub DB session for unit tests."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    orch = ConversationOrchestrator(db)
    # Override the state_machine so we can assert against its calls without
    # actually hitting the DB.
    orch.state_machine.transition_to = AsyncMock()
    orch.state_machine.get_current_state = AsyncMock()
    return orch


def _new_conversation(state_id: uuid.UUID | None = None) -> Conversation:
    """Build an unattached Conversation row for assertion."""
    return Conversation(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        status=ConversationStatus.ACTIVE,
        current_state_id=state_id,
        message_count=0,
        state_turn_count=0,
    )


@pytest.mark.asyncio
async def test_handle_transition_tool_returns_tuple_with_serializable_dict():
    """Regression guard: tool_result dict must NOT contain the State ORM
    object. _store_tool_messages json.dumps's it, so leaking the object
    would produce '<...object at 0x...>' garbage in the LLM-visible
    tool_result content."""
    pitch = _state("Pitch")
    current = _state("Need Discovery", outgoing=[_transition(pitch)])
    orch = _build_orchestrator()
    orch.state_machine.get_current_state.return_value = pitch
    conv = _new_conversation(current.id)

    result, new_state = await orch._handle_transition_tool(
        conv, current, {"target_state": "Pitch", "reason": "needs identified"},
    )

    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["new_state_name"] == "Pitch"
    assert "new_state" not in result  # ORM object stays out of result
    assert new_state is pitch  # but is handed back via the tuple
    # Sanity: the dict serializes cleanly with default=str (the same
    # behaviour _store_tool_messages uses).
    serialized = json.dumps(result, default=str)
    assert "object at 0x" not in serialized


@pytest.mark.asyncio
async def test_handle_transition_tool_rejects_invalid_target_name():
    pitch = _state("Pitch")
    current = _state("Need Discovery", outgoing=[_transition(pitch)])
    orch = _build_orchestrator()
    conv = _new_conversation(current.id)

    result, new_state = await orch._handle_transition_tool(
        conv, current, {"target_state": "NonExistent", "reason": "bad"},
    )

    assert result["ok"] is False
    assert "not an outgoing transition" in result["error"]
    assert new_state is None
    orch.state_machine.transition_to.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_transition_tool_rejects_when_no_outgoing():
    """A terminal-or-stuck state should refuse all targets."""
    current = _state("Closure", is_terminal=True, outgoing=[])
    orch = _build_orchestrator()
    conv = _new_conversation(current.id)

    result, new_state = await orch._handle_transition_tool(
        conv, current, {"target_state": "Anything", "reason": "x"},
    )

    assert result["ok"] is False
    assert new_state is None


@pytest.mark.asyncio
async def test_handle_transition_tool_marks_terminal_state_completed():
    """Transitioning into a terminal state should set status=COMPLETED
    and ended_at."""
    closure = _state("Closure", is_terminal=True)
    current = _state("Documents", outgoing=[_transition(closure)])
    orch = _build_orchestrator()
    orch.state_machine.get_current_state.return_value = closure
    conv = _new_conversation(current.id)
    assert conv.ended_at is None

    result, new_state = await orch._handle_transition_tool(
        conv, current, {"target_state": "Closure", "reason": "all done"},
    )

    assert result["ok"] is True
    assert new_state is closure
    assert conv.status == ConversationStatus.COMPLETED
    assert conv.ended_at is not None


@pytest.mark.asyncio
async def test_handle_transition_tool_does_not_mark_completed_for_non_terminal():
    pitch = _state("Pitch", is_terminal=False)
    current = _state("Need Discovery", outgoing=[_transition(pitch)])
    orch = _build_orchestrator()
    orch.state_machine.get_current_state.return_value = pitch
    conv = _new_conversation(current.id)

    result, new_state = await orch._handle_transition_tool(
        conv, current, {"target_state": "Pitch", "reason": "needs ok"},
    )

    assert result["ok"] is True
    assert new_state is pitch
    assert conv.status == ConversationStatus.ACTIVE
    assert conv.ended_at is None


@pytest.mark.asyncio
async def test_handle_transition_tool_routes_via_state_machine_transition_to():
    """Verify the state-machine call carries the right transition_id and reason."""
    pitch = _state("Pitch")
    transition = _transition(pitch)
    current = _state("Need Discovery", outgoing=[transition])
    orch = _build_orchestrator()
    orch.state_machine.get_current_state.return_value = pitch
    conv = _new_conversation(current.id)

    await orch._handle_transition_tool(
        conv, current, {"target_state": "Pitch", "reason": "user agreed"},
    )

    orch.state_machine.transition_to.assert_awaited_once()
    kwargs = orch.state_machine.transition_to.await_args.kwargs
    assert kwargs["new_state"] is pitch
    assert kwargs["transition_id"] == transition.id
    assert kwargs["reason"] == "user agreed"


@pytest.mark.asyncio
async def test_handle_transition_tool_with_none_current_state():
    """When current_state is None (stateless agent), the tool should
    politely refuse rather than crash."""
    orch = _build_orchestrator()
    conv = _new_conversation(None)

    result, new_state = await orch._handle_transition_tool(
        conv, None, {"target_state": "Pitch", "reason": "x"},
    )

    assert result["ok"] is False
    assert new_state is None
