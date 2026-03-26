from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Settings:
    agent_name: str
    bank_name: str
    groq_api_key: str
    groq_model: str
    deepgram_api_key: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    elevenlabs_voice_id_hi: str  # Hindi voice
    elevenlabs_voice_id_te: str  # Telugu voice
    elevenlabs_voice_id_ta: str  # Tamil voice

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            agent_name=getenv("AGENT_NAME", "Rohan"),
            bank_name=getenv("BANK_NAME", "ABC Bank"),
            groq_api_key=getenv("GROQ_API_KEY", ""),
            groq_model=getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
            deepgram_api_key=getenv("DEEPGRAM_API_KEY", ""),
            elevenlabs_api_key=getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            elevenlabs_model_id=getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5"),
            elevenlabs_voice_id_hi=getenv("ELEVENLABS_VOICE_ID_HI", "EXAVITQu4vr4xnSDxMaL"),
            elevenlabs_voice_id_te=getenv("ELEVENLABS_VOICE_ID_TE", "EXAVITQu4vr4xnSDxMaL"),
            elevenlabs_voice_id_ta=getenv("ELEVENLABS_VOICE_ID_TA", "EXAVITQu4vr4xnSDxMaL"),
        )

    def validate(self) -> None:
        required = {
            "GROQ_API_KEY": self.groq_api_key,
            "DEEPGRAM_API_KEY": self.deepgram_api_key,
            "ELEVENLABS_API_KEY": self.elevenlabs_api_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {missing_list}")
