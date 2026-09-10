from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)


# =========================================================
# LANGUAGE DETECTION PROVIDER
# =========================================================
#
# Purpose:
#
# Deterministic language_detector.py
#       ↓
# uncertain / ambiguous result
#       ↓
# Gemini fallback
#       ↓
# normalized language code
#
# IMPORTANT:
#
# - This module does NOT translate.
# - This module does NOT publish.
# - This module does NOT write to database.
# - This module is used only when deterministic detection
#   is not reliable enough.
# =========================================================


DEFAULT_MODEL = "gemini-2.5-flash"

DEFAULT_TIMEOUT_SECONDS = 30

GEMINI_API_BASE = (
    "https://generativelanguage.googleapis.com/v1beta"
)


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class ProviderLanguageDetectionResult:
    success: bool

    language: str = "auto"

    confidence: float = 0.0

    language_name: str = ""

    script: str = ""

    reason: str = ""

    model: str = ""

    raw_response: str = ""

    metadata: Optional[
        Dict[str, Any]
    ] = None


# =========================================================
# CONFIG
# =========================================================

def get_language_detection_model() -> str:

    return (
        os.getenv(
            "LANGUAGE_DETECTION_MODEL"
        )
        or os.getenv(
            "TRANSLATION_MODEL"
        )
        or os.getenv(
            "GEMINI_MODEL"
        )
        or DEFAULT_MODEL
    ).strip()


def get_language_detection_timeout() -> int:

    raw = str(
        os.getenv(
            "LANGUAGE_DETECTION_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        )
        or DEFAULT_TIMEOUT_SECONDS
    ).strip()

    try:

        value = int(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):

        value = (
            DEFAULT_TIMEOUT_SECONDS
        )

    return max(
        5,
        min(
            value,
            120,
        ),
    )


def language_detection_provider_configured() -> bool:

    return bool(
        str(
            os.getenv(
                "GEMINI_API_KEY",
                "",
            )
            or ""
        ).strip()
    )


# =========================================================
# NORMALIZATION
# =========================================================

_LANGUAGE_ALIASES = {

    "persian": "fa",
    "farsi": "fa",
    "فارسی": "fa",

    "english": "en",

    "arabic": "ar",

    "turkish": "tr",

    "russian": "ru",

    "ukrainian": "uk",

    "french": "fr",

    "german": "de",

    "spanish": "es",

    "italian": "it",

    "portuguese": "pt",

    "dutch": "nl",

    "polish": "pl",

    "czech": "cs",

    "slovak": "sk",

    "hungarian": "hu",

    "romanian": "ro",

    "bulgarian": "bg",

    "serbian": "sr",

    "croatian": "hr",

    "bosnian": "bs",

    "slovenian": "sl",

    "greek": "el",

    "hebrew": "he",

    "hindi": "hi",

    "urdu": "ur",

    "bengali": "bn",

    "punjabi": "pa",

    "marathi": "mr",

    "nepali": "ne",

    "tamil": "ta",

    "telugu": "te",

    "kannada": "kn",

    "malayalam": "ml",

    "gujarati": "gu",

    "chinese": "zh",

    "japanese": "ja",

    "korean": "ko",

    "indonesian": "id",

    "malay": "ms",

    "thai": "th",

    "vietnamese": "vi",

    "filipino": "fil",

    "tagalog": "tl",

    "swedish": "sv",

    "norwegian": "no",

    "danish": "da",

    "finnish": "fi",

    "icelandic": "is",

    "estonian": "et",

    "latvian": "lv",

    "lithuanian": "lt",

    "georgian": "ka",

    "armenian": "hy",

    "azerbaijani": "az",

    "kazakh": "kk",

    "uzbek": "uz",

    "tajik": "tg",

    "kyrgyz": "ky",

    "pashto": "ps",

    "kurdish": "ku",

    "sorani": "ckb",

    "somali": "so",

    "swahili": "sw",

    "amharic": "am",

    "afrikaans": "af",

    "albanian": "sq",

    "macedonian": "mk",

    "belarusian": "be",

    "catalan": "ca",

    "galician": "gl",

    "basque": "eu",

    "irish": "ga",

    "welsh": "cy",
}


def normalize_language_code(
    value: Any,
) -> str:

    text = str(
        value
        or ""
    ).strip()

    if not text:

        return "auto"

    lowered = (
        text
        .lower()
        .replace(
            "_",
            "-",
        )
    )

    if lowered in {
        "unknown",
        "und",
        "auto",
        "uncertain",
        "mixed",
    }:

        return "auto"

    if lowered in _LANGUAGE_ALIASES:

        return (
            _LANGUAGE_ALIASES[
                lowered
            ]
        )

    # Accept BCP-47 style values but use base language for
    # routing decisions.
    base = (
        lowered
        .split(
            "-",
            1,
        )[0]
        .strip()
    )

    if (
        2 <= len(base) <= 3
        and base.isalpha()
    ):

        return base

    return "auto"


def _normalize_confidence(
    value: Any,
) -> float:

    try:

        confidence = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return 0.0

    if confidence > 1.0:

        confidence = (
            confidence
            / 100.0
        )

    return max(
        0.0,
        min(
            confidence,
            1.0,
        ),
    )


# =========================================================
# PROMPT
# =========================================================

def build_language_detection_instruction(
    text: str,
) -> str:

    return f"""
You are a language identification system.

Identify the PRIMARY natural language of the supplied text.

Rules:

1. Do not translate the text.
2. Do not summarize or rewrite it.
3. Return the actual language of the human-readable prose.
4. Ignore URLs, usernames, hashtags, numbers, emojis and
   isolated foreign names when deciding the primary language.
5. Mixed text:
   choose the language carrying most of the semantic content.
6. If the language genuinely cannot be determined, return
   language_code = "auto".
7. Use an ISO 639 language code when possible.
8. For Persian use "fa".
9. For Arabic use "ar".
10. For Urdu use "ur".
11. For Chinese use "zh".
12. For Filipino may use "fil".
13. Kurdish varieties may use "ku" or a more specific code
    such as "ckb" when clearly identifiable.
14. Do not assume English merely because the script is Latin.
15. Do not assume Hindi merely because the script is
    Devanagari.
16. Do not assume Arabic merely because Arabic script is used.

Return ONLY valid JSON in this exact structure:

{{
  "language_code": "fa",
  "language_name": "Persian",
  "confidence": 0.98,
  "script": "Arabic",
  "reason": "Short explanation"
}}

TEXT:

{text}
""".strip()


# =========================================================
# GEMINI RESPONSE
# =========================================================

def _extract_response_text(
    payload: Dict[str, Any],
) -> str:

    candidates = (
        payload.get(
            "candidates",
            [],
        )
        or []
    )

    for candidate in candidates:

        content = (
            candidate.get(
                "content",
                {},
            )
            or {}
        )

        parts = (
            content.get(
                "parts",
                [],
            )
            or []
        )

        for part in parts:

            text = str(
                part.get(
                    "text",
                    "",
                )
                or ""
            ).strip()

            if text:

                return text

    return ""


def _strip_json_fence(
    text: str,
) -> str:

    value = str(
        text
        or ""
    ).strip()

    if value.startswith(
        "```json"
    ):

        value = (
            value[
                len(
                    "```json"
                ):
            ]
        )

    elif value.startswith(
        "```"
    ):

        value = (
            value[
                len(
                    "```"
                ):
            ]
        )

    if value.endswith(
        "```"
    ):

        value = (
            value[
                :-3
            ]
        )

    return value.strip()


# =========================================================
# PROVIDER
# =========================================================

def detect_language_with_gemini(
    text: str,
) -> ProviderLanguageDetectionResult:

    source_text = str(
        text
        or ""
    ).strip()

    if not source_text:

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason="empty_text",
        )

    api_key = str(
        os.getenv(
            "GEMINI_API_KEY",
            "",
        )
        or ""
    ).strip()

    if not api_key:

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "gemini_api_key_not_configured"
            ),
        )

    model = (
        get_language_detection_model()
    )

    timeout = (
        get_language_detection_timeout()
    )

    endpoint = (
        f"{GEMINI_API_BASE}/models/"
        f"{model}:generateContent"
    )

    request_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text":
                            build_language_detection_instruction(
                                source_text
                            )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "topP": 0.9,
            "responseMimeType":
                "application/json",
        }
    }

    try:

        response = requests.post(
            endpoint,
            params={
                "key":
                    api_key,
            },
            json=request_payload,
            timeout=timeout,
        )

    except Exception as exc:

        logger.exception(
            "❌ LANGUAGE-DETECTION-PROVIDER | "
            "transport error | model=%s",
            model,
        )

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "provider_transport_error:"
                f"{type(exc).__name__}"
            ),
            model=model,
        )

    if response.status_code != 200:

        logger.error(
            "❌ LANGUAGE-DETECTION-PROVIDER | "
            "status=%s | model=%s | response=%s",
            response.status_code,
            model,
            response.text[
                :500
            ],
        )

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "provider_http_error:"
                f"{response.status_code}"
            ),
            model=model,
        )

    try:

        envelope = (
            response.json()
        )

    except Exception:

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "provider_invalid_json_envelope"
            ),
            model=model,
        )

    raw_text = (
        _extract_response_text(
            envelope
        )
    )

    if not raw_text:

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "provider_empty_response"
            ),
            model=model,
        )

    try:

        parsed = json.loads(
            _strip_json_fence(
                raw_text
            )
        )

    except Exception:

        logger.warning(
            "⚠️ LANGUAGE-DETECTION-PROVIDER | "
            "invalid model JSON | model=%s",
            model,
        )

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=0.0,
            reason=(
                "provider_invalid_model_json"
            ),
            model=model,
            raw_response=(
                raw_text[
                    :500
                ]
            ),
        )

    language = (
        normalize_language_code(
            parsed.get(
                "language_code"
            )
        )
    )

    confidence = (
        _normalize_confidence(
            parsed.get(
                "confidence",
                0.0,
            )
        )
    )

    language_name = str(
        parsed.get(
            "language_name",
            "",
        )
        or ""
    ).strip()

    script = str(
        parsed.get(
            "script",
            "",
        )
        or ""
    ).strip()

    reason = str(
        parsed.get(
            "reason",
            "",
        )
        or ""
    ).strip()

    if language == "auto":

        return ProviderLanguageDetectionResult(
            success=False,
            language="auto",
            confidence=confidence,
            language_name=language_name,
            script=script,
            reason=(
                reason
                or "provider_language_uncertain"
            ),
            model=model,
            raw_response=(
                raw_text[
                    :500
                ]
            ),
        )

    logger.info(
        "✅ LANGUAGE-DETECTION-PROVIDER | "
        "language=%s | confidence=%.2f | model=%s",
        language,
        confidence,
        model,
    )

    return ProviderLanguageDetectionResult(
        success=True,
        language=language,
        confidence=confidence,
        language_name=language_name,
        script=script,
        reason=reason,
        model=model,
        raw_response="",
        metadata={
            "provider":
                "gemini",

            "model":
                model,
        },
    )


# =========================================================
# RELIABILITY
# =========================================================

def provider_detection_is_reliable(
    result: ProviderLanguageDetectionResult,
    minimum_confidence: float = 0.75,
) -> bool:

    if not result.success:

        return False

    if (
        not result.language
        or result.language
        == "auto"
    ):

        return False

    return (
        result.confidence
        >= minimum_confidence
    )


# =========================================================
# SAFE FALLBACK
# =========================================================

def detect_language_with_provider_fallback(
    text: str,
    minimum_confidence: float = 0.75,
) -> ProviderLanguageDetectionResult:
    """
    Public provider entry point.

    Failure never guesses a language.

    The caller may safely fall back to:
        source_language = "auto"
    """

    result = (
        detect_language_with_gemini(
            text
        )
    )

    if provider_detection_is_reliable(
        result,
        minimum_confidence=(
            minimum_confidence
        ),
    ):

        return result

    return ProviderLanguageDetectionResult(
        success=False,
        language="auto",
        confidence=(
            result.confidence
        ),
        language_name=(
            result.language_name
        ),
        script=(
            result.script
        ),
        reason=(
            result.reason
            or "provider_detection_unreliable"
        ),
        model=(
            result.model
        ),
        metadata={
            "provider_result_language":
                result.language,

            "provider_result_confidence":
                result.confidence,
        },
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_language_detection_provider() -> Dict[str, Any]:

    return {
        "configured":
            language_detection_provider_configured(),

        "provider":
            "gemini",

        "model":
            get_language_detection_model(),

        "timeout_seconds":
            get_language_detection_timeout(),
    }
