"""Bolna REST API client for agent lifecycle management.

Creates and deletes agents in the Bolna Docker sidecar via its REST API.
Each voice call gets an ephemeral Bolna agent with the conversation_id
baked into the LiteLLM API key for routing.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.config import settings
from app.services.channels.voice.bolna_config import build_bolna_agent_config

logger = logging.getLogger(__name__)


class BolnaService:
    """Client for Bolna's agent management REST API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.BOLNA_API_URL).rstrip("/")

    async def create_agent(
        self,
        agent_config: dict,
        agent_prompts: dict | None = None,
    ) -> str:
        """Create a Bolna agent and return its ID.

        Args:
            agent_config: Bolna agent configuration dict.
            agent_prompts: Optional prompt overrides per task.

        Returns:
            The Bolna agent ID (UUID string).
        """
        payload = {
            "agent_config": agent_config,
            "agent_prompts": agent_prompts or {},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/agent",
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        bolna_agent_id = data.get("agent_id", "")
        logger.info("Created Bolna agent: %s", bolna_agent_id)
        return bolna_agent_id

    async def delete_agent(self, bolna_agent_id: str) -> bool:
        """Delete a Bolna agent.

        Returns True if successful, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(
                    f"{self.base_url}/agent/{bolna_agent_id}",
                )
                response.raise_for_status()
            logger.info("Deleted Bolna agent: %s", bolna_agent_id)
            return True
        except Exception:
            logger.exception("Failed to delete Bolna agent %s", bolna_agent_id)
            return False

    async def create_call_agent(
        self,
        agent_config: dict,
        conversation_id: uuid.UUID,
        system_prompt: str = "",
    ) -> str:
        """Create an ephemeral Bolna agent for a single voice call.

        The conversation_id is encoded in the LiteLLM API key so our
        voice completions endpoint can route to the right conversation.

        Args:
            agent_config: Base Bolna config (from build_bolna_agent_config).
            conversation_id: Our conversation UUID.
            system_prompt: Optional system prompt for the agent.

        Returns:
            The Bolna agent ID.
        """
        # Inject our completions endpoint into the LLM config
        backend_url = settings.PUBLIC_API_URL.rstrip("/")
        llm_config = agent_config["tasks"][0]["tools_config"]["llm_agent"]["llm_config"]
        llm_config["provider"] = "custom"
        llm_config["base_url"] = f"{backend_url}/api/v1/voice"
        llm_config["llm_key"] = f"bolna_{conversation_id}"
        llm_config["model"] = "orchestrator"

        agent_prompts = {}
        if system_prompt:
            agent_prompts["task_1"] = {"system_prompt": system_prompt}

        return await self.create_agent(agent_config, agent_prompts)
