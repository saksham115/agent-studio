"""Prompt assembler for the Agent Studio conversation orchestrator.

Constructs the full system prompt, tool definitions, and message history
that get sent to the LLM on each turn. The quality of the assembled prompt
directly determines agent performance, so care is taken to produce
clear, well-structured instructions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.models.agent import Agent
from app.models.state import State, Transition
from app.models.guardrail import Guardrail, GuardrailAction
from app.models.action import Action
from app.models.conversation import Message, MessageRole

# Maximum number of recent messages sent to Claude in the messages array.
MAX_MESSAGES = 40

# Name of the system meta-tool the orchestrator uses to let the LLM advance
# the conversation through the state diagram. Double-underscore-prefixed so
# it can never collide with a user-defined Action name (``_slugify`` strips
# leading underscores from user names — see _slugify below).
TRANSITION_TOOL_NAME = "__transition_to_state"


def _max_turns(state: State | None) -> int | None:
    """Read the configured `maxTurns` from a state's metadata.

    Wizard saves the field as camelCase ``metadata.maxTurns``. Returns
    ``None`` when unset, non-numeric, zero, or negative — the orchestrator
    treats those as "no limit, no force-pick".
    """
    if state is None or state.metadata_json is None:
        return None
    raw = state.metadata_json.get("maxTurns")
    if not isinstance(raw, (int, str)) or not str(raw).isdigit():
        return None
    value = int(raw)
    return value if value > 0 else None


class PromptBuilder:
    """Assembles all inputs for a Claude API call from Agent Studio models.

    Stateless — every public method is a pure function of its arguments.
    Instantiate once and reuse across requests.
    """

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        agent: Agent,
        current_state: State | None,
        guardrails: list[Guardrail],
        kb_context: str,
        state_turn_count: int = 0,
        max_turns: int | None = None,
    ) -> str:
        """Assemble the full system prompt from agent configuration.

        The state-aware ``# YOUR CURRENT TASK`` block is promoted to the
        very top so the LLM treats it as the primary directive. Section
        order:

        0. ``# YOUR CURRENT TASK`` — current state name, goal, instructions,
           pacing, and available next-state transitions (only when an
           ``current_state`` is provided).
        1. Agent base system prompt.
        2. Persona.
        3. Languages.
        4. Guardrail constraints.
        5. Knowledge-base context.
        6. Fallback / escalation instructions.

        Parameters
        ----------
        agent:
            The Agent ORM object with core configuration.
        current_state:
            The active state in the conversation flow (may be ``None``
            when the agent has no state machine or hasn't entered one).
        guardrails:
            Active guardrail rules the agent must obey.
        kb_context:
            Pre-retrieved knowledge-base text relevant to the current
            user query.  Empty string when nothing was retrieved.
        state_turn_count:
            How many agent turns have already completed in the current
            state (incremented at the top of ``process_message``). Used
            to render the pacing line.
        max_turns:
            Configured ``metadata.maxTurns`` for the current state, or
            ``None`` when unset. When ``state_turn_count >= max_turns``
            the pacing line escalates to a FINAL TURN warning.
        """
        sections: list[str] = []

        # 0. # YOUR CURRENT TASK (top-of-prompt) ------------------------
        if current_state is not None:
            sections.append(
                self._build_current_task_section(
                    current_state, state_turn_count, max_turns,
                )
            )

        # 1. Base system prompt -----------------------------------------
        base_prompt = (agent.system_prompt or "").strip()
        if base_prompt:
            base_prompt = base_prompt.replace("{{persona_name}}", agent.persona or "Agent")
            base_prompt = base_prompt.replace("{{customer_name}}", agent.description or "the company")
            sections.append(base_prompt)

        # 2. Persona ----------------------------------------------------
        if agent.persona:
            sections.append(f"## Persona\nYour name is {agent.persona}.")

        # 3. Languages --------------------------------------------------
        languages = agent.languages or []
        if languages:
            lang_list = ", ".join(languages)
            sections.append(
                f"## Languages\n"
                f"You can communicate in: {lang_list}. "
                f"Respond in the language the user writes to you in, "
                f"unless they explicitly ask for a different language."
            )

        # 4. Guardrails -------------------------------------------------
        guardrails_section = self._build_guardrails_section(guardrails)
        if guardrails_section:
            sections.append(guardrails_section)

        # 5. Knowledge-base context -------------------------------------
        if kb_context and kb_context.strip():
            sections.append(
                f"## Relevant Knowledge\n{kb_context.strip()}"
            )

        # 6. Fallback / escalation --------------------------------------
        fallback_section = self._build_fallback_section(agent)
        if fallback_section:
            sections.append(fallback_section)

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    def build_tools(
        self,
        actions: list[Action],
        current_state: State | None = None,
    ) -> list[dict]:
        """Convert agent Actions + the system transition tool to OpenAI tool defs.

        Returns the user's Action tools (existing behaviour) followed by the
        ``__transition_to_state`` meta-tool when ``current_state`` has at
        least one outgoing transition and is not terminal. The transition
        tool's ``target_state`` parameter is constrained via JSON Schema
        ``enum`` to the unique outgoing target names — most providers
        honour this; ``Orchestrator._handle_transition_tool`` re-validates
        as defence in depth.

        See module-level ``TRANSITION_TOOL_NAME`` for the system tool's
        reserved name (double-underscore-prefixed; cannot collide with
        user-defined Action names because ``_slugify`` strips leading
        underscores).
        """
        tools: list[dict] = []

        for action in actions:
            if not action.is_active:
                continue

            tool_name = self._slugify(action.name)
            description = action.description or action.name

            input_schema = self._build_input_schema(action.input_params)

            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": description,
                        "parameters": input_schema,
                    },
                }
            )

        transition_tool = self._build_transition_tool(current_state)
        if transition_tool is not None:
            tools.append(transition_tool)

        return tools

    @staticmethod
    def _build_transition_tool(state: State | None) -> dict | None:
        """Build the ``__transition_to_state`` system tool definition.

        Returns ``None`` when:
        - ``state`` is ``None`` (stateless agent),
        - ``state.is_terminal`` (no outgoing transitions),
        - or there are no outgoing transitions with valid target states.

        Multi-edges to the same target collapse to a single ``enum`` entry
        (the prompt's "Available next steps" still shows them grouped with
        OR-joined conditions).
        """
        if state is None or state.is_terminal:
            return None
        targets = list(dict.fromkeys(
            t.to_state.name for t in (state.outgoing_transitions or [])
            if t.to_state is not None
        ))
        if not targets:
            return None
        return {
            "type": "function",
            "function": {
                "name": TRANSITION_TOOL_NAME,
                "description": (
                    "Move the conversation to a new state when the current "
                    "state's goal is met or a trigger condition appears. "
                    "Available targets are listed in your system prompt's "
                    "'Available next steps' section."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_state": {
                            "type": "string",
                            "enum": targets,
                            "description": "Name of the target state.",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One-sentence justification for the "
                                "transition based on the conversation."
                            ),
                        },
                    },
                    "required": ["target_state", "reason"],
                },
            },
        }

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------

    def format_messages(self, messages: list[Message]) -> list[dict]:
        """Convert DB ``Message`` objects to OpenAI-compatible message dicts.

        - ``MessageRole.USER`` messages become ``{"role": "user", ...}``
        - ``MessageRole.ASSISTANT`` messages become ``{"role": "assistant", ...}``
          including any ``tool_calls`` stored on the message.
        - ``MessageRole.SYSTEM`` messages are skipped (system prompt is
          passed separately).
        - ``MessageRole.TOOL`` messages become ``{"role": "tool", ...}``
          with a ``tool_call_id``.
        - The list is truncated to the most recent ``MAX_MESSAGES``
          messages to stay within context limits.

        Parameters
        ----------
        messages:
            Ordered list of ``Message`` ORM objects (oldest first).

        Returns
        -------
        list[dict]
            Message dicts in OpenAI-compatible format.
        """
        if not messages:
            return []

        # Truncate to most recent messages.
        recent = messages[-MAX_MESSAGES:]

        formatted: list[dict] = []

        for msg in recent:
            if msg.role == MessageRole.SYSTEM:
                continue

            if msg.role == MessageRole.USER:
                formatted.append({"role": "user", "content": msg.content})

            elif msg.role == MessageRole.ASSISTANT:
                formatted.append(self._format_assistant_message(msg))

            elif msg.role == MessageRole.TOOL:
                formatted.append(self._format_tool_result_message(msg))

        # Ensure the messages list starts with a user message.
        while formatted and formatted[0]["role"] not in ("user", "system"):
            formatted.pop(0)

        return formatted


    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_current_task_section(
        state: State,
        state_turn_count: int,
        max_turns: int | None,
    ) -> str:
        """Format the top-of-prompt ``# YOUR CURRENT TASK`` block.

        Renders sections conditionally:

        - ``## Goal`` from ``state.description`` (always present in
          practice).
        - ``## Instructions`` only when ``state.instructions`` is a
          non-empty, non-whitespace string. Pre-PR rows have NULL here;
          for those, the section is omitted entirely.
        - ``## Conversation pacing`` only when ``max_turns`` is set
          (non-None). Renders FINAL-TURN escalation text once
          ``state_turn_count >= max_turns`` (the counter is incremented at
          the top of ``process_message`` before the prompt is built, so
          the value the LLM sees is the count of turns about to happen
          including this one).
        - ``## Available next steps`` lists outgoing transitions, grouped
          by target name (multi-edges with different conditions OR-
          collapse into one bullet). Replaced by a "this is a terminal
          state" line when ``state.is_terminal``.

        Closes with a directive to call the ``__transition_to_state`` tool
        with the target state name and a reason — matches the tool the
        orchestrator wires in via ``build_tools``.
        """
        lines: list[str] = ["# YOUR CURRENT TASK", "", f"You are in state: **{state.name}**"]

        # Goal
        if state.description and state.description.strip():
            lines += ["", "## Goal", state.description.strip()]

        # Instructions — omit when None/blank
        if state.instructions and state.instructions.strip():
            lines += ["", "## Instructions", state.instructions.strip()]

        # Pacing — omit when no maxTurns configured
        if max_turns is not None:
            lines.append("")
            lines.append("## Conversation pacing")
            if state_turn_count >= max_turns:
                lines.append(
                    "FINAL TURN — you MUST transition this turn or the "
                    "conversation will auto-advance."
                )
            else:
                lines.append(
                    f"Turn {state_turn_count} of {max_turns} in this state."
                )

        # Available next steps (or terminal-state notice)
        lines.append("")
        if state.is_terminal:
            lines.append("## Available next steps")
            lines.append(
                "This is a terminal state. Wrap up the conversation; do not "
                "transition."
            )
        else:
            transitions: list[Transition] = state.outgoing_transitions or []
            if transitions:
                # Group by target name so multi-edges to the same target
                # collapse into one bullet whose conditions are OR-joined.
                by_target: dict[str, list[str]] = {}
                for t in transitions:
                    if t.to_state is None:
                        continue
                    cond = (t.condition or t.description or "").strip()
                    by_target.setdefault(t.to_state.name, []).append(cond)
                if by_target:
                    lines.append("## Available next steps")
                    for target, conds in by_target.items():
                        nonempty = [c for c in conds if c]
                        if nonempty:
                            lines.append(
                                f"- **{target}** — {' OR '.join(nonempty)}"
                            )
                        else:
                            lines.append(f"- **{target}**")
                    lines.append("")
                    lines.append(
                        f"To advance the conversation, call the "
                        f"`{TRANSITION_TOOL_NAME}` tool with the target state "
                        f"name and a brief reason. ONLY transition when the "
                        f"goal is genuinely met or a specific trigger "
                        f"appears. Stay in this state otherwise. Your reply "
                        f"to the user should come AFTER any transition "
                        f"decision."
                    )

        return "\n".join(lines).rstrip()

    @staticmethod
    def _build_guardrails_section(guardrails: list[Guardrail]) -> str:
        """Format guardrail rules as constraints in the system prompt."""
        # Only include active guardrails.
        active = [g for g in guardrails if g.is_active]
        if not active:
            return ""

        # Sort by priority (higher first).
        active.sort(key=lambda g: g.priority, reverse=True)

        lines = ["## Constraints & Rules"]
        lines.append(
            "You MUST follow these rules at all times. Violations may "
            "cause the response to be blocked or flagged."
        )

        for g in active:
            action_label = {
                GuardrailAction.BLOCK: "MUST NOT",
                GuardrailAction.WARN: "SHOULD NOT",
                GuardrailAction.REDIRECT: "MUST redirect instead",
                GuardrailAction.LOG: "AVOID",
            }.get(g.action, "MUST NOT")

            rule_text = g.rule.strip()
            line = f"- **[{g.guardrail_type.value.upper()}]** {action_label}: {rule_text}"
            if g.description:
                line += f" — {g.description}"
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _build_fallback_section(agent: Agent) -> str:
        """Format fallback and escalation instructions."""
        parts: list[str] = []

        if agent.fallback_message or agent.escalation_message:
            parts.append("## Fallback & Escalation")

        if agent.fallback_message:
            parts.append(
                f"When you cannot help or do not understand the user's "
                f"request, respond with: \"{agent.fallback_message}\""
            )

        if agent.escalation_message:
            parts.append(
                f"When the user explicitly asks to speak with a human "
                f"or the conversation requires human intervention, "
                f"respond with: \"{agent.escalation_message}\""
            )

        return "\n".join(parts)

    @staticmethod
    def _build_input_schema(input_params: dict | None) -> dict[str, Any]:
        """Convert the Agent Studio param format to JSON Schema.

        Input format (from ``action.input_params``)::

            {
                "customer_name": {
                    "type": "string",
                    "description": "Customer full name",
                    "required": true
                }
            }

        Output (JSON Schema for Claude tools)::

            {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Customer full name"
                    }
                },
                "required": ["customer_name"]
            }
        """
        if not input_params:
            return {"type": "object", "properties": {}}

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param_def in input_params.items():
            if not isinstance(param_def, dict):
                # Skip malformed entries.
                continue

            prop: dict[str, Any] = {}

            # Copy standard JSON Schema fields.
            if "type" in param_def:
                prop["type"] = param_def["type"]
            else:
                prop["type"] = "string"  # Default to string.

            if "description" in param_def:
                prop["description"] = param_def["description"]

            if "enum" in param_def:
                prop["enum"] = param_def["enum"]

            if "default" in param_def:
                prop["default"] = param_def["default"]

            if "items" in param_def:
                prop["items"] = param_def["items"]

            properties[param_name] = prop

            # Track required fields.
            if param_def.get("required", False):
                required.append(param_name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    @staticmethod
    def _format_assistant_message(msg: Message) -> dict:
        """Format an assistant message, including any tool_calls."""
        if not msg.tool_calls:
            return {"role": "assistant", "content": msg.content}

        # Build the OpenAI-format tool_calls array from stored data.
        tool_calls_list: list[dict] = []

        tool_calls_data = msg.tool_calls
        items = [tool_calls_data] if isinstance(tool_calls_data, dict) else (tool_calls_data or [])

        for tc in items:
            tool_calls_list.append({
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": json.dumps(tc.get("input", {})),
                },
            })

        result: dict = {"role": "assistant", "tool_calls": tool_calls_list}
        # Include text content if present.
        text = msg.content.strip() if msg.content else ""
        if text:
            result["content"] = text

        return result

    @staticmethod
    def _format_tool_result_message(msg: Message) -> dict:
        """Format a tool-result message in OpenAI format.

        Tool results are sent as ``tool``-role messages with a
        ``tool_call_id`` referencing the assistant's tool call.
        """
        meta = msg.metadata_json or {}
        tool_call_id = meta.get("tool_use_id", "")

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": msg.content,
        }

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a human-readable action name to a tool-safe slug.

        Examples:
            "Generate Payment Link" -> "generate_payment_link"
            "Look Up  Customer" -> "look_up_customer"
        """
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "_", slug)
        slug = slug.strip("_")
        return slug or "unnamed_tool"
