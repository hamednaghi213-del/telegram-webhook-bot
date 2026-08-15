import sys
import types

from unittest.mock import (
    patch,
    MagicMock
)


# =========================================================
# FAKE DATABASE
# =========================================================
#
# database.py در زمان import به SUPABASE_URL و
# SUPABASE_KEY نیاز دارد.
#
# در Unit/Integration Test نیازی به اتصال واقعی
# به Supabase نداریم.
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
#
# نکته مهم:
#
# flask.request یک LocalProxy است.
#
# Patch کردن:
#
# webhook_handler.request.get_json
#
# بدون Flask Request Context باعث خطای:
#
# Working outside of request context
#
# می‌شود.
#
# بنابراین خود request را با این Object ساده
# جایگزین می‌کنیم.
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

    "media_group_id": (
        "album_1"
    ),

    "photo": [
        {
            "file_id": (
                "photo_small"
            )
        },
        {
            "file_id": (
                "photo_large"
            )
        }
    ],

    "caption": "کپشن آلبوم",

    "caption_entities": [
        {
            "type": (
                "expandable_blockquote"
            ),
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
# TEST SETUP
# =========================================================

def setup_function():
    """
    Reset fake modules before every test.
    """

    fake_database.get_tenant.reset_mock()

    fake_database.get_tenant.return_value = {
        "telegram_channel": "@channel"
    }

    fake_command_handler.handle_command.reset_mock()


# =========================================================
# TEST 01
# MESSAGE TEXT PREFERS CAPTION
# =========================================================

def test_get_message_text_prefers_caption():

    message = {

        "caption": "CAPTION",

        "text": "TEXT"
    }

    result = (
        webhook_handler
        .get_message_text(
            message
        )
    )

    assert (
        result
        == "CAPTION"
    )


# =========================================================
# TEST 02
# MESSAGE TEXT
# =========================================================

def test_get_message_text_uses_text():

    message = {
        "text": "TEXT"
    }

    result = (
        webhook_handler
        .get_message_text(
            message
        )
    )

    assert (
        result
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

    message = {

        "caption": "CAPTION",

        "caption_entities": (
            entities
        )
    }

    result = (
        webhook_handler
        .get_message_entities(
            message
        )
    )

    assert (
        result
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

    message = {

        "text": "TEXT",

        "entities": entities
    }

    result = (
        webhook_handler
        .get_message_entities(
            message
        )
    )

    assert (
        result
        == entities
    )


# =========================================================
# TEST 05
# PHOTO HIGHEST QUALITY
# =========================================================

def test_get_media_from_photo_uses_last_file_id():

    media = (
        webhook_handler
        .get_media_from_message(
            PHOTO_MESSAGE
        )
    )

    assert (
        media[
            "type"
        ]
        == "photo"
    )

    assert (
        media[
            "file_id"
        ]
        == "large"
    )

    assert (
        media[
            "caption"
        ]
        == "خبر تصویری"
    )


# =========================================================
# TEST 06
# VIDEO EXTRACTION
# =========================================================

def test_get_media_from_video():

    media = (
        webhook_handler
        .get_media_from_message(
            VIDEO_MESSAGE
        )
    )

    assert (
        media[
            "type"
        ]
        == "video"
    )

    assert (
        media[
            "file_id"
        ]
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
        "core.content_entities."
        "parse_telegram_entities",
        return_value=parsed
    ) as mock_parse, patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ) as mock_format, patch(
        "core.caption_manager."
        "analyze_content",
        return_value=plan
    ) as mock_analyze, patch(
        "core.media_handler."
        "execute_telegram_plan",
        return_value=True
    ) as mock_telegram, patch(
        "core.media_handler."
        "execute_bale_plan",
        return_value=True
    ) as mock_bale, patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value="#TAG\n@CHANNEL"
    ):

        success = (
            webhook_handler
            .process_single_photo_video(
                chat_id=1001,
                file_id="photo_1",
                media_type="photo",
                caption="RAW",
                caption_entities=[
                    {
                        "type": (
                            "blockquote"
                        ),
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

    mock_telegram.assert_called_once()

    mock_bale.assert_called_once()


# =========================================================
# TEST 08
# SINGLE VIDEO ENTITY PIPELINE
# =========================================================

def test_single_video_uses_entity_pipeline():

    parsed = {

        "main_text": (
            "VIDEO MAIN"
        ),

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
        "core.content_entities."
        "parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value=(
            "FORMATTED VIDEO"
        )
    ), patch(
        "core.caption_manager."
        "analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler."
        "execute_telegram_plan",
        return_value=True
    ) as mock_telegram, patch(
        "core.media_handler."
        "execute_bale_plan",
        return_value=True
    ), patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler
            .process_single_photo_video(
                chat_id=1001,
                file_id="video_1",
                media_type="video",
                caption="RAW",
                caption_entities=[]
            )
        )

    assert success is True

    files = (
        mock_telegram
        .call_args
        .args[0]
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
        "core.content_entities."
        "parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ), patch(
        "core.caption_manager."
        "analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler."
        "execute_telegram_plan",
        return_value=False
    ), patch(
        "core.media_handler."
        "execute_bale_plan",
        return_value=True
    ) as mock_bale, patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler
            .process_single_photo_video(
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
# BALE FAILURE DOES NOT FAIL TELEGRAM
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
        "core.content_entities."
        "parse_telegram_entities",
        return_value=parsed
    ), patch(
        "core.formatter.format_news",
        return_value="FORMATTED"
    ), patch(
        "core.caption_manager."
        "analyze_content",
        return_value=plan
    ), patch(
        "core.media_handler."
        "execute_telegram_plan",
        return_value=True
    ), patch(
        "core.media_handler."
        "execute_bale_plan",
        return_value=False
    ), patch.object(
        webhook_handler,
        "build_branding_for_user",
        return_value=""
    ):

        success = (
            webhook_handler
            .process_single_photo_video(
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
        "core.media_handler."
        "handle_media_group_message",
        return_value=True
    ) as mock_group:

        result, status = (
            webhook_handler
            .handle_webhook()
        )

    assert status == 200

    assert result == {
        "ok": True
    }

    mock_group.assert_called_once()

    kwargs = (
        mock_group
        .call_args
        .kwargs
    )

    assert (
        kwargs[
            "caption_entities"
        ]
        == ALBUM_MESSAGE[
            "caption_entities"
        ]
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
        "core.media_handler."
        "handle_media_group_message",
        return_value=True
    ) as mock_group:

        webhook_handler.handle_webhook()

    message_passed = (
        mock_group
        .call_args
        .kwargs[
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
# ALBUM NEVER USES SINGLE PROCESSOR
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
        "core.media_handler."
        "handle_media_group_message",
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
            webhook_handler
            .handle_webhook()
        )

    assert status == 200

    mock_single.assert_called_once()

    kwargs = (
        mock_single
        .call_args
        .kwargs
    )

    assert (
        kwargs[
            "media_type"
        ]
        == "photo"
    )

    assert (
        kwargs[
            "file_id"
        ]
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
        mock_single
        .call_args
        .kwargs
    )

    assert (
        kwargs[
            "media_type"
        ]
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
            webhook_handler
            .handle_webhook()
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
            webhook_handler
            .handle_webhook()
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
            "message": (
                command_message
            )
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
            webhook_handler
            .handle_webhook()
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
        "core.media_handler."
        "handle_media_group_message",
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
        "core.media_handler."
        "handle_media_group_message",
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
            "type": (
                "expandable_blockquote"
            ),
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
        mock_single
        .call_args
        .kwargs
    )

    assert (
        kwargs[
            "caption_entities"
        ]
        == message[
            "caption_entities"
        ]
    )
