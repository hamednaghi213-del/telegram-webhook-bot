from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.translation_provider import TranslationProviderError
from core.translation_provider_registry import (
    TranslationProviderEntry,
    get_translation_provider_entries,
)

logger = logging.getLogger(__name__)


# =========================================================
# UNIVERSAL TRANSLATION PROVIDER CHAIN
# =========================================================
#
# این ماژول اجرای واقعی زنجیره Providerها را مدیریت می‌کند.
#
# Translation Service
#        ↓
# Provider Chain
#        ↓
# Provider 1
#        ↓ failure
# Provider 2
#        ↓ failure
# Provider 3
#        ↓
# Fail Closed
#
# این لایه:
# - به زبان خاصی وابسته نیست.
# - Telegram / Bale / Workspace را نمی‌شناسد.
# - Translation Policy را تغییر نمی‌دهد.
# - فقط Providerهای ثبت‌شده را به ترتیب Registry اجرا می‌کند.
# - Provider خراب یا دارای quota را موقتاً cooldown می‌کند.
# - اگر همه Providerها شکست بخورند Fail-Closed باقی می‌ماند.
#
# =========================================================


# خطاهایی که اجازه عبور به Provider بعدی را دارند.
# خطاهای invalid_request عمداً در این لیست نیستند؛ چون معمولاً
# مشکل Request است و تکرار همان Request روی Provider دیگر ممکن است
# خطای منطقی را پنهان کند.
FALLBACK_CATEGORIES = frozenset(
    {
        "transient_server",
        "quota_unavailable",
        "rate_limited",
        "timeout",
        "connection",
        "authentication",
        "configuration",
        "invalid_response",
        "unknown",
    }
)

DEFAULT_COOLDOWN_SECONDS = 30.0
MAX_COOLDOWN_SECONDS = 300.0
MIN_COOLDOWN_SECONDS = 1.0


@dataclass(frozen=True)
class ProviderFailure:
    name: str
    category: str
    reason: str
    retry_after_seconds: Optional[float]
    http_status: Optional[int]
    retryable: bool
    model: str = ""


_cooldown_lock = threading.RLock()
_provider_cooldown_until: Dict[str, float] = {}


def _provider_name(entry: TranslationProviderEntry) -> str:
    return str(entry.name or "").strip().lower()


def _safe_delay(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None

    try:
        delay = float(value)
    except (TypeError, ValueError):
        return None

    if delay < 0:
        return None

    return delay


def _cooldown_seconds(error: TranslationProviderError) -> float:
    requested = _safe_delay(error.retry_after_seconds)

    if requested is None:
        if error.category == "quota_unavailable":
            requested = 60.0
        elif error.category == "rate_limited":
            requested = 30.0
        elif error.category in {
            "transient_server",
            "timeout",
            "connection",
        }:
            requested = 15.0
        else:
            requested = DEFAULT_COOLDOWN_SECONDS

    return max(
        MIN_COOLDOWN_SECONDS,
        min(requested, MAX_COOLDOWN_SECONDS),
    )


def provider_in_cooldown(name: str) -> bool:
    provider_name = str(name or "").strip().lower()
    if not provider_name:
        return False

    now = time.monotonic()

    with _cooldown_lock:
        until = _provider_cooldown_until.get(provider_name)

        if until is None:
            return False

        if until <= now:
            _provider_cooldown_until.pop(provider_name, None)
            return False

        return True


def provider_cooldown_remaining(name: str) -> float:
    provider_name = str(name or "").strip().lower()
    if not provider_name:
        return 0.0

    now = time.monotonic()

    with _cooldown_lock:
        until = _provider_cooldown_until.get(provider_name)

        if until is None:
            return 0.0

        remaining = until - now

        if remaining <= 0:
            _provider_cooldown_until.pop(provider_name, None)
            return 0.0

        return remaining


def mark_provider_cooldown(
    name: str,
    error: TranslationProviderError,
) -> float:
    provider_name = str(name or "").strip().lower()
    if not provider_name:
        return 0.0

    delay = _cooldown_seconds(error)
    until = time.monotonic() + delay

    with _cooldown_lock:
        previous = _provider_cooldown_until.get(provider_name, 0.0)
        _provider_cooldown_until[provider_name] = max(previous, until)

    logger.warning(
        "TRANSLATION-PROVIDER-COOLDOWN | "
        "provider=%s | category=%s | seconds=%.1f",
        provider_name,
        error.category,
        delay,
    )

    return delay


def clear_provider_cooldown(name: Optional[str] = None) -> None:
    with _cooldown_lock:
        if name is None:
            _provider_cooldown_until.clear()
            return

        provider_name = str(name or "").strip().lower()
        _provider_cooldown_until.pop(provider_name, None)


def _normalize_failure(
    entry: TranslationProviderEntry,
    exc: Exception,
) -> TranslationProviderError:
    if isinstance(exc, TranslationProviderError):
        return exc

    return TranslationProviderError(
        "unknown",
        retryable=False,
        provider=_provider_name(entry) or "unknown",
    )


def _failure_record(
    entry: TranslationProviderEntry,
    error: TranslationProviderError,
) -> ProviderFailure:
    return ProviderFailure(
        name=_provider_name(entry),
        category=str(error.category or "unknown"),
        reason=str(error.reason or "translation_provider_unknown"),
        retry_after_seconds=_safe_delay(error.retry_after_seconds),
        http_status=error.http_status,
        retryable=bool(error.retryable),
        model=str(error.model or ""),
    )


def _raise_chain_failure(
    failures: Tuple[ProviderFailure, ...],
) -> None:
    if not failures:
        raise TranslationProviderError(
            "configuration",
            retryable=False,
            provider="registry",
        )

    last = failures[-1]

    error = TranslationProviderError(
        last.category,
        http_status=last.http_status,
        retryable=False,
        retry_after_seconds=last.retry_after_seconds,
        provider=last.name or "registry",
        model=last.model,
    )

    # JSON-safe metadata for upper layers.
    error.provider_failures = [
        {
            "name": failure.name,
            "category": failure.category,
            "reason": failure.reason,
            "retry_after_seconds": failure.retry_after_seconds,
            "http_status": failure.http_status,
            "retryable": failure.retryable,
            "model": failure.model,
        }
        for failure in failures
    ]

    raise error


def translation_provider_chain(
    *,
    text: str,
    instruction: str,
    source_language: str = "auto",
    target_language: str,
) -> str:
    """
    Provider callable compatible with TranslationService.

    Providers are read from the universal Registry in priority order.

    A provider failure may move execution to the next provider.
    If every configured provider is unavailable or fails, the function
    raises TranslationProviderError and publication remains fail-closed.
    """

    entries = get_translation_provider_entries()

    if not entries:
        raise TranslationProviderError(
            "configuration",
            retryable=False,
            provider="registry",
        )

    failures = []

    for entry in entries:
        name = _provider_name(entry)

        if provider_in_cooldown(name):
            remaining = provider_cooldown_remaining(name)

            logger.info(
                "TRANSLATION-PROVIDER-SKIP | "
                "provider=%s | reason=cooldown | remaining=%.1f",
                name,
                remaining,
            )

            failures.append(
                ProviderFailure(
                    name=name,
                    category="rate_limited",
                    reason="translation_provider_cooldown",
                    retry_after_seconds=remaining,
                    http_status=None,
                    retryable=True,
                    model="",
                )
            )
            continue

        logger.info(
            "TRANSLATION-PROVIDER-TRY | "
            "provider=%s | source=%s | target=%s",
            name,
            source_language,
            target_language,
        )

        try:
            output = entry.provider(
                text=text,
                instruction=instruction,
                source_language=source_language,
                target_language=target_language,
            )

        except Exception as exc:
            error = _normalize_failure(entry, exc)
            failure = _failure_record(entry, error)
            failures.append(failure)

            logger.warning(
                "TRANSLATION-PROVIDER-FAIL | "
                "provider=%s | category=%s | status=%s | "
                "retryable=%s | fallback=%s",
                name,
                error.category,
                error.http_status,
                error.retryable,
                error.category in FALLBACK_CATEGORIES,
            )

            if error.category not in FALLBACK_CATEGORIES:
                raise

            mark_provider_cooldown(name, error)
            continue

        output = str(output or "").strip()

        if not output:
            error = TranslationProviderError(
                "invalid_response",
                retryable=False,
                provider=name or "unknown",
            )

            failures.append(
                _failure_record(entry, error)
            )

            mark_provider_cooldown(name, error)
            continue

        clear_provider_cooldown(name)

        logger.info(
            "TRANSLATION-PROVIDER-SUCCESS | "
            "provider=%s | output_length=%s",
            name,
            len(output),
        )

        return output

    _raise_chain_failure(tuple(failures))

    # Unreachable; keeps static analyzers satisfied.
    raise TranslationProviderError(
        "unknown",
        retryable=False,
        provider="registry",
    )


def describe_provider_cooldowns() -> Dict[str, float]:
    now = time.monotonic()
    result: Dict[str, float] = {}

    with _cooldown_lock:
        expired = []

        for name, until in _provider_cooldown_until.items():
            remaining = until - now

            if remaining <= 0:
                expired.append(name)
                continue

            result[name] = remaining

        for name in expired:
            _provider_cooldown_until.pop(name, None)

    return result
