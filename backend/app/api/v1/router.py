from fastapi import APIRouter

from app.api.v1 import agents, knowledge_base, actions, states, channels, guardrails, conversations, dashboard

v1_router = APIRouter(tags=["v1"])

v1_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
v1_router.include_router(knowledge_base.router, prefix="/agents/{agent_id}/kb", tags=["Knowledge Base"])
v1_router.include_router(actions.router, prefix="/agents/{agent_id}/actions", tags=["Actions"])
v1_router.include_router(states.router, prefix="/agents/{agent_id}/states", tags=["States"])
v1_router.include_router(channels.router, prefix="/agents/{agent_id}/channels", tags=["Channels"])
v1_router.include_router(guardrails.router, prefix="/agents/{agent_id}/guardrails", tags=["Guardrails"])
v1_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
