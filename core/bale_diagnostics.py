"""Safe diagnostics for the centrally configured Bale bot transport."""

import logging
import os
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)
API_BASE = "https://tapi.bale.ai/bot"


def bale_response_ok(response, operation):
    """Report rejected/malformed responses without logging credential URLs."""
    try:
        body = response.json()
    except (ValueError, TypeError):
        body = None
    if (
        response.status_code == 200
        and isinstance(body, dict)
        and body.get("ok") is True
    ):
        return True
    description = str(body.get("description") or "") if isinstance(body, dict) else "invalid JSON response"
    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if token:
        description = description.replace(token, "[REDACTED]")
    logger.error(
        "Bale API rejected request | operation=%s | status=%s | error_code=%s | description=%s",
        operation,
        response.status_code,
        body.get("error_code") if isinstance(body, dict) else None,
        description[:300],
    )
    return False


def check_bale_connection():
    """Read-only startup check; never changes webhooks or sends messages."""
    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("Bale connection check skipped | BALE_BOT_TOKEN missing")
        return
    if not os.getenv("ADMIN_BALE_USER_ID", "").strip():
        logger.warning("Bale admin configuration missing | ADMIN_BALE_USER_ID")
    for operation in ("getMe", "getWebhookInfo"):
        try:
            response = requests.get(
                f"{API_BASE}{token}/{operation}", timeout=(5, 10)
            )
            if not bale_response_ok(response, operation):
                continue
            result = response.json().get("result") or {}
            if not isinstance(result, dict):
                logger.warning("Bale connection check | operation=%s | unexpected result", operation)
                continue
            if operation == "getMe":
                logger.info("Bale connection verified | bot_username=%s | bot_id=%s", result.get("username"), result.get("id"))
            else:
                url = urlsplit(str(result.get("url") or ""))
                logger.info(
                    "Bale webhook configuration | host=%s | path=%s | pending=%s | allowed_updates=%s | last_error_present=%s",
                    url.hostname, url.path, result.get("pending_update_count"),
                    result.get("allowed_updates"), bool(result.get("last_error_message")),
                )
        except Exception as exc:
            # requests exceptions can include a complete URL containing the token.
            logger.error("Bale connection check failed | operation=%s | exception_type=%s", operation, type(exc).__name__)
