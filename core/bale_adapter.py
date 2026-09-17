"""Bale inbound adapter (Bale Full Bot Parity — slice 1).

Normalizes inbound Bale bot updates and runs them through the
SAME shared command handlers the Telegram webhook uses. Platform
differences live here:

- secret-token validation of the inbound Bale webhook,
- update shape normalization (message/text/callback),
- binding the Bale outbound messaging context,
- binding the Bale identity origin so shared logic resolves the
  user through ``bale_user_id`` (never via Telegram numeric IDs).

Business logic (commands, onboarding, workspaces) is NOT
duplicated: ``core.command_handler.handle_command`` is invoked
exactly as the Telegram webhook does.
"""

import logging
import os
import secrets
from typing import Any, Dict, Optional, Tuple

from core import command_handler
from core.messaging import BaleMessagingContext


logger = logging.getLogger(__name__)


BALE_WEBHOOK_INITIALIZED: bool = False
BALE_SECRET_TOKEN: str = ""


def initialize(secret_token: str = "") -> None:
    """Configure the Bale webhook secret (optional endpoint)."""
    global BALE_WEBHOOK_INITIALIZED
    global BALE_SECRET_TOKEN

    BALE_SECRET_TOKEN = (secret_token or "").strip()
    BALE_WEBHOOK_INITIALIZED = True

    logger.info(
        "✅ Bale Adapter initialized | secret_configured=%s",
        bool(BALE_SECRET_TOKEN),
    )


def validate_bale_webhook_token(request) -> bool:
    """Validate the inbound Bale webhook secret header.

    Uses the same compare_digest pattern as the Telegram webhook.
    When no Bale secret is configured the endpoint is disabled:
    it fails closed instead of accepting unsigned updates.
    """
    if not BALE_WEBHOOK_INITIALIZED:
        logger.error(
            "❌ Bale Adapter not initialized"
        )
        return False

    if not BALE_SECRET_TOKEN:
        logger.error(
            "❌ BALE_WEBHOOK_SECRET_TOKEN is not configured"
        )
        return False

    request_token = request.headers.get(
        "X-Bale-Bot-Secret-Token"
    )

    if not request_token:
        logger.warning(
            "⚠️ Missing Bale webhook secret header"
        )
        return False

    if not secrets.compare_digest(
        request_token,
        BALE_SECRET_TOKEN,
    ):
        logger.error(
            "❌ Invalid Bale webhook secret token"
        )
        return False

    return True


def _extract_message(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    message = data.get("message")

    if isinstance(message, dict):
        return message

    # Bale may deliver edited updates; slice 1 treats them as
    # plain messages only when they carry text (no lifecycle sync
    # is implemented here).
    edited = data.get("edited_message")

    if isinstance(edited, dict) and edited.get("text"):
        return edited

    return None


def _extract_command_text(message: Dict[str, Any]) -> str:
    text = str(message.get("text") or "").strip()

    if not text:
        # Bale bot commands may arrive as entities over captions.
        caption = str(message.get("caption") or "").strip()

        if caption.startswith("/"):
            text = caption

    return text


def _is_bot_command(message: Dict[str, Any], text: str) -> bool:
    if not text.startswith("/"):
        return False

    entities = message.get("entities") or []

    for entity in entities:
        if (
            isinstance(entity, dict)
            and entity.get("type") == "bot_command"
            and int(entity.get("offset") or 0) == 0
        ):
            return True

    # Fallback for Bale clients that omit entities: leading slash
    # with a valid command shape.
    first = text.split(" ")[0]
    return first.startswith("/") and len(first) > 1


def handle_bale_update(
    data: Dict[str, Any],
) -> Tuple[Dict[str, Any], int]:
    """Process one Bale update through the shared application core.

    Returns a JSON-serializable response tuple. Commands are
    executed by the shared ``handle_command``; non-command text
    and unsupported update kinds are acknowledged without action
    in slice 1 (media, callbacks and editorial flows follow in
    later slices).
    """
    message = _extract_message(data)

    if message is None:
        return {"ok": True, "handled": False}, 200

    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id is None:
        return {"ok": True, "handled": False}, 200

    text = _extract_command_text(message)

    if not _is_bot_command(message, text):
        return {
            "ok": True,
            "handled": False,
            "reason": "non_command",
        }, 200

    previous_origin = command_handler.CURRENT_ORIGIN

    try:
        command_handler.CURRENT_ORIGIN = "bale"

        from core.messaging import bind_context

        bind_context(BaleMessagingContext())

        handled = command_handler.handle_command(
            text,
            int(chat_id),
        )

        return {
            "ok": True,
            "handled": bool(handled),
        }, 200
    except Exception as exc:
        logger.exception(
            "❌ Bale command handling failed | chat=%s | %s",
            chat_id,
            exc,
        )
        return {"ok": True, "handled": False}, 200
    finally:
        command_handler.CURRENT_ORIGIN = previous_origin

        from core.messaging import reset_default_context

        reset_default_context()


def bale_secret_configured() -> bool:
    return bool(
        os.getenv("BALE_WEBHOOK_SECRET_TOKEN", "").strip()
    )
