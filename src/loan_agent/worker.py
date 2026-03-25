from __future__ import annotations

import json
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, elevenlabs, openai, silero

from loan_agent.config import Settings
from loan_agent.language_lock import LanguageLock
from loan_agent.prompts import build_base_instructions

load_dotenv(Path.cwd() / ".env")


class LoanRecoveryAgent(Agent):
    def __init__(
        self,
        settings: Settings,
        language_lock: LanguageLock,
        customer_context: dict,
    ) -> None:
        self.settings = settings
        self.language_lock = language_lock
        self.customer_context = customer_context
        super().__init__(instructions=self._build_instructions())

    def _build_instructions(self) -> str:
        """Build full instructions combining base prompt + customer context + current language rule."""
        ctx = self.customer_context
        base = build_base_instructions(self.settings.agent_name, self.settings.bank_name)
        context_line = (
            f"Customer: {ctx['name']} | Loan#: {ctx['loan_number']} "
            f"| Amount: {ctx['emi_amount']} | Due: {ctx['due_date']} | Status: {ctx['emi_status']}"
        )
        lang_rule = self.language_lock.system_rule()
        return f"{base}\n{context_line}\n{lang_rule}"

    async def on_user_turn_completed(
        self, turn_ctx, new_message
    ) -> None:
        """Called after every user speech, before LLM responds.
        Detect language from transcript and update instructions if it changed.
        """
        text = new_message.text_content or ""
        if not text.strip():
            return

        _, changed = self.language_lock.process_customer_text(text)
        if changed:
            # Live-update LLM instructions so the next response is in the right language
            await self.update_instructions(self._build_instructions())


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

    customer_context = {
        "name": customer_name,
        "loan_number": loan_number,
        "emi_amount": emi_amount,
        "due_date": due_date,
        "emi_status": emi_status,
    }

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(
            model="nova-2",
            language="multi",
            interim_results=True,
            endpointing_ms=200,           # Detect speech end after 200ms silence
            no_delay=True,                # Send audio immediately (no buffering)
        ),
        llm=openai.LLM(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        ),
        tts=elevenlabs.TTS(
            voice_id=settings.elevenlabs_voice_id,
            model="eleven_turbo_v2",      # Fastest ElevenLabs model
            api_key=settings.elevenlabs_api_key,
            streaming_latency=4,          # Max streaming optimization (0-4)
            auto_mode=True,               # Adaptive streaming: sends chunks as generated
        ),
        allow_interruptions=True,
        min_endpointing_delay=0.2,        # Faster turn detection: 200ms
        max_endpointing_delay=0.6,        # Give up waiting after 600ms
    )

    agent = LoanRecoveryAgent(
        settings=settings,
        language_lock=language_lock,
        customer_context=customer_context,
    )

    await session.start(agent=agent, room=ctx.room)

    # Trigger the opening greeting — all context is already in agent.instructions
    await session.generate_reply(
        instructions=f"Greet the customer. Say hello, confirm you are speaking with {customer_name}, and ask if it is a good time to talk. Keep it short — one or two sentences only."
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=getenv("AGENT_DISPATCH_NAME", "loan-recovery-agent"),
        )
    )
