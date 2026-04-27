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

# Number of recent messages included in a conversation summary.
SUMMARY_MESSAGE_COUNT = 5


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
    ) -> str:
        """Assemble the full system prompt from agent configuration.

        The prompt is built from distinct sections, each clearly separated
        by markdown headers so Claude can parse them easily:

        1. Agent base system prompt
        2. Persona
        3. Languages
        4. Current state (name, description, instructions, max turns)
        5. Available transitions from the current state
        6. Guardrail constraints
        7. Knowledge-base context
        8. Fallback / escalation instructions

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
        """
        sections: list[str] = []

        # 1. Base system prompt -----------------------------------------
        base_prompt = (agent.system_prompt or "").strip()
        if base_prompt:
            # Substitute template placeholders
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

        # 4. Current state block ----------------------------------------
        if current_state is not None:
            sections.append(self._build_state_section(current_state))

        # 5. Available transitions --------------------------------------
        if current_state is not None:
            transitions_section = self._build_transitions_section(current_state)
            if transitions_section:
                sections.append(transitions_section)

        # 6. Guardrails -------------------------------------------------
        guardrails_section = self._build_guardrails_section(guardrails)
        if guardrails_section:
            sections.append(guardrails_section)

        # 7. Knowledge-base context -------------------------------------
        if kb_context and kb_context.strip():
            sections.append(
                f"## Relevant Knowledge\n{kb_context.strip()}"
            )

        # 8. Fallback / escalation --------------------------------------
        fallback_section = self._build_fallback_section(agent)
        if fallback_section:
            sections.append(fallback_section)

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    def build_tools(self, actions: list[Action]) -> list[dict]:
        """Convert agent Action models to OpenAI-compatible tool definitions.

        Each ``Action`` is mapped to a tool dict with the shape expected
        by the OpenAI chat completions API::

            {
                "type": "function",
                "function": {
                    "name": "generate_payment_link",
                    "description": "...",
                    "parameters": {
                        "type": "object",
                        "properties": { ... },
                        "required": [ ... ]
                    }
                }
            }

        The ``action.input_params`` JSONB column stores parameter
        definitions in the format::

            {
                "customer_name": {
                    "type": "string",
                    "description": "Customer full name",
                    "required": true
                },
                ...
            }

        This method converts that to proper JSON Schema.

        Parameters
        ----------
        actions:
            Active ``Action`` ORM objects for the agent.

        Returns
        -------
        list[dict]
            Tool definitions ready for the ``tools`` parameter of the
            OpenAI-compatible chat completions API.
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

        return tools

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
    # Conversation summary (for transition evaluation)
    # ------------------------------------------------------------------

    def build_conversation_summary(
        self,
        messages: list[Message],
        current_state: State | None = None,
    ) -> str:
        """Build a brief text summary of the conversation for condition eval.

        Includes the last few messages with role labels and optionally the
        name of the current state the conversation is in.

        Parameters
        ----------
        messages:
            Full ordered list of conversation messages.
        current_state:
            The current state the conversation is in, if any.

        Returns
        -------
        str
            A human-readable summary suitable for passing to
            ``LLMClient.evaluate_condition``.
        """
        parts: list[str] = []

        if current_state:
            parts.append(f"Current state: {current_state.name}")
            if current_state.description:
                parts.append(f"State purpose: {current_state.description}")

        recent = messages[-SUMMARY_MESSAGE_COUNT:]

        if recent:
            parts.append("\nRecent messages:")
            for msg in recent:
                role_label = msg.role.value.upper()
                # Truncate very long messages for the summary.
                content = msg.content
                if len(content) > 300:
                    content = content[:297] + "..."
                parts.append(f"  [{role_label}]: {content}")

        if not parts:
            return "No conversation history available."

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_state_section(state: State) -> str:
        """Format the current-state block for the system prompt."""
        lines = [f"## Current State: {state.name}"]

        if state.description:
            lines.append(state.description)

        if state.instructions:
            lines.append(f"\n### State Instructions\n{state.instructions}")

        meta = state.metadata_json or {}
        max_turns = meta.get("max_turns")
        if max_turns is not None:
            lines.append(
                f"\nYou have a maximum of {max_turns} turns in this state. "
                f"Work efficiently within this limit."
            )

        if state.is_terminal:
            lines.append(
                "\nThis is a terminal state. Wrap up the conversation "
                "appropriately when the objective is met."
            )

        return "\n".join(lines)

    @staticmethod
    def _build_transitions_section(state: State) -> str:
        """Format available transitions from the current state."""
        transitions: list[Transition] = state.outgoing_transitions or []
        if not transitions:
            return ""

        # Sort by priority (higher priority first).
        sorted_transitions = sorted(
            transitions, key=lambda t: t.priority, reverse=True
        )

        lines = ["## Available Transitions"]
        lines.append(
            "When any of the following conditions are met, the conversation "
            "will move to the corresponding next state:"
        )

        for idx, t in enumerate(sorted_transitions, start=1):
            target_name = t.to_state.name if t.to_state else "unknown"
            condition_text = t.condition or t.description or "No condition specified"
            lines.append(f"{idx}. **{target_name}**: {condition_text}")

        return "\n".join(lines)

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
