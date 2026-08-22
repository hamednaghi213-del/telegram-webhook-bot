import sys
import types

from core.workspace_publisher import (
    publish_to_destinations,
    sync_edited_channel_post_to_bale,
)


def test_publish_records_telegram_bale_message_pair(monkeypatch):
    monkeypatch.setenv("BALE_BOT_TOKEN", "token")
    monkeypatch.setattr(
        "core.workspace_publisher._send_text_to_destination",
        lambda *_args: (
            True,
            "",
            {"message_id": 101, "chat": {"id": -10055}},
        ),
    )
    fake_bale = types.ModuleType("core.bale_forwarder")
    fake_bale.send_text_to_bale = lambda *_args, **_kwargs: {
        "ok": True,
        "message_id": 202,
    }
    fake_bale.send_photo_to_bale = fake_bale.send_text_to_bale
    fake_bale.send_video_to_bale = fake_bale.send_text_to_bale
    fake_bale.send_document_to_bale = fake_bale.send_text_to_bale
    monkeypatch.setitem(sys.modules, "core.bale_forwarder", fake_bale)

    recorded = []
    result = publish_to_destinations(
        "https://telegram.test",
        [
            {"id": 1, "workspace_id": 7, "platform": "telegram",
             "external_id": "@telegram"},
            {"id": 2, "workspace_id": 7, "platform": "bale",
             "external_id": "@bale"},
        ],
        "خبر",
        None,
        None,
        lambda _id: {},
        lambda _id: {},
        record_message_link_fn=lambda **payload: recorded.append(payload),
    )

    assert result["success"] == 2
    assert recorded == [{
        "workspace_id": 7,
        "telegram_destination_id": 1,
        "telegram_chat_id": "-10055",
        "telegram_message_id": 101,
        "bale_destination_id": 2,
        "bale_chat_id": "@bale",
        "bale_message_id": 202,
        "content_kind": "text",
    }]


def test_known_telegram_caption_edit_is_mirrored_to_bale(monkeypatch):
    fake_database = types.ModuleType("core.database")
    fake_database.get_publication_message_link = lambda *_args: {
        "content_kind": "caption",
        "bale_chat_id": "@bale",
        "bale_message_id": 202,
    }
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setenv("BALE_BOT_TOKEN", "token")

    calls = []
    fake_bale = types.ModuleType("core.bale_forwarder")
    fake_bale.edit_bale_message = lambda *args, **kwargs: (
        calls.append((args, kwargs)) or True
    )
    monkeypatch.setitem(sys.modules, "core.bale_forwarder", fake_bale)

    assert sync_edited_channel_post_to_bale({
        "chat": {"id": -10055},
        "message_id": 101,
        "caption": "متن ویرایش‌شده",
    }) is True
    assert calls == [(('@bale', 'token', 202, 'متن ویرایش‌شده'), {
        "is_caption": True,
    })]


def test_unknown_telegram_edit_is_ignored(monkeypatch):
    fake_database = types.ModuleType("core.database")
    fake_database.get_publication_message_link = lambda *_args: None
    monkeypatch.setitem(sys.modules, "core.database", fake_database)

    assert sync_edited_channel_post_to_bale({
        "chat": {"id": -10055},
        "message_id": 999,
        "text": "ویرایش",
    }) is False
