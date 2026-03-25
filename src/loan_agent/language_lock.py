from __future__ import annotations

import re
from dataclasses import dataclass

from langdetect import LangDetectException, detect

LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
}

SWITCH_PATTERNS: dict[str, tuple[str, ...]] = {
    "en": (
        r"\b(?:speak|talk|continue|switch)\s+(?:in\s+)?english\b",
        r"\benglish\s+(?:please|lo\s+matladandi)\b",
        r"ఇంగ్లీష్(?:లో)?\s*మాట్లాడ(?:ండి|ు)",
    ),
    "hi": (
        r"\b(?:speak|talk|continue|switch)\s+(?:in\s+)?hindi\b",
        r"\b(?:hindi|हिंदी)\s+(?:में\s+)?(?:बोलिए|बात\s+कीजिए)\b",
        r"हिंदी\s+में\s+बात\s+कर(?:ो|िए)",
    ),
    "te": (
        r"\b(?:speak|talk|continue|switch)\s+(?:in\s+)?telugu\b",
        r"\bతెలుగు(?:లో)?\s*మాట్లాడ(?:ండి|ు)",
        r"\btelugu\s+(?:please|matladandi)\b",
    ),
    "ta": (
        r"\b(?:speak|talk|continue|switch)\s+(?:in\s+)?tamil\b",
        r"\bதமிழில்\s*பேச(?:ு|ுங்கள்)\b",
        r"\btamil\s+(?:please|pesunga)\b",
    ),
}

TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")


@dataclass
class LanguageState:
    language_code: str | None = None

    @property
    def language_label(self) -> str:
        if not self.language_code:
            return "customer language"
        return LANGUAGE_LABELS.get(self.language_code, self.language_code)


class LanguageLock:
    def __init__(self, initial_language_code: str | None = None) -> None:
        normalized = (initial_language_code or "").strip().lower()
        if normalized and not normalized.isalpha():
            normalized = None
        self.state = LanguageState(language_code=normalized)

    def process_customer_text(self, text: str) -> tuple[str | None, bool]:
        normalized = text.strip()
        if not normalized:
            return self.state.language_code, False

        requested = self._detect_explicit_switch(normalized)
        if requested and requested != self.state.language_code:
            self.state.language_code = requested
            return self.state.language_code, True

        detected = self._detect_language(normalized)
        if self.state.language_code is None:
            self.state.language_code = detected
            return self.state.language_code, False

        if detected != self.state.language_code and self._strong_language_signal(normalized, detected):
            self.state.language_code = detected
            return self.state.language_code, True

        return self.state.language_code, False

    def system_rule(self) -> str:
        locked = self.state.language_label
        return (
            "Language policy:\n"
            f"- Current locked language: {locked}.\n"
            "- Always reply in the customer's current speaking language.\n"
            "- Do not switch language for code-mixed speech.\n"
            "- If customer clearly shifts language, shift your replies to that language.\n"
            "- If customer asks to switch, acknowledge once in current language and continue in new language."
        )

    def _strong_language_signal(self, text: str, detected_language: str) -> bool:
        if detected_language == "te" and TELUGU_RANGE.search(text):
            return True
        if detected_language == "hi" and DEVANAGARI_RANGE.search(text):
            return True

        if detected_language == "ta":
            return True

        word_count = len(text.split())
        return word_count >= 3

    def _detect_explicit_switch(self, text: str) -> str | None:
        lower_text = text.lower()
        for code, patterns in SWITCH_PATTERNS.items():
            if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in patterns):
                return code
        return None

    def _detect_language(self, text: str) -> str:
        if TELUGU_RANGE.search(text):
            return "te"
        if DEVANAGARI_RANGE.search(text):
            return "hi"

        lower = text.lower()
        romanized_telugu_markers = (
            "avunu",
            "kaadu",
            "matlad",
            "cheppandi",
            "enti",
            "ippudu",
            "nenu",
            "meeru",
            "telugu",
        )
        marker_hits = sum(1 for marker in romanized_telugu_markers if marker in lower)
        if marker_hits >= 2:
            return "te"

        try:
            guessed = detect(text)
        except LangDetectException:
            return "en"

        return guessed if guessed and guessed.isalpha() else "en"
