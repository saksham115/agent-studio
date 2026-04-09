"""Action Executor — dispatch and execute agent actions with audit logging.

Supports action types: API_CALL and DATA_LOOKUP.  Every execution is
persisted to the ``action_executions`` audit table regardless of outcome.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from string import Template
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action import Action, ActionType
from app.models.audit import ActionExecution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result data-class
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 10


@dataclass
class ActionResult:
    """Outcome of a single action execution."""

    success: bool
    result: dict[str, Any]
    error: str | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ActionExecutor:
    """Execute agent actions and record the results.

    Usage::

        executor = ActionExecutor(db)
        result = await executor.execute(action, params, conversation_id)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- public entry-point -------------------------------------------------

    async def execute(
        self,
        action: Action,
        params: dict[str, Any],
        conversation_id: uuid.UUID,
    ) -> ActionResult:
        """Execute *action* with *params* and persist the audit record.

        Dispatches to a type-specific handler based on ``action.action_type``,
        measures wall-clock duration, and writes an ``ActionExecution`` row.
        """
        start_ns = time.perf_counter_ns()

        try:
            handler = self._get_handler(action.action_type)
            result_data = await handler(action, params)
            duration_ms = self._elapsed_ms(start_ns)

            action_result = ActionResult(
                success=True,
                result=result_data,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = self._elapsed_ms(start_ns)
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Action %s (%s) failed: %s",
                action.name,
                action.action_type.value,
                error_msg,
            )
            action_result = ActionResult(
                success=False,
                result={},
                error=error_msg,
                duration_ms=duration_ms,
            )

        await self._log_execution(
            conversation_id=conversation_id,
            action=action,
            params=params,
            action_result=action_result,
        )

        return action_result

    # -- handler dispatch ---------------------------------------------------

    def _get_handler(self, action_type: ActionType):
        """Return the coroutine that handles *action_type*."""
        dispatch = {
            ActionType.API_CALL: self._handle_api_call,
            ActionType.DATA_LOOKUP: self._handle_data_lookup,
        }
        handler = dispatch.get(action_type)
        if handler is None:
            raise ValueError(f"Unsupported action type: {action_type!r}")
        return handler

    # -- type-specific handlers ---------------------------------------------

    async def _handle_api_call(
        self, action: Action, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Make an HTTP request as described by *action.config*.

        Expected config keys:
            url (str): The endpoint URL.  May contain ``$variable``
                placeholders that are substituted from *params*.
            method (str): HTTP method — ``GET``, ``POST``, ``PUT``, ``PATCH``,
                ``DELETE``.  Defaults to ``POST``.
            headers (dict, optional): Extra headers to send.
            body_template (dict, optional): A JSON body template.  String
                values containing ``$variable`` placeholders are expanded
                from *params*.
            timeout (int, optional): Per-request timeout in seconds.
                Defaults to ``DEFAULT_TIMEOUT_SECONDS``.
        """
        config = action.config or {}
        url = self._render_template_string(config.get("url", ""), params)
        method = (config.get("method") or "POST").upper()
        headers = config.get("headers") or {}
        timeout = config.get("timeout", DEFAULT_TIMEOUT_SECONDS)

        # Build request body by rendering template values through params
        body_template = config.get("body_template")
        body = self._render_template_dict(body_template, params) if body_template else params

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=body)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=body)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Attempt to parse JSON; fall back to raw text.
            try:
                data = response.json()
            except Exception:
                data = {"raw_response": response.text}

            return {
                "status_code": response.status_code,
                "data": data,
            }

    async def _handle_data_lookup(
        self, action: Action, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Query an external data source.

        Expected config keys:
            endpoint (str): The lookup API URL.  Supports ``$variable``
                placeholders.
            query_template (dict, optional): Query parameters template.
            timeout (int, optional): Request timeout in seconds.
        """
        config = action.config or {}
        endpoint = self._render_template_string(config.get("endpoint", ""), params)
        timeout = config.get("timeout", DEFAULT_TIMEOUT_SECONDS)
        query_template = config.get("query_template")

        query_params = (
            self._render_template_dict(query_template, params)
            if query_template
            else params
        )

        if not endpoint:
            # No endpoint configured — return params as mock structured data.
            logger.info(
                "Data lookup '%s' has no endpoint; returning params as mock.",
                action.name,
            )
            return {"source": "mock", "data": params}

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(endpoint, params=query_params)
            response.raise_for_status()

            try:
                data = response.json()
            except Exception:
                data = {"raw_response": response.text}

            return {"source": "external", "data": data}

    # -- audit logging ------------------------------------------------------

    async def _log_execution(
        self,
        conversation_id: uuid.UUID,
        action: Action,
        params: dict[str, Any],
        action_result: ActionResult,
    ) -> None:
        """Persist an ``ActionExecution`` audit row."""
        try:
            execution = ActionExecution(
                conversation_id=conversation_id,
                action_id=action.id,
                action_name=action.name,
                input_data=params,
                output_data=action_result.result,
                success=action_result.success,
                error_message=action_result.error,
                latency_ms=action_result.duration_ms,
            )
            self.db.add(execution)
            await self.db.flush()
        except Exception:
            # Audit logging must never prevent the caller from receiving the
            # result.  Log the failure but do not re-raise.
            logger.exception("Failed to persist ActionExecution audit record")

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _elapsed_ms(start_ns: int) -> int:
        """Return elapsed milliseconds since *start_ns*."""
        return int((time.perf_counter_ns() - start_ns) / 1_000_000)

    @staticmethod
    def _render_template_string(template: str, params: dict[str, Any]) -> str:
        """Substitute ``$variable`` placeholders in *template* from *params*.

        Uses :class:`string.Template` with ``safe_substitute`` so that
        missing keys are left as-is rather than raising.
        """
        if not template:
            return template
        return Template(template).safe_substitute(params)

    @classmethod
    def _render_template_dict(
        cls, template: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep-render ``$variable`` placeholders inside a dict template.

        Only string values are interpolated; nested dicts are processed
        recursively.  Non-string, non-dict values pass through unchanged.
        """
        rendered: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str):
                rendered[key] = cls._render_template_string(value, params)
            elif isinstance(value, dict):
                rendered[key] = cls._render_template_dict(value, params)
            else:
                rendered[key] = value
        return rendered
