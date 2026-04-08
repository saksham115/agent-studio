"""Bolna voice AI server — manages agents and WebSocket connections.

This is a minimal server based on Bolna's quickstart_server.py, running
inside Docker as a sidecar to the Agent Studio backend.
"""

import os
import asyncio
import json
import uuid
import traceback

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict, List, Optional

from bolna.helpers.utils import store_file
from bolna.helpers.logger_config import configure_logger
from bolna.agent_manager.assistant_manager import AssistantManager

load_dotenv()
logger = configure_logger(__name__)

redis_pool = redis.ConnectionPool.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/1"),
    decode_responses=True,
)
redis_client = redis.Redis.from_pool(redis_pool)

app = FastAPI(title="Bolna Voice Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateAgentPayload(BaseModel):
    agent_config: dict
    agent_prompts: Optional[Dict[str, Dict[str, str]]] = None


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/agent")
async def create_agent(agent_data: CreateAgentPayload):
    agent_uuid = str(uuid.uuid4())
    data_for_db = agent_data.agent_config
    data_for_db["assistant_status"] = "seeding"
    agent_prompts = agent_data.agent_prompts or {}

    stored_prompt_file_path = f"{agent_uuid}/conversation_details.json"
    await asyncio.gather(
        redis_client.set(agent_uuid, json.dumps(data_for_db)),
        store_file(file_key=stored_prompt_file_path, file_data=agent_prompts, local=True),
    )

    logger.info(f"Created agent {agent_uuid}")
    return {"agent_id": agent_uuid, "state": "created"}


@app.get("/agent/{agent_id}")
async def get_agent(agent_id: str):
    agent_data = await redis_client.get(agent_id)
    if not agent_data:
        raise HTTPException(status_code=404, detail="Agent not found")
    return json.loads(agent_data)


@app.delete("/agent/{agent_id}")
async def delete_agent(agent_id: str):
    exists = await redis_client.exists(agent_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Agent not found")
    await redis_client.delete(agent_id)
    logger.info(f"Deleted agent {agent_id}")
    return {"agent_id": agent_id, "state": "deleted"}


@app.websocket("/chat/v1/{agent_id}")
async def websocket_endpoint(agent_id: str, websocket: WebSocket):
    logger.info(f"WebSocket connected for agent={agent_id}")
    await websocket.accept()

    try:
        retrieved = await redis_client.get(agent_id)
        if not retrieved:
            logger.error(f"Agent {agent_id} not found")
            await websocket.close(code=4004)
            return
        agent_config = json.loads(retrieved)
    except Exception as e:
        logger.error(f"Failed to load agent config: {e}")
        await websocket.close(code=4000)
        return

    assistant_manager = AssistantManager(agent_config, websocket, agent_id)

    try:
        async for index, task_output in assistant_manager.run(local=True):
            logger.info(f"Task {index} output: {str(task_output)[:200]}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for agent={agent_id}")
    except Exception as e:
        logger.error(f"Error in agent {agent_id}: {e}")
        traceback.print_exc()
