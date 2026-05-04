"""State machine service for managing conversation state transitions.

Handles state lookups, transition evaluation, and audit logging for
the agent conversation flow. Works with stateless agents (no states
defined) gracefully by returning None where appropriate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.state import State, Transition
from app.models.conversation import Conversation
from app.models.audit import StateTransitionLog


class StateMachine:
    """Manages state lookups and transitions for agent conversations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_initial_state(self, agent_id: uuid.UUID) -> State | None:
        """Find the initial state for an agent.

        Returns the state where ``is_initial=True`` for the given agent.
        If no states are defined (stateless agent), returns None.
        """
        stmt = (
            select(State)
            .where(State.agent_id == agent_id, State.is_initial.is_(True))
            .options(selectinload(State.outgoing_transitions).selectinload(Transition.to_state))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_state(self, state_id: uuid.UUID) -> State | None:
        """Load a state by ID with its outgoing transitions eagerly loaded.

        Transitions are loaded with their target states so that callers
        can inspect both the condition and the destination state without
        additional queries.
        """
        stmt = (
            select(State)
            .where(State.id == state_id)
            .options(
                selectinload(State.outgoing_transitions)
                .selectinload(Transition.to_state)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_transitions(self, state_id: uuid.UUID) -> list[Transition]:
        """Get outgoing transitions from a state ordered by priority (ascending).

        Lower priority number = higher precedence. Eagerly loads the target
        state for each transition so condition evaluation has full context.
        """
        stmt = (
            select(Transition)
            .where(Transition.from_state_id == state_id)
            .options(selectinload(Transition.to_state))
            .order_by(Transition.priority.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def transition_to(
        self,
        conversation: Conversation,
        new_state: State,
        *,
        transition_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition a conversation to a new state and log the change.

        Captures the previous ``current_state_id`` BEFORE mutation, then
        updates ``current_state_id``, resets the per-state turn counter
        and entry timestamp, and writes an audit row to
        ``state_transitions``.

        Args:
            conversation: The conversation to transition.
            new_state: The destination state.
            transition_id: Optional ID of the Transition rule that triggered
                this change (may be None for programmatic transitions).
            reason: Optional human-readable reason for the transition.
        """
        old_state_id = conversation.current_state_id  # capture BEFORE mutation

        now = datetime.now(timezone.utc)
        conversation.current_state_id = new_state.id
        conversation.state_entered_at = now
        conversation.state_turn_count = 0

        log = StateTransitionLog(
            conversation_id=conversation.id,
            from_state_id=old_state_id,
            to_state_id=new_state.id,
            transition_id=transition_id,
            reason=reason,
            metadata_json={
                "new_state_name": new_state.name,
                "timestamp": now.isoformat(),
            },
        )
        self.db.add(log)
        await self.db.flush()

    async def bootstrap_initial_state(
        self,
        conversation: Conversation,
        initial_state: State,
    ) -> None:
        """Seed the timeline + counters when a conversation enters its first state.

        Writes a ``StateTransitionLog`` row with ``from_state_id=None`` and
        ``reason="initial_state"`` so the timeline endpoint has a starting
        anchor; sets the conversation's ``current_state_id``,
        ``state_entered_at``, and ``state_turn_count`` accordingly. Called by
        ``Orchestrator.start_conversation`` when the agent has an initial
        state defined.
        """
        now = datetime.now(timezone.utc)
        conversation.current_state_id = initial_state.id
        conversation.state_entered_at = now
        conversation.state_turn_count = 0

        log = StateTransitionLog(
            conversation_id=conversation.id,
            from_state_id=None,
            to_state_id=initial_state.id,
            transition_id=None,
            reason="initial_state",
            metadata_json={
                "new_state_name": initial_state.name,
                "timestamp": now.isoformat(),
            },
        )
        self.db.add(log)
        await self.db.flush()

    async def is_terminal(self, state_id: uuid.UUID) -> bool:
        """Check whether a state is terminal (end of conversation flow).

        Returns False if the state does not exist.
        """
        stmt = select(State.is_terminal).where(State.id == state_id)
        result = await self.db.execute(stmt)
        value = result.scalar_one_or_none()
        return bool(value)
