import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentStatus


class AgentService:
    """Business logic for agent management.

    Encapsulates database queries and domain logic for creating, updating,
    publishing, and retrieving agents. Route handlers delegate to this
    service for all non-trivial operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_agent_by_id(self, agent_id: uuid.UUID, org_id: uuid.UUID) -> Agent | None:
        """Fetch a single agent by ID, scoped to the organization."""
        stmt = select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_agents(
        self,
        org_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: AgentStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Agent], int]:
        """List agents for an organization with optional filtering and pagination."""
        stmt = select(Agent).where(Agent.org_id == org_id)

        if status_filter is not None:
            stmt = stmt.where(Agent.status == status_filter)

        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                Agent.name.ilike(search_term) | Agent.description.ilike(search_term)
            )

        # Get total count
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar_one()

        # Apply pagination
        stmt = stmt.order_by(Agent.updated_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        agents = list(result.scalars().all())

        return agents, total

    async def create_agent(
        self,
        org_id: uuid.UUID,
        created_by: uuid.UUID,
        name: str,
        description: str | None = None,
        system_prompt: str | None = None,
        persona: str | None = None,
        languages: list[str] | None = None,
        welcome_message: str | None = None,
        fallback_message: str | None = None,
        escalation_message: str | None = None,
        max_turns: int | None = 50,
        model_config_data: dict | None = None,
    ) -> Agent:
        """Create a new agent in draft status."""
        agent = Agent(
            org_id=org_id,
            created_by=created_by,
            name=name,
            description=description,
            system_prompt=system_prompt,
            persona=persona,
            languages=languages or ["en"],
            welcome_message=welcome_message,
            fallback_message=fallback_message,
            escalation_message=escalation_message,
            max_turns=max_turns,
            model_config_json=model_config_data,
            status=AgentStatus.DRAFT,
        )
        self.db.add(agent)
        await self.db.flush()
        await self.db.refresh(agent)
        return agent

    async def update_agent(self, agent: Agent, **kwargs: object) -> Agent:
        """Update agent fields with the provided keyword arguments."""
        for key, value in kwargs.items():
            if value is not None and hasattr(agent, key):
                setattr(agent, key, value)
        await self.db.flush()
        await self.db.refresh(agent)
        return agent

    async def publish_agent(self, agent: Agent) -> Agent:
        """Publish an agent, transitioning it from draft to published."""
        agent.status = AgentStatus.PUBLISHED
        current_version = agent.published_version or 0
        agent.published_version = current_version + 1
        from datetime import datetime, timezone

        agent.published_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(agent)
        return agent

    async def delete_agent(self, agent: Agent) -> None:
        """Archive (soft-delete) an agent."""
        agent.status = AgentStatus.ARCHIVED
        await self.db.flush()
