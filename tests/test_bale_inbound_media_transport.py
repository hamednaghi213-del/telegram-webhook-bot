"""Bale media references must cross transport boundaries as uploads."""

import os
import sys

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

if "supabase" not in sys.modules:
    fake_supabase = type(sys)("supabase")
    fake_supabase._is_persistence_fake = True
    fake_supabase.create_client = lambda _url, _key: object()
    sys.modules["supabase"] = fake_supabase

from core import bale_forwarder, bale_media, media_handler, publication_engine, telegram_rich_sender
from core.content_model import PublicationTarget
from core.webhook_handler import get_media_from_message


class _Response:
    status_code = 200
    content = b"{}"
    text = "{}"

    def json(self):
        return {"ok": True, "result": {"message_id": 31}}


@pytest.mark.parametrize("media_type", [
    "photo", "video", "document", "audio", "voice", "animation",
])
def test_bale_single_media_uploads_bytes_to_telegram(monkeypatch, media_type):
    calls = []
    monkeypatch.setattr(bale_media, "download_bale_media", lambda value: (b"media", "item.bin"))
    monkeypatch.setattr(
        media_handler,
        "telegram_post",
        lambda endpoint, payload, **kwargs: calls.append((endpoint, payload, kwargs)) or _Response(),
    )

    result = media_handler.send_single_media_to_channel(
        bale_media.bale_media_ref("bale-id"), media_type,
        channel_id="@target", api_url="https://telegram.test/bot-token",
    )

    assert result is True
    endpoint, payload, kwargs = calls[0]
    assert endpoint == "send" + media_type.capitalize()
    assert payload[media_type] == f"attach://{media_type}"
    assert kwargs["upload_files"][media_type] == ("item.bin", b"media")
    assert "bale-id" not in str(payload)


def test_bale_album_uploads_each_member_to_telegram(monkeypatch):
    calls = []
    monkeypatch.setattr(bale_media, "download_bale_media", lambda value: (value.encode(), "item.bin"))
    monkeypatch.setattr(
        media_handler,
        "telegram_post",
        lambda endpoint, payload, **kwargs: calls.append((endpoint, payload, kwargs)) or _Response(),
    )
    files = [
        {"type": "photo", "file_id": bale_media.bale_media_ref("first")},
        {"type": "video", "file_id": bale_media.bale_media_ref("second")},
    ]

    assert media_handler.send_media_group_to_channel(
        files, caption="Album", channel_id="@target",
        api_url="https://telegram.test/bot-token",
    )
    endpoint, payload, kwargs = calls[0]
    assert endpoint == "sendMediaGroup"
    assert [item["media"] for item in payload["media"]] == [
        "attach://media0", "attach://media1",
    ]
    assert list(kwargs["upload_files"]) == ["media0", "media1"]
    assert payload["media"][0]["caption"] == "Album"


def test_bale_resolver_uses_only_bale_get_file(monkeypatch):
    calls = []

    class _FileResponse:
        content = b"contents"

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True, "result": {"file_path": "videos/item.mp4"}}

    monkeypatch.setattr(bale_media.requests, "get", lambda url, **kwargs: calls.append(url) or _FileResponse())
    assert bale_media.download_bale_media(
        bale_media.bale_media_ref("bale-id"), token="secret"
    ) == (b"contents", "item.mp4")
    assert calls == [
        "https://tapi.bale.ai/botsecret/getFile",
        "https://tapi.bale.ai/file/botsecret/videos/item.mp4",
    ]


def test_bale_destination_reuses_own_file_id(monkeypatch):
    calls = []
    monkeypatch.setenv("BALE_BOT_TOKEN", "inbound-token")
    monkeypatch.setattr(
        bale_forwarder.requests, "post",
        lambda url, **kwargs: calls.append((url, kwargs)) or _Response(),
    )
    monkeypatch.setattr(
        bale_forwarder, "download_file_from_telegram",
        lambda value: pytest.fail("Bale ID reached Telegram getFile"),
    )

    assert bale_forwarder.send_video_to_bale(
        "@target", "inbound-token", "Caption",
        bale_media.bale_media_ref("bale-id"),
    )
    assert calls[0][1]["data"]["video"] == "bale-id"


def test_bale_download_failure_never_sends_file_id_to_telegram(monkeypatch):
    monkeypatch.setattr(bale_media, "download_bale_media", lambda value: (None, None))
    monkeypatch.setattr(
        media_handler, "telegram_post",
        lambda *args, **kwargs: pytest.fail("Unresolved Bale ID reached Telegram"),
    )
    assert not media_handler.send_single_media_to_channel(
        bale_media.bale_media_ref("bale-id"), "video",
        channel_id="@target", api_url="https://telegram.test/bot-token",
    )


def test_telegram_post_sends_upload_as_multipart(monkeypatch):
    calls = []
    monkeypatch.setattr(
        media_handler.requests, "post",
        lambda url, **kwargs: calls.append(kwargs) or _Response(),
    )
    media_handler.telegram_post(
        "sendVideo",
        {"chat_id": "@target", "video": "attach://video"},
        api_url="https://telegram.test/bot-token",
        upload_files={"video": ("clip.mp4", b"contents")},
    )
    assert calls[0]["files"]["video"] == ("clip.mp4", b"contents")
    assert calls[0]["data"]["video"] == "attach://video"
    assert "json" not in calls[0]


def test_unresolved_bale_reference_is_blocked_at_telegram_boundary(monkeypatch):
    monkeypatch.setattr(
        media_handler.requests, "post",
        lambda *args, **kwargs: pytest.fail("Bale ID reached Telegram"),
    )
    assert media_handler.telegram_post(
        "sendMediaGroup",
        {"media": [{"type": "video", "media": bale_media.bale_media_ref("id")}]},
        api_url="https://telegram.test/bot-token",
    ) is None


def test_bale_media_uses_upload_plan_before_rich_send(monkeypatch):
    calls = []
    monkeypatch.setattr(
        telegram_rich_sender, "send_rich_media_to_channel",
        lambda **kwargs: pytest.fail("Bale ID reached Telegram Rich sender"),
    )
    monkeypatch.setattr(
        media_handler, "execute_telegram_plan",
        lambda files, plan, **kwargs: calls.append(files) or {"ok": True, "message_id": 31},
    )
    target = PublicationTarget(
        key="tg", kind="workspace", platform="telegram",
        external_id="@target", workspace_id=1, destination_id=1,
    )
    result = publication_engine._send_media_target(
        1, "https://telegram.test/bot-token", target,
        [{"type": "photo", "file_id": bale_media.bale_media_ref("id")}],
        {"_media_presentation": "slideshow", "media_caption": "Caption"},
    )
    assert result.success
    assert len(calls) == 1


@pytest.mark.parametrize("media_type", ["audio", "voice", "animation"])
def test_bale_typed_media_keeps_type(monkeypatch, media_type):
    calls = []
    monkeypatch.setenv("BALE_BOT_TOKEN", "inbound-token")
    monkeypatch.setattr(
        bale_forwarder.requests, "post",
        lambda url, **kwargs: calls.append((url, kwargs)) or _Response(),
    )
    assert bale_forwarder.send_typed_media_to_bale(
        "@target", "inbound-token", "Caption",
        bale_media.bale_media_ref("bale-id"), media_type,
    )
    assert calls[0][0].endswith("/send" + media_type.capitalize())
    assert calls[0][1]["data"][media_type] == "bale-id"


@pytest.mark.parametrize("media_type", ["audio", "voice", "animation"])
def test_shared_inbound_extractor_keeps_typed_bale_reference(media_type):
    reference = bale_media.bale_media_ref("bale-id")
    assert get_media_from_message({
        media_type: {"file_id": reference}, "caption": "Caption",
    }) == {
        "type": media_type,
        "file_id": reference,
        "caption": "Caption",
    }
