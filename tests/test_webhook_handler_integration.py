from unittest.mock import patch

from core import webhook_handler


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
# CAPTION ENTITIES SELECTED
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
# TEXT ENTITIES SELECTED
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

    assert media["type"] == "photo"

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

    assert media["type"] == "video"

    assert (
        media["file_id"]
        == "video_1"
    )


# =========================================================
# TEST 07
# SINGLE PHOTO USES ENTITY PIPELINE
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
# SINGLE VIDEO USES ENTITY PIPELINE
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
# SINGLE TELEGRAM FAILURE STOPS BALE
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
# SINGLE BALE FAILURE DOES NOT FAIL TELEGRAM
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
# MEDIA GROUP PASSES CAPTION ENTITIES
# =========================================================

def test_media_group_passes_caption_entities():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ) as mock_group, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": ALBUM_MESSAGE
        }
    ):

        result, status = (
            webhook_handler.handle_webhook()
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
# MEDIA GROUP USES ORIGINAL GROUP ID
# =========================================================

def test_media_group_keeps_media_group_id():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ) as mock_group, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": ALBUM_MESSAGE
        }
    ):

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
# MEDIA GROUP DOES NOT USE SINGLE PROCESSOR
# =========================================================

def test_album_does_not_use_single_media_processor():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": ALBUM_MESSAGE
        }
    ):

        webhook_handler.handle_webhook()

    mock_single.assert_not_called()


# =========================================================
# TEST 14
# SINGLE PHOTO WEBHOOK PATH
# =========================================================

def test_single_photo_webhook_path():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": PHOTO_MESSAGE
        }
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    mock_single.assert_called_once()

    kwargs = (
        mock_single
        .call_args
        .kwargs
    )

    assert kwargs[
        "media_type"
    ] == "photo"

    assert kwargs[
        "file_id"
    ] == "large"


# =========================================================
# TEST 15
# SINGLE VIDEO WEBHOOK PATH
# =========================================================

def test_single_video_webhook_path():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": VIDEO_MESSAGE
        }
    ):

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
# DOCUMENT USES LEGACY PATH
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

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "process_legacy_single_media",
        return_value=True
    ) as mock_legacy, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": message
        }
    ):

        webhook_handler.handle_webhook()

    mock_legacy.assert_called_once()


# =========================================================
# TEST 17
# TEXT USES TEXT PROCESSOR
# =========================================================

def test_text_webhook_path():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "process_text_message",
        return_value=True
    ) as mock_text, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": TEXT_MESSAGE
        }
    ):

        webhook_handler.handle_webhook()

    mock_text.assert_called_once_with(
        chat_id=1001,
        text="خبر متنی",
        entities=[]
    )


# =========================================================
# TEST 18
# INVALID SECRET TOKEN
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

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status, patch(
        "core.database.get_tenant",
        return_value=None
    ), patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": PHOTO_MESSAGE
        }
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    mock_status.assert_called_once()


# =========================================================
# TEST 20
# COMMAND PATH
# =========================================================

def test_command_path():

    command_message = {
        "chat": {
            "id": 1001
        },
        "text": "/start"
    }

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.command_handler.handle_command"
    ) as mock_command, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": command_message
        }
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    mock_command.assert_called_once_with(
        "/start",
        1001
    )


# =========================================================
# TEST 21
# ALBUM STATUS MESSAGE
# =========================================================

def test_album_status_message_sent():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": ALBUM_MESSAGE
        }
    ):

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "✅ آلبوم شما در حال پردازش است..."
    )


# =========================================================
# TEST 22
# SINGLE PHOTO STATUS MESSAGE
# =========================================================

def test_single_photo_success_status():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": PHOTO_MESSAGE
        }
    ):

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "✅ خبر تصویری/ویدیویی شما "
        "در کانال منتشر شد."
    )


# =========================================================
# TEST 23
# ALBUM FAILURE STATUS MESSAGE
# =========================================================

def test_album_failure_status():

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch(
        "core.media_handler.handle_media_group_message",
        return_value=False
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ) as mock_status, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": ALBUM_MESSAGE
        }
    ):

        webhook_handler.handle_webhook()

    mock_status.assert_called_once_with(
        1001,
        "❌ خطا در پردازش آلبوم"
    )


# =========================================================
# TEST 24
# SINGLE MEDIA CAPTION ENTITIES FORWARDED
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

    with patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True
    ), patch(
        "core.database.get_tenant",
        return_value={
            "telegram_channel": "@channel"
        }
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ), patch.object(
        webhook_handler,
        "process_single_photo_video",
        return_value=True
    ) as mock_single, patch.object(
        webhook_handler.request,
        "get_json",
        return_value={
            "message": message
        }
    ):

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
