from __future__ import annotations

import logging
import os
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION PROVIDER
# =========================================================
#
# NEW FILE
#
# وظیفه:
# Adapter عمومی برای Provider هوش مصنوعی ترجمه.
#
# در نسخه فعلی:
# - Gemini REST API
#
# این فایل:
# - هیچ پیام Telegram ارسال نمی‌کند.
# - هیچ پیام Bale ارسال نمی‌کند.
# - Publication Engine را تغییر نمی‌دهد.
# - Workspace / Legacy را تغییر نمی‌دهد.
# - فقط متن + دستور ترجمه را به Provider می‌دهد.
#
# translation_service.py
#          ↓
# translation_provider.py
#          ↓
# Gemini
#
# =========================================================


# =========================================================
# ENVIRONMENT
# =========================================================

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"

TRANSLATION_MODEL_ENV = "TRANSLATION_MODEL"

GEMINI_MODEL_ENV = "GEMINI_MODEL"

TRANSLATION_TIMEOUT_ENV = "TRANSLATION_TIMEOUT_SECONDS"


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

DEFAULT_TIMEOUT_SECONDS = 60

MAX_TIMEOUT_SECONDS = 180

MIN_TIMEOUT_SECONDS = 10


# =========================================================
# GEMINI ENDPOINT
# =========================================================

GEMINI_API_BASE = (
    "https://generativelanguage.googleapis.com/v1beta"
)


# =========================================================
# RESULT MODEL
# =========================================================

class TranslationProviderError(RuntimeError):
    """Safe, structured provider failure; raw exceptions stay in the cause chain."""

    def __init__(self, category, *, http_status=None, retryable=False,
                 retry_after_seconds=None, provider="gemini", model=""):
        self.category = category
        self.http_status = http_status
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider = provider
        self.model = model
        self.reason = "translation_provider_" + category
        super().__init__(self.reason)

    def as_metadata(self):
        return {key: getattr(self, key) for key in (
            "category", "http_status", "retryable", "retry_after_seconds",
            "provider", "model", "reason",
        )}


def _seconds(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def _http_provider_error(response, data, model):
    error = data.get("error", {})
    error = error if isinstance(error, dict) else {}
    details = error.get("details", [])
    details = details if isinstance(details, list) else []
    delays = []
    header = response.headers.get("Retry-After")
    if header is not None:
        delay = _seconds(header)
        if delay is None:
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is not None:
                    delay = max(0, (date - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
        if delay is not None:
            delays.append(delay)
    quota = False
    error_reasons = set()
    for detail in details:
        if not isinstance(detail, dict):
            continue
        kind = str(detail.get("@type", "")).rsplit("/", 1)[-1]
        if kind == "google.rpc.ErrorInfo":
            error_reasons.add(str(detail.get("reason", "")))
        if kind == "google.rpc.QuotaFailure" and detail.get("violations"):
            quota = True
        if kind == "google.rpc.RetryInfo":
            raw = detail.get("retryDelay")
            if isinstance(raw, str) and raw.endswith("s"):
                delay = _seconds(raw[:-1])
            elif isinstance(raw, dict):
                seconds = _seconds(raw.get("seconds", 0))
                nanos = _seconds(raw.get("nanos", 0))
                delay = seconds + nanos / 1e9 if seconds is not None and nanos is not None else None
            else:
                delay = None
            if delay is not None:
                delays.append(delay)
    delay = max(delays) if delays else None
    status = response.status_code
    if status == 429:
        category = "quota_unavailable" if quota else "rate_limited"
        retryable = not quota and delay is not None
    elif status in {500, 502, 503, 504}:
        category, retryable = "transient_server", True
    elif status in {401, 403} or error_reasons & {"API_KEY_INVALID", "API_KEY_EXPIRED", "CREDENTIALS_MISSING"}:
        category, retryable = "authentication", False
    elif status == 404 or error_reasons & {"SERVICE_DISABLED", "MODEL_NOT_FOUND"}:
        category, retryable = "configuration", False
    elif 400 <= status < 500:
        category, retryable = "invalid_request", False
    else:
        category, retryable = "unknown", False
    return TranslationProviderError(category, http_status=status, retryable=retryable,
                                    retry_after_seconds=delay, model=model)


@dataclass(frozen=True)
class ProviderStatus:
    configured: bool

    provider: str

    model: str

    reason: str = ""


# =========================================================
# CONFIG HELPERS
# =========================================================

def _clean_env(
    name: str,
    default: str = "",
) -> str:
    return str(
        os.getenv(
            name,
            default,
        )
        or ""
    ).strip()


def get_gemini_api_key() -> str:
    return _clean_env(
        GEMINI_API_KEY_ENV
    )


def get_translation_model() -> str:
    """
    اولویت:

    1. TRANSLATION_MODEL
    2. GEMINI_MODEL
    3. gemini-2.5-flash

    بنابراین اگر پروژه از قبل GEMINI_MODEL داشته باشد،
    ترجمه همان تنظیم موجود را استفاده می‌کند.
    """

    translation_model = _clean_env(
        TRANSLATION_MODEL_ENV
    )

    if translation_model:
        return translation_model

    gemini_model = _clean_env(
        GEMINI_MODEL_ENV
    )

    if gemini_model:
        return gemini_model

    return DEFAULT_GEMINI_MODEL


def get_translation_timeout() -> int:
    raw_value = _clean_env(
        TRANSLATION_TIMEOUT_ENV,
        str(
            DEFAULT_TIMEOUT_SECONDS
        ),
    )

    try:
        timeout = int(
            raw_value
        )

    except (
        TypeError,
        ValueError,
    ):
        timeout = DEFAULT_TIMEOUT_SECONDS

    return max(
        MIN_TIMEOUT_SECONDS,
        min(
            timeout,
            MAX_TIMEOUT_SECONDS,
        ),
    )


# =========================================================
# PROVIDER STATUS
# =========================================================

def get_translation_provider_status() -> ProviderStatus:
    api_key = get_gemini_api_key()

    model = get_translation_model()

    if not api_key:
        return ProviderStatus(
            configured=False,
            provider="gemini",
            model=model,
            reason="gemini_api_key_missing",
        )

    return ProviderStatus(
        configured=True,
        provider="gemini",
        model=model,
        reason="configured",
    )


def translation_provider_configured() -> bool:
    return (
        get_translation_provider_status()
        .configured
    )


# =========================================================
# RESPONSE HELPERS
# =========================================================

def _safe_json(
    response: requests.Response
) -> Dict[str, Any]:
    try:
        data = response.json()

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception:
        pass

    return {}


def _extract_error_message(
    payload: Dict[str, Any]
) -> str:
    error = payload.get(
        "error"
    )

    if isinstance(
        error,
        dict,
    ):
        message = error.get(
            "message"
        )

        if message:
            return str(
                message
            ).strip()

    return ""


def _extract_candidate_text(
    payload: Dict[str, Any]
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

        texts = []

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

            value = str(
                value
            )

            if value:
                texts.append(
                    value
                )

        if texts:
            return "".join(
                texts
            ).strip()

    return ""


# =========================================================
# PROMPT
# =========================================================

def _build_provider_prompt(
    *,
    text: str,
    instruction: str,
    source_language: str,
    target_language: str,
) -> str:
    """
    TranslationService تمام محدودیت‌های معنایی را در
    instruction تولید می‌کند.

    این Adapter فقط آن را به Prompt قطعی Provider تبدیل می‌کند.
    """

    return (
        "TRANSLATION TASK\n\n"
        f"Source language: {source_language}\n"
        f"Target language: {target_language}\n\n"
        "MANDATORY INSTRUCTIONS\n"
        f"{instruction}\n\n"
        "SOURCE CONTENT\n"
        "<<<D24_SOURCE>>>\n"
        f"{text}\n"
        "<<<END_D24_SOURCE>>>\n\n"
        "Return only the translated content."
    )


# =========================================================
# GEMINI PROVIDER
# =========================================================

def gemini_translation_provider(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    """
    Signature اصلی مورد انتظار translation_service.py

    provider(
        text=...,
        instruction=...,
        source_language=...,
        target_language=...
    )
    """

    api_key = get_gemini_api_key()

    if not api_key:
        raise TranslationProviderError("configuration", model=get_translation_model())

    model = get_translation_model()

    timeout = get_translation_timeout()

    prompt = _build_provider_prompt(
        text=text,
        instruction=instruction,
        source_language=source_language,
        target_language=target_language,
    )

    endpoint = (
        f"{GEMINI_API_BASE}/"
        f"models/{model}:generateContent"
    )

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
        },
    }

    logger.info(
        "🌐 Gemini translation request | "
        "model=%s | "
        "source=%s | "
        "target=%s | "
        "input_length=%s",
        model,
        source_language,
        target_language,
        len(
            text or ""
        ),
    )

    try:
        response = requests.post(
            endpoint,
            params={
                "key": api_key
            },
            json=payload,
            timeout=timeout,
        )

    except requests.Timeout as exc:
        logger.warning(
            "⚠️ Gemini translation timeout | "
            "model=%s | "
            "target=%s | "
            "timeout=%s",
            model,
            target_language,
            timeout,
        )

        raise TranslationProviderError("timeout", retryable=True, model=model) from exc

    except requests.RequestException as exc:
        raise TranslationProviderError(
            "connection", model=model, retryable=isinstance(exc, requests.ConnectionError)
            and not isinstance(exc, (requests.exceptions.SSLError, requests.exceptions.ProxyError)),
        ) from exc

    data = _safe_json(
        response
    )

    if not response.ok:
        raise _http_provider_error(response, data, model) from requests.HTTPError(
            "Translation provider HTTP failure", response=response,
        )

    try:
        translated_text = _extract_candidate_text(data)
    except (TypeError, ValueError, AttributeError, IndexError) as exc:
        raise TranslationProviderError("invalid_response", model=model) from exc

    if not translated_text:
        logger.error(
            "❌ Gemini translation returned no text | "
            "model=%s | "
            "source=%s | "
            "target=%s",
            model,
            source_language,
            target_language,
        )

        raise TranslationProviderError("invalid_response", model=model)

    logger.info(
        "✅ Gemini translation response | "
        "model=%s | "
        "source=%s | "
        "target=%s | "
        "output_length=%s",
        model,
        source_language,
        target_language,
        len(
            translated_text
        ),
    )

    return translated_text


# =========================================================
# DEFAULT PROVIDER
# =========================================================

def get_default_translation_provider():
    """
    نقطه مشترک برای TranslationService و Controller.

    بعداً اگر Provider دیگری اضافه شد، Publication Engine
    نیازی به تغییر نخواهد داشت.
    """

    if not translation_provider_configured():
        return None

    return gemini_translation_provider


# =========================================================
# HEALTH / DEBUG DESCRIPTION
# =========================================================

def describe_translation_provider() -> Dict[str, Any]:
    """
    فقط اطلاعات غیرحساس.

    API Key هرگز برگردانده نمی‌شود.
    """

    status = (
        get_translation_provider_status()
    )

    return {
        "configured": status.configured,
        "provider": status.provider,
        "model": status.model,
        "reason": status.reason,
        "timeout_seconds": (
            get_translation_timeout()
        ),
    }
