from core.caption_manager import (
    analyze_content,
    TELEGRAM_MESSAGE_LIMIT,
    TELEGRAM_CAPTION_SAFE_LIMIT,
    compact_long_text,
)


# =========================================================
# TEST DATA
# =========================================================

DEFAULT_BRANDING = (
    "#دنیا_۲۴_نیوز\n"
    "@Donya24News"
)


# =========================================================
# TEST 01
# ORPHAN SOURCE ICON / SEPARATOR MUST DISAPPEAR
# =========================================================

def test_orphan_source_icon_and_separator_are_removed():

    from core.formatter import (
        format_news
    )

    raw_text = (
        "تیتر خبر\n\n"
        "متن اصلی خبر به پایان می‌رسد.\n\n"
        "🔷 🆔 @source_channel | #source_tag\n"
        "🔷 |"
    )

    result = format_news(
        raw_text,
        source_title="رسانه منبع",
        source_username="source_channel"
    )

    # =====================================================
    # REAL CONTENT MUST REMAIN
    # =====================================================

    assert (
        "تیتر خبر"
        in result
    )

    assert (
        "متن اصلی خبر"
        in result
    )

    # =====================================================
    # SOURCE ICONS MUST DISAPPEAR
    # =====================================================

    assert (
        "🔷"
        not in result
    )

    assert (
        "🆔"
        not in result
    )

    # =====================================================
    # SOURCE BRANDING MUST DISAPPEAR
    # =====================================================

    assert (
        "@source_channel"
        not in result
    )

    assert (
        "#source_tag"
        not in result
    )

    # =====================================================
    # ORPHAN SEPARATOR LINE MUST NOT EXIST
    # =====================================================

    lines = [
        line.strip()

        for line
        in result.splitlines()

        if line.strip()
    ]

    assert (
        "|"
        not in lines
    )

    assert (
        "🔹 |"
        not in lines
    )

    # =====================================================
    # DONYA24 FORMAT MUST REMAIN
    # =====================================================

    assert (
        result.startswith(
            "❇️ "
        )
    )

    assert (
        "🔹"
        in result
    )


# =========================================================
# TEST 02
# EXPANDABLE BLOCKQUOTE MUST BE CLEANED
# =========================================================

def test_expandable_blockquote_removes_foreign_emoji():

    plan = analyze_content(
        main_text=(
            "❇️ تیتر خبر\n\n"
            "🔹 متن اصلی خبر"
        ),

        expandable_blocks=[
            {
                "type": (
                    "expandable_blockquote"
                ),
                "text": (
                    "🔴 این بخش تحلیل تکمیلی "
                    "و ادامه خبر است."
                ),
                "offset": 100,
                "length": 40
            }
        ],

        branding=DEFAULT_BRANDING
    )

    blockquotes = (
        plan.text[
            "telegram"
        ][
            "blockquote_messages"
        ]
    )

    assert (
        len(blockquotes)
        == 1
    )

    blockquote = (
        blockquotes[0]
    )

    # =====================================================
    # EXPANDABLE STRUCTURE MUST REMAIN
    # =====================================================

    assert (
        blockquote.startswith(
            "<blockquote expandable>"
        )
    )

    assert (
        blockquote.endswith(
            "</blockquote>"
        )
    )

    # =====================================================
    # REAL CONTENT MUST REMAIN
    # =====================================================

    assert (
        "این بخش تحلیل تکمیلی"
        in blockquote
    )

    assert (
        "ادامه خبر است"
        in blockquote
    )

    # =====================================================
    # FOREIGN EMOJI MUST DISAPPEAR
    # =====================================================

    assert (
        "🔴"
        not in blockquote
    )


# =========================================================
# TEST 03
# LONG TEXT COMPACT MODE
# =========================================================

def test_long_text_compact_mode_avoids_unnecessary_split():

    title = (
        "❇️ گزارش تحولات سیاسی"
    )

    paragraphs = [
        (
            "🔹 "
            + (
                "ا"
                * 40
            )
        )
        for _ in range(
            95
        )
    ]

    normal_text = (
        title
        + "\n\n"
        + "\n\n".join(
            paragraphs
        )
    )

    normal_final = (
        normal_text
        + "\n\n"
        + DEFAULT_BRANDING
    )

    # =====================================================
    # PRECONDITION
    # =====================================================

    assert (
        len(normal_final)
        > TELEGRAM_MESSAGE_LIMIT
    )

    # =====================================================
    # PLAN
    # =====================================================

    plan = analyze_content(
        main_text=normal_text,
        branding=DEFAULT_BRANDING
    )

    messages = (
        plan.text[
            "telegram"
        ][
            "messages"
        ]
    )

    # =====================================================
    # CORE REGRESSION
    # =====================================================

    assert (
        len(messages)
        == 1
    )

    final_message = (
        messages[0]
    )

    assert (
        len(final_message)
        <= TELEGRAM_MESSAGE_LIMIT
    )

    # =====================================================
    # TITLE ICON MUST REMAIN
    # =====================================================

    assert (
        final_message.startswith(
            "❇️ گزارش تحولات سیاسی"
        )
    )

    # =====================================================
    # BLUE BULLETS MUST BE REMOVED
    # =====================================================

    assert (
        "🔹"
        not in final_message
    )

    # =====================================================
    # FIRST GAP MUST REMAIN
    # =====================================================

    assert (
        "❇️ گزارش تحولات سیاسی\n\n"
        in final_message
    )

    # =====================================================
    # BODY MUST BE COMPACT
    # =====================================================

    body_without_branding = (
        final_message.split(
            "\n\n"
            + DEFAULT_BRANDING
        )[0]
    )

    body_lines = (
        body_without_branding
        .splitlines()
    )

    assert (
        len(body_lines)
        > 50
    )

    body_part = (
        body_without_branding
        .split(
            "\n\n",
            1
        )[1]
    )

    assert (
        "\n\n"
        not in body_part
    )

    # =====================================================
    # BRANDING MUST REMAIN EXACTLY ONCE
    # =====================================================

    assert (
        final_message.count(
            "#دنیا_۲۴_نیوز"
        )
        == 1
    )

    assert (
        final_message.count(
            "@Donya24News"
        )
        == 1
    )


# =========================================================
# TEST 04
# SINGLE MEDIA COMPACT MUST AVOID FOLLOWUP
# WHEN COMPACT CAPTION FITS
# =========================================================

def test_single_media_compact_avoids_followup_when_compact_fits():

    # =====================================================
    # BUILD MEDIA TEXT
    # =====================================================

    title = (
        "❇️ گزارش رسانه‌ای"
    )

    paragraphs = [
        (
            "🔹 "
            + (
                "ا"
                * 25
            )
        )
        for _ in range(
            32
        )
    ]

    main_text = (
        title
        + "\n\n"
        + "\n\n".join(
            paragraphs
        )
    )

    # =====================================================
    # PRECONDITION
    # =====================================================

    assert (
        len(main_text)
        > TELEGRAM_CAPTION_SAFE_LIMIT
    )

    compact_text = (
        compact_long_text(
            main_text
        )
    )

    assert (
        len(compact_text)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    )

    # =====================================================
    # PLAN
    # =====================================================

    plan = analyze_content(
        main_text=main_text,
        branding=""
    )

    telegram = (
        plan.telegram
    )

    # =====================================================
    # CORE REGRESSION
    # =====================================================

    assert (
        telegram[
            "followup_messages"
        ]
        == []
    )

    assert (
        telegram[
            "media_caption"
        ]
        == compact_text
    )

    assert (
        len(
            telegram[
                "media_caption"
            ]
        )
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    )

    # =====================================================
    # COMPACT FORMAT
    # =====================================================

    assert (
        telegram[
            "media_caption"
        ]
        .startswith(
            "❇️ گزارش رسانه‌ای\n\n"
        )
    )

    assert (
        "🔹"
        not in telegram[
            "media_caption"
        ]
    )

    body_part = (
        telegram[
            "media_caption"
        ]
        .split(
            "\n\n",
            1
        )[1]
    )

    assert (
        "\n\n"
        not in body_part
    )
