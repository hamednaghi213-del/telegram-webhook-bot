from __future__ import annotations

import logging
import os
import time

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from core.ai_runtime import provider_post, timed_stage


logger = logging.getLogger(__name__)


# =========================================================
# MULTILINGUAL TRANSLATION QUALITY PROVIDER
# =========================================================
#
# Provider adapter used by:
#
#     core/translation_quality.py
#
# Responsibilities:
#
# Translation candidate
#       ↓
# Multilingual semantic review
#       ↓
# JSON quality result
#
# IMPORTANT:
#
# - This module does NOT translate content.
# - This module does NOT publish content.
# - This module does NOT modify Translation Policy.
# - This module does NOT modify Workspace / Legacy.
# - This module does NOT write to the database.
#
# It only sends the quality-review prompt to Gemini and
# returns the raw JSON text expected by translation_quality.
#
# The same provider works for ANY source/target language.
# =========================================================


# =========================================================
# ENVIRONMENT
# =========================================================

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"

TRANSLATION_QUALITY_MODEL_ENV = (
    "TRANSLATION_QUALITY_MODEL"
)

TRANSLATION_MODEL_ENV = (
    "TRANSLATION_MODEL"
)

GEMINI_MODEL_ENV = (
    "GEMINI_MODEL"
)

QUALITY_TIMEOUT_ENV = (
    "TRANSLATION_QUALITY_TIMEOUT_SECONDS"
)


# =========================================================
# DEFAULTS
# =========================================================

DEFAULT_GEMINI_MODEL = (
    "gemini-2.5-flash"
)

DEFAULT_TIMEOUT_SECONDS = 60

MIN_TIMEOUT_SECONDS = 10
MAX_TIMEOUT_SECONDS = 180


GEMINI_API_BASE = (
    "https://generativelanguage.googleapis.com/v1beta"
)

CLOUDFLARE_AI_API_TOKEN_ENV = "CLOUDFLARE_AI_API_TOKEN"
CLOUDFLARE_ACCOUNT_ID_ENV = "CLOUDFLARE_ACCOUNT_ID"
CLOUDFLARE_QUALITY_MODEL_ENV = "CLOUDFLARE_TRANSLATION_QUALITY_MODEL"
DEFAULT_CLOUDFLARE_QUALITY_MODEL = "@cf/zai-org/glm-4.7-flash"
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"


# =========================================================
# STATUS MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationQualityProviderStatus:
    configured: bool

    provider: str

    model: str

    timeout_seconds: int

    reason: str = ""


# =========================================================
# ENV HELPERS
# =========================================================

def _clean_env(
    name: str,
) -> str:

    return str(
        os.getenv(
            name,
            ""
        )
        or ""
    ).strip()


def get_gemini_api_key() -> str:

    return _clean_env(
        GEMINI_API_KEY_ENV
    )


def get_translation_quality_model() -> str:
    """
    Model priority:

    1. TRANSLATION_QUALITY_MODEL
    2. TRANSLATION_MODEL
    3. GEMINI_MODEL
    4. default Gemini model
    """

    return (
        _clean_env(
            TRANSLATION_QUALITY_MODEL_ENV
        )
        or _clean_env(
            TRANSLATION_MODEL_ENV
        )
        or _clean_env(
            GEMINI_MODEL_ENV
        )
        or DEFAULT_GEMINI_MODEL
    )


def get_translation_quality_timeout() -> int:

    raw = _clean_env(
        QUALITY_TIMEOUT_ENV
    )

    try:
        timeout = int(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):
        timeout = (
            DEFAULT_TIMEOUT_SECONDS
        )

    return max(
        MIN_TIMEOUT_SECONDS,
        min(
            MAX_TIMEOUT_SECONDS,
            timeout,
        ),
    )


def get_cloudflare_ai_api_token() -> str:
    return _clean_env(CLOUDFLARE_AI_API_TOKEN_ENV)

def get_cloudflare_account_id() -> str:
    return _clean_env(CLOUDFLARE_ACCOUNT_ID_ENV)

def get_cloudflare_translation_quality_model() -> str:
    return _clean_env(CLOUDFLARE_QUALITY_MODEL_ENV) or DEFAULT_CLOUDFLARE_QUALITY_MODEL

def cloudflare_translation_quality_provider_configured() -> bool:
    return bool(get_cloudflare_ai_api_token() and get_cloudflare_account_id())


# =========================================================
# PROVIDER STATUS
# =========================================================

def get_translation_quality_provider_status(
) -> TranslationQualityProviderStatus:

    api_key = get_gemini_api_key()

    model = (
        get_translation_quality_model()
    )

    timeout = (
        get_translation_quality_timeout()
    )

    if not api_key:

        return TranslationQualityProviderStatus(
            configured=False,
            provider="gemini",
            model=model,
            timeout_seconds=timeout,
            reason=(
                "GEMINI_API_KEY is not configured."
            ),
        )

    return TranslationQualityProviderStatus(
        configured=True,
        provider="gemini",
        model=model,
        timeout_seconds=timeout,
    )


def translation_quality_provider_configured(
) -> bool:

    return bool(
        get_translation_quality_provider_status()
        .configured
    )


# =========================================================
# RESPONSE HELPERS
# =========================================================

def _safe_json(
    response: requests.Response,
) -> Dict[str, Any]:

    try:

        value = response.json()

    except Exception:

        return {}

    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def _extract_error_message(
    response: requests.Response,
) -> str:

    payload = _safe_json(
        response
    )

    error = payload.get(
        "error"
    )

    if isinstance(
        error,
        dict,
    ):

        message = str(
            error.get(
                "message",
                ""
            )
            or ""
        ).strip()

        if message:
            return message

    text = str(
        response.text
        or ""
    ).strip()

    if text:
        return text[:500]

    return (
        f"HTTP {response.status_code}"
    )


def _extract_candidate_text(
    payload: Dict[str, Any],
) -> str:

    candidates = payload.get(
        "candidates"
    )

    if not isinstance(
        candidates,
        list,
    ):
        return ""

    for candidate in candidates:

        if not isinstance(
            candidate,
            dict,
        ):
            continue

        content = candidate.get(
            "content"
        )

        if not isinstance(
            content,
            dict,
        ):
            continue

        parts = content.get(
            "parts"
        )

        if not isinstance(
            parts,
            list,
        ):
            continue

        text_parts = []

        for part in parts:

            if not isinstance(
                part,
                dict,
            ):
                continue

            value = part.get(
                "text"
            )

            if value is None:
                continue

            text_parts.append(
                str(
                    value
                )
            )

        if text_parts:

            return "\n".join(
                text_parts
            ).strip()

    return ""


# =========================================================
# PROVIDER PROMPT
# =========================================================

def _build_quality_prompt(
    *,
    text: str,
    instruction: str,
    source_language: str,
    target_language: str,
) -> str:
    """
    Build provider request.

    `text` already contains:

        SOURCE TEXT
        TRANSLATED TEXT

    from translation_quality.py.
    """

    source_language = str(
        source_language
        or "auto"
    ).strip()

    target_language = str(
        target_language
        or ""
    ).strip()

    return f"""
You are executing a multilingual translation quality
validation task.

Source language:
{source_language}

Target language:
{target_language}

Follow the validation instructions exactly.

Do not translate the source again.
Do not rewrite the candidate.
Do not summarize the content.
Do not provide commentary outside the required JSON.
Do not use Markdown code fences.

VALIDATION INSTRUCTIONS:

{instruction}

CONTENT TO REVIEW:

{text}

Return ONLY the required valid JSON object.
""".strip()


# =========================================================
# GEMINI QUALITY PROVIDER
# =========================================================

def _post_quality_request(endpoint, *, api_key, payload, timeout, model):
    for attempt in range(3):
        try:
            response = provider_post(
                endpoint,
                params={"key": api_key},
                json=payload,
                # Keep retries short even when the initial request times out.
                timeout=timeout if attempt == 0 else min(timeout, 10),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.ProxyError)):
                raise
            if attempt == 2:
                raise
            category = type(exc).__name__
        else:
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                return response
            category = f"http_{response.status_code}"
            response.close()

        delay = 2 ** attempt
        logger.warning(
            "TRANSLATION-QUALITY-RETRY | provider=gemini | model=%s | "
            "attempt=%s/3 | category=%s | delay=%ss",
            model, attempt + 2, category, delay,
        )
        time.sleep(delay)


@timed_stage("translation_quality", provider="gemini", model=get_translation_quality_model)
def gemini_translation_quality_provider(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    """
    Gemini adapter compatible with:

        core.translation_quality.QualityProvider

    Returns raw provider text.

    translation_quality.py is responsible for parsing and
    validating the JSON.
    """

    api_key = get_gemini_api_key()

    if not api_key:

        raise RuntimeError(
            "Translation quality provider unavailable: "
            "GEMINI_API_KEY is not configured."
        )

    model = (
        get_translation_quality_model()
    )

    timeout = (
        get_translation_quality_timeout()
    )

    prompt = _build_quality_prompt(
        text=text,
        instruction=instruction,
        source_language=source_language,
        target_language=target_language,
    )

    endpoint = (
        f"{GEMINI_API_BASE}/models/"
        f"{model}:generateContent"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text":
                            prompt
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature":
                0.0,

            "topP":
                0.9,

            "responseMimeType":
                "application/json",
        },
    }

    logger.info(
        "🌐 TRANSLATION-QUALITY-PROVIDER | "
        "provider=gemini | "
        "model=%s | "
        "source_language=%s | "
        "target_language=%s | "
        "input_length=%s",
        model,
        source_language,
        target_language,
        len(
            text
            or ""
        ),
    )

    try:

        response = _post_quality_request(
            endpoint,
            api_key=api_key,
            payload=payload,
            timeout=timeout,
            model=model,
        )

    except requests.Timeout as exc:

        logger.warning(
            "⚠️ TRANSLATION-QUALITY-PROVIDER-TIMEOUT | "
            "model=%s",
            model,
        )

        raise RuntimeError(
            "Translation quality provider timed out."
        ) from exc

    except requests.RequestException as exc:

        logger.warning(
            "⚠️ TRANSLATION-QUALITY-PROVIDER-NETWORK | "
            "model=%s | error=%s",
            model,
            type(exc).__name__,
        )

        raise RuntimeError(
            "Translation quality provider network error."
        ) from exc

    if not response.ok:

        message = (
            _extract_error_message(
                response
            )
        )

        logger.warning(
            "⚠️ TRANSLATION-QUALITY-PROVIDER-HTTP | "
            "model=%s | status=%s | error=%s",
            model,
            response.status_code,
            message,
        )

        raise RuntimeError(
            "Translation quality provider HTTP error: "
            f"{response.status_code} | {message}"
        )

    response_payload = (
        _safe_json(
            response
        )
    )

    candidate_text = (
        _extract_candidate_text(
            response_payload
        )
    )

    if not candidate_text:

        logger.warning(
            "⚠️ TRANSLATION-QUALITY-PROVIDER-EMPTY | "
            "model=%s",
            model,
        )

        raise RuntimeError(
            "Translation quality provider returned "
            "an empty response."
        )

    logger.info(
        "✅ TRANSLATION-QUALITY-PROVIDER-SUCCESS | "
        "provider=gemini | "
        "model=%s | "
        "output_length=%s",
        model,
        len(
            candidate_text
        ),
    )

    return candidate_text


# =========================================================
# CLOUDFLARE QUALITY PROVIDER
# =========================================================

def _extract_cloudflare_text(payload: Dict[str, Any]) -> str:
    result = payload.get("result")
    if not isinstance(result, dict):
        return ""
    response = result.get("response")
    if isinstance(response, str):
        return response.strip()
    choices = result.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "").strip()
    return ""


@timed_stage("translation_quality", provider="cloudflare", model=get_cloudflare_translation_quality_model)
def cloudflare_translation_quality_provider(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    token = get_cloudflare_ai_api_token()
    account_id = get_cloudflare_account_id()
    model = get_cloudflare_translation_quality_model()
    timeout = get_translation_quality_timeout()

    if not token or not account_id:
        raise RuntimeError("Cloudflare Workers AI quality provider is not configured.")

    prompt = _build_quality_prompt(
        text=text,
        instruction=instruction,
        source_language=source_language,
        target_language=target_language,
    )
    endpoint = f"{CLOUDFLARE_API_BASE}/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "temperature": 0.0, "max_tokens": 2048}

    logger.info(
        "🌐 TRANSLATION-QUALITY-PROVIDER | provider=cloudflare | model=%s | "
        "source_language=%s | target_language=%s | input_length=%s",
        model, source_language, target_language, len(text or ""),
    )
    try:
        response = provider_post(endpoint, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise RuntimeError("Cloudflare translation quality provider timed out.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Cloudflare translation quality provider network error.") from exc

    if not response.ok:
        message = _extract_error_message(response)
        logger.warning(
            "⚠️ TRANSLATION-QUALITY-PROVIDER-HTTP | provider=cloudflare | "
            "model=%s | status=%s | error=%s",
            model, response.status_code, message,
        )
        raise RuntimeError(
            f"Cloudflare translation quality provider HTTP error: {response.status_code} | {message}"
        )

    candidate_text = _extract_cloudflare_text(_safe_json(response))
    if not candidate_text:
        raise RuntimeError("Cloudflare translation quality provider returned an empty response.")

    logger.info(
        "✅ TRANSLATION-QUALITY-PROVIDER-SUCCESS | provider=cloudflare | "
        "model=%s | output_length=%s",
        model, len(candidate_text),
    )
    return candidate_text


def translation_quality_provider_chain(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    failures = []
    if translation_quality_provider_configured():
        try:
            return gemini_translation_quality_provider(
                text=text, instruction=instruction,
                source_language=source_language, target_language=target_language,
            )
        except Exception as exc:
            failures.append(("gemini", exc))
            logger.warning(
                "⚠️ TRANSLATION-QUALITY-FALLBACK | from=gemini | to=cloudflare | error=%s",
                type(exc).__name__,
            )

    if cloudflare_translation_quality_provider_configured():
        try:
            return cloudflare_translation_quality_provider(
                text=text, instruction=instruction,
                source_language=source_language, target_language=target_language,
            )
        except Exception as exc:
            failures.append(("cloudflare", exc))

    if failures:
        provider, exc = failures[-1]
        raise RuntimeError(
            f"Translation quality provider chain failed | last_provider={provider} | error={exc}"
        ) from exc
    raise RuntimeError("Translation quality provider unavailable: no configured quality provider.")


# =========================================================
# DEFAULT PROVIDER
# =========================================================

def get_default_translation_quality_provider() -> Optional[Any]:
    if not (
        translation_quality_provider_configured()
        or cloudflare_translation_quality_provider_configured()
    ):
        return None
    return translation_quality_provider_chain


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translation_quality_provider(
) -> Dict[str, Any]:
    """
    Safe status information.

    API key is NEVER returned.
    """

    status = (
        get_translation_quality_provider_status()
    )

    return {
        "configured":
            status.configured,

        "provider":
            status.provider,

        "model":
            status.model,

        "timeout_seconds":
            status.timeout_seconds,

        "reason":
            status.reason,
    }

