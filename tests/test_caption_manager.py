import pytest

from core.caption_manager import (
    PublicationPlan,
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    TELEGRAM_CAPTION_SAFE_LIMIT,
    TELEGRAM_MESSAGE_SAFE_LIMIT,
    BALE_CAPTION_LIMIT,
    BALE_MESSAGE_LIMIT,
    append_branding,
    split_text,
    place_branding,
    create_telegram_blockquote_messages,
    create_bale_blockquote_messages,
    analyze_content,
)


# =========================================================
# TEST DATA
# =========================================================

DEFAULT_BRANDING = (
    "#دنیا_۲۴_نیوز\n"
    "@Donya24News"
)


def make_text(
    target_length: int,
    unit: str = "متن خبر "
) -> str:
    """
    ساخت متن تست با طول تقریبی مشخص،
    بدون اینکه کلمه را نصف کنیم.
    """

    if target_length <= 0:
        return ""

    parts = []
    current_length = 0

    while True:

        if (
            current_length
            + len(unit)
            > target_length
        ):
            break

        parts.append(
            unit
        )

        current_length += len(
            unit
        )

    if not parts:
        return unit[:target_length]

    return "".join(
        parts
    ).strip()


def assert_telegram_limits(
    plan: PublicationPlan
) -> None:
    """
    بررسی تمام Limitهای Telegram.
    """

    telegram = plan.telegram

    assert (
        len(
            telegram[
                "media_caption"
            ]
        )
        <= TELEGRAM_CAPTION_LIMIT
    )

    for message in telegram[
        "followup_messages"
    ]:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )

    for message in telegram[
        "blockquote_messages"
    ]:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )


def assert_bale_limits(
    plan: PublicationPlan
) -> None:
    """
    بررسی تمام Limitهای Bale.
    """

    bale = plan.bale

    assert (
        len(
            bale[
                "media_caption"
            ]
        )
        <= BALE_CAPTION_LIMIT
    )

    for message in bale[
        "followup_messages"
    ]:

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )

    for message in bale[
        "blockquote_messages"
    ]:

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )


# =========================================================
# TEST 01
# SHORT CAPTION
# =========================================================

def test_short_caption_fits_in_telegram_media():

    main_text = (
        "❇️ تیتر خبر\n\n"
        "🔹 متن کوتاه خبر"
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram = plan.telegram

    assert (
        telegram[
            "media_caption"
        ]
    )

    assert (
        DEFAULT_BRANDING
        in telegram[
            "media_caption"
        ]
    )

    assert (
        telegram[
            "followup_messages"
        ]
        == []
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 02
# CAPTION CLOSE TO SAFE LIMIT
# =========================================================

def test_caption_near_safe_limit():

    main_text = make_text(
        TELEGRAM_CAPTION_SAFE_LIMIT
        - len(DEFAULT_BRANDING)
        - 10
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram = plan.telegram

    assert (
        len(
            telegram[
                "media_caption"
            ]
        )
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 03
# CAPTION ABOVE TELEGRAM SAFE LIMIT
# =========================================================

def test_caption_above_telegram_safe_limit_creates_followup():

    main_text = make_text(
        TELEGRAM_CAPTION_SAFE_LIMIT
        + 500
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram = plan.telegram

    assert (
        len(
            telegram[
                "media_caption"
            ]
        )
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    )

    assert (
        len(
            telegram[
                "followup_messages"
            ]
        )
        >= 1
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 04
# TEXT OVER MESSAGE LIMIT
# =========================================================

def test_text_over_telegram_message_limit_splits_multiple_times():

    main_text = make_text(
        9500
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram = plan.telegram

    assert (
        len(
            telegram[
                "followup_messages"
            ]
        )
        >= 2
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 05
# VERY LONG MULTI-PARAGRAPH TEXT
# =========================================================

def test_very_long_paragraph_text_preserves_content():

    paragraphs = [
        (
            f"پاراگراف شماره {i}. "
            + (
                "این یک متن خبری آزمایشی است. "
                * 40
            )
        )
        for i in range(
            1,
            20
        )
    ]

    main_text = "\n\n".join(
        paragraphs
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram_text = (
        plan.telegram[
            "media_caption"
        ]
        + "\n"
        + "\n".join(
            plan.telegram[
                "followup_messages"
            ]
        )
    )

    assert (
        "پاراگراف شماره 1"
        in telegram_text
    )

    assert (
        "پاراگراف شماره 19"
        in telegram_text
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 06
# BRANDING FITS
# =========================================================

def test_branding_added_to_caption_when_it_fits():

    result = place_branding(
        media_caption="متن کوتاه",
        followup_messages=[],
        branding=DEFAULT_BRANDING,
        caption_limit=1000,
        message_limit=4000
    )

    assert (
        result[
            "followup_messages"
        ]
        == []
    )

    assert (
        DEFAULT_BRANDING
        in result[
            "media_caption"
        ]
    )


# =========================================================
# TEST 07
# BRANDING OVERFLOW
# =========================================================

def test_branding_moves_to_followup_if_caption_would_overflow():

    media_caption = (
        "الف"
        * 995
    )

    result = place_branding(
        media_caption=media_caption,
        followup_messages=[],
        branding=DEFAULT_BRANDING,
        caption_limit=1000,
        message_limit=4000
    )

    assert (
        result[
            "media_caption"
        ]
        == media_caption
    )

    assert (
        result[
            "followup_messages"
        ]
    )

    assert (
        DEFAULT_BRANDING
        in result[
            "followup_messages"
        ][-1]
    )


# =========================================================
# TEST 08
# NORMAL BLOCKQUOTE
# =========================================================

def test_normal_blockquote_becomes_telegram_html():

    blocks = [
        {
            "type": "blockquote",
            "text": "متن نقل قول",
            "offset": 100,
            "length": 10
        }
    ]

    messages = (
        create_telegram_blockquote_messages(
            blocks,
            []
        )
    )

    assert len(messages) == 1

    assert (
        messages[0]
        .startswith(
            "<blockquote>"
        )
    )

    assert (
        messages[0]
        .endswith(
            "</blockquote>"
        )
    )

    assert (
        "متن نقل قول"
        in messages[0]
    )


# =========================================================
# TEST 09
# EXPANDABLE BLOCKQUOTE
# =========================================================

def test_expandable_blockquote_becomes_expandable_html():

    blocks = [
        {
            "type": "expandable_blockquote",
            "text": "تحلیل تکمیلی",
            "offset": 200,
            "length": 12
        }
    ]

    messages = (
        create_telegram_blockquote_messages(
            [],
            blocks
        )
    )

    assert len(messages) == 1

    assert (
        messages[0]
        .startswith(
            "<blockquote expandable>"
        )
    )

    assert (
        "تحلیل تکمیلی"
        in messages[0]
    )


# =========================================================
# TEST 10
# BLOCKQUOTE OFFSET ORDER
# =========================================================

def test_blockquotes_are_sorted_by_offset():

    normal = [
        {
            "text": "دوم",
            "offset": 200
        }
    ]

    expandable = [
        {
            "text": "اول",
            "offset": 100
        }
    ]

    messages = (
        create_telegram_blockquote_messages(
            normal,
            expandable
        )
    )

    assert len(messages) == 2

    assert (
        "اول"
        in messages[0]
    )

    assert (
        "دوم"
        in messages[1]
    )


# =========================================================
# TEST 11
# LONG BLOCKQUOTE
# =========================================================

def test_long_blockquote_is_split():

    long_text = (
        "این یک بخش تحلیلی طولانی است. "
        * 300
    )

    blocks = [
        {
            "text": long_text,
            "offset": 10
        }
    ]

    messages = (
        create_telegram_blockquote_messages(
            [],
            blocks
        )
    )

    assert (
        len(messages)
        > 1
    )

    for message in messages:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )

        assert (
            message.startswith(
                "<blockquote expandable>"
            )
        )

        assert (
            message.endswith(
                "</blockquote>"
            )
        )


# =========================================================
# TEST 12
# PERSIAN + ZWNJ
# =========================================================

def test_persian_and_zwnj_content():

    main_text = (
        "❇️ چشم‌انداز منطقه\n\n"
        "🔹 قدرت‌های منطقه‌ای می‌توانند "
        "در تصمیم‌گیری‌های آینده اثرگذار باشند."
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    assert (
        "چشم‌انداز"
        in plan.telegram[
            "media_caption"
        ]
    )

    assert (
        "می‌توانند"
        in plan.telegram[
            "media_caption"
        ]
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 13
# EMOJI
# =========================================================

def test_emoji_content_does_not_break_planner():

    main_text = (
        "❇️ خبر فوری 🌍\n\n"
        "🔹 تحولات جدید در منطقه 🚨"
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    assert isinstance(
        plan,
        PublicationPlan
    )

    assert (
        plan.telegram[
            "media_caption"
        ]
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 14
# HARD SPLIT
# =========================================================

def test_extremely_long_token_uses_hard_split():

    token = (
        "A"
        * 9000
    )

    parts = split_text(
        token,
        4000
    )

    assert (
        len(parts)
        == 3
    )

    assert (
        len(parts[0])
        == 4000
    )

    assert (
        len(parts[1])
        == 4000
    )

    assert (
        len(parts[2])
        == 1000
    )


# =========================================================
# TEST 15
# EMPTY INPUT
# =========================================================

def test_empty_input():

    plan = analyze_content(
        main_text="",
        branding=""
    )

    assert (
        plan.telegram[
            "media_caption"
        ]
        == ""
    )

    assert (
        plan.telegram[
            "followup_messages"
        ]
        == []
    )

    assert (
        plan.telegram[
            "blockquote_messages"
        ]
        == []
    )

    assert (
        plan.bale[
            "media_caption"
        ]
        == ""
    )


# =========================================================
# TEST 16
# BRANDING ONLY
# =========================================================

def test_branding_only():

    plan = analyze_content(
        main_text="",
        branding=DEFAULT_BRANDING
    )

    telegram_chain = (
        plan.telegram[
            "media_caption"
        ]
        + "\n"
        + "\n".join(
            plan.telegram[
                "followup_messages"
            ]
        )
    )

    assert (
        DEFAULT_BRANDING
        in telegram_chain
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 17
# OTHER ENTITIES
# =========================================================

def test_other_entities_preserved_in_metadata():

    entities = [
        {
            "type": "bold",
            "offset": 0,
            "length": 5,
            "text": "سلام"
        },
        {
            "type": "text_link",
            "offset": 10,
            "length": 4,
            "url": "https://example.com",
            "text": "لینک"
        }
    ]

    plan = analyze_content(
        main_text="خبر آزمایشی",
        other_entities=entities
    )

    assert (
        plan.metadata[
            "other_entities"
        ]
        == entities
    )


# =========================================================
# TEST 18
# NO NETWORK CALLS
# =========================================================

def test_caption_manager_has_no_network_dependency(
    monkeypatch
):

    try:
        import requests
    except ImportError:
        requests = None

    def fail_network_call(
        *args,
        **kwargs
    ):

        raise AssertionError(
            "Network call detected"
        )

    if requests:

        monkeypatch.setattr(
            requests,
            "get",
            fail_network_call
        )

        monkeypatch.setattr(
            requests,
            "post",
            fail_network_call
        )

    plan = analyze_content(
        main_text=(
            "❇️ خبر\n\n"
            "🔹 متن خبر"
        ),
        branding=DEFAULT_BRANDING
    )

    assert isinstance(
        plan,
        PublicationPlan
    )


# =========================================================
# TEST 19
# TELEGRAM LIMIT GUARANTEE
# =========================================================

def test_no_telegram_output_exceeds_official_limits():

    main_text = (
        "پاراگراف خبری بسیار طولانی. "
        * 1000
    )

    blockquote = [
        {
            "text": (
                "تحلیل بسیار طولانی. "
                * 500
            ),
            "offset": 500
        }
    ]

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=blockquote,
        branding=DEFAULT_BRANDING
    )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 20
# BALE LIMIT GUARANTEE
# =========================================================

def test_no_bale_output_exceeds_configured_limits():

    main_text = (
        "متن خبری بلند برای بله. "
        * 1000
    )

    blockquote = [
        {
            "text": (
                "تحلیل بله. "
                * 800
            ),
            "offset": 400
        }
    ]

    plan = analyze_content(
        main_text=main_text,
        blockquote_blocks=blockquote,
        branding=DEFAULT_BRANDING
    )

    assert_bale_limits(
        plan
    )


# =========================================================
# TEST 21
# FULL INTEGRATION STRUCTURE
# =========================================================

def test_full_publication_plan_structure():

    plan = analyze_content(
        main_text=(
            "❇️ عنوان خبر\n\n"
            + (
                "🔹 متن خبر برای بررسی کامل سیستم. "
                * 150
            )
        ),

        blockquote_blocks=[
            {
                "text": "نقل قول معمولی",
                "offset": 500
            }
        ],

        expandable_blocks=[
            {
                "text": "تحلیل تکمیلی قابل گسترش",
                "offset": 1000
            }
        ],

        other_entities=[
            {
                "type": "bold",
                "offset": 0,
                "length": 5
            }
        ],

        branding=DEFAULT_BRANDING
    )

    result = plan.to_dict()

    assert (
        "telegram"
        in result
    )

    assert (
        "bale"
        in result
    )

    assert (
        "metadata"
        in result
    )

    assert (
        "media_caption"
        in result[
            "telegram"
        ]
    )

    assert (
        "followup_messages"
        in result[
            "telegram"
        ]
    )

    assert (
        "blockquote_messages"
        in result[
            "telegram"
        ]
    )

    assert (
        "document_fallback"
        in result[
            "telegram"
        ]
    )

    assert (
        "media_caption"
        in result[
            "bale"
        ]
    )

    assert (
        "followup_messages"
        in result[
            "bale"
        ]
    )

    assert (
        "blockquote_messages"
        in result[
            "bale"
        ]
    )

    assert_telegram_limits(
        plan
    )

    assert_bale_limits(
        plan
    )
