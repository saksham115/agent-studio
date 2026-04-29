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
from bolna.transcriber.sarvam_transcriber import SarvamTranscriber

load_dotenv()
logger = configure_logger(__name__)

# -----------------------------------------------------------------------------
# Monkey-patch: teach Bolna's Sarvam transcriber about Exotel.
#
# Bolna only auto-configures the input sample rate for plivo and twilio. With
# telephony_provider="exotel" it falls to the else branch and leaves
# input_sampling_rate == sampling_rate (16 kHz default), so Bolna tells Sarvam
# the audio is 16 kHz while actually sending Exotel's 8 kHz PCM. Sarvam then
# mis-interprets the stream (we saw a 7-second utterance transcribed as ~200 ms
# of garbage). Setting sampling_rate=8000 in the config makes Sarvam reject the
# WebSocket (8 kHz unsupported on their streaming endpoint).
#
# The right fix is to match Bolna's plivo behaviour: declare input_sampling_rate
# 8000 and sampling_rate 16000, letting Bolna's internal audioop.ratecv upsample
# before streaming to Sarvam.
# -----------------------------------------------------------------------------
_original_configure_audio_params = SarvamTranscriber._configure_audio_params


def _configure_audio_params_with_exotel(self):
    if self.telephony_provider == "exotel":
        self.encoding = "linear16"
        self.input_sampling_rate = 8000
        self.sampling_rate = 16000
        self.audio_frame_duration = 0.2
        return
    _original_configure_audio_params(self)


SarvamTranscriber._configure_audio_params = _configure_audio_params_with_exotel
logger.info("Patched SarvamTranscriber._configure_audio_params to handle exotel")

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

    # Bolna's TaskManager rebuilds llm_config as a fresh dict that drops
    # llm_key and base_url — it looks for them in self.kwargs instead. Pass
    # them through so OpenAiLLM receives an api_key.
    llm_cfg = (
        agent_config.get("tasks", [{}])[0]
        .get("tools_config", {})
        .get("llm_agent", {})
        .get("llm_config", {})
    )
    extra_kwargs = {}
    if llm_cfg.get("llm_key"):
        extra_kwargs["llm_key"] = llm_cfg["llm_key"]
    if llm_cfg.get("base_url"):
        extra_kwargs["base_url"] = llm_cfg["base_url"]

    assistant_manager = AssistantManager(agent_config, websocket, agent_id, **extra_kwargs)

    try:
        async for index, task_output in assistant_manager.run(local=True):
            logger.info(f"Task {index} output: {str(task_output)[:200]}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for agent={agent_id}")
    except Exception as e:
        logger.error(f"Error in agent {agent_id}: {e}")
        traceback.print_exc()
