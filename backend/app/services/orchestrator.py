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
from dataclasses import asdict, dataclass, field
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
from app.services.prompt_builder import (
    PromptBuilder,
    TRANSITION_TOOL_NAME,
    _max_turns,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.action_executor import ActionExecutor
from app.services.guardrail_service import GuardrailService
from app.services.state_machine import StateMachine
from app.services.transition_picker import force_pick_transition
from app.observability import tracer

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

        # Create conversation; bootstrap_initial_state below sets the
        # state-related fields (current_state_id, state_entered_at,
        # state_turn_count) and writes the seed StateTransitionLog row.
        conversation = Conversation(
            agent_id=agent_id,
            status=ConversationStatus.ACTIVE,
            context={},
            message_count=0,
        )
        self.db.add(conversation)
        await self.db.flush()

        if initial_state is not None:
            await self.state_machine.bootstrap_initial_state(
                conversation, initial_state,
            )

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
        with tracer.start_as_current_span("orchestrator.process_message") as _root_span:
            _root_span.set_attribute("conversation.id", str(conversation_id))
            _root_span.set_attribute("user_message.length", len(user_message))
            return await self._process_message_impl(conversation_id, user_message)

    async def _process_message_impl(
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
        with tracer.start_as_current_span("orchestrator.load_conversation"):
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
        with tracer.start_as_current_span("orchestrator.load_guardrails"):
            guardrails = await self._load_guardrails(agent.id)
        input_guardrails = [g for g in guardrails if g.is_active]

        if input_guardrails:
            with tracer.start_as_current_span("orchestrator.input_guardrails") as gspan:
                gspan.set_attribute("guardrails.count", len(input_guardrails))
                input_check = await self.guardrail_service.check_input(user_message, input_guardrails)
            if not input_check.passed:
                # Log triggered guardrail rules
                for rule in (input_check.triggered_rules or []):
                    rule_info = self._rule_to_dict(rule)
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
                for rule in input_check.triggered_rules:
                    guardrails_triggered.append(self._rule_to_dict(rule))

        # ---- 4. Store user message ---------------------------------------
        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        # ---- 5. Knowledge-base retrieval ---------------------------------
        # kb_service.search returns a list[str] of chunk contents ordered by
        # similarity. build_system_prompt expects a single string, so join
        # them with a blank line so each chunk reads as its own paragraph.
        kb_chunks: list[str] = []
        with tracer.start_as_current_span("orchestrator.kb_search") as kb_span:
            try:
                kb_chunks = await self.kb_service.search(agent.id, user_message, top_k=5)
                kb_span.set_attribute("kb.chunks_returned", len(kb_chunks))
            except Exception:
                logger.warning(
                    "Knowledge base search failed for agent %s — continuing without KB context",
                    agent.id,
                    exc_info=True,
                )
                kb_span.set_attribute("kb.error", True)
        kb_context = "\n\n".join(kb_chunks)

        # ---- 6. Build prompt ---------------------------------------------
        current_state: State | None = None
        if conversation.current_state_id:
            current_state = await self.state_machine.get_current_state(
                conversation.current_state_id
            )

        # Per-state turn tracking. Counter is bumped BEFORE building the
        # prompt so the rendered "Turn N of M" reflects the turn about to
        # happen (including this one). Lazy-init state_entered_at for
        # conversations migrated from before 004_state_turn_tracking.
        if current_state is not None:
            conversation.state_turn_count = (conversation.state_turn_count or 0) + 1
            if conversation.state_entered_at is None:
                conversation.state_entered_at = datetime.now(timezone.utc)
        max_turns = _max_turns(current_state)

        # Load recent messages from the DB (the relationship may be stale)
        messages_list = await self._load_messages(conversation_id)

        system_prompt = self.prompt_builder.build_system_prompt(
            agent=agent,
            current_state=current_state,
            guardrails=guardrails,
            kb_context=kb_context,
            state_turn_count=conversation.state_turn_count or 0,
            max_turns=max_turns,
        )

        formatted_messages = self.prompt_builder.format_messages(messages_list)

        # Load active actions and build tools (includes the
        # __transition_to_state meta-tool when current_state has outgoing
        # transitions and isn't terminal).
        actions = await self._load_actions(agent.id)
        tools = self.prompt_builder.build_tools(actions, current_state)

        # ---- 7. Call LLM -------------------------------------------------
        start_ts = time.monotonic()
        with tracer.start_as_current_span("orchestrator.llm_call") as llm_span:
            llm_span.set_attribute("llm.tools_count", len(tools) if tools else 0)
            llm_span.set_attribute("llm.messages_count", len(formatted_messages))
            llm_response = await self.llm.chat(
                system_prompt=system_prompt,
                messages=formatted_messages,
                tools=tools or None,
                max_tokens=4096,
            )
            llm_span.set_attribute("llm.input_tokens", llm_response.input_tokens or 0)
            llm_span.set_attribute("llm.output_tokens", llm_response.output_tokens or 0)
            llm_span.set_attribute("llm.tool_calls", len(llm_response.tool_calls or []))
        llm_latency_ms = int((time.monotonic() - start_ts) * 1000)

        total_input_tokens += llm_response.input_tokens or 0
        total_output_tokens += llm_response.output_tokens or 0

        # ---- 8. Tool-use loop --------------------------------------------
        # transitioned_this_turn tracks whether ANY successful state transition
        # fired during this turn — set as a boolean flag inside the loop, NOT
        # derived from a final-state-ID comparison. The LLM could transition
        # A→B→A within MAX_TOOL_CALL_ITERATIONS leaving final state ID equal
        # to start state ID; the flag captures the truth either way.
        transitioned_this_turn = False
        iteration = 0
        while llm_response.tool_calls and iteration < MAX_TOOL_CALL_ITERATIONS:
            iteration += 1

            for tool_call in llm_response.tool_calls:
                tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
                tool_input = tool_call.get("input") or tool_call.get("arguments", {})
                tool_use_id = tool_call.get("id", str(uuid.uuid4()))

                # System meta-tool: state transition
                if tool_name == TRANSITION_TOOL_NAME:
                    result, new_state = await self._handle_transition_tool(
                        conversation, current_state, tool_input,
                    )
                    # _store_tool_messages json.dumps's `result` — keep it
                    # serializable-only. The State ORM object travels via
                    # the tuple so the LLM-visible tool_result content is
                    # clean.
                    await self._store_tool_messages(
                        conversation_id, TRANSITION_TOOL_NAME,
                        tool_input, result, tool_use_id,
                    )
                    if result.get("ok") and new_state is not None:
                        transitioned_this_turn = True
                        current_state = new_state
                        max_turns = _max_turns(current_state)
                        # Rebuild system prompt + tools so the next loop
                        # iteration sees the new state's directives.
                        system_prompt = self.prompt_builder.build_system_prompt(
                            agent=agent,
                            current_state=current_state,
                            guardrails=guardrails,
                            kb_context=kb_context,
                            state_turn_count=conversation.state_turn_count or 0,
                            max_turns=max_turns,
                        )
                        tools = self.prompt_builder.build_tools(
                            actions, current_state,
                        )
                    continue

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
                    for rule in output_check.triggered_rules:
                        rule_info = self._rule_to_dict(rule)
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

        # ---- 11. maxTurns force-pick safety net --------------------------
        # If the LLM didn't transition this turn AND we've reached the per-
        # state turn limit AND there are still outgoing transitions, force
        # one. The LLM-judged tool path is the primary mechanism; this is
        # the deterministic backstop. Fires before storing the assistant
        # message so the user-facing reply reflects the new state.
        if (
            current_state is not None
            and not transitioned_this_turn
            and not current_state.is_terminal
            and current_state.outgoing_transitions
            and max_turns is not None
            and (conversation.state_turn_count or 0) >= max_turns
        ):
            forced_state = await force_pick_transition(
                state_machine=self.state_machine,
                conversation=conversation,
                current_state=current_state,
                recent_messages=messages_list,
                llm=self.llm,
            )
            if forced_state is not None:
                current_state = forced_state
                if forced_state.is_terminal:
                    conversation.status = ConversationStatus.COMPLETED
                    conversation.ended_at = datetime.now(timezone.utc)
                # Re-call the LLM ONCE under the forced new state's prompt
                # so the user-facing reply reflects the new state, not the
                # stuck old one. Pass tools=None — we just FORCED a
                # transition; allowing the LLM to transition again or call
                # Action tools here would either thrash (this is a single-
                # shot re-call without a tool loop) or compete with the
                # deterministic decision we just made.
                forced_system_prompt = self.prompt_builder.build_system_prompt(
                    agent=agent,
                    current_state=current_state,
                    guardrails=guardrails,
                    kb_context=kb_context,
                    state_turn_count=conversation.state_turn_count or 0,
                    max_turns=_max_turns(current_state),
                )
                forced_messages = await self._load_messages(conversation_id)
                forced_formatted = self.prompt_builder.format_messages(
                    forced_messages
                )
                forced_response = await self.llm.chat(
                    system_prompt=forced_system_prompt,
                    messages=forced_formatted,
                    tools=None,
                    max_tokens=4096,
                )
                response_text = (
                    forced_response.content
                    or agent.fallback_message
                    or "I'm sorry, I wasn't able to generate a response."
                )
                total_input_tokens += forced_response.input_tokens or 0
                total_output_tokens += forced_response.output_tokens or 0
                # The output-guardrail block earlier in this function has
                # already run against the original response_text; rerun it
                # here against the forced reply.
                if output_guardrails:
                    try:
                        forced_check = await self.guardrail_service.check_output(
                            response_text, output_guardrails,
                        )
                        if not forced_check.passed:
                            response_text = (
                                forced_check.modified_text
                                or agent.fallback_message
                                or "I'm sorry, I can't provide that response."
                            )
                        elif forced_check.modified_text:
                            response_text = forced_check.modified_text
                        if forced_check.triggered_rules:
                            for rule in forced_check.triggered_rules:
                                rule_info = self._rule_to_dict(rule)
                                guardrails_triggered.append(rule_info)
                                await self._log_guardrail_trigger(
                                    conversation_id=conversation_id,
                                    guardrails=guardrails,
                                    rule_info=rule_info,
                                    original=forced_response.content,
                                    modified=forced_check.modified_text,
                                )
                    except Exception:
                        logger.warning(
                            "Output guardrail re-check failed after force-pick "
                            "— returning forced response as-is",
                            exc_info=True,
                        )

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

    @staticmethod
    def _rule_to_dict(rule) -> dict:
        """Convert a guardrail_service.TriggeredRule dataclass to a JSON-safe
        dict for storage in OrchestratorResponse.guardrails_triggered and for
        consumption by ``_log_guardrail_trigger`` (which dict-accesses fields).
        """
        data = asdict(rule)
        # asdict leaves uuid.UUID objects in place; coerce to str for JSON.
        if "guardrail_id" in data and data["guardrail_id"] is not None:
            data["guardrail_id"] = str(data["guardrail_id"])
        return data

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

    async def _handle_transition_tool(
        self,
        conversation: Conversation,
        current_state: State | None,
        tool_input: dict,
    ) -> tuple[dict, State | None]:
        """Validate + commit a ``__transition_to_state`` tool call.

        Returns a tuple ``(result_dict, new_state | None)``. The
        ``result_dict`` is JSON-serializable (only string fields) and is
        what gets fed back to the LLM via ``_store_tool_messages``. The
        ``new_state`` is the actual ORM object handed back to the
        orchestrator via the tuple — keeping it out of ``result_dict``
        prevents ``json.dumps(default=str)`` from leaking
        ``<app.models.state.State object at 0x...>`` strings into the
        LLM-visible tool_result content.

        Validation:
        - Reject when ``target_state`` doesn't match an outgoing transition's
          target name (defence-in-depth backstop in case the model ignores
          the JSON Schema ``enum`` constraint).
        - Reject when the target state can't be loaded (data inconsistency).

        Side effects on success:
        - Calls ``state_machine.transition_to`` (which writes the audit log
          and resets the per-state counters).
        - Marks the conversation COMPLETED + sets ``ended_at`` when the new
          state is terminal.
        """
        target_name = (tool_input.get("target_state") or "").strip()
        reason = tool_input.get("reason") or ""

        if current_state is None or not current_state.outgoing_transitions:
            return (
                {
                    "ok": False,
                    "error": (
                        "No outgoing transitions available from the current "
                        "state."
                    ),
                },
                None,
            )

        transition = next(
            (
                t
                for t in current_state.outgoing_transitions
                if t.to_state is not None and t.to_state.name == target_name
            ),
            None,
        )
        if transition is None:
            valid = [
                t.to_state.name
                for t in current_state.outgoing_transitions
                if t.to_state is not None
            ]
            return (
                {
                    "ok": False,
                    "error": (
                        f"'{target_name}' is not an outgoing transition "
                        f"from '{current_state.name}'. Valid targets: "
                        f"{valid}. Stay in the current state."
                    ),
                },
                None,
            )

        new_state = await self.state_machine.get_current_state(
            transition.to_state_id
        )
        if new_state is None:
            return (
                {"ok": False, "error": "Target state not found in database."},
                None,
            )

        await self.state_machine.transition_to(
            conversation=conversation,
            new_state=new_state,
            transition_id=transition.id,
            reason=reason,
        )
        if new_state.is_terminal:
            conversation.status = ConversationStatus.COMPLETED
            conversation.ended_at = datetime.now(timezone.utc)

        return (
            {"ok": True, "new_state_name": new_state.name},
            new_state,
        )

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
