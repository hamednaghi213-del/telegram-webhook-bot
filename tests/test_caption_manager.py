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


def assert_telegram_text_limits(
    plan: PublicationPlan
) -> None:

    telegram_text = (
        plan.text[
            "telegram"
        ]
    )

    for message in telegram_text[
        "messages"
    ]:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )

    for message in telegram_text[
        "blockquote_messages"
    ]:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )


def assert_bale_text_limits(
    plan: PublicationPlan
) -> None:

    bale_text = (
        plan.text[
            "bale"
        ]
    )

    for message in bale_text[
        "messages"
    ]:

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )

    for message in bale_text[
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

    assert (
        plan.text[
            "telegram"
        ][
            "messages"
        ]
        == []
    )

    assert (
        plan.text[
            "bale"
        ][
            "messages"
        ]
        == []
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

    assert_telegram_text_limits(
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

    assert_bale_text_limits(
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

    assert (
        "telegram"
        in plan.text
    )

    assert (
        "bale"
        in plan.text
    )

    assert (
        "messages"
        in plan.text[
            "telegram"
        ]
    )

    assert (
        "blockquote_messages"
        in plan.text[
            "telegram"
        ]
    )

    assert (
        "messages"
        in plan.text[
            "bale"
        ]
    )

    assert (
        "blockquote_messages"
        in plan.text[
            "bale"
        ]
    )

    assert_telegram_limits(
        plan
    )

    assert_bale_limits(
        plan
    )

    assert_telegram_text_limits(
        plan
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 22
# TELEGRAM TEXT PLAN SHORT MESSAGE
# =========================================================

def test_telegram_text_plan_short_message():

    plan = analyze_content(
        main_text=(
            "❇️ تیتر خبر\n\n"
            "🔹 متن کوتاه خبر"
        ),
        branding=DEFAULT_BRANDING
    )

    telegram_text = (
        plan.text[
            "telegram"
        ]
    )

    messages = (
        telegram_text[
            "messages"
        ]
    )

    assert (
        len(messages)
        == 1
    )

    assert (
        "❇️ تیتر خبر"
        in messages[0]
    )

    assert (
        "🔹 متن کوتاه خبر"
        in messages[0]
    )

    assert (
        DEFAULT_BRANDING
        in messages[0]
    )

    assert (
        telegram_text[
            "blockquote_messages"
        ]
        == []
    )

    assert_telegram_text_limits(
        plan
    )


# =========================================================
# TEST 23
# TELEGRAM TEXT PLAN LONG MESSAGE SPLITS
# =========================================================

def test_telegram_text_plan_long_message_splits():

    main_text = make_text(
        9500
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram_text = (
        plan.text[
            "telegram"
        ]
    )

    messages = (
        telegram_text[
            "messages"
        ]
    )

    assert (
        len(messages)
        >= 3
    )

    for message in messages:

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )

    combined = "\n".join(
        messages
    )

    assert (
        DEFAULT_BRANDING
        in combined
    )

    assert_telegram_text_limits(
        plan
    )


# =========================================================
# TEST 24
# TEXT PLAN BRANDING ONLY ONCE
# =========================================================

def test_text_plan_branding_added_only_once():

    main_text = make_text(
        8500
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    telegram_messages = (
        plan.text[
            "telegram"
        ][
            "messages"
        ]
    )

    telegram_chain = "\n".join(
        telegram_messages
    )

    assert (
        telegram_chain.count(
            "#دنیا_۲۴_نیوز"
        )
        == 1
    )

    assert (
        telegram_chain.count(
            "@Donya24News"
        )
        == 1
    )

    assert (
        DEFAULT_BRANDING
        in telegram_messages[-1]
    )

    bale_messages = (
        plan.text[
            "bale"
        ][
            "messages"
        ]
    )

    bale_chain = "\n".join(
        bale_messages
    )

    assert (
        bale_chain.count(
            "#دنیا_۲۴_نیوز"
        )
        == 1
    )

    assert (
        bale_chain.count(
            "@Donya24News"
        )
        == 1
    )

    assert_telegram_text_limits(
        plan
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 25
# TELEGRAM TEXT PLAN EXPANDABLE BLOCKQUOTE
# =========================================================

def test_telegram_text_plan_expandable_blockquote():

    plan = analyze_content(
        main_text=(
            "❇️ تیتر خبر\n\n"
            "🔹 متن اصلی"
        ),
        expandable_blocks=[
            {
                "text": (
                    "این تحلیل تکمیلی است"
                ),
                "offset": 100
            }
        ],
        branding=DEFAULT_BRANDING
    )

    telegram_text = (
        plan.text[
            "telegram"
        ]
    )

    blockquotes = (
        telegram_text[
            "blockquote_messages"
        ]
    )

    assert (
        len(blockquotes)
        == 1
    )

    assert (
        blockquotes[0].startswith(
            "<blockquote expandable>"
        )
    )

    assert (
        "این تحلیل تکمیلی است"
        in blockquotes[0]
    )

    assert (
        blockquotes[0].endswith(
            "</blockquote>"
        )
    )

    assert_telegram_text_limits(
        plan
    )


# =========================================================
# TEST 26
# BALE TEXT PLAN LIMITS
# =========================================================

def test_bale_text_plan_respects_limits():

    main_text = make_text(
        10000
    )

    plan = analyze_content(
        main_text=main_text,
        blockquote_blocks=[
            {
                "text": (
                    "تحلیل تکمیلی برای بله. "
                    * 400
                ),
                "offset": 200
            }
        ],
        branding=DEFAULT_BRANDING
    )

    bale_text = (
        plan.text[
            "bale"
        ]
    )

    messages = (
        bale_text[
            "messages"
        ]
    )

    blockquotes = (
        bale_text[
            "blockquote_messages"
        ]
    )

    assert (
        len(messages)
        >= 2
    )

    for message in messages:

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )

    for message in blockquotes:

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )

    bale_chain = "\n".join(
        messages
    )

    assert (
        DEFAULT_BRANDING
        in bale_chain
    )

    assert (
        len(blockquotes)
        >= 1
    )

    assert (
        blockquotes[0]
        .startswith(
            "▌ "
        )
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 27
# TELEGRAM TEXT MUST NOT SPLIT BELOW OFFICIAL LIMIT
# =========================================================

def test_telegram_text_does_not_split_when_final_message_fits_4096():

    # متن عمداً بیشتر از Safe Limit فعلی 4000 است،
    # اما همراه Branding هنوز باید زیر سقف رسمی
    # Telegram یعنی 4096 باقی بماند.

    available_for_main_text = (
        TELEGRAM_MESSAGE_LIMIT
        - len(DEFAULT_BRANDING)
        - 2
    )

    main_text = (
        "الف"
        * (
            available_for_main_text
            - 5
        )
    )

    assert (
        len(main_text)
        > TELEGRAM_MESSAGE_SAFE_LIMIT
    )

    assert (
        len(
            append_branding(
                main_text,
                DEFAULT_BRANDING
            )
        )
        <= TELEGRAM_MESSAGE_LIMIT
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    messages = (
        plan.text[
            "telegram"
        ][
            "messages"
        ]
    )

    # انتظار مطلوب:
    # چون متن + Branding زیر 4096 است،
    # نباید به دو پیام تقسیم شود.

    assert (
        len(messages)
        == 1
    )

    assert (
        DEFAULT_BRANDING
        in messages[0]
    )

    assert (
        len(messages[0])
        <= TELEGRAM_MESSAGE_LIMIT
    )


# =========================================================
# TEST 28
# FORMATTER REMOVES SOURCE ICONS AND FOOTER
# =========================================================

def test_formatter_removes_source_icons_and_promotional_footer():

    from core.formatter import (
        format_news
    )

    raw_text = (
        "کارشناس صداوسیما در برنامه به وقت ایران "
        "می‌گوید به رهبر شهید درباره نفت آمریکا "
        "گزارش غلط داده بودند.\n\n"
        "🔷 رهبر شهید گفته بودند نفت آمریکا "
        "۱۰ سال دیگر تمام می‌شود.\n\n"
        "🔷 🆔 @AbdiMediaNet | #عبدی_مدیا\n"
        "🔷 سایت | واتس‌اپ | یوتیوب | کست باکس"
    )

    result = format_news(
        raw_text,
        source_title="عبدی مدیا",
        source_username="AbdiMediaNet"
    )

    # متن واقعی خبر باید باقی بماند
    assert (
        "کارشناس صداوسیما"
        in result
    )

    assert (
        "رهبر شهید گفته بودند"
        in result
    )

    # آیکون منبع نباید باقی بماند
    assert (
        "🔷"
        not in result
    )

    assert (
        "🆔"
        not in result
    )

    # شناسه و هشتگ منبع نباید باقی بمانند
    assert (
        "@AbdiMediaNet"
        not in result
    )

    assert (
        "#عبدی_مدیا"
        not in result
    )

    # Footer تبلیغاتی منبع نباید باقی بماند
    assert (
        "واتس‌اپ"
        not in result
    )

    assert (
        "یوتیوب"
        not in result
    )

    assert (
        "کست باکس"
        not in result
    )

    # Formatter دنیا ۲۴ باید همچنان فعال باشد
    assert (
        "❇️"
        in result
    )

    assert (
        "🔹"
        in result
    )
