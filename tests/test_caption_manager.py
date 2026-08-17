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
    telegram_html_visible_length,
    analyze_content,
)


# =========================================================
# TEST DATA
# =========================================================

DEFAULT_BRANDING = (
    "#دنیا_۲۴_نیوز\n"
    "@Donya24News"
)


# =========================================================
# BIDI TEST HELPER
# =========================================================

def strip_bidi_marks(
    text: str
) -> str:
    """
    فقط برای تست.

    علامت‌های نامرئی جهت متن Telegram را حذف می‌کند
    تا محتوای قابل‌مشاهده Branding بررسی شود.

    RLM = U+200F
    LRM = U+200E
    """

    if not text:
        return ""

    return (
        text
        .replace("\u200f", "")
        .replace("\u200e", "")
    )


def make_text(
    target_length: int,
    unit: str = "متن خبر "
) -> str:

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

    caption = (
        telegram[
            "media_caption"
        ]
    )

    if (
        telegram.get(
            "media_parse_mode"
        )
        == "HTML"
    ):

        assert (
            telegram_html_visible_length(
                caption
            )
            <= TELEGRAM_CAPTION_LIMIT
        )

    else:

        assert (
            len(
                caption
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
            telegram_html_visible_length(
                message
            )
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

    visible_caption = (
        strip_bidi_marks(
            telegram[
                "media_caption"
            ]
        )
    )

    assert (
        DEFAULT_BRANDING
        in visible_caption
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

    if (
        telegram.get(
            "media_parse_mode"
        )
        == "HTML"
    ):

        assert (
            telegram_html_visible_length(
                telegram[
                    "media_caption"
                ]
            )
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        )

    else:

        assert (
            len(
                telegram[
                    "media_caption"
                ]
            )
            <= TELEGRAM_CAPTION_LIMIT
        )

    assert_telegram_limits(
        plan
    )


# =========================================================
# TEST 03
# CAPTION ABOVE SAFE LIMIT
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
# LONG MEDIA TEXT
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
# LONG MULTI-PARAGRAPH
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
        "ا"
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

    assert (
        len(messages)
        == 1
    )

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

    assert (
        len(messages)
        == 1
    )

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
# BLOCKQUOTE ORDER
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

    assert (
        len(messages)
        == 2
    )

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

    visible_chain = (
        strip_bidi_marks(
            telegram_chain
        )
    )

    assert (
        DEFAULT_BRANDING
        in visible_chain
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
# NO NETWORK
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
# TELEGRAM LIMITS
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
# BALE LIMITS
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
# FULL STRUCTURE
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

    assert_telegram_text_limits(
        plan
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 22
# TELEGRAM TEXT SHORT
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
# TELEGRAM TEXT LONG
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
# EVERY MESSAGE MUST HAVE ITS OWN BRANDING
# =========================================================

def test_text_plan_each_message_has_own_branding():

    main_text = make_text(
        8500
    )

    plan = analyze_content(
        main_text=main_text,
        branding=DEFAULT_BRANDING
    )

    # =====================================================
    # TELEGRAM
    # =====================================================

    telegram_messages = (
        plan.text[
            "telegram"
        ][
            "messages"
        ]
    )

    assert (
        len(telegram_messages)
        >= 2
    )

    for message in telegram_messages:

        assert (
            message.count(
                "#دنیا_۲۴_نیوز"
            )
            == 1
        )

        assert (
            message.count(
                "@Donya24News"
            )
            == 1
        )

        assert (
            message.endswith(
                DEFAULT_BRANDING
            )
        )

        assert (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        )

    # =====================================================
    # BALE
    # =====================================================

    bale_messages = (
        plan.text[
            "bale"
        ][
            "messages"
        ]
    )

    assert (
        len(bale_messages)
        >= 2
    )

    for message in bale_messages:

        assert (
            message.count(
                "#دنیا_۲۴_نیوز"
            )
            == 1
        )

        assert (
            message.count(
                "@Donya24News"
            )
            == 1
        )

        assert (
            message.endswith(
                DEFAULT_BRANDING
            )
        )

        assert (
            len(message)
            <= BALE_MESSAGE_LIMIT
        )

    assert_telegram_text_limits(
        plan
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 25
# EXPANDABLE TEXT PLAN
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

    # When the combined message (main text + blockquote + branding)
    # fits within Telegram's 4096-char limit the blockquote must be
    # inlined into messages[0] and blockquote_messages must be empty.

    messages = (
        telegram_text[
            "messages"
        ]
    )

    blockquotes = (
        telegram_text[
            "blockquote_messages"
        ]
    )

    assert (
        len(blockquotes)
        == 0
    ), "blockquote_messages must be empty when content fits in one message"

    assert (
        len(messages)
        == 1
    )

    assert (
        "<blockquote expandable>"
        in messages[0]
    )

    assert (
        "این تحلیل تکمیلی است"
        in messages[0]
    )

    assert_telegram_text_limits(
        plan
    )


# =========================================================
# TEST 26
# BALE TEXT PLAN
# INLINE BLOCKQUOTE POLICY
# =========================================================

def test_bale_text_plan_respects_limits():

    main_text = make_text(
        10000
    )

    blockquote_text = (
        "تحلیل تکمیلی برای بله. "
        * 400
    )

    plan = analyze_content(
        main_text=main_text,
        blockquote_blocks=[
            {
                "text": blockquote_text,
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

    assert (
        blockquotes
        == []
    )

    bale_chain = "\n".join(
        messages
    )

    assert (
        DEFAULT_BRANDING
        in bale_chain
    )

    assert (
        "▌ تحلیل تکمیلی برای بله."
        in bale_chain
    )

    assert_bale_text_limits(
        plan
    )


# =========================================================
# TEST 27
# TELEGRAM TEXT MUST STAY ONE MESSAGE
# IF FINAL CONTENT FITS 4096
# =========================================================

def test_telegram_text_does_not_split_when_final_message_fits_4096():

    branding_overhead = (
        len(DEFAULT_BRANDING)
        + 2
    )

    target_main_length = (
        TELEGRAM_MESSAGE_LIMIT
        - branding_overhead
        - 5
    )

    main_text = (
        "ا"
        * target_main_length
    )

    assert (
        len(main_text)
        > TELEGRAM_MESSAGE_SAFE_LIMIT
    )

    final_content = (
        append_branding(
            main_text,
            DEFAULT_BRANDING
        )
    )

    assert (
        len(final_content)
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

    assert (
        len(messages)
        == 1
    )

    assert (
        messages[0]
        == final_content
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
# REMOVE SOURCE ICONS / PROMOTIONAL FOOTER
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

    assert (
        "کارشناس صداوسیما"
        in result
    )

    assert (
        "رهبر شهید گفته بودند"
        in result
    )

    assert (
        "🔷"
        not in result
    )

    assert (
        "🆔"
        not in result
    )

    assert (
        "@AbdiMediaNet"
        not in result
    )

    assert (
        "#عبدی_مدیا"
        not in result
    )

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

    result_lines = [
        line.strip()

        for line
        in result.splitlines()

        if line.strip()
    ]

    assert (
        "سایت"
        not in result_lines
    )

    assert (
        "🔹 سایت"
        not in result_lines
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
