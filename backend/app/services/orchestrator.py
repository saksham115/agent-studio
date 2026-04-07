"""Conversation orchestrator — the core message-processing loop.

Coordinates all services (LLM, knowledge base, guardrails, actions, state
machine) to handle an incoming user message and produce the agent's response.
Designed to work for agents of any complexity: from a bare system-prompt
chatbot all the way to a fully configured stateful agent with tools,
guardrails, and a knowledge base.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent, AgentStatus
from app.models.conversation import Conversation, ConversationStatus, Message, MessageRole
from app.models.state import State
from app.models.action import Action
from app.models.guardrail import Guardrail
from app.models.audit import ActionExecution, GuardrailTrigger
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.action_executor import ActionExecutor
from app.services.guardrail_service import GuardrailService
from app.services.state_machine import StateMachine

logger = logging.getLogger(__name__)

# Maximum sequential tool-call iterations to prevent infinite loops.
MAX_TOOL_CALL_ITERATIONS = 5


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResponse:
    """Value object returned by the orchestrator after processing a message."""

    message: str
    conversation_id: uuid.UUID
    state: str | None = None
    actions_executed: list[dict] = field(default_factory=list)
    guardrails_triggered: list[dict] = field(default_factory=list)
    status: str = ConversationStatus.ACTIVE.value
    token_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ConversationOrchestrator:
    """Processes a user message through the full agent pipeline.

    Typical usage::

        async with async_session_factory() as db:
            orchestrator = ConversationOrchestrator(db)
            response = await orchestrator.process_message(conversation_id, "Hi!")
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.llm = LLMClient()
        self.prompt_builder = PromptBuilder()
        self.kb_service = KnowledgeBaseService(db)
        self.action_executor = ActionExecutor(db)
        self.guardrail_service = GuardrailService(db)
        self.state_machine = StateMachine(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_conversation(self, agent_id: uuid.UUID) -> OrchestratorResponse:
        """Create a new conversation for the given agent.

        Sets the current state to the agent's initial state (if one exists)
        and stores the welcome message (if configured) as the first
        assistant message.

        Returns an :class:`OrchestratorResponse` with the welcome message
        or a sensible default greeting.
        """

        # Load agent
        agent = await self._load_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        if agent.status != AgentStatus.PUBLISHED:
            raise ValueError(f"Agent {agent_id} is not published (status={agent.status.value})")

        # Determine initial state (may be None for stateless agents)
        initial_state = await self.state_machine.get_initial_state(agent_id)

        # Create conversation
        conversation = Conversation(
            agent_id=agent_id,
            status=ConversationStatus.ACTIVE,
            current_state_id=initial_state.id if initial_state else None,
            context={},
            message_count=0,
        )
        self.db.add(conversation)
        await self.db.flush()

        # Determine the greeting
        welcome_text = agent.welcome_message or f"Hello! I'm {agent.name}. How can I help you today?"

        # Store welcome message
        welcome_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=welcome_text,
        )
        self.db.add(welcome_msg)
        conversation.message_count = 1
        await self.db.flush()

        return OrchestratorResponse(
            message=welcome_text,
            conversation_id=conversation.id,
            state=initial_state.name if initial_state else None,
            status=ConversationStatus.ACTIVE.value,
        )

    async def process_message(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
    ) -> OrchestratorResponse:
        """Process an incoming user message and return the agent's response.

        This is the main entry-point for the conversation loop.  The full
        pipeline is:

        1. Load conversation (with agent, state, recent messages)
        2. Validate conversation/agent status
        3. Input guardrails
        4. Store user message
        5. Knowledge-base retrieval
        6. Build prompt & call LLM
        7. Handle tool-use loop (up to ``MAX_TOOL_CALL_ITERATIONS``)
        8. Output guardrails
        9. Store assistant message
        10. Evaluate state transitions
        11. Update conversation metadata
        12. Return response
        """

        # Accumulators for the response
        actions_executed: list[dict] = []
        guardrails_triggered: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0

        # ---- 1. Load conversation ----------------------------------------
        conversation = await self._load_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        agent: Agent = conversation.agent

        # ---- 2. Validate -------------------------------------------------
        if conversation.status != ConversationStatus.ACTIVE:
            raise ValueError(
                f"Conversation {conversation_id} is not active "
                f"(status={conversation.status.value})"
            )
        if agent.status != AgentStatus.PUBLISHED:
            raise ValueError(
                f"Agent {agent.id} is not published (status={agent.status.value})"
            )

        # ---- 3. Input guardrails -----------------------------------------
        guardrails = await self._load_guardrails(agent.id)
        input_guardrails = [g for g in guardrails if g.is_active]

        if input_guardrails:
            input_check = await self.guardrail_service.check_input(user_message, input_guardrails)
            if not input_check.passed:
                # Log triggered guardrail rules
                for rule_info in (input_check.triggered_rules or []):
                    guardrails_triggered.append(rule_info)
                    await self._log_guardrail_trigger(
                        conversation_id=conversation_id,
                        guardrails=guardrails,
                        rule_info=rule_info,
                        original=user_message,
                        modified=input_check.modified_text,
                    )
                # Return block message without calling the LLM
                block_text = (
                    input_check.modified_text
                    or "I'm sorry, I can't process that request."
                )
                return OrchestratorResponse(
                    message=block_text,
                    conversation_id=conversation_id,
                    state=await self._state_name(conversation.current_state_id),
                    guardrails_triggered=guardrails_triggered,
                    status=ConversationStatus.ACTIVE.value,
                )

            # If guardrail modified the text (warn/log), use the modified version
            if input_check.modified_text:
                user_message = input_check.modified_text
            if input_check.triggered_rules:
                for rule_info in input_check.triggered_rules:
                    guardrails_triggered.append(rule_info)

        # ---- 4. Store user message ---------------------------------------
        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        # ---- 5. Knowledge-base retrieval ---------------------------------
        kb_context: list[str] = []
        try:
            kb_context = await self.kb_service.search(agent.id, user_message, top_k=5)
        except Exception:
            logger.warning(
                "Knowledge base search failed for agent %s — continuing without KB context",
                agent.id,
                exc_info=True,
            )

        # ---- 6. Build prompt ---------------------------------------------
        current_state: State | None = None
        if conversation.current_state_id:
            current_state = await self.state_machine.get_current_state(
                conversation.current_state_id
            )

        # Load recent messages from the DB (the relationship may be stale)
        messages_list = await self._load_messages(conversation_id)

        system_prompt = self.prompt_builder.build_system_prompt(
            agent=agent,
            current_state=current_state,
            guardrails=guardrails,
            kb_context=kb_context,
        )

        formatted_messages = self.prompt_builder.format_messages(messages_list)

        # Load active actions and build tools
        actions = await self._load_actions(agent.id)
        tools = self.prompt_builder.build_tools(actions) if actions else []

        # ---- 7. Call LLM -------------------------------------------------
        start_ts = time.monotonic()
        llm_response = await self.llm.chat(
            system_prompt=system_prompt,
            messages=formatted_messages,
            tools=tools or None,
            max_tokens=4096,
        )
        llm_latency_ms = int((time.monotonic() - start_ts) * 1000)

        total_input_tokens += llm_response.input_tokens or 0
        total_output_tokens += llm_response.output_tokens or 0

        # ---- 8. Tool-use loop --------------------------------------------
        iteration = 0
        while llm_response.tool_calls and iteration < MAX_TOOL_CALL_ITERATIONS:
            iteration += 1

            for tool_call in llm_response.tool_calls:
                tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
                tool_input = tool_call.get("input") or tool_call.get("arguments", {})
                tool_use_id = tool_call.get("id", str(uuid.uuid4()))

                # Find matching action
                action = self._find_action(actions, tool_name)
                if action is None:
                    # Unknown tool — return error to the LLM
                    tool_result = {"error": f"Unknown tool: {tool_name}"}
                    await self._store_tool_messages(
                        conversation_id, tool_name, tool_input, tool_result, tool_use_id,
                    )
                    continue

                # If action requires confirmation, pause and ask the user
                if action.requires_confirmation:
                    confirm_text = (
                        f"I need to perform the action **{action.name}**"
                        f" with the following parameters: "
                        f"{json.dumps(tool_input, default=str)}. "
                        f"Shall I proceed?"
                    )
                    # Store the pending action context so a follow-up can resume
                    conversation.context = {
                        **(conversation.context or {}),
                        "pending_action": {
                            "action_id": str(action.id),
                            "action_name": tool_name,
                            "input": tool_input,
                            "tool_use_id": tool_use_id,
                        },
                    }
                    await self.db.flush()

                    return OrchestratorResponse(
                        message=confirm_text,
                        conversation_id=conversation_id,
                        state=current_state.name if current_state else None,
                        actions_executed=actions_executed,
                        guardrails_triggered=guardrails_triggered,
                        status=ConversationStatus.ACTIVE.value,
                        token_usage={
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                        },
                    )

                # Execute the action
                action_start = time.monotonic()
                try:
                    tool_result = await self.action_executor.execute(
                        action=action,
                        params=tool_input,
                        conversation_id=conversation_id,
                    )
                    action_latency = int((time.monotonic() - action_start) * 1000)
                    action_success = True
                    action_error = None
                except Exception as exc:
                    action_latency = int((time.monotonic() - action_start) * 1000)
                    tool_result = {"error": str(exc)}
                    action_success = False
                    action_error = str(exc)
                    logger.error(
                        "Action %s execution failed: %s", tool_name, exc, exc_info=True
                    )

                # Log action execution audit
                action_execution = ActionExecution(
                    conversation_id=conversation_id,
                    action_id=action.id,
                    action_name=tool_name,
                    input_data=tool_input,
                    output_data=tool_result,
                    success=action_success,
                    error_message=action_error,
                    latency_ms=action_latency,
                )
                self.db.add(action_execution)

                actions_executed.append({
                    "action": tool_name,
                    "input": tool_input,
                    "output": tool_result,
                    "success": action_success,
                    "latency_ms": action_latency,
                })

                # Store tool call & result messages
                await self._store_tool_messages(
                    conversation_id, tool_name, tool_input, tool_result, tool_use_id,
                )

            # Re-call LLM with tool results to get next response
            messages_list = await self._load_messages(conversation_id)
            formatted_messages = self.prompt_builder.format_messages(messages_list)

            start_ts = time.monotonic()
            llm_response = await self.llm.chat(
                system_prompt=system_prompt,
                messages=formatted_messages,
                tools=tools or None,
                max_tokens=4096,
            )
            llm_latency_ms = int((time.monotonic() - start_ts) * 1000)
            total_input_tokens += llm_response.input_tokens or 0
            total_output_tokens += llm_response.output_tokens or 0

        # Extract text content from the final LLM response
        response_text = llm_response.content or agent.fallback_message or "I'm sorry, I wasn't able to generate a response."

        # ---- 9. Output guardrails ----------------------------------------
        output_guardrails = [g for g in guardrails if g.is_active]
        if output_guardrails:
            try:
                output_check = await self.guardrail_service.check_output(
                    response_text, output_guardrails,
                )
                if not output_check.passed:
                    response_text = (
                        output_check.modified_text
                        or agent.fallback_message
                        or "I'm sorry, I can't provide that response."
                    )
                elif output_check.modified_text:
                    response_text = output_check.modified_text

                if output_check.triggered_rules:
                    for rule_info in output_check.triggered_rules:
                        guardrails_triggered.append(rule_info)
                        await self._log_guardrail_trigger(
                            conversation_id=conversation_id,
                            guardrails=guardrails,
                            rule_info=rule_info,
                            original=llm_response.content,
                            modified=output_check.modified_text,
                        )
            except Exception:
                logger.warning(
                    "Output guardrail check failed — returning raw response",
                    exc_info=True,
                )

        # ---- 10. Store assistant message ---------------------------------
        assistant_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            token_count=(total_input_tokens + total_output_tokens) or None,
            latency_ms=llm_latency_ms,
            model_used=getattr(llm_response, "model", None),
            tool_calls=(
                llm_response.tool_calls
                if llm_response.tool_calls
                else None
            ),
        )
        self.db.add(assistant_msg)
        await self.db.flush()

        # ---- 11. Evaluate state transitions ------------------------------
        if current_state and current_state.outgoing_transitions:
            transitions = sorted(
                current_state.outgoing_transitions, key=lambda t: t.priority
            )
            conversation_summary = self.prompt_builder.build_conversation_summary(
                messages_list
            )

            for transition in transitions:
                # Skip transitions without conditions — they're manual/always
                if not transition.condition:
                    continue

                try:
                    condition_met = await self.llm.evaluate_condition(
                        conversation_summary, transition.condition
                    )
                except Exception:
                    logger.warning(
                        "Condition evaluation failed for transition %s",
                        transition.id,
                        exc_info=True,
                    )
                    continue

                if condition_met:
                    target_state = transition.to_state
                    if target_state is None:
                        target_state = await self.state_machine.get_current_state(
                            transition.to_state_id
                        )
                    if target_state is None:
                        continue

                    await self.state_machine.transition_to(
                        conversation=conversation,
                        new_state=target_state,
                        transition_id=transition.id,
                        reason=f"Condition met: {transition.condition}",
                    )

                    # Store a system message noting the transition
                    sys_msg = Message(
                        conversation_id=conversation_id,
                        role=MessageRole.SYSTEM,
                        content=(
                            f"[State transition] "
                            f"{current_state.name} -> {target_state.name} "
                            f"(condition: {transition.condition})"
                        ),
                    )
                    self.db.add(sys_msg)

                    current_state = target_state

                    # If the new state is terminal, complete the conversation
                    if target_state.is_terminal:
                        conversation.status = ConversationStatus.COMPLETED
                        conversation.ended_at = datetime.now(timezone.utc)

                    # Only apply the first matching transition
                    break

        # ---- 12. Update conversation metadata ----------------------------
        conversation.message_count = (conversation.message_count or 0) + 2  # user + assistant
        conversation.context = {
            **(conversation.context or {}),
            "last_message_at": datetime.now(timezone.utc).isoformat(),
            "last_model_used": getattr(llm_response, "model", None),
        }
        # Clear any pending action after successful processing
        if conversation.context and "pending_action" in conversation.context:
            ctx = dict(conversation.context)
            ctx.pop("pending_action", None)
            conversation.context = ctx

        await self.db.flush()

        # ---- 13. Return response -----------------------------------------
        return OrchestratorResponse(
            message=response_text,
            conversation_id=conversation_id,
            state=current_state.name if current_state else None,
            actions_executed=actions_executed,
            guardrails_triggered=guardrails_triggered,
            status=conversation.status.value,
            token_usage={
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_agent(self, agent_id: uuid.UUID) -> Agent | None:
        """Load an agent by ID."""
        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Load a conversation with its agent eagerly loaded."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.agent))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[Message]:
        """Load recent messages for a conversation, ordered chronologically.

        Returns the most recent ``limit`` messages so the context window
        stays bounded.  We fetch ordered by ``created_at ASC`` so the
        oldest-to-newest ordering is correct for the LLM.
        """
        # Subquery to get the IDs of the most recent messages
        from sqlalchemy import desc

        subq = (
            select(Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
            .subquery()
        )
        stmt = (
            select(Message)
            .where(Message.id.in_(select(subq.c.id)))
            .order_by(Message.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _load_guardrails(self, agent_id: uuid.UUID) -> list[Guardrail]:
        """Load all guardrails for an agent."""
        stmt = (
            select(Guardrail)
            .where(Guardrail.agent_id == agent_id)
            .order_by(Guardrail.priority.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _load_actions(self, agent_id: uuid.UUID) -> list[Action]:
        """Load active actions for an agent."""
        stmt = (
            select(Action)
            .where(Action.agent_id == agent_id, Action.is_active.is_(True))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _find_action(actions: list[Action], tool_name: str) -> Action | None:
        """Find an action by name (case-insensitive match)."""
        for action in actions:
            if action.name.lower() == tool_name.lower():
                return action
        return None

    async def _store_tool_messages(
        self,
        conversation_id: uuid.UUID,
        tool_name: str,
        tool_input: dict,
        tool_result: dict,
        tool_use_id: str,
    ) -> None:
        """Store the tool call (as an assistant message) and the tool result.

        This pairs the Claude ``tool_use`` content block with the subsequent
        ``tool_result`` block so the conversation history is complete.
        """
        # Assistant message recording the tool call
        tool_call_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=f"[Tool call: {tool_name}]",
            tool_calls={
                "id": tool_use_id,
                "name": tool_name,
                "input": tool_input,
            },
        )
        self.db.add(tool_call_msg)

        # Tool result message
        tool_result_content = json.dumps(tool_result, default=str)
        tool_result_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.TOOL,
            content=tool_result_content,
            metadata_json={
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
            },
        )
        self.db.add(tool_result_msg)
        await self.db.flush()

    async def _log_guardrail_trigger(
        self,
        conversation_id: uuid.UUID,
        guardrails: list[Guardrail],
        rule_info: dict,
        original: str | None,
        modified: str | None,
    ) -> None:
        """Write a guardrail trigger audit record."""
        rule_name = rule_info.get("name", rule_info.get("rule", "unknown"))
        action_taken = rule_info.get("action", "block")

        # Try to find the matching guardrail for the foreign key
        guardrail_id: uuid.UUID | None = None
        for g in guardrails:
            if g.name == rule_name or g.rule == rule_info.get("rule"):
                guardrail_id = g.id
                break

        trigger = GuardrailTrigger(
            conversation_id=conversation_id,
            guardrail_id=guardrail_id,
            guardrail_name=rule_name,
            triggered_rule=json.dumps(rule_info, default=str),
            action_taken=action_taken,
            original_content=original,
            modified_content=modified,
        )
        self.db.add(trigger)
        await self.db.flush()

    async def _state_name(self, state_id: uuid.UUID | None) -> str | None:
        """Resolve a state ID to its name, or return None."""
        if state_id is None:
            return None
        state = await self.state_machine.get_current_state(state_id)
        return state.name if state else None
