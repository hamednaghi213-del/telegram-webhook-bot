import sys
import types

from unittest.mock import (
    patch,
    MagicMock
)


# =========================================================
# FAKE DATABASE
# =========================================================

fake_database = types.ModuleType(
    "core.database"
)

fake_database.get_tenant = MagicMock(
    return_value={
        "telegram_channel": "@channel"
    }
)


# =========================================================
# FAKE COMMAND HANDLER
# =========================================================

fake_command_handler = types.ModuleType(
    "core.command_handler"
)

fake_command_handler.handle_command = (
    MagicMock()
)


# =========================================================
# REGISTER FAKE MODULES
# =========================================================

sys.modules[
    "core.database"
] = fake_database

sys.modules[
    "core.command_handler"
] = fake_command_handler


# =========================================================
# IMPORT WEBHOOK HANDLER
# =========================================================

from core import webhook_handler


# =========================================================
# FAKE FLASK REQUEST
# =========================================================

class FakeRequest:

    def __init__(
        self,
        payload=None
    ):

        self.payload = payload
        self.headers = {}

    def get_json(
        self,
        silent=True
    ):

        return self.payload


# =========================================================
# SHARED TEST DATA
# =========================================================

PHOTO_MESSAGE = {
    "message_id": 1,
    "chat": {
        "id": 1001
    },
    "photo": [
        {
            "file_id": "small"
        },
        {
            "file_id": "large"
        }
    ],
    "caption": "خبر تصویری",
    "caption_entities": []
}


VIDEO_MESSAGE = {
    "message_id": 2,
    "chat": {
        "id": 1001
    },
    "video": {
        "file_id": "video_1"
    },
    "caption": "خبر ویدیویی",
    "caption_entities": []
}


ALBUM_MESSAGE = {
    "message_id": 3,
    "chat": {
        "id": 1001
    },
    "media_group_id": "album_1",
    "photo": [
        {
            "file_id": "photo_small"
        },
        {
            "file_id": "photo_large"
        }
    ],
    "caption": "کپشن آلبوم",
    "caption_entities": [
        {
            "type": "expandable_blockquote",
            "offset": 0,
            "length": 5
        }
    ]
}


TEXT_MESSAGE = {
    "message_id": 4,
    "chat": {
        "id": 1001
    },
    "text": "خبر متنی",
    "entities": []
}


# =========================================================
# RESET BEFORE EVERY TEST
# =========================================================

def setup_function():

    fake_database.get_tenant.reset_mock()

    fake_database.get_tenant.return_value = {
        "telegram_channel": "@channel"
    }

    fake_command_handler.handle_command.reset_mock()


# =========================================================
# TEST 01
# GET MESSAGE TEXT FROM CAPTION
# =========================================================

def test_get_message_text_prefers_caption():

    msg = {
        "caption": "CAPTION",
        "text": "TEXT"
    }

    assert (
        webhook_handler.get_message_text(
            msg
        )
        == "CAPTION"
    )


# =========================================================
# TEST 02
# GET MESSAGE TEXT FROM TEXT
# =========================================================

def test_get_message_text_uses_text():

    msg = {
        "text": "TEXT"
    }

    assert (
        webhook_handler.get_message_text(
            msg
        )
        == "TEXT"
    )


# =========================================================
# TEST 03
# CAPTION ENTITIES
# =========================================================

def test_get_message_entities_for_caption():

    entities = [
        {
            "type": "blockquote"
        }
    ]

    msg = {
        "caption": "CAPTION",
        "caption_entities": entities
    }

    assert (
        webhook_handler.get_message_entities(
            msg
        )
        == entities
    )


# =========================================================
# TEST 04
# TEXT ENTITIES
# =========================================================

def test_get_message_entities_for_text():

    entities = [
        {
            "type": "bold"
        }
    ]

    msg = {
        "text": "TEXT",
        "entities": entities
    }

    assert (
        webhook_handler.get_message_entities(
            msg
        )
        == entities
    )


# =========================================================
# TEST 05
# PHOTO HIGHEST QUALITY
# =========================================================

def test_get_media_from_photo_uses_last_file_id():

    media = (
        webhook_handler.get_media_from_message(
            PHOTO_MESSAGE
        )
    )

    assert (
        media["type"]
        == "photo"
    )

    assert (
        media["file_id"]
        == "large"
    )

    assert (
        media["caption"]
        == "خبر تصویری"
    )


# =========================================================
# TEST 06
# VIDEO EXTRACTION
# =========================================================

def test_get_media_from_video():

    media = (
        webhook_handler.get_media_from_message(
            VIDEO_MESSAGE
        )
    )

    assert (
        media["type"]
        == "video"
    )

    assert (
        media["file_id"]
        == "video_1"
    )


# =========================================================
# TEST 07
# SINGLE PHOTO ENTITY PIPELINE
# =========================================================

def test_single_photo_uses_entity_pipeline():

    parsed = {
        "main_text": "MAIN",
        "blockquote_blocks": [],
        "expandable_blocks": [],
        "other_entities": []
    }

    plan = type(
        "Plan",
        (),
        {
            "telegram": {
                "media_caption": "TG",
                "followup_messages": [],
                "blockquote_messages": [],
                "document_fallback": False
            },
            "bale": {
                "media_caption": "BALE",
                "followup_messages": [],
                "blockquote_messages": [],
                "document_fallback": False
            }
        }
    )()

    with patch(
        "core.content_entities.parse_telegram_entities",
        return_value=parsed
    ) as mock_parse, patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ) as mock_format, patch(
        "core.caption_manager.analyze_content",
        return_value=plan
    ) as mock_analyze, patch(
        "core.media_handler.execute_telegram_plan",
        return_value=True
    ) as mock_tg, patch(
        "core.media_handler.execute_bale_plan",
        return_value=True
    ) as mock_bale, patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value="#TAG\n@CHANNEL"
    ):

        success = (
            webhook_handler.process_single_photo_video(
                chat_id=1001,
                file_id="photo_1",
                media_type="photo",
                caption="RAW",
                caption_entities=[
                    {
                        "type": "blockquote",
                        "offset": 0,
                        "length": 3
                    }
                ]
            )
        )

    assert success is True

    mock_parse.assert_called_once()

    mock_format.assert_called_once_with(
        "MAIN"
    )

    mock_analyze.assert_called_once()

    mock_tg.assert_called_once()

    mock_bale.assert_called_once()


# =========================================================
# TEST 08
# SINGLE VIDEO ENTITY PIPELINE
# =========================================================

def test_single_video_uses_entity_pipeline():

    parsed = {
        "main_text": "VIDEO MAIN",
        "blockquote_blocks": [],
        "expandable_blocks": [],
        "other_entities": []
    }

    plan = type(
        "Plan",
        (),
        {
            "telegram": {
                "media_caption": "TG",
                "followup_messages": [],
                "blockquote_messages": [],
                "document_fallback": False
            },
            "bale": {
                "media_caption": "BALE",
                "followup_messages": [],
                "blockquote_messages": [],
                "document_fallback": False
            }
        }
    )()

    with patch(
        "core.content_entities.parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value="FORMATTED VIDEO"
    ), patch(
        "core.caption_manager.analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler.execute_telegram_plan",
        return_value=True
    ) as mock_tg, patch(
        "core.media_handler.execute_bale_plan",
        return_value=True
    ), patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler.process_single_photo_video(
                chat_id=1001,
                file_id="video_1",
                media_type="video",
                caption="RAW",
                caption_entities=[]
            )
        )

    assert success is True

    files = (
        mock_tg.call_args.args[0]
    )

    assert files == [
        {
            "type": "video",
            "file_id": "video_1"
        }
    ]


# =========================================================
# TEST 09
# TELEGRAM FAILURE PREVENTS BALE
# =========================================================

def test_single_media_telegram_failure_prevents_bale():

    parsed = {
        "main_text": "MAIN",
        "blockquote_blocks": [],
        "expandable_blocks": [],
        "other_entities": []
    }

    plan = type(
        "Plan",
        (),
        {
            "telegram": {},
            "bale": {}
        }
    )()

    with patch(
        "core.content_entities.parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ), patch(
        "core.caption_manager.analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler.execute_telegram_plan",
        return_value=False
    ), patch(
        "core.media_handler.execute_bale_plan",
        return_value=True
    ) as mock_bale, patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler.process_single_photo_video(
                chat_id=1001,
                file_id="photo_1",
                media_type="photo",
                caption="RAW",
                caption_entities=[]
            )
        )

    assert success is False

    mock_bale.assert_not_called()


# =========================================================
# TEST 10
# BALE FAILURE DOES NOT FAIL OPERATION
# =========================================================

def test_single_media_bale_failure_does_not_fail_operation():

    parsed = {
        "main_text": "MAIN",
        "blockquote_blocks": [],
        "expandable_blocks": [],
        "other_entities": []
    }

    plan = type(
        "Plan",
        (),
        {
            "telegram": {},
            "bale": {}
        }
    )()

    with patch(
        "core.content_entities.parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ), patch(
        "core.caption_manager.analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler.execute_telegram_plan",
        return_value=True
    ), patch(
        "core.media_handler.execute_bale_plan",
        return_value=False
    ), patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler.process_single_photo_video(
                chat_id=1001,
                file_id="photo_1",
                media_type="photo",
                caption="RAW",
                caption_entities=[]
            )
        )

    assert success is True


# =========================================================
# TEST 11
# ALBUM CAPTION ENTITIES
# =========================================================

def test_media_group_passes_caption_entities():

    fake_request = FakeRequest(
        {
            "message": ALBUM_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ) as mock_group:

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result == {
        "ok": True
    }

    kwargs = (
        mock_group.call_args.kwargs
    )

    assert (
        kwargs["caption_entities"]
        == ALBUM_MESSAGE["caption_entities"]
    )


# =========================================================
# TEST 12
# ALBUM GROUP ID
# =========================================================

def test_media_group_keeps_media_group_id():

    fake_request = FakeRequest(
        {
            "message": ALBUM_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ) as mock_group:

        webhook_handler.handle_webhook()

    message_passed = (
        mock_group.call_args.kwargs[
            "message"
        ]
    )

    assert (
        message_passed[
            "media_group_id"
        ]
        == "album_1"
    )


# =========================================================
# TEST 13
# ALBUM DOES NOT USE SINGLE PATH
# =========================================================

def test_album_does_not_use_single_media_processor():

    fake_request = FakeRequest(
        {
            "message": ALBUM_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single:

        webhook_handler.handle_webhook()

    mock_single.assert_not_called()


# =========================================================
# TEST 14
# SINGLE PHOTO WEBHOOK
# =========================================================

def test_single_photo_webhook_path():

    fake_request = FakeRequest(
        {
            "message": PHOTO_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single:

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    kwargs = (
        mock_single.call_args.kwargs
    )

    assert (
        kwargs["media_type"]
        == "photo"
    )

    assert (
        kwargs["file_id"]
        == "large"
    )


# =========================================================
# TEST 15
# SINGLE VIDEO WEBHOOK
# =========================================================

def test_single_video_webhook_path():

    fake_request = FakeRequest(
        {
            "message": VIDEO_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single:

        webhook_handler.handle_webhook()

    kwargs = (
        mock_single.call_args.kwargs
    )

    assert (
        kwargs["media_type"]
        == "video"
    )


# =========================================================
# TEST 16
# DOCUMENT LEGACY PATH
# =========================================================

def test_document_uses_legacy_path():

    message = {
        "chat": {
            "id": 1001
        },
        "document": {
            "file_id": "doc_1"
        },
        "caption": "DOC"
    }

    fake_request = FakeRequest(
        {
            "message": message
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_legacy_single_media",
        return_value=True
    ) as mock_legacy:

        webhook_handler.handle_webhook()

    mock_legacy.assert_called_once()


# =========================================================
# TEST 17
# TEXT WEBHOOK
# =========================================================

def test_text_webhook_path():

    fake_request = FakeRequest(
        {
            "message": TEXT_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_text_message",
        return_value=True
    ) as mock_text:

        webhook_handler.handle_webhook()

    mock_text.assert_called_once_with(
        chat_id=1001,
        text="خبر متنی",
        entities=[]
    )


# =========================================================
# TEST 18
# INVALID TOKEN
# =========================================================

def test_invalid_secret_token_rejected():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=False
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 403

    assert result == {
        "ok": False
    }


# =========================================================
# TEST 19
# MISSING TENANT
# =========================================================

def test_missing_tenant_stops_processing():

    fake_database.get_tenant.return_value = (
        None
    )

    fake_request = FakeRequest(
        {
            "message": PHOTO_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status:

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    mock_status.assert_called_once()


# =========================================================
# TEST 20
# COMMAND
# =========================================================

def test_command_path():

    command_message = {
        "chat": {
            "id": 1001
        },
        "text": "/start"
    }

    fake_request = FakeRequest(
        {
            "message": command_message
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    fake_command_handler.handle_command.assert_called_once_with(
        "/start",
        1001
    )


# =========================================================
# TEST 21
# ALBUM STATUS
# =========================================================

def test_album_status_message_sent():

    fake_request = FakeRequest(
        {
            "message": ALBUM_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status:

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "✅ آلبوم شما در حال پردازش است..."
    )


# =========================================================
# TEST 22
# SINGLE PHOTO STATUS
# =========================================================

def test_single_photo_success_status():

    fake_request = FakeRequest(
        {
            "message": PHOTO_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status:

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "✅ خبر تصویری/ویدیویی شما "
        "در کانال منتشر شد."
    )


# =========================================================
# TEST 23
# ALBUM FAILURE STATUS
# =========================================================

def test_album_failure_status():

    fake_request = FakeRequest(
        {
            "message": ALBUM_MESSAGE
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=False
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status:

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "❌ خطا در پردازش آلبوم"
    )


# =========================================================
# TEST 24
# SINGLE CAPTION ENTITIES FORWARDED
# =========================================================

def test_single_media_caption_entities_forwarded():

    message = dict(
        PHOTO_MESSAGE
    )

    message[
        "caption_entities"
    ] = [
        {
            "type": "expandable_blockquote",
            "offset": 2,
            "length": 4
        }
    ]

    fake_request = FakeRequest(
        {
            "message": message
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single:

        webhook_handler.handle_webhook()

    kwargs = (
        mock_single.call_args.kwargs
    )

    assert (
        kwargs[
            "caption_entities"
        ]
        == message[
            "caption_entities"
        ]
    )


# =========================================================
# TEST 25
# FORWARD ORIGIN EXTRACTS CHANNEL SOURCE
# =========================================================

def test_forward_origin_extracts_channel_source():

    message = {
        "forward_origin": {
            "type": "channel",
            "chat": {
                "id": -1001234567890,
                "title": "کانال آزمایشی",
                "username": "test_source_channel"
            },
            "message_id": 555
        }
    }

    result = (
        webhook_handler
        .extract_forward_source_metadata(
            message
        )
    )

    assert (
        result[
            "is_forwarded"
        ]
        is True
    )

    assert (
        result[
            "origin_type"
        ]
        == "channel"
    )

    assert (
        result[
            "source_chat_id"
        ]
        == -1001234567890
    )

    assert (
        result[
            "source_title"
        ]
        == "کانال آزمایشی"
    )

    assert (
        result[
            "source_username"
        ]
        == "test_source_channel"
    )

    assert (
        result[
            "source_message_id"
        ]
        == 555
    )


# =========================================================
# TEST 26
# SINGLE FORWARD PASSES SOURCE
# =========================================================

def test_single_forward_passes_source_metadata():

    message = dict(
        PHOTO_MESSAGE
    )

    message[
        "forward_origin"
    ] = {
        "type": "channel",
        "chat": {
            "id": -100999,
            "title": "منبع خبر",
            "username": "news_source"
        },
        "message_id": 77
    }

    fake_request = FakeRequest(
        {
            "message": message
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single:

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result == {
        "ok": True
    }

    kwargs = (
        mock_single.call_args.kwargs
    )

    assert (
        kwargs[
            "forward_source"
        ][
            "source_title"
        ]
        == "منبع خبر"
    )

    assert (
        kwargs[
            "forward_source"
        ][
            "source_username"
        ]
        == "news_source"
    )


# =========================================================
# TEST 27
# FORMAT WITH SOURCE
# =========================================================

def test_format_with_source_passes_dynamic_source():

    source = {
        "is_forwarded": True,
        "source_title": "رسانه نمونه",
        "source_username": "sample_media"
    }

    with patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ) as mock_format:

        result = (
            webhook_handler
            .format_with_source(
                "RAW NEWS",
                source
            )
        )

    assert (
        result
        == "FORMATTED"
    )

    mock_format.assert_called_once_with(
        "RAW NEWS",
        source_title="رسانه نمونه",
        source_username="sample_media"
    )


# =========================================================
# TEST 28
# NO DUPLICATE BLUE BULLET
# =========================================================

def test_formatter_does_not_duplicate_blue_bullet():

    from core.formatter import (
        format_news
    )

    raw_text = (
        "تیتر خبر\n\n"
        "🔹 متن اول خبر\n"
        "🔹 متن دوم خبر"
    )

    result = (
        format_news(
            raw_text
        )
    )

    assert (
        "🔹 🔹"
        not in result
    )

    assert (
        result.count(
            "🔹"
        )
        == 2
    )


# =========================================================
# TEST 29
# REMOVE DYNAMIC SOURCE SIGNATURE
# =========================================================

def test_formatter_removes_dynamic_source_signature():

    from core.formatter import (
        format_news
    )

    raw_text = (
        "تیتر خبر\n\n"
        "متن اصلی خبر.\n\n"
        "کانال خبر آزمایشی\n"
        "🆔 @test_news_channel"
    )

    result = (
        format_news(
            raw_text,
            source_title="خبر آزمایشی",
            source_username="test_news_channel"
        )
    )

    assert (
        "کانال خبر آزمایشی"
        not in result
    )

    assert (
        "@test_news_channel"
        not in result
    )

    assert (
        "متن اصلی خبر"
        in result
    )


# =========================================================
# TEST 30
# DONYA24 ICON POLICY
# =========================================================

def test_formatter_keeps_only_donya24_format_icons():

    from core.formatter import (
        format_news
    )

    raw_text = (
        "تیتر خبر\n\n"
        "🇮🇷 این ایموجی متعلق به متن منبع است.\n"
        "برای اطلاعات بیشتر "
        "@another_account را ببینید.\n\n"
        "منبع نمونه\n"
        "🆔 @source_account"
    )

    result = (
        format_news(
            raw_text,
            source_title="منبع نمونه",
            source_username="source_account"
        )
    )

    assert (
        "🇮🇷"
        not in result
    )

    assert (
        "🆔"
        not in result
    )

    assert (
        "@another_account"
        not in result
    )

    assert (
        "@source_account"
        not in result
    )

    assert (
        "منبع نمونه"
        not in result
    )

    assert (
        "این ایموجی متعلق به متن منبع است"
        in result
    )

    assert (
        "برای اطلاعات بیشتر"
        in result
    )

    assert (
        "❇️"
        in result
    )

    assert (
        "🔹"
        in result
    )

    assert (
        "🔹 🔹"
        not in result
    )


# =========================================================
# TEST 31
# ALBUM PASSES FORWARD SOURCE
# =========================================================

def test_album_passes_forward_source_metadata():

    message = dict(
        ALBUM_MESSAGE
    )

    message[
        "forward_origin"
    ] = {
        "type": "channel",
        "chat": {
            "id": -100888,
            "title": "کانال آلبوم",
            "username": "album_source"
        },
        "message_id": 333
    }

    fake_request = FakeRequest(
        {
            "message": message
        }
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ) as mock_group:

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result == {
        "ok": True
    }

    passed_message = (
        mock_group
        .call_args
        .kwargs[
            "message"
        ]
    )

    assert (
        "_forward_source"
        in passed_message
    )

    assert (
        passed_message[
            "_forward_source"
        ][
            "source_title"
        ]
        == "کانال آلبوم"
    )

    assert (
        passed_message[
            "_forward_source"
        ][
            "source_username"
        ]
        == "album_source"
    )


# =========================================================
# TEST 32
# TEXT MESSAGE PRESERVES DONYA24 BRANDING
# =========================================================

def test_text_message_preserves_own_branding():

    raw_text = (
        "تیتر خبر\n\n"
        "متن اصلی خبر."
    )

    forward_source = {
        "is_forwarded": True,
        "origin_type": "channel",
        "source_chat_id": -1003455586070,
        "source_title": "فردای نو",
        "source_username": "farda_no",
        "source_message_id": 896
    }

    expected_formatted = (
        "❇️ تیتر خبر\n\n"
        "🔹 متن اصلی خبر."
    )

    expected_branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    # =====================================================
    # FAKE BALE FORWARDER
    # =====================================================

    fake_bale_forwarder = types.ModuleType(
        "core.bale_forwarder"
    )

    fake_bale_forwarder.send_to_bale_for_user = (
        MagicMock(
            return_value=True
        )
    )

    old_bale_module = sys.modules.get(
        "core.bale_forwarder"
    )

    sys.modules[
        "core.bale_forwarder"
    ] = fake_bale_forwarder

    try:

        with patch.object(
            webhook_handler,
            "format_with_source",
            return_value=expected_formatted
        ) as mock_format, patch.object(
            webhook_handler,
            "build_branding_for_user",
            return_value=expected_branding
        ) as mock_branding, patch.object(
            webhook_handler,
            "send_to_channel",
            return_value=True
        ) as mock_telegram:

            success = (
                webhook_handler
                .process_text_message(
                    chat_id=1001,
                    text=raw_text,
                    entities=[],
                    forward_source=(
                        forward_source
                    )
                )
            )

        # =================================================
        # OPERATION SUCCESS
        # =================================================

        assert success is True

        # =================================================
        # SOURCE-AWARE FORMATTER
        # =================================================

        mock_format.assert_called_once_with(
            raw_text,
            forward_source
        )

        # =================================================
        # BRANDING LOADED
        # =================================================

        mock_branding.assert_called_once_with(
            1001
        )

        # =================================================
        # TELEGRAM
        # =================================================

        mock_telegram.assert_called_once()

        telegram_text = (
            mock_telegram
            .call_args
            .args[0]
        )

        assert (
            "❇️ تیتر خبر"
            in telegram_text
        )

        assert (
            "🔹 متن اصلی خبر."
            in telegram_text
        )

        assert (
            "#دنیا_۲۴_نیوز"
            in telegram_text
        )

        assert (
            "@Donya24News"
            in telegram_text
        )

        # =================================================
        # SOURCE BRANDING MUST NOT RETURN
        # =================================================

        assert (
            "#فردای_نو"
            not in telegram_text
        )

        assert (
            "@farda_no"
            not in telegram_text
        )

        assert (
            "فردای نو"
            not in telegram_text
        )

        # =================================================
        # DONYA24 BRANDING EXACTLY ONCE
        # =================================================

        assert (
            telegram_text.count(
                "#دنیا_۲۴_نیوز"
            )
            == 1
        )

        assert (
            telegram_text.count(
                "@Donya24News"
            )
            == 1
        )

        # =================================================
        # BALE
        # =================================================

        mock_bale = (
            fake_bale_forwarder
            .send_to_bale_for_user
        )

        mock_bale.assert_called_once()

        bale_args = (
            mock_bale
            .call_args
            .args
        )

        assert (
            bale_args[0]
            == 1001
        )

        bale_text = (
            bale_args[1]
        )

        assert (
            "#دنیا_۲۴_نیوز"
            in bale_text
        )

        assert (
            "@Donya24News"
            in bale_text
        )

        assert (
            "@farda_no"
            not in bale_text
        )

    finally:

        # =================================================
        # RESTORE ORIGINAL BALE MODULE
        # =================================================

        if old_bale_module is None:

            sys.modules.pop(
                "core.bale_forwarder",
                None
            )

        else:

            sys.modules[
                "core.bale_forwarder"
            ] = old_bale_module
