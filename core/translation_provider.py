from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict

import requests

from core.ai_runtime import provider_post, timed_stage
from core.translation_provider_registry import (
    describe_translation_provider_registry,
    get_translation_provider_chain,
    get_translation_provider_names,
    register_translation_provider,
)

logger = logging.getLogger(__name__)

# =========================================================
# ENVIRONMENT
# =========================================================

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_MODEL_ENV = "DEEPSEEK_MODEL"
TRANSLATION_MODEL_ENV = "TRANSLATION_MODEL"
GEMINI_MODEL_ENV = "GEMINI_MODEL"
TRANSLATION_TIMEOUT_ENV = "TRANSLATION_TIMEOUT_SECONDS"

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 180
MIN_TIMEOUT_SECONDS = 10

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEEPSEEK_API_BASE = "https://api.deepseek.com"


# =========================================================
# RESULT MODEL
# =========================================================

class TranslationProviderError(RuntimeError):
    """Safe, structured provider failure; raw exceptions stay in the cause chain."""

    def __init__(
        self,
        category,
        *,
        http_status=None,
        retryable=False,
        retry_after_seconds=None,
        provider="gemini",
        model="",
    ):
        self.category = category
        self.http_status = http_status
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider = provider
        self.model = model
        self.reason = "translation_provider_" + category
        super().__init__(self.reason)

    def as_metadata(self):
        return {
            key: getattr(self, key)
            for key in (
                "category",
                "http_status",
                "retryable",
                "retry_after_seconds",
                "provider",
                "model",
                "reason",
            )
        }


@dataclass(frozen=True)
class ProviderStatus:
    configured: bool
    provider: str
    model: str
    reason: str = ""


# =========================================================
# ERROR HELPERS
# =========================================================

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
                    delay = max(
                        0,
                        (date - datetime.now(timezone.utc)).total_seconds(),
                    )
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
                delay = (
                    seconds + nanos / 1e9
                    if seconds is not None and nanos is not None
                    else None
                )
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
    elif status in {401, 403} or error_reasons & {
        "API_KEY_INVALID",
        "API_KEY_EXPIRED",
        "CREDENTIALS_MISSING",
    }:
        category, retryable = "authentication", False
    elif status == 404 or error_reasons & {
        "SERVICE_DISABLED",
        "MODEL_NOT_FOUND",
    }:
        category, retryable = "configuration", False
    elif 400 <= status < 500:
        category, retryable = "invalid_request", False
    else:
        category, retryable = "unknown", False

    return TranslationProviderError(
        category,
        http_status=status,
        retryable=retryable,
        retry_after_seconds=delay,
        provider="gemini",
        model=model,
    )


# =========================================================
# CONFIG HELPERS
# =========================================================

def _clean_env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def get_gemini_api_key() -> str:
    return _clean_env(GEMINI_API_KEY_ENV)


def get_deepseek_api_key() -> str:
    return _clean_env(DEEPSEEK_API_KEY_ENV)


def get_deepseek_model() -> str:
    return _clean_env(DEEPSEEK_MODEL_ENV, DEFAULT_DEEPSEEK_MODEL)


def get_translation_model() -> str:
    translation_model = _clean_env(TRANSLATION_MODEL_ENV)
    if translation_model:
        return translation_model

    gemini_model = _clean_env(GEMINI_MODEL_ENV)
    if gemini_model:
        return gemini_model

    return DEFAULT_GEMINI_MODEL


def get_translation_timeout() -> int:
    raw_value = _clean_env(
        TRANSLATION_TIMEOUT_ENV,
        str(DEFAULT_TIMEOUT_SECONDS),
    )

    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS

    return max(
        MIN_TIMEOUT_SECONDS,
        min(timeout, MAX_TIMEOUT_SECONDS),
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
    return get_translation_provider_status().configured


# =========================================================
# RESPONSE HELPERS
# =========================================================

def _safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return {}


def _extract_error_message(payload: Dict[str, Any]) -> str:
    error = payload.get("error")

    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return str(message).strip()

    return ""


def _extract_candidate_text(payload: Dict[str, Any]) -> str:
    candidates = payload.get("candidates")

    if not isinstance(candidates, list):
        return ""

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content")
        if not isinstance(content, dict):
            continue

        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        texts = []

        for part in parts:
            if not isinstance(part, dict):
                continue

            value = part.get("text")
            if value is None:
                continue

            value = str(value)
            if value:
                texts.append(value)

        if texts:
            return "".join(texts).strip()

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

@timed_stage(
    "translation_generation",
    provider="gemini",
    model=get_translation_model,
)
def gemini_translation_provider(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    api_key = get_gemini_api_key()

    if not api_key:
        raise TranslationProviderError(
            "configuration",
            provider="gemini",
            model=get_translation_model(),
        )

    model = get_translation_model()
    timeout = get_translation_timeout()

    prompt = _build_provider_prompt(
        text=text,
        instruction=instruction,
        source_language=source_language,
        target_language=target_language,
    )

    endpoint = f"{GEMINI_API_BASE}/models/{model}:generateContent"

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
        },
    }

    logger.info(
        "🌐 Gemini translation request | "
        "model=%s | source=%s | target=%s | input_length=%s",
        model,
        source_language,
        target_language,
        len(text or ""),
    )

    try:
        response = provider_post(
            endpoint,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )

    except requests.Timeout as exc:
        logger.warning(
            "⚠️ Gemini translation timeout | "
            "model=%s | target=%s | timeout=%s",
            model,
            target_language,
            timeout,
        )

        raise TranslationProviderError(
            "timeout",
            retryable=True,
            provider="gemini",
            model=model,
        ) from exc

    except requests.RequestException as exc:
        retryable = (
            isinstance(exc, requests.ConnectionError)
            and not isinstance(
                exc,
                (
                    requests.exceptions.SSLError,
                    requests.exceptions.ProxyError,
                ),
            )
        )

        raise TranslationProviderError(
            "connection",
            retryable=retryable,
            provider="gemini",
            model=model,
        ) from exc

    data = _safe_json(response)

    if not response.ok:
        raise _http_provider_error(
            response,
            data,
            model,
        ) from requests.HTTPError(
            "Translation provider HTTP failure",
            response=response,
        )

    try:
        translated_text = _extract_candidate_text(data)
    except (
        TypeError,
        ValueError,
        AttributeError,
        IndexError,
    ) as exc:
        raise TranslationProviderError(
            "invalid_response",
            provider="gemini",
            model=model,
        ) from exc

    if not translated_text:
        logger.error(
            "❌ Gemini translation returned no text | "
            "model=%s | source=%s | target=%s",
            model,
            source_language,
            target_language,
        )

        raise TranslationProviderError(
            "invalid_response",
            provider="gemini",
            model=model,
        )

    logger.info(
        "✅ Gemini translation response | "
        "model=%s | source=%s | target=%s | output_length=%s",
        model,
        source_language,
        target_language,
        len(translated_text),
    )

    return translated_text


# =========================================================
# DEEPSEEK PROVIDER
# =========================================================

def _deepseek_http_provider_error(response, data, model):
    status = response.status_code
    delay = _seconds(response.headers.get("Retry-After"))

    if status == 429:
        category, retryable = "rate_limited", False
    elif status in {500, 502, 503, 504}:
        category, retryable = "transient_server", True
    elif status in {401, 403}:
        category, retryable = "authentication", False
    elif status == 402:
        category, retryable = "quota_unavailable", False
    elif status == 404:
        category, retryable = "configuration", False
    elif 400 <= status < 500:
        category, retryable = "invalid_request", False
    else:
        category, retryable = "unknown", False

    return TranslationProviderError(
        category,
        http_status=status,
        retryable=retryable,
        retry_after_seconds=delay,
        provider="deepseek",
        model=model,
    )


def _extract_deepseek_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content or "").strip()


@timed_stage(
    "translation_generation",
    provider="deepseek",
    model=get_deepseek_model,
)
def deepseek_translation_provider(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    api_key = get_deepseek_api_key()
    model = get_deepseek_model()

    if not api_key:
        raise TranslationProviderError(
            "configuration", provider="deepseek", model=model
        )

    prompt = _build_provider_prompt(
        text=text,
        instruction=instruction,
        source_language=source_language,
        target_language=target_language,
    )

    endpoint = f"{DEEPSEEK_API_BASE}/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info(
        "🌐 DeepSeek translation request | model=%s | source=%s | target=%s | input_length=%s",
        model, source_language, target_language, len(text or ""),
    )

    try:
        response = provider_post(
            endpoint, headers=headers, json=payload, timeout=get_translation_timeout()
        )
    except requests.Timeout as exc:
        raise TranslationProviderError(
            "timeout", retryable=True, provider="deepseek", model=model
        ) from exc
    except requests.RequestException as exc:
        retryable = isinstance(exc, requests.ConnectionError) and not isinstance(
            exc, (requests.exceptions.SSLError, requests.exceptions.ProxyError)
        )
        raise TranslationProviderError(
            "connection", retryable=retryable, provider="deepseek", model=model
        ) from exc

    data = _safe_json(response)
    if not response.ok:
        raise _deepseek_http_provider_error(response, data, model) from requests.HTTPError(
            "DeepSeek translation provider HTTP failure", response=response
        )

    translated_text = _extract_deepseek_text(data)
    if not translated_text:
        raise TranslationProviderError(
            "invalid_response", provider="deepseek", model=model
        )

    logger.info(
        "✅ DeepSeek translation response | model=%s | source=%s | target=%s | output_length=%s",
        model, source_language, target_language, len(translated_text),
    )
    return translated_text


# =========================================================
# REGISTRY BOOTSTRAP
# =========================================================

def configure_default_translation_providers() -> None:
    """
    Register every currently configured provider.

    This function is intentionally safe to call repeatedly.
    replace=True also keeps monkeypatch/test injection deterministic.
    """

    if translation_provider_configured():
        register_translation_provider(
            name="gemini",
            provider=gemini_translation_provider,
            priority=10,
            enabled=True,
            replace=True,
        )

    if get_deepseek_api_key():
        register_translation_provider(
            name="deepseek",
            provider=deepseek_translation_provider,
            priority=20,
            enabled=True,
            replace=True,
        )


def get_translation_provider_entries():
    configure_default_translation_providers()

    from core.translation_provider_registry import (
        get_translation_provider_entries as registry_entries,
    )

    return registry_entries()


def get_translation_providers():
    configure_default_translation_providers()
    return get_translation_provider_chain()


# =========================================================
# DEFAULT PROVIDER
# =========================================================

def get_default_translation_provider():
    """
    Backward-compatible entry point used by TranslationService/Controller.

    Today the first configured provider is Gemini.
    The registry now owns provider selection order, so additional providers
    can be added without changing Publication Engine or language routing.
    """

    providers = get_translation_providers()

    if not providers:
        return None

    return providers[0]


# =========================================================
# HEALTH / DEBUG DESCRIPTION
# =========================================================

def describe_translation_provider() -> Dict[str, Any]:
    status = get_translation_provider_status()

    configure_default_translation_providers()

    registry = describe_translation_provider_registry()
    provider_names = list(get_translation_provider_names())

    return {
        "configured": bool(provider_names),
        "provider": provider_names[0] if provider_names else status.provider,
        "model": status.model,
        "reason": status.reason,
        "timeout_seconds": get_translation_timeout(),
        "provider_chain": provider_names,
        "registry": registry,
    }

