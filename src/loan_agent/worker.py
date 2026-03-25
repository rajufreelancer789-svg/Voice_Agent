from __future__ import annotations

import json
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, elevenlabs, openai, silero

from loan_agent.config import Settings
from loan_agent.language_lock import LanguageLock
from loan_agent.prompts import build_base_instructions, build_runtime_instructions

load_dotenv(Path.cwd() / ".env")


class LoanRecoveryAgent(Agent):
    def __init__(self, settings: Settings, language_lock: LanguageLock) -> None:
        self.settings = settings
        self.language_lock = language_lock
        super().__init__(instructions=build_base_instructions(settings.agent_name, settings.bank_name))


async def entrypoint(ctx: JobContext) -> None:
    settings = Settings.from_env()
    settings.validate()

    await ctx.connect()

    room_metadata = {}
    if ctx.room.metadata:
        try:
            room_metadata = json.loads(ctx.room.metadata)
        except json.JSONDecodeError:
            room_metadata = {}

    customer_name = room_metadata.get("customer_name", getenv("TEST_CUSTOMER_NAME", "Customer"))
    loan_number = room_metadata.get("loan_number", getenv("TEST_LOAN_NUMBER", "LN-00001"))
    emi_amount = room_metadata.get("emi_amount", getenv("TEST_EMI_AMOUNT", "₹4,500"))
    due_date = room_metadata.get("due_date", getenv("TEST_DUE_DATE", "2026-03-28"))
    emi_status = room_metadata.get("emi_status", getenv("TEST_EMI_STATUS", "pending"))
    language_hint = room_metadata.get("language_hint", "")

    language_lock = LanguageLock(initial_language_code=None)

    # ULTRA-LOW LATENCY CONFIG
    # Streaming at every stage + faster models
    session = AgentSession(
        # Fast voice detection (aggressive silence detection)
        vad=silero.VAD.load(),
        # Streaming STT with interim results
        stt=deepgram.STT(
            model="nova-2",
            language="multi",
            interim_results=True,         # Stream interim transcripts
        ),
        # Ultra-fast LLM with token limit
        llm=openai.LLM(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        ),
        # Streaming TTS with turbo model
        tts=elevenlabs.TTS(
            voice_id=settings.elevenlabs_voice_id,
            model="eleven_turbo_v2",      # TURBO model (fast)
            api_key=settings.elevenlabs_api_key,
            enable_streaming=True,        # Stream audio chunks
        ),
        # Enable interruptions for faster interaction
        allow_interruptions=True,
    )

    agent = LoanRecoveryAgent(settings=settings, language_lock=language_lock)

    await session.start(agent=agent, room=ctx.room)

    await session.generate_reply(
        instructions=build_runtime_instructions(
            language_lock=language_lock,
            customer_name=customer_name,
            loan_number=loan_number,
            emi_amount=emi_amount,
            due_date=due_date,
            emi_status=emi_status,
        )
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=getenv("AGENT_DISPATCH_NAME", "loan-recovery-agent"),
        )
    )
