"""Origin-scoped outbound transport registry (Bale parity).

Shared command/onboarding logic must reply over the platform the
user is actually talking to. Adapters (Telegram webhook, Bale
adapter) register their outbound senders for the duration of one
inbound request; the default context remains Telegram so every
existing Telegram path keeps its exact historical behavior.
"""

import contextlib
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

# The Bale forwarder is used only for its API base constant. It is
# imported defensively so this transport module stays importable in
# test environments (and degraded runtimes) where core.database is
# stubbed or partially unavailable.
try:
    from core import bale_forwarder

    BALE_API_BASE = bale_forwarder.BALE_API_BASE
except Exception:  # pragma: no cover - degraded environments only
    bale_forwarder = None

    BALE_API_BASE = "https://tapi.bale.ai/bot"


class MessagingContext:
    """Outbound transport for one inbound platform context."""

    name = "telegram"

    def send_text(
        self,
        chat_id,
        text,
        parse_mode=None,
    ) -> bool:
        raise NotImplementedError

    def send_keyboard(
        self,
        chat_id,
        text,
        keyboard,
    ) -> bool:
        raise NotImplementedError

    def acknowledge_callback(
        self,
        callback_id,
        text="",
    ) -> bool:
        """Acknowledge a callback query on this platform."""
        raise NotImplementedError


class TelegramMessagingContext(MessagingContext):
    """Delegates to the historical Telegram senders.

    Thin wrappers around core.command_handler's Telegram HTTP
    senders so existing tests that patch those functions keep
    working.
    """

    name = "telegram"

    def send_text(
        self,
        chat_id,
        text,
        parse_mode=None,
    ) -> bool:
        from core import command_handler

        return command_handler.send_message(
            chat_id,
            text,
        )

    def send_keyboard(
        self,
        chat_id,
        text,
        keyboard,
    ) -> bool:
        from core import command_handler

        return command_handler.send_message_with_keyboard(
            chat_id,
            text,
            keyboard,
        )

    def acknowledge_callback(
        self,
        callback_id,
        text="",
    ) -> bool:
        from core import command_handler

        try:
            return command_handler.answer_callback_query_telegram(
                callback_id,
                text,
            )
        except Exception:
            logger.exception(
                "Telegram callback acknowledgement failed"
            )
            return False


class BaleMessagingContext(MessagingContext):
    """Bale outbound transport built on the Bale Bot API."""

    name = "bale"

    def send_text(
        self,
        chat_id,
        text,
        parse_mode=None,
    ) -> bool:
        return send_bale_text(
            chat_id,
            text,
        )

    def send_keyboard(
        self,
        chat_id,
        text,
        keyboard,
    ) -> bool:
        # Bale supports inline keyboards via reply_markup on
        # sendMessage; send plain text when no token is set.
        return send_bale_keyboard(
            chat_id,
            text,
            keyboard,
        )

    def acknowledge_callback(
        self,
        callback_id,
        text="",
    ) -> bool:
        return acknowledge_bale_callback(
            callback_id,
            text,
        )


def _bale_token() -> str:
    return os.getenv("BALE_BOT_TOKEN", "").strip()


def send_bale_text(
    chat_id,
    text,
) -> bool:
    token = _bale_token()

    if not token:
        logger.error(
            "BALE_BOT_TOKEN not configured; "
            "cannot reply over Bale"
        )
        return False

    try:
        response = requests.post(
            f"{BALE_API_BASE}{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
            },
            timeout=30,
        )

        return (
            response.status_code == 200
            and (
                response.json() or {}
            ).get("ok", True) is not False
        )
    except Exception:
        logger.exception(
            "Bale sendMessage failed"
        )
        return False


def acknowledge_bale_callback(
    callback_id,
    text="",
) -> bool:
    token = _bale_token()

    if not token:
        logger.error(
            "BALE_BOT_TOKEN not configured; "
            "cannot acknowledge Bale callback"
        )
        return False

    if not callback_id:
        return False

    try:
        response = requests.post(
            f"{BALE_API_BASE}{token}/answerCallbackQuery",
            json={
                "callback_query_id": callback_id,
                "text": text or "",
            },
            timeout=10,
        )

        return (
            response.status_code == 200
            and (
                response.json() or {}
            ).get("ok", True) is not False
        )
    except Exception:
        logger.exception(
            "Bale answerCallbackQuery failed"
        )
        return False


def send_bale_keyboard(
    chat_id,
    text,
    keyboard,
) -> bool:
    token = _bale_token()

    if not token:
        logger.error(
            "BALE_BOT_TOKEN not configured; "
            "cannot reply over Bale"
        )
        return False

    try:
        response = requests.post(
            f"{BALE_API_BASE}{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {
                    "inline_keyboard": keyboard,
                },
            },
            timeout=30,
        )

        return (
            response.status_code == 200
            and (
                response.json() or {}
            ).get("ok", True) is not False
        )
    except Exception:
        logger.exception(
            "Bale keyboard sendMessage failed"
        )
        return False


_telegram_default = TelegramMessagingContext()

_storage = threading.local()

_binding_lock = threading.Lock()


def bind_context(context) -> None:
    """Bind the outbound context for the current thread/request."""
    with _binding_lock:
        _storage.context = context


def current_context():
    """Return the thread's bound context (default: Telegram)."""
    context = getattr(
        _storage,
        "context",
        None,
    )

    if context is not None:
        return context

    return _telegram_default


@contextlib.contextmanager
def bound_context(context):
    """Temporarily bind a context (tests and adapters)."""
    previous = getattr(
        _storage,
        "context",
        None,
    )
    _storage.context = context
    try:
        yield context
    finally:
        _storage.context = previous


def reset_default_context() -> TelegramMessagingContext:
    """Clear any bound context (test isolation helper)."""
    _storage.context = None

    return _telegram_default
