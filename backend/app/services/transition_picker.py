"""Maximum-turns force-transition helper.

When the agent gets stuck in a state past its configured ``maxTurns``
without calling ``__transition_to_state`` itself, the orchestrator falls
back to this helper to deterministically advance the conversation.

The helper does ONE short LLM call (≤32 tokens) asking the model which
outgoing transition is the best fit for the conversation so far, then
commits that transition via ``state_machine.transition_to`` with
``reason="max_turns_exceeded"``. If the LLM call fails or returns an
invalid target, falls back to the first outgoing transition by priority.

Lives outside ``StateMachine`` so the state machine itself stays free of
``LLMClient`` dependency — it remains a pure DB-mutation primitive.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.models.conversation import Conversation, Message
    from app.models.state import State
    from app.services.state_machine import StateMachine
    from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def force_pick_transition(
    *,
    state_machine: "StateMachine",
    conversation: "Conversation",
    current_state: "State",
    recent_messages: list["Message"],
    llm: "LLMClient",
) -> "State | None":
    """Pick the most appropriate outgoing transition and commit it.

    Returns the new state on success, or ``None`` when the current state
    has no outgoing transitions (the orchestrator's caller checks this
    before calling, but we double-check here for safety).
    """
    candidates = [
        t for t in (current_state.outgoing_transitions or [])
        if t.to_state is not None
    ]
    if not candidates:
        return None

    summary = "\n".join(
        f"[{m.role.value}] {m.content[:200]}"
        for m in recent_messages[-5:]
    )
    options = "\n".join(
        f"- {t.to_state.name}: "
        f"{(t.condition or t.description or '(no condition specified)').strip()}"
        for t in candidates
    )

    pick = ""
    try:
        response = await llm.chat(
            system_prompt=(
                "You pick the best next state for a stalled conversation. "
                "Respond with ONLY the target state name from the options "
                "list — no commentary, no quotes, no extra words."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Current state: {current_state.name}\n"
                        f"Recent conversation:\n{summary}\n\n"
                        f"Options:\n{options}\n\n"
                        "Reply with ONLY the target state name."
                    ),
                }
            ],
            max_tokens=32,
            temperature=0.0,
        )
        pick = (response.content or "").strip()
    except Exception:
        logger.warning(
            "force_pick LLM call failed for conversation %s; falling back "
            "to first-by-priority candidate",
            conversation.id,
            exc_info=True,
        )

    chosen = next(
        (t for t in candidates if t.to_state.name == pick),
        candidates[0],
    )
    logger.info(
        "transition_picker.force_pick conversation=%s reason=max_turns_exceeded "
        "from=%s to=%s llm_pick=%r matched=%s",
        conversation.id,
        current_state.name,
        chosen.to_state.name,
        pick,
        chosen.to_state.name == pick,
    )
    await state_machine.transition_to(
        conversation=conversation,
        new_state=chosen.to_state,
        transition_id=chosen.id,
        reason="max_turns_exceeded",
    )
    return chosen.to_state
