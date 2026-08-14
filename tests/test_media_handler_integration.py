from unittest.mock import patch

from core.caption_manager import PublicationPlan
from core import media_handler


# =========================================================
# HELPERS
# =========================================================

SAMPLE_FILES = [
    {
        "type": "photo",
        "file_id": "photo_1"
    },
    {
        "type": "video",
        "file_id": "video_1"
    }
]


def build_plan(
    telegram_caption="TG CAPTION",
    telegram_followups=None,
    telegram_blockquotes=None,
    telegram_fallback=False,
    bale_caption="BALE CAPTION",
    bale_followups=None,
    bale_blockquotes=None,
    bale_fallback=False
):
    """
    ساخت PublicationPlan تستی.
    """

    plan = PublicationPlan()

    plan.telegram = {
        "media_caption": telegram_caption,
        "followup_messages": list(
            telegram_followups or []
        ),
        "blockquote_messages": list(
            telegram_blockquotes or []
        ),
        "document_fallback": telegram_fallback
    }

    plan.bale = {
        "media_caption": bale_caption,
        "followup_messages": list(
            bale_followups or []
        ),
        "blockquote_messages": list(
            bale_blockquotes or []
        ),
        "document_fallback": bale_fallback
    }

    return plan


# =========================================================
# TEST 01
# TELEGRAM MEDIA GROUP USES PLAN CAPTION
# =========================================================

def test_execute_telegram_plan_uses_media_caption():

    plan = {
        "media_caption": "CAPTION FROM PLAN",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=True
    ) as mock_send_group:

        success = media_handler.execute_telegram_plan(
            SAMPLE_FILES,
            plan
        )

    assert success is True

    mock_send_group.assert_called_once_with(
        SAMPLE_FILES,
        "CAPTION FROM PLAN"
    )


# =========================================================
# TEST 02
# TELEGRAM FOLLOWUPS ARE EXECUTED
# =========================================================

def test_execute_telegram_plan_sends_followups():

    plan = {
        "media_caption": "CAPTION",
        "followup_messages": [
            "FOLLOWUP 1",
            "FOLLOWUP 2"
        ],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=True
    ), patch.object(
        media_handler,
        "send_text_to_channel",
        return_value=True
    ) as mock_text:

        success = media_handler.execute_telegram_plan(
            SAMPLE_FILES,
            plan
        )

    assert success is True

    assert mock_text.call_count == 2

    assert (
        mock_text.call_args_list[0].args[0]
        == "FOLLOWUP 1"
    )

    assert (
        mock_text.call_args_list[1].args[0]
        == "FOLLOWUP 2"
    )


# =========================================================
# TEST 03
# TELEGRAM BLOCKQUOTE USES HTML MODE
# =========================================================

def test_execute_telegram_plan_sends_blockquote_as_html():

    plan = {
        "media_caption": "CAPTION",
        "followup_messages": [],
        "blockquote_messages": [
            "<blockquote>TEXT</blockquote>"
        ],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=True
    ), patch.object(
        media_handler,
        "send_text_to_channel",
        return_value=True
    ) as mock_text:

        success = media_handler.execute_telegram_plan(
            SAMPLE_FILES,
            plan
        )

    assert success is True

    mock_text.assert_called_once_with(
        "<blockquote>TEXT</blockquote>",
        parse_mode="HTML"
    )


# =========================================================
# TEST 04
# TELEGRAM MEDIA FAILURE STOPS PLAN
# =========================================================

def test_execute_telegram_plan_stops_if_media_fails():

    plan = {
        "media_caption": "CAPTION",
        "followup_messages": [
            "SHOULD NOT SEND"
        ],
        "blockquote_messages": [
            "<blockquote>NO</blockquote>"
        ],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=False
    ), patch.object(
        media_handler,
        "send_text_to_channel",
        return_value=True
    ) as mock_text:

        success = media_handler.execute_telegram_plan(
            SAMPLE_FILES,
            plan
        )

    assert success is False

    mock_text.assert_not_called()


# =========================================================
# TEST 05
# TELEGRAM DOCUMENT FALLBACK ABORTS
# =========================================================

def test_execute_telegram_plan_aborts_on_document_fallback():

    plan = {
        "media_caption": "",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": True
    }

    with patch.object(
        media_handler,
        "send_media_group_to_channel",
        return_value=True
    ) as mock_send:

        success = media_handler.execute_telegram_plan(
            SAMPLE_FILES,
            plan
        )

    assert success is False

    mock_send.assert_not_called()


# =========================================================
# TEST 06
# SINGLE MEDIA PATH
# =========================================================

def test_execute_telegram_plan_single_media_path():

    files = [
        {
            "type": "photo",
            "file_id": "photo_1"
        }
    ]

    plan = {
        "media_caption": "SINGLE CAPTION",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_single_media_to_channel",
        return_value=True
    ) as mock_single:

        success = media_handler.execute_telegram_plan(
            files,
            plan
        )

    assert success is True

    mock_single.assert_called_once_with(
        "photo_1",
        "photo",
        "SINGLE CAPTION"
    )


# =========================================================
# TEST 07
# BALE PLAN USES BALE CAPTION
# =========================================================

def test_execute_bale_plan_uses_bale_caption():

    plan = {
        "media_caption": "BALE CAPTION",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_album_to_bale",
        return_value=True
    ) as mock_album:

        success = media_handler.execute_bale_plan(
            12345,
            SAMPLE_FILES,
            plan
        )

    assert success is True

    mock_album.assert_called_once_with(
        12345,
        SAMPLE_FILES,
        "BALE CAPTION"
    )


# =========================================================
# TEST 08
# BALE FOLLOWUPS AND BLOCKQUOTES
# =========================================================

def test_execute_bale_plan_sends_followups_and_blockquotes():

    plan = {
        "media_caption": "BALE",
        "followup_messages": [
            "CONTINUE"
        ],
        "blockquote_messages": [
            "▌ QUOTE"
        ],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_album_to_bale",
        return_value=True
    ), patch.object(
        media_handler,
        "send_text_to_bale",
        return_value=True
    ) as mock_text:

        success = media_handler.execute_bale_plan(
            12345,
            SAMPLE_FILES,
            plan
        )

    assert success is True

    assert mock_text.call_count == 2

    assert (
        mock_text.call_args_list[0].args
        == (
            12345,
            "CONTINUE"
        )
    )

    assert (
        mock_text.call_args_list[1].args
        == (
            12345,
            "▌ QUOTE"
        )
    )


# =========================================================
# TEST 09
# BALE MEDIA FAILURE STOPS FOLLOWUPS
# =========================================================

def test_execute_bale_plan_stops_if_media_fails():

    plan = {
        "media_caption": "BALE",
        "followup_messages": [
            "NO SEND"
        ],
        "blockquote_messages": [
            "NO SEND"
        ],
        "document_fallback": False
    }

    with patch.object(
        media_handler,
        "send_album_to_bale",
        return_value=False
    ), patch.object(
        media_handler,
        "send_text_to_bale",
        return_value=True
    ) as mock_text:

        success = media_handler.execute_bale_plan(
            12345,
            SAMPLE_FILES,
            plan
        )

    assert success is False

    mock_text.assert_not_called()


# =========================================================
# TEST 10
# BALE DOCUMENT FALLBACK ABORTS
# =========================================================

def test_execute_bale_plan_aborts_on_document_fallback():

    plan = {
        "media_caption": "",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": True
    }

    with patch.object(
        media_handler,
        "send_album_to_bale",
        return_value=True
    ) as mock_album:

        success = media_handler.execute_bale_plan(
            12345,
            SAMPLE_FILES,
            plan
        )

    assert success is False

    mock_album.assert_not_called()


# =========================================================
# TEST 11
# ADD GROUP PARSES ENTITIES
# =========================================================

def test_add_to_pending_group_parses_entities():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    message_group_id = "group_parse"
    chat_id = 100

    parsed_result = {
        "main_text": "MAIN",
        "blockquote_blocks": [
            {
                "text": "BQ",
                "offset": 20
            }
        ],
        "expandable_blocks": [
            {
                "text": "EXP",
                "offset": 30
            }
        ],
        "other_entities": [
            {
                "type": "bold",
                "text": "BOLD"
            }
        ]
    }

    with patch.object(
        media_handler,
        "parse_telegram_entities",
        return_value=parsed_result
    ) as mock_parser:

        media_handler.add_to_pending_group(
            media_group_id=message_group_id,
            chat_id=chat_id,
            file_id="photo_a",
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

    group = media_handler.pending_groups[
        (
            chat_id,
            message_group_id
        )
    ]

    mock_parser.assert_called_once()

    assert group["main_text"] == "MAIN"

    assert (
        len(
            group[
                "blockquote_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            group[
                "expandable_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            group[
                "other_entities"
            ]
        )
        == 1
    )


# =========================================================
# TEST 12
# FIRST CAPTION WINS
# =========================================================

def test_first_caption_is_not_overwritten():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_caption"
    chat_id = 101

    with patch.object(
        media_handler,
        "parse_telegram_entities",
        return_value={
            "main_text": "FIRST",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    ):

        media_handler.add_to_pending_group(
            group_id,
            chat_id,
            "file_1",
            "photo",
            "FIRST RAW",
            []
        )

    with patch.object(
        media_handler,
        "parse_telegram_entities",
        return_value={
            "main_text": "SECOND",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    ):

        media_handler.add_to_pending_group(
            group_id,
            chat_id,
            "file_2",
            "photo",
            "SECOND RAW",
            []
        )

    group = media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ]

    assert group[
        "main_text"
    ] == "FIRST"

    assert group[
        "raw_caption"
    ] == "FIRST RAW"


# =========================================================
# TEST 13
# DUPLICATE MEDIA IGNORED
# =========================================================

def test_duplicate_media_is_ignored():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_duplicate"
    chat_id = 102

    media_handler.add_to_pending_group(
        group_id,
        chat_id,
        "same_file",
        "photo"
    )

    media_handler.add_to_pending_group(
        group_id,
        chat_id,
        "same_file",
        "photo"
    )

    group = media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ]

    assert (
        len(
            group[
                "files"
            ]
        )
        == 1
    )


# =========================================================
# TEST 14
# OVER 10 MEDIA FAILS SAFELY
# =========================================================

def test_media_group_over_ten_items_fails_without_slicing():

    files = [
        {
            "type": "photo",
            "file_id": f"file_{i}"
        }
        for i in range(
            11
        )
    ]

    media_handler.API_URL = (
        "https://example.invalid"
    )

    media_handler.CHANNEL_ID = (
        "@channel"
    )

    with patch.object(
        media_handler,
        "telegram_post",
        return_value=None
    ) as mock_post:

        success = (
            media_handler.send_media_group_to_channel(
                files,
                "caption"
            )
        )

    assert success is False

    mock_post.assert_not_called()


# =========================================================
# TEST 15
# MEDIA GROUP NEVER FALLS BACK
# =========================================================

def test_media_group_failure_has_no_single_media_fallback():

    media_handler.API_URL = (
        "https://example.invalid"
    )

    media_handler.CHANNEL_ID = (
        "@channel"
    )

    with patch.object(
        media_handler,
        "telegram_post",
        return_value=None
    ), patch.object(
        media_handler,
        "send_single_media_to_channel",
        return_value=True
    ) as mock_single:

        success = (
            media_handler.send_media_group_to_channel(
                SAMPLE_FILES,
                "caption"
            )
        )

    assert success is False

    mock_single.assert_not_called()


# =========================================================
# TEST 16
# PROCESS MEDIA GROUP CALLS CAPTION MANAGER
# =========================================================

def test_process_media_group_calls_analyze_content():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_process"
    chat_id = 200

    media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ] = {
        "chat_id": chat_id,
        "media_group_id": group_id,
        "files": list(
            SAMPLE_FILES
        ),
        "raw_caption": "RAW",
        "caption_entities": [],
        "main_text": "MAIN TEXT",
        "expandable_blocks": [],
        "blockquote_blocks": [],
        "other_entities": [],
        "caption_received": True,
        "last_update": 0,
        "is_processing": False
    }

    plan = build_plan()

    with patch.object(
        media_handler,
        "format_news",
        return_value="FORMATTED"
    ) as mock_formatter, patch.object(
        media_handler,
        "build_branding_for_user",
        return_value="#TAG\n@CHANNEL"
    ), patch.object(
        media_handler,
        "analyze_content",
        return_value=plan
    ) as mock_analyze, patch.object(
        media_handler,
        "execute_telegram_plan",
        return_value=True
    ), patch.object(
        media_handler,
        "execute_bale_plan",
        return_value=True
    ):

        success = (
            media_handler.process_media_group(
                group_id,
                chat_id
            )
        )

    assert success is True

    mock_formatter.assert_called_once_with(
        "MAIN TEXT"
    )

    mock_analyze.assert_called_once()

    kwargs = (
        mock_analyze
        .call_args
        .kwargs
    )

    assert (
        kwargs[
            "main_text"
        ]
        == "FORMATTED"
    )

    assert (
        kwargs[
            "branding"
        ]
        == "#TAG\n@CHANNEL"
    )


# =========================================================
# TEST 17
# TELEGRAM FAILURE PREVENTS BALE
# =========================================================

def test_process_media_group_does_not_send_bale_if_telegram_fails():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_tg_fail"
    chat_id = 201

    media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ] = {
        "chat_id": chat_id,
        "media_group_id": group_id,
        "files": list(
            SAMPLE_FILES
        ),
        "raw_caption": "",
        "caption_entities": [],
        "main_text": "MAIN",
        "expandable_blocks": [],
        "blockquote_blocks": [],
        "other_entities": [],
        "caption_received": True,
        "last_update": 0,
        "is_processing": False
    }

    plan = build_plan()

    with patch.object(
        media_handler,
        "format_news",
        return_value="FORMATTED"
    ), patch.object(
        media_handler,
        "build_branding_for_user",
        return_value=""
    ), patch.object(
        media_handler,
        "analyze_content",
        return_value=plan
    ), patch.object(
        media_handler,
        "execute_telegram_plan",
        return_value=False
    ), patch.object(
        media_handler,
        "execute_bale_plan",
        return_value=True
    ) as mock_bale:

        success = (
            media_handler.process_media_group(
                group_id,
                chat_id
            )
        )

    assert success is False

    mock_bale.assert_not_called()


# =========================================================
# TEST 18
# BALE FAILURE DOES NOT FAIL TELEGRAM RESULT
# =========================================================

def test_process_media_group_returns_true_if_bale_fails():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_bale_fail"
    chat_id = 202

    media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ] = {
        "chat_id": chat_id,
        "media_group_id": group_id,
        "files": list(
            SAMPLE_FILES
        ),
        "raw_caption": "",
        "caption_entities": [],
        "main_text": "MAIN",
        "expandable_blocks": [],
        "blockquote_blocks": [],
        "other_entities": [],
        "caption_received": True,
        "last_update": 0,
        "is_processing": False
    }

    plan = build_plan()

    with patch.object(
        media_handler,
        "format_news",
        return_value="FORMATTED"
    ), patch.object(
        media_handler,
        "build_branding_for_user",
        return_value=""
    ), patch.object(
        media_handler,
        "analyze_content",
        return_value=plan
    ), patch.object(
        media_handler,
        "execute_telegram_plan",
        return_value=True
    ), patch.object(
        media_handler,
        "execute_bale_plan",
        return_value=False
    ):

        success = (
            media_handler.process_media_group(
                group_id,
                chat_id
            )
        )

    assert success is True


# =========================================================
# TEST 19
# PROCESS GROUP CLEANUP
# =========================================================

def test_process_media_group_cleans_pending_group():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_cleanup"
    chat_id = 203

    media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ] = {
        "chat_id": chat_id,
        "media_group_id": group_id,
        "files": list(
            SAMPLE_FILES
        ),
        "raw_caption": "",
        "caption_entities": [],
        "main_text": "MAIN",
        "expandable_blocks": [],
        "blockquote_blocks": [],
        "other_entities": [],
        "caption_received": True,
        "last_update": 0,
        "is_processing": False
    }

    plan = build_plan()

    with patch.object(
        media_handler,
        "format_news",
        return_value="FORMATTED"
    ), patch.object(
        media_handler,
        "build_branding_for_user",
        return_value=""
    ), patch.object(
        media_handler,
        "analyze_content",
        return_value=plan
    ), patch.object(
        media_handler,
        "execute_telegram_plan",
        return_value=True
    ), patch.object(
        media_handler,
        "execute_bale_plan",
        return_value=True
    ):

        success = (
            media_handler.process_media_group(
                group_id,
                chat_id
            )
        )

    assert success is True

    assert (
        (
            chat_id,
            group_id
        )
        not in media_handler.pending_groups
    )


# =========================================================
# TEST 20
# ENTITY PARSER FAILURE FALLBACK
# =========================================================

def test_entity_parser_failure_falls_back_to_raw_caption():

    media_handler.pending_groups.clear()
    media_handler.group_timers.clear()

    group_id = "group_parser_fail"
    chat_id = 300

    with patch.object(
        media_handler,
        "parse_telegram_entities",
        side_effect=RuntimeError(
            "parser failed"
        )
    ):

        media_handler.add_to_pending_group(
            media_group_id=group_id,
            chat_id=chat_id,
            file_id="file",
            media_type="photo",
            caption="RAW CAPTION",
            caption_entities=[
                {
                    "type": "blockquote",
                    "offset": 0,
                    "length": 5
                }
            ]
        )

    group = media_handler.pending_groups[
        (
            chat_id,
            group_id
        )
    ]

    assert (
        group[
            "main_text"
        ]
        == "RAW CAPTION"
    )

    assert (
        group[
            "blockquote_blocks"
        ]
        == []
    )

    assert (
        group[
            "expandable_blocks"
        ]
        == []
    )


# =========================================================
# TEST 21
# HANDLE MEDIA GROUP PASSES CAPTION ENTITIES
# =========================================================

def test_handle_media_group_passes_caption_entities():

    message = {
        "media_group_id": "mg_test",
        "chat": {
            "id": 777
        },
        "caption_entities": [
            {
                "type": "expandable_blockquote",
                "offset": 10,
                "length": 20
            }
        ]
    }

    with patch.object(
        media_handler,
        "add_to_pending_group"
    ) as mock_add, patch.object(
        media_handler,
        "schedule_processing"
    ) as mock_schedule:

        success = (
            media_handler.handle_media_group_message(
                message=message,
                file_id="file_777",
                media_type="photo",
                caption="RAW"
            )
        )

    assert success is True

    mock_add.assert_called_once_with(
        "mg_test",
        777,
        "file_777",
        "photo",
        "RAW",
        message[
            "caption_entities"
        ]
    )

    mock_schedule.assert_called_once_with(
        "mg_test",
        777,
        delay=media_handler.MEDIA_GROUP_DELAY
    )
