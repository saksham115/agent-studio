"""Build Bolna agent configuration from Agent Studio DB models.

Constructs the JSON config dict that Bolna's AssistantManager expects,
using the agent's voice channel settings for language, speaker, etc.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.channel import Channel, ChannelType

logger = logging.getLogger(__name__)


async def build_bolna_agent_config(
    db: AsyncSession,
    agent_id: uuid.UUID,
) -> dict:
    """Build a Bolna-compatible agent config from our DB models.

    Returns the full config dict expected by AssistantManager.
    """
    # Load agent
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one()

    # Load voice channel config
    channel = (await db.execute(
        select(Channel).where(
            Channel.agent_id == agent_id,
            Channel.channel_type == ChannelType.VOICE,
        )
    )).scalar_one_or_none()

    channel_config = channel.config if channel else {}
    language = channel_config.get("language", "hi-IN")
    speaker = channel_config.get("speaker") or channel_config.get("ttsVoice", "anushka")

    welcome_message = agent.welcome_message or f"Hello! I'm {agent.name}. How can I help you today?"

    return {
        "agent_name": agent.name,
        "agent_type": "other",
        "agent_welcome_message": welcome_message,
        "tasks": [
            {
                "task_type": "conversation",
                "toolchain": {
                    "execution": "parallel",
                    "pipelines": [["transcriber", "llm", "synthesizer"]],
                },
                "tools_config": {
                    "input": {
                        "format": "pcm",
                        "provider": "exotel",
                    },
                    "output": {
                        "format": "pcm",
                        "provider": "exotel",
                    },
                    "transcriber": {
                        "provider": "sarvam",
                        "model": "saarika:v2.5",
                        "language": language,
                        "stream": True,
                        "encoding": "linear16",
                        "endpointing": 500,
                        # Input 8 kHz → resample to 16 kHz before Sarvam. The
                        # resample logic only fires when telephony_provider ∈
                        # {plivo, twilio}; "exotel" falls to the else branch
                        # and skips resampling. We monkey-patch
                        # _configure_audio_params in bolna/server.py to add
                        # exotel handling there.
                    },
                    "llm_agent": {
                        "agent_type": "simple_llm_agent",
                        "agent_flow_type": "streaming",
                        "llm_config": {
                            "provider": "custom",
                            "model": "orchestrator",
                            "max_tokens": 200,
                            "temperature": 0.0,
                            # base_url and llm_key are injected by BolnaService.create_call_agent()
                        },
                    },
                    "synthesizer": {
                        "provider": "sarvam",
                        "stream": True,
                        "audio_format": "pcm",
                        "buffer_size": 150,
                        "provider_config": {
                            "voice": speaker,
                            "voice_id": speaker,
                            "model": "bulbul:v2",
                            "language": language,
                            "speed": 1.0,
                        },
                    },
                },
                "task_config": {
                    "optimize_latency": True,
                    "hangup_after_silence": 30,
                    "number_of_words_for_interruption": 1,
                    "interruption_backoff_period": 100,
                    "call_terminate": 300,
                    "use_fillers": False,
                    "check_if_user_online": True,
                    "trigger_user_online_message_after": 15,
                },
            }
        ],
    }
