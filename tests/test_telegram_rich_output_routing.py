from core import media_handler
from core import publication_engine
from core import telegram_rich_sender

from core.content_model import (
    PreparedContent,
    PublicationTarget,
)


def _telegram_target():
    return PublicationTarget(
        key="telegram-test",
        kind="workspace",
        platform="telegram",
        external_id="@test_channel",
        workspace_id=1,
        destination_id=10,
    )


def _legacy_telegram_target():
    return PublicationTarget(
        key="legacy-telegram",
        kind="legacy",
        platform="telegram",
        external_id="@legacy_channel",
    )


def _legacy_bale_target():
    return PublicationTarget(
        key="legacy-bale",
        kind="legacy",
        platform="bale",
        external_id="@bale_channel",
    )


def _files():
    return [
        {
            "type": "photo",
            "file_id": "photo-1",
        },
        {
            "type": "photo",
            "file_id": "photo-2",
        },
    ]


def _plan(
    presentation="",
):
    return {
        "media_caption": "متن خبر",
        "media_parse_mode": None,
        "media_caption_entities": [],
        "followup_messages": [],
        "blockquote_messages": [],
        "_media_presentation": presentation,
    }


def test_slideshow_routes_to_send_rich_message(
    monkeypatch,
):
    rich_calls = []
    normal_calls = []

    def fake_rich_sender(
        files,
        presentation,
        caption="",
        channel_id=None,
        api_url=None,
        is_rtl=None,
    ):
        rich_calls.append(
            {
                "files": list(files),
                "presentation": presentation,
                "caption": caption,
                "channel_id": channel_id,
                "api_url": api_url,
            }
        )

        return {
            "ok": True,
            "message_id": 101,
        }

    def fake_normal_sender(
        *args,
        **kwargs,
    ):
        normal_calls.append(
            (
                args,
                kwargs,
            )
        )

        return True

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        fake_rich_sender,
    )

    monkeypatch.setattr(
        media_handler,
        "execute_telegram_plan",
        fake_normal_sender,
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        _files(),
        _plan("slideshow"),
    )

    assert result.success is True

    assert len(
        rich_calls
    ) == 1

    assert (
        rich_calls[0][
            "presentation"
        ]
        == "slideshow"
    )

    assert (
        rich_calls[0][
            "caption"
        ]
        == "متن خبر"
    )

    assert (
        rich_calls[0][
            "channel_id"
        ]
        == "@test_channel"
    )

    assert normal_calls == []


def test_collage_routes_to_send_rich_message(
    monkeypatch,
):
    rich_calls = []
    normal_calls = []

    def fake_rich_sender(
        files,
        presentation,
        caption="",
        channel_id=None,
        api_url=None,
        is_rtl=None,
    ):
        rich_calls.append(
            presentation
        )

        return {
            "ok": True,
            "message_id": 202,
        }

    def fake_normal_sender(
        *args,
        **kwargs,
    ):
        normal_calls.append(
            1
        )

        return True

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        fake_rich_sender,
    )

    monkeypatch.setattr(
        media_handler,
        "execute_telegram_plan",
        fake_normal_sender,
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        _files(),
        _plan("collage"),
    )

    assert result.success is True

    assert rich_calls == [
        "collage"
    ]

    assert normal_calls == []


def test_normal_album_keeps_existing_telegram_path(
    monkeypatch,
):
    rich_calls = []
    normal_calls = []

    def fake_rich_sender(
        *args,
        **kwargs,
    ):
        rich_calls.append(
            1
        )

        return {
            "ok": True,
            "message_id": 301,
        }

    def fake_normal_sender(
        files,
        plan,
        channel_id=None,
        api_url=None,
        return_result=False,
    ):
        normal_calls.append(
            {
                "files":
                    list(files),

                "plan":
                    dict(plan),

                "channel_id":
                    channel_id,

                "api_url":
                    api_url,

                "return_result":
                    return_result,
            }
        )

        return {
            "ok": True,
            "message_id": 302,
        }

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        fake_rich_sender,
    )

    monkeypatch.setattr(
        media_handler,
        "execute_telegram_plan",
        fake_normal_sender,
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        _files(),
        _plan(""),
    )

    assert result.success is True

    assert rich_calls == []

    assert len(
        normal_calls
    ) == 1

    assert (
        normal_calls[0][
            "channel_id"
        ]
        == "@test_channel"
    )

    assert (
        normal_calls[0][
            "return_result"
        ]
        is True
    )


def test_unknown_presentation_keeps_existing_path(
    monkeypatch,
):
    rich_calls = []
    normal_calls = []

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        lambda *args, **kwargs:
            rich_calls.append(1)
            or {
                "ok": True,
                "message_id": 401,
            },
    )

    monkeypatch.setattr(
        media_handler,
        "execute_telegram_plan",
        lambda *args, **kwargs:
            normal_calls.append(1)
            or {
                "ok": True,
                "message_id": 402,
            },
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        _files(),
        _plan(
            "future-presentation"
        ),
    )

    assert result.success is True

    assert rich_calls == []

    assert normal_calls == [
        1
    ]


def test_rich_send_failure_does_not_fallback_to_album(
    monkeypatch,
):
    rich_calls = []
    normal_calls = []

    def fake_rich_sender(
        *args,
        **kwargs,
    ):
        rich_calls.append(
            1
        )

        return {
            "ok": False,
            "error": (
                "simulated rich failure"
            ),
            "operation":
                "sendRichMessage",
        }

    def fake_normal_sender(
        *args,
        **kwargs,
    ):
        normal_calls.append(
            1
        )

        return {
            "ok": True,
            "message_id": 502,
        }

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        fake_rich_sender,
    )

    monkeypatch.setattr(
        media_handler,
        "execute_telegram_plan",
        fake_normal_sender,
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        _files(),
        _plan("slideshow"),
    )

    assert result.success is False

    assert rich_calls == [
        1
    ]

    # Critical duplicate-safety lock:
    # sendRichMessage failure must not immediately
    # send the same publication again as MediaGroup.
    assert normal_calls == []


def test_legacy_telegram_slideshow_uses_rich_sender(
    monkeypatch,
):
    calls = []

    def fake_rich_sender(
        files,
        presentation,
        caption="",
        channel_id=None,
        api_url=None,
        is_rtl=None,
    ):
        calls.append(
            {
                "presentation":
                    presentation,

                "channel_id":
                    channel_id,

                "api_url":
                    api_url,
            }
        )

        return {
            "ok": True,
            "message_id": 601,
        }

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        fake_rich_sender,
    )

    result = publication_engine._send_media_target(
        1,
        "https://api.telegram.org/botTEST",
        _legacy_telegram_target(),
        _files(),
        _plan("slideshow"),
    )

    assert result.success is True

    assert len(calls) == 1

    assert (
        calls[0][
            "presentation"
        ]
        == "slideshow"
    )

    # Legacy Telegram continues to resolve its
    # configured destination inside media_handler.
    assert (
        calls[0][
            "channel_id"
        ]
        is None
    )

    assert (
        calls[0][
            "api_url"
        ]
        is None
    )


def test_bale_ignores_rich_presentation_and_keeps_bale_path(
    monkeypatch,
):
    rich_calls = []
    bale_calls = []

    monkeypatch.setattr(
        telegram_rich_sender,
        "send_rich_media_to_channel",
        lambda *args, **kwargs:
            rich_calls.append(1)
            or {
                "ok": True,
                "message_id": 701,
            },
    )

    def fake_bale_plan(
        chat_id,
        files,
        plan,
        return_result=False,
    ):
        bale_calls.append(
            {
                "chat_id":
                    chat_id,

                "files":
                    list(files),

                "presentation":
                    plan.get(
                        "_media_presentation"
                    ),

                "return_result":
                    return_result,
            }
        )

        return {
            "ok": True,
            "message_id": 702,
        }

    monkeypatch.setattr(
        media_handler,
        "execute_bale_plan",
        fake_bale_plan,
    )

    result = publication_engine._send_media_target(
        99,
        "https://api.telegram.org/botTEST",
        _legacy_bale_target(),
        _files(),
        _plan("slideshow"),
    )

    assert result.success is True

    assert rich_calls == []

    assert len(
        bale_calls
    ) == 1

    assert (
        bale_calls[0][
            "return_result"
        ]
        is True
    )


def test_delivery_part_carries_presentation_without_changing_sender_signature(
    monkeypatch,
):
    calls = []

    def fake_sender(
        chat_id,
        api_url,
        target,
        files,
        plan,
    ):
        calls.append(
            {
                "chat_id":
                    chat_id,

                "api_url":
                    api_url,

                "target":
                    target,

                "files":
                    list(files),

                "presentation":
                    plan.get(
                        "_media_presentation"
                    ),
            }
        )

        return {
            "ok": True,
            "message_id": 801,
        }

    monkeypatch.setattr(
        publication_engine,
        "_send_media_target",
        fake_sender,
    )

    prepared = PreparedContent(
        main_text="خبر",
        files=_files(),
        media_presentation=(
            "slideshow"
        ),
        source_key=(
            "rich-routing-test"
        ),
    )

    result = publication_engine._execute_delivery_part(
        1,
        "https://api.telegram.org/botTEST",
        _telegram_target(),
        prepared,
        _plan(""),
        "primary",
        0,
    )

    assert (
        publication_engine._outcome_ok(
            result
        )
        is True
    )

    assert len(
        calls
    ) == 1

    assert (
        calls[0][
            "presentation"
        ]
        == "slideshow"
    )
