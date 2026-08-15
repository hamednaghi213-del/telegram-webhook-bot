from core.caption_manager import (
    analyze_content,
    TELEGRAM_MESSAGE_LIMIT,
    TELEGRAM_CAPTION_SAFE_LIMIT,
    compact_long_text,
    telegram_html_visible_length,
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

    assert (
        "تیتر خبر"
        in result
    )

    assert (
        "متن اصلی خبر"
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
        "@source_channel"
        not in result
    )

    assert (
        "#source_tag"
        not in result
    )

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

    telegram = (
        plan.telegram
    )

    # در Media Plan جدید باید Blockquote داخل Caption باشد.
    assert (
        telegram[
            "media_parse_mode"
        ]
        == "HTML"
    )

    caption = (
        telegram[
            "media_caption"
        ]
    )

    assert (
        "<blockquote expandable>"
        in caption
    )

    assert (
        "</blockquote>"
        in caption
    )

    assert (
        "این بخش تحلیل تکمیلی"
        in caption
    )

    assert (
        "ادامه خبر است"
        in caption
    )

    assert (
        "🔴"
        not in caption
    )

    # نباید Blockquote جداگانه Media ساخته شود.
    assert (
        telegram[
            "blockquote_messages"
        ]
        == []
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

    assert (
        len(normal_final)
        > TELEGRAM_MESSAGE_LIMIT
    )

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

    assert (
        final_message.startswith(
            "❇️ گزارش تحولات سیاسی"
        )
    )

    assert (
        "🔹"
        not in final_message
    )

    assert (
        "❇️ گزارش تحولات سیاسی\n\n"
        in final_message
    )

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
# SINGLE MEDIA COMPACT / SMART EXPANDABLE
# MUST AVOID FOLLOWUP WHEN IT FITS
# =========================================================

def test_single_media_compact_avoids_followup_when_compact_fits():

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
            35
        )
    ]

    main_text = (
        title
        + "\n\n"
        + "\n\n".join(
            paragraphs
        )
    )

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

    plan = analyze_content(
        main_text=main_text,
        branding=""
    )

    telegram = (
        plan.telegram
    )

    # =====================================================
    # MUST REMAIN ONE MEDIA POST
    # =====================================================

    assert (
        telegram[
            "followup_messages"
        ]
        == []
    )

    assert (
        telegram[
            "document_fallback"
        ]
        is False
    )

    # =====================================================
    # NEW POLICY:
    #
    # اگر Smart Expandable قابل ساخت باشد،
    # خروجی HTML است.
    #
    # اگر Raw HTML به Safe Limit نخورد،
    # Compact ساده مجاز است.
    # =====================================================

    media_caption = (
        telegram[
            "media_caption"
        ]
    )

    if (
        telegram[
            "media_parse_mode"
        ]
        == "HTML"
    ):

        assert (
            "<blockquote expandable>"
            in media_caption
        )

        assert (
            "</blockquote>"
            in media_caption
        )

        assert (
            len(media_caption)
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        )

        assert (
            telegram_html_visible_length(
                media_caption
            )
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        )

        assert (
            media_caption.startswith(
                "❇️ گزارش رسانه‌ای"
            )
        )

    else:

        assert (
            media_caption
            == compact_text
        )

        assert (
            len(media_caption)
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        )

        assert (
            media_caption.startswith(
                "❇️ گزارش رسانه‌ای\n\n"
            )
        )

        assert (
            "🔹"
            not in media_caption
        )
