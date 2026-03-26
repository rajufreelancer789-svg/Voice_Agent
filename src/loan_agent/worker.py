from __future__ import annotations

import json
import logging
from os import getenv
from pathlib import Path
import time

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, elevenlabs, openai, silero

from loan_agent.config import Settings
from loan_agent.language_lock import LanguageLock
from loan_agent.prompts import build_base_instructions

load_dotenv(Path.cwd() / ".env")

logger = logging.getLogger(__name__)


class LoanRecoveryAgent(Agent):
    def __init__(
        self,
        settings: Settings,
        language_lock: LanguageLock,
        customer_context: dict,
        voice_map: dict[str, str],
    ) -> None:
        self.settings = settings
        self.language_lock = language_lock
        self.customer_context = customer_context
        self.voice_map = voice_map
        super().__init__(instructions=self._build_instructions())

    async def on_enter(self) -> None:
        customer_name = self.customer_context["name"]
        greeting = f"Hello! Am I speaking with {customer_name}? Is this a good time to talk?"
        await self.session.say(greeting, allow_interruptions=True)

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
        Also switch TTS voice to match the detected language.
        Log detailed latency metrics for LLM response pipeline.
        """
        t0 = time.perf_counter()
        try:
            text = new_message.text_content or ""
            if not text.strip():
                return
            logger.info(f"[LATENCY] STT transcript received: '{text[:50]}' at {t0:.3f}")
            logger.info(f"[LATENCY] ===== START LLM RESPONSE CYCLE =====")

            _, changed = self.language_lock.process_customer_text(text)
            t1 = time.perf_counter()
            lang_detect_ms = (t1-t0)*1000
            logger.info(f"[LATENCY] Language detection done in {lang_detect_ms:.1f}ms")
            
            if changed:
                # Update instructions for new language
                await self.update_instructions(self._build_instructions())
                t2 = time.perf_counter()
                update_ms = (t2-t1)*1000
                logger.info(f"[LATENCY] Instructions updated in {update_ms:.1f}ms")
                
                # Switch TTS voice to match detected language
                new_voice_id = self.language_lock.get_voice_for_language(self.voice_map)
                self.session.tts.voice_id = new_voice_id
                logger.info(f"[LATENCY] TTS voice switched to {new_voice_id} for {self.language_lock.state.language_label}")
                t1 = time.perf_counter()  # Reset t1 for overall timing
            
            # Log when we begin waiting for LLM response
            t_llm_wait = time.perf_counter()
            logger.info(f"[LATENCY] Ready for LLM response at T+{(t_llm_wait-t0)*1000:.1f}ms from speech")
        except Exception:
            logger.exception("[LATENCY] Error in on_user_turn_completed")


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

    # Build language-to-voice mapping
    voice_map = {
        "en": settings.elevenlabs_voice_id,
        "hi": settings.elevenlabs_voice_id_hi,
        "te": settings.elevenlabs_voice_id_te,
        "ta": settings.elevenlabs_voice_id_ta,
    }

    language_lock = LanguageLock(initial_language_code=None)

    customer_context = {
        "name": customer_name,
        "loan_number": loan_number,
        "emi_amount": emi_amount,
        "due_date": due_date,
        "emi_status": emi_status,
    }

    # Determine initial voice based on language hint or default to English
    initial_voice_id = language_lock.get_voice_for_language(voice_map)

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(
            model="nova-2",
            language="multi",
            interim_results=True,
            endpointing_ms=100,           # Reduced: 100ms for faster turn detection (was 200ms)
            no_delay=True,                # Send audio immediately (no buffering)
        ),
        llm=openai.LLM(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        ),
        tts=elevenlabs.TTS(
            voice_id=initial_voice_id,
            model=settings.elevenlabs_model_id,
            api_key=settings.elevenlabs_api_key,
            streaming_latency=4,          # Max streaming optimization (0-4)
            auto_mode=True,               # Adaptive streaming: sends chunks as generated
        ),
        allow_interruptions=True,
        min_endpointing_delay=0.1,        # Reduced: 100ms for faster response (was 200ms)
        max_endpointing_delay=0.4,        # Reduced: 400ms max wait (was 600ms)
    )

    agent = LoanRecoveryAgent(
        settings=settings,
        language_lock=language_lock,
        customer_context=customer_context,
        voice_map=voice_map,
    )

    t_start = time.perf_counter()
    await session.start(agent=agent, room=ctx.room)
    logger.info(f"[LATENCY] Session started in {(time.perf_counter()-t_start)*1000:.1f}ms")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="loan-recovery-agent-local",
        )
    )
