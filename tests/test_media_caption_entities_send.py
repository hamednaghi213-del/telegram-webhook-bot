from unittest.mock import Mock, patch

from core import media_handler


# =========================================================
# TEST DATA
# =========================================================

CAPTION = (
    "❇️ عنوان خبر\n\n"
    "🔹 متن اصلی خبر\n\n"
    "تحلیل تکمیلی\n\n"
    "#دنیا_۲۴_نیوز\n"
    "@Donya24News"
)

CAPTION_ENTITIES = [
    {
        "type": "expandable_blockquote",
        "offset": 28,
        "length": 13
    }
]


# =========================================================
# HELPERS
# =========================================================

class FakeResponse:

    status_code = 200
    text = '{"ok": true}'

    def __init__(
        self,
        result
    ):
        self._result = result

    def json(self):

        return {
            "ok": True,
            "result": self._result
        }


def fake_single_response():

    return FakeResponse(
        {
            "message_id": 501
        }
    )


def fake_group_response():

    return FakeResponse(
        [
            {
                "message_id": 601
            },
            {
                "message_id": 602
            }
        ]
    )


# =========================================================
# TEST 01
# SINGLE PHOTO MUST SEND CAPTION_ENTITIES
# WITHOUT PARSE_MODE
# =========================================================

def test_single_photo_sends_caption_entities_without_parse_mode():

    media_handler.API_URL = (
        "https://api.telegram.org/botTEST"
    )

    media_handler.CHANNEL_ID = (
        "-1001234567890"
    )

    captured = {}

    def fake_post(
        endpoint,
        payload
    ):

        captured[
            "endpoint"
        ] = endpoint

        captured[
            "payload"
        ] = payload

        return fake_single_response()

    with patch.object(
        media_handler,
        "telegram_post",
        side_effect=fake_post
    ):

        success = (
            media_handler
            .send_single_media_to_channel(
                file_id="PHOTO_FILE_ID",
                media_type="photo",
                caption=CAPTION,
                parse_mode="HTML",
                caption_entities=(
                    CAPTION_ENTITIES
                )
            )
        )

    assert success is True

    assert (
        captured[
            "endpoint"
        ]
        == "sendPhoto"
    )

    payload = (
        captured[
            "payload"
        ]
    )

    assert (
        payload[
            "caption"
        ]
        == CAPTION
    )

    assert (
        payload[
            "caption_entities"
        ]
        == CAPTION_ENTITIES
    )

    assert (
        "parse_mode"
        not in payload
    )


# =========================================================
# TEST 02
# SINGLE VIDEO MUST SEND CAPTION_ENTITIES
# WITHOUT PARSE_MODE
# =========================================================

def test_single_video_sends_caption_entities_without_parse_mode():

    media_handler.API_URL = (
        "https://api.telegram.org/botTEST"
    )

    media_handler.CHANNEL_ID = (
        "-1001234567890"
    )

    captured = {}

    def fake_post(
        endpoint,
        payload
    ):

        captured[
            "endpoint"
        ] = endpoint

        captured[
            "payload"
        ] = payload

        return fake_single_response()

    with patch.object(
        media_handler,
        "telegram_post",
        side_effect=fake_post
    ):

        success = (
            media_handler
            .send_single_media_to_channel(
                file_id="VIDEO_FILE_ID",
                media_type="video",
                caption=CAPTION,
                parse_mode="HTML",
                caption_entities=(
                    CAPTION_ENTITIES
                )
            )
        )

    assert success is True

    assert (
        captured[
            "endpoint"
        ]
        == "sendVideo"
    )

    payload = (
        captured[
            "payload"
        ]
    )

    assert (
        payload[
            "caption"
        ]
        == CAPTION
    )

    assert (
        payload[
            "caption_entities"
        ]
        == CAPTION_ENTITIES
    )

    assert (
        "parse_mode"
        not in payload
    )


# =========================================================
# TEST 03
# MEDIA GROUP MUST PUT ENTITIES ONLY
# ON FIRST ITEM
# =========================================================

def test_media_group_sends_caption_entities_on_first_item_only():

    media_handler.API_URL = (
        "https://api.telegram.org/botTEST"
    )

    media_handler.CHANNEL_ID = (
        "-1001234567890"
    )

    captured = {}

    def fake_post(
        endpoint,
        payload
    ):

        captured[
            "endpoint"
        ] = endpoint

        captured[
            "payload"
        ] = payload

        return fake_group_response()

    files = [
        {
            "type": "photo",
            "file_id": "PHOTO_1"
        },
        {
            "type": "photo",
            "file_id": "PHOTO_2"
        }
    ]

    with patch.object(
        media_handler,
        "telegram_post",
        side_effect=fake_post
    ):

        success = (
            media_handler
            .send_media_group_to_channel(
                files=files,
                caption=CAPTION,
                parse_mode="HTML",
                caption_entities=(
                    CAPTION_ENTITIES
                )
            )
        )

    assert success is True

    assert (
        captured[
            "endpoint"
        ]
        == "sendMediaGroup"
    )

    payload = (
        captured[
            "payload"
        ]
    )

    media = (
        payload[
            "media"
        ]
    )

    assert (
        len(media)
        == 2
    )

    first = media[0]
    second = media[1]

    assert (
        first[
            "caption"
        ]
        == CAPTION
    )

    assert (
        first[
            "caption_entities"
        ]
        == CAPTION_ENTITIES
    )

    assert (
        "parse_mode"
        not in first
    )

    assert (
        "caption"
        not in second
    )

    assert (
        "caption_entities"
        not in second
    )

    assert (
        "parse_mode"
        not in second
    )


# =========================================================
# TEST 04
# EXECUTE PLAN SINGLE MEDIA
# MUST FORWARD ENTITY LIST
# =========================================================

def test_execute_telegram_plan_forwards_entities_to_single_media():

    files = [
        {
            "type": "photo",
            "file_id": "PHOTO_FILE_ID"
        }
    ]

    plan = {
        "media_caption": CAPTION,
        "media_parse_mode": None,
        "media_caption_entities": (
            CAPTION_ENTITIES
        ),
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_single_media_to_channel",
        return_value=True
    ) as mocked_send:

        success = (
            media_handler
            .execute_telegram_plan(
                files,
                plan
            )
        )

    assert success is True

    mocked_send.assert_called_once_with(
        "PHOTO_FILE_ID",
        "photo",
        CAPTION,
        caption_entities=(
            CAPTION_ENTITIES
        )
    )


def test_send_single_document_uses_telegram_document_endpoint():

    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {"message_id": 123}
    }

    with patch.object(
        media_handler,
        "telegram_post",
        return_value=response
    ) as mocked_post:

        success = media_handler.send_single_media_to_channel(
            "DOCUMENT_FILE_ID",
            "document",
            CAPTION
        )

    assert success is True
    mocked_post.assert_called_once_with(
        "sendDocument",
        {
            "chat_id": media_handler.CHANNEL_ID,
            "document": "DOCUMENT_FILE_ID",
            "caption": CAPTION
        }
    )


# =========================================================
# TEST 05
# EXECUTE PLAN MEDIA GROUP
# MUST FORWARD ENTITY LIST
# =========================================================

def test_execute_telegram_plan_forwards_entities_to_media_group():

    files = [
        {
            "type": "photo",
            "file_id": "PHOTO_1"
        },
        {
            "type": "video",
            "file_id": "VIDEO_1"
        }
    ]

    plan = {
        "media_caption": CAPTION,
        "media_parse_mode": None,
        "media_caption_entities": (
            CAPTION_ENTITIES
        ),
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=True
    ) as mocked_send:

        success = (
            media_handler
            .execute_telegram_plan(
                files,
                plan
            )
        )

    assert success is True

    mocked_send.assert_called_once_with(
        files,
        CAPTION,
        caption_entities=(
            CAPTION_ENTITIES
        )
    )


# =========================================================
# TEST 06
# OLD HTML PATH MUST STILL WORK
# =========================================================

def test_old_html_path_still_uses_parse_mode_when_no_entities():

    files = [
        {
            "type": "photo",
            "file_id": "PHOTO_FILE_ID"
        }
    ]

    plan = {
        "media_caption": (
            "<blockquote expandable>"
            "متن"
            "</blockquote>"
        ),
        "media_parse_mode": "HTML",
        "media_caption_entities": [],
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_single_media_to_channel",
        return_value=True
    ) as mocked_send:

        success = (
            media_handler
            .execute_telegram_plan(
                files,
                plan
            )
        )

    assert success is True

    mocked_send.assert_called_once_with(
        "PHOTO_FILE_ID",
        "photo",
        (
            "<blockquote expandable>"
            "متن"
            "</blockquote>"
        ),
        parse_mode="HTML"
    )


# =========================================================
# TEST 07
# NORMAL OLD PATH MUST REMAIN UNCHANGED
# =========================================================

def test_normal_media_path_without_entities_or_parse_mode():

    files = [
        {
            "type": "photo",
            "file_id": "PHOTO_FILE_ID"
        }
    ]

    plan = {
        "media_caption": (
            "❇️ خبر\n\n"
            "#دنیا_۲۴_نیوز\n"
            "@Donya24News"
        ),
        "media_parse_mode": None,
        "media_caption_entities": [],
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_single_media_to_channel",
        return_value=True
    ) as mocked_send:

        success = (
            media_handler
            .execute_telegram_plan(
                files,
                plan
            )
        )

    assert success is True

    mocked_send.assert_called_once_with(
        "PHOTO_FILE_ID",
        "photo",
        (
            "❇️ خبر\n\n"
            "#دنیا_۲۴_نیوز\n"
            "@Donya24News"
        )
    )
