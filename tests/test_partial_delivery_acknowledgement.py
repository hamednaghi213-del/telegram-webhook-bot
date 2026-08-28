from unittest.mock import patch

from core import webhook_handler
from core.content_model import DeliveryResult


def _delivery(platform: str, destination_id: int, status: str) -> DeliveryResult:
    return DeliveryResult(
        platform=platform,
        workspace_id=3 if destination_id else None,
        destination_id=destination_id or None,
        destination_chat_id=str(destination_id or "legacy"),
        status=status,
    )


def test_partial_delivery_uses_partial_acknowledgement_not_complete_failure():
    result = {
        "ok": False,
        "results": [
            _delivery("telegram", 0, "succeeded"),
            _delivery("bale", 0, "succeeded"),
            _delivery("telegram", 3, "failed"),
            _delivery("bale", 4, "failed"),
        ],
        "errors": [],
    }

    with patch.object(webhook_handler, "send_message") as send:
        webhook_handler._send_media_publication_acknowledgement(
            1001, result, "✅ رسانه شما در کانال منتشر شد."
        )

    sent = send.call_args.args[1]
    assert "در برخی مقصدها منتشر شد" in sent
    assert sent != "❌ ارسال رسانه با مشکل روبرو شد."


def test_all_destinations_succeed_uses_normal_success_acknowledgement():
    result = {
        "ok": True,
        "results": [
            _delivery("telegram", 0, "succeeded"),
            _delivery("bale", 4, "succeeded"),
        ],
        "errors": [],
    }

    with patch.object(webhook_handler, "send_message") as send:
        webhook_handler._send_media_publication_acknowledgement(
            1001, result, "✅ رسانه شما در کانال منتشر شد."
        )

    send.assert_called_once_with(1001, "✅ رسانه شما در کانال منتشر شد.")


def test_all_destinations_fail_uses_complete_failure_acknowledgement():
    result = {
        "ok": False,
        "results": [
            _delivery("telegram", 3, "failed"),
            _delivery("bale", 4, "failed"),
        ],
        "errors": [],
    }

    with patch.object(webhook_handler, "send_message") as send:
        webhook_handler._send_media_publication_acknowledgement(
            1001, result, "✅ رسانه شما در کانال منتشر شد."
        )

    send.assert_called_once_with(1001, "❌ ارسال رسانه با مشکل روبرو شد.")
