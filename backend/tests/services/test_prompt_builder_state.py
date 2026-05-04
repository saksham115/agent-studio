"""Unit tests for the # YOUR CURRENT TASK block + __transition_to_state tool.

Pure-function tests: build small fake State / Transition objects and
verify the prompt_builder emits the expected strings + tool definitions.
No DB required.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.prompt_builder import (
    MAX_MESSAGES,  # noqa: F401 — sanity: ensures public surface intact
    PromptBuilder,
    TRANSITION_TOOL_NAME,
    _max_turns,
)


def _state(
    *,
    name: str = "Need Discovery",
    description: str | None = "Understand customer requirements.",
    instructions: str | None = None,
    is_terminal: bool = False,
    metadata: dict | None = None,
    outgoing: list | None = None,
) -> Any:
    return SimpleNamespace(
        name=name,
        description=description,
        instructions=instructions,
        is_terminal=is_terminal,
        metadata_json=metadata,
        outgoing_transitions=outgoing or [],
    )


def _transition(target_name: str, *, condition: str | None = None,
                description: str | None = None) -> Any:
    target = SimpleNamespace(name=target_name)
    return SimpleNamespace(
        to_state=target,
        condition=condition,
        description=description,
    )


# ---------------------------------------------------------------------------
# # YOUR CURRENT TASK block
# ---------------------------------------------------------------------------


def test_current_task_block_is_first_in_system_prompt():
    """The new top block must precede base prompt / persona / etc."""
    pb = PromptBuilder()
    state = _state(
        name="Greeting",
        description="Welcome the customer",
        instructions="Be warm",
        outgoing=[_transition("Need Discovery", condition="user replies")],
    )
    agent = SimpleNamespace(
        system_prompt="BASE PROMPT TEXT",
        persona="Aarti",
        languages=["en"],
        description=None,
        fallback_message=None,
        escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    assert prompt.startswith("# YOUR CURRENT TASK")
    # Base prompt must come AFTER the task block, but BEFORE persona.
    task_idx = prompt.index("# YOUR CURRENT TASK")
    base_idx = prompt.index("BASE PROMPT TEXT")
    persona_idx = prompt.index("## Persona")
    assert task_idx < base_idx < persona_idx


def test_instructions_section_omitted_when_state_instructions_blank():
    pb = PromptBuilder()
    state = _state(
        name="Greeting",
        description="Welcome",
        instructions=None,
        outgoing=[_transition("Need Discovery", condition="x")],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    assert "## Instructions" not in prompt


def test_instructions_section_renders_when_state_instructions_present():
    pb = PromptBuilder()
    state = _state(
        name="Need Discovery",
        instructions="Ask about family size, budget, existing coverage.",
        outgoing=[_transition("Product Pitch", condition="needs identified")],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    assert "## Instructions" in prompt
    assert "Ask about family size, budget, existing coverage." in prompt


def test_pacing_line_renders_turn_count_when_max_turns_set():
    pb = PromptBuilder()
    state = _state(
        instructions="Do X",
        outgoing=[_transition("Pitch", condition="ready")],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
        state_turn_count=3, max_turns=8,
    )
    assert "Turn 3 of 8 in this state." in prompt


def test_pacing_line_escalates_to_final_turn_when_threshold_reached():
    pb = PromptBuilder()
    state = _state(
        instructions="Do X",
        outgoing=[_transition("Pitch", condition="ready")],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
        state_turn_count=8, max_turns=8,
    )
    assert "FINAL TURN" in prompt
    # Off-by-one regression guard: the pre-fix text was "Turn 9 of 8"
    # because the threshold compared `state_turn_count + 1 >= max_turns`.
    assert "Turn 8 of 8" not in prompt
    assert "Turn 9 of 8" not in prompt


def test_pacing_section_omitted_when_max_turns_unset():
    pb = PromptBuilder()
    state = _state(
        outgoing=[_transition("Pitch", condition="ready")],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
        state_turn_count=3, max_turns=None,
    )
    assert "## Conversation pacing" not in prompt


def test_terminal_state_replaces_available_next_steps():
    pb = PromptBuilder()
    state = _state(name="Closure", is_terminal=True, outgoing=[])
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    assert "This is a terminal state" in prompt
    assert TRANSITION_TOOL_NAME not in prompt


def test_non_terminal_state_with_no_outgoing_renders_wrap_up_hint():
    """Regression: a non-terminal state with zero outgoing transitions
    used to emit a stray blank line and no guidance. Now it renders an
    explicit 'no next steps configured' line so the LLM has an exit hint."""
    pb = PromptBuilder()
    state = _state(
        name="Stuck",
        description="Some description",
        is_terminal=False,
        outgoing=[],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    assert "## Available next steps" in prompt
    assert "No outgoing transitions" in prompt
    # The transition tool should not be referenced when there are no
    # outgoing targets — the orchestrator's build_tools omits it too.
    assert TRANSITION_TOOL_NAME not in prompt
    # Sanity: no triple-blank-line artefact from the previous unconditional
    # `lines.append("")` regression.
    assert "\n\n\n" not in prompt


def test_multi_edges_to_same_target_collapse_with_or_join():
    """Multi-edges A→B with different conditions render as ONE bullet."""
    pb = PromptBuilder()
    state = _state(
        instructions="Decide",
        outgoing=[
            _transition("Escalation", condition="user asks for human"),
            _transition("Escalation", condition="user shows frustration"),
            _transition("Pitch", condition="ready"),
        ],
    )
    agent = SimpleNamespace(
        system_prompt=None, persona=None, languages=[],
        description=None, fallback_message=None, escalation_message=None,
    )
    prompt = pb.build_system_prompt(
        agent=agent, current_state=state, guardrails=[], kb_context="",
    )
    # Only ONE Escalation bullet, with conditions OR-joined.
    assert prompt.count("**Escalation**") == 1
    assert "user asks for human OR user shows frustration" in prompt


# ---------------------------------------------------------------------------
# __transition_to_state tool definition
# ---------------------------------------------------------------------------


def test_build_tools_includes_transition_tool_for_non_terminal_state():
    pb = PromptBuilder()
    state = _state(
        outgoing=[_transition("Pitch"), _transition("Escalation")],
    )
    tools = pb.build_tools(actions=[], current_state=state)
    names = [t["function"]["name"] for t in tools]
    assert TRANSITION_TOOL_NAME in names


def test_build_tools_omits_transition_tool_in_terminal_state():
    pb = PromptBuilder()
    state = _state(name="Closure", is_terminal=True, outgoing=[])
    tools = pb.build_tools(actions=[], current_state=state)
    names = [t["function"]["name"] for t in tools]
    assert TRANSITION_TOOL_NAME not in names


def test_build_tools_omits_transition_tool_when_no_outgoing():
    pb = PromptBuilder()
    state = _state(outgoing=[])
    tools = pb.build_tools(actions=[], current_state=state)
    names = [t["function"]["name"] for t in tools]
    assert TRANSITION_TOOL_NAME not in names


def test_build_tools_omits_transition_tool_when_no_state():
    pb = PromptBuilder()
    tools = pb.build_tools(actions=[], current_state=None)
    names = [t["function"]["name"] for t in tools]
    assert TRANSITION_TOOL_NAME not in names


def test_transition_tool_enum_contains_only_outgoing_targets():
    pb = PromptBuilder()
    state = _state(
        outgoing=[
            _transition("Pitch"),
            _transition("Escalation"),
        ],
    )
    tools = pb.build_tools(actions=[], current_state=state)
    transition_tool = next(
        t for t in tools if t["function"]["name"] == TRANSITION_TOOL_NAME
    )
    enum_values = transition_tool["function"]["parameters"][
        "properties"
    ]["target_state"]["enum"]
    assert enum_values == ["Pitch", "Escalation"]


def test_transition_tool_enum_dedupes_multi_edges():
    """Multi-edges to the same target produce ONE enum entry."""
    pb = PromptBuilder()
    state = _state(
        outgoing=[
            _transition("Escalation", condition="cond a"),
            _transition("Escalation", condition="cond b"),
            _transition("Pitch"),
        ],
    )
    tools = pb.build_tools(actions=[], current_state=state)
    transition_tool = next(
        t for t in tools if t["function"]["name"] == TRANSITION_TOOL_NAME
    )
    enum_values = transition_tool["function"]["parameters"][
        "properties"
    ]["target_state"]["enum"]
    assert enum_values == ["Escalation", "Pitch"]
    assert len(enum_values) == len(set(enum_values))


def test_transition_tool_definition_is_json_serializable():
    """Regression guard: the tool definition must be json.dumps()-able."""
    pb = PromptBuilder()
    state = _state(
        outgoing=[_transition("Pitch"), _transition("Escalation")],
    )
    tools = pb.build_tools(actions=[], current_state=state)
    # If anything in the tool definition leaked an ORM object, this would
    # raise TypeError or produce <... object at 0x...> garbage.
    serialized = json.dumps(tools)
    assert "object at 0x" not in serialized
    assert TRANSITION_TOOL_NAME in serialized


def test_transition_tool_name_is_double_underscore_prefixed():
    """Namespace reservation: name must start with __ so user Action slugs
    (which strip leading underscores) can't collide."""
    assert TRANSITION_TOOL_NAME.startswith("__")


# ---------------------------------------------------------------------------
# _max_turns helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metadata, expected",
    [
        (None, None),
        ({}, None),
        ({"maxTurns": 5}, 5),
        ({"maxTurns": "8"}, 8),  # string-int coercion
        ({"max_turns": 5}, None),  # snake_case is the OLD bug — must NOT match
        ({"maxTurns": 0}, None),  # zero treated as unset
        ({"maxTurns": -3}, None),  # negative treated as unset
        ({"maxTurns": "5.5"}, None),  # non-integer string
        ({"maxTurns": "abc"}, None),  # garbage string
    ],
)
def test_max_turns_helper(metadata, expected):
    state = _state(metadata=metadata)
    assert _max_turns(state) == expected


def test_max_turns_helper_returns_none_for_none_state():
    assert _max_turns(None) is None
