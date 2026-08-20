import sys
import types

from core.bale_verifier import verify_bale_channel_admin
from core.workspace_publisher import publish_to_destinations


class Response:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok

    def json(self):
        return self._payload


def test_central_bale_bot_admin_is_verified():
    responses = iter([
        Response({"ok": True, "result": {"id": 42}}),
        Response({
            "ok": True,
            "result": {"status": "administrator", "can_post_messages": True},
        }),
    ])
    verified, _ = verify_bale_channel_admin(
        "central-token",
        "@news",
        request_post=lambda *args, **kwargs: next(responses),
    )
    assert verified is True


def test_missing_bale_token_does_not_undo_telegram_success(monkeypatch):
    monkeypatch.delenv("BALE_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        "core.workspace_publisher._send_text_to_destination",
        lambda *args: (True, None),
    )
    destinations = [
        {"id": 1, "workspace_id": 7, "platform": "telegram", "external_id": "@tg"},
        {"id": 2, "workspace_id": 7, "platform": "bale", "external_id": "@bale"},
    ]
    result = publish_to_destinations(
        "https://telegram.test",
        destinations,
        "خبر",
        None,
        None,
        lambda _id: {},
        lambda _id: {},
    )
    assert result == {"success": 1, "failure": 1, "errors": ["@bale"]}


def test_telegram_and_bale_can_both_publish_with_central_token(monkeypatch):
    monkeypatch.setenv("BALE_BOT_TOKEN", "central-token")
    monkeypatch.setattr(
        "core.workspace_publisher._send_text_to_destination",
        lambda *args: (True, None),
    )
    fake_sender = types.ModuleType("core.bale_forwarder")
    fake_sender.send_text_to_bale = lambda *args: True
    fake_sender.send_photo_to_bale = lambda *args: True
    fake_sender.send_video_to_bale = lambda *args: True
    fake_sender.send_document_to_bale = lambda *args: True
    monkeypatch.setitem(sys.modules, "core.bale_forwarder", fake_sender)
    destinations = [
        {"id": 1, "workspace_id": 7, "platform": "telegram", "external_id": "@tg"},
        {"id": 2, "workspace_id": 7, "platform": "bale", "external_id": "@bale"},
    ]
    result = publish_to_destinations(
        "https://telegram.test",
        destinations,
        "خبر",
        None,
        None,
        lambda _id: {},
        lambda _id: {},
    )
    assert result == {"success": 2, "failure": 0, "errors": []}


def test_bale_is_optional_for_workspace_completion():
    from core.workspace_pairing import has_required_telegram_destination

    assert has_required_telegram_destination([
        {"platform": "telegram", "status": "active"}
    ]) is True


def test_bale_only_cannot_complete_required_telegram_setup():
    from core.workspace_pairing import has_required_telegram_destination

    assert has_required_telegram_destination([
        {"platform": "bale", "status": "active"}
    ]) is False
