from core.caption_manager import (
    TELEGRAM_CAPTION_SAFE_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    analyze_content,
    compact_long_text,
    telegram_html_visible_length,
)

from core.formatter import (
    format_news,
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
# ORPHAN SOURCE ICON / SEPARATOR
# =========================================================

def test_orphan_source_icon_and_separator_are_removed():

    raw_text = (
        "عنوان خبر آزمایشی\n\n"
        "متن اصلی خبر برای بررسی پاک‌سازی منبع.\n\n"
        "🔷 🆔 @SourceChannel | #SourceTag\n"
        "🔷 |"
    )

    result = format_news(
        raw_text,
        source_title="Source Channel",
        source_username="SourceChannel"
    )

    assert (
        "عنوان خبر آزمایشی"
        in result
    )

    assert (
        "متن اصلی خبر"
        in result
    )

    assert (
        "@SourceChannel"
        not in result
    )

    assert (
        "#SourceTag"
        not in result
    )

    assert (
        "🆔"
        not in result
    )

    assert (
        "🔷"
        not in result
    )

    assert (
        "🔹 |"
        not in result
    )

    assert (
        "\n|"
        not in result
    )


# =========================================================
# TEST 02
# EXPANDABLE BLOCKQUOTE
# FINAL ONE-MESSAGE MEDIA POLICY
#
# Media:
#   Photo
#   Main text
#   Expandable blockquote
#   Branding
#
# Everything must stay inside ONE Telegram media caption.
#
# Important:
#
# Branding is now explicitly represented as Telegram entities:
#
#   expandable_blockquote
#   hashtag
#   mention
#
# This avoids RTL / LTR positioning problems.
# =========================================================

def test_expandable_blockquote_removes_foreign_emoji():

    main_text = (
        "❇️ عنوان خبر\n\n"
        "🔹 متن اصلی خبر"
    )

    expandable_text = (
        "🔷 بخش اول تحلیل\n"
        "🆔 بخش دوم تحلیل\n"
        "📡 بخش سوم تحلیل"
    )

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=[
            {
                "type": "expandable_blockquote",
                "text": expandable_text,
                "offset": 100,
                "length": len(
                    expandable_text
                )
            }
        ],
        branding=DEFAULT_BRANDING
    )

    telegram = (
        plan.telegram
    )

    # =====================================================
    # ONE-MESSAGE ENTITY POLICY
    # =====================================================

    assert (
        telegram[
            "media_parse_mode"
        ]
        is None
    )

    entities = (
        telegram[
            "media_caption_entities"
        ]
    )

    # =====================================================
    # FINAL ENTITY POLICY
    #
    # Expected:
    #
    # 1. expandable_blockquote
    #
    # Telegram auto-detects the RTL hashtag and LTR mention. Keeping them out
    # of the explicit entity list avoids the confirmed client BiDi bug.
    # =====================================================

    entity_types = [
        entity.get(
            "type"
        )
        for entity in entities
    ]

    assert (
        entity_types.count(
            "expandable_blockquote"
        )
        == 1
    )

    assert "hashtag" not in entity_types
    assert "mention" not in entity_types
    assert len(entities) == 1

    expandable_entity = next(
        (
            entity
            for entity in entities
            if entity.get(
                "type"
            )
            == "expandable_blockquote"
        ),
        None
    )

    assert (
        expandable_entity
        is not None
    )

    assert (
        expandable_entity.get(
            "length",
            0
        )
        > 0
    )

    caption = (
        telegram[
            "media_caption"
        ]
    )

    # =====================================================
    # CAPTION MUST BE PLAIN TEXT
    #
    # Telegram formatting is carried through entities,
    # not HTML.
    # =====================================================

    assert (
        "<blockquote"
        not in caption
    )

    assert (
        "</blockquote>"
        not in caption
    )

    # =====================================================
    # MAIN TEXT MUST REMAIN
    # =====================================================

    assert (
        "عنوان خبر"
        in caption
    )

    assert (
        "متن اصلی خبر"
        in caption
    )

    # =====================================================
    # FOREIGN DECORATION MUST BE CLEANED
    # =====================================================

    assert (
        "🔷"
        not in caption
    )

    assert (
        "🆔"
        not in caption
    )

    assert (
        "📡"
        not in caption
    )

    # =====================================================
    # REAL EXPANDABLE CONTENT MUST REMAIN
    # INSIDE THE SAME CAPTION
    # =====================================================

    assert (
        "بخش اول تحلیل"
        in caption
    )

    assert (
        "بخش دوم تحلیل"
        in caption
    )

    assert (
        "بخش سوم تحلیل"
        in caption
    )

    # =====================================================
    # BRANDING MUST ALSO BE INSIDE SAME CAPTION
    # =====================================================

    assert (
        DEFAULT_BRANDING
        in caption
    )

    assert (
        "#دنیا_۲۴_نیوز"
        in caption
    )

    assert (
        "@Donya24News"
        in caption
    )

    # =====================================================
    # BRANDING MUST NOT BE DUPLICATED
    # =====================================================

    assert (
        caption.count(
            "#دنیا_۲۴_نیوز"
        )
        == 1
    )

    assert (
        caption.count(
            "@Donya24News"
        )
        == 1
    )

    # =====================================================
    # NO EXTRA TELEGRAM MESSAGES
    # =====================================================

    assert (
        telegram[
            "followup_messages"
        ]
        == []
    )

    assert (
        telegram[
            "blockquote_messages"
        ]
        == []
    )

    # =====================================================
    # NO FALLBACK
    # =====================================================

    assert (
        telegram[
            "document_fallback"
        ]
        is False
    )

    # =====================================================
    # TELEGRAM CAPTION LIMIT
    # =====================================================

    assert (
        len(caption)
        <= 1024
    )


# =========================================================
# TEST 03
# LONG TEXT COMPACT MODE
# MUST AVOID UNNECESSARY SPLIT
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

    # =====================================================
    # COMPACT VERSION MUST FIT IN ONE MESSAGE
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

    assert (
        final_message.startswith(
            "❇️ گزارش تحولات سیاسی"
        )
    )

    # Bulletها در Compact Mode حذف می‌شوند.
    assert (
        "🔹"
        not in final_message
    )

    assert (
        "❇️ گزارش تحولات سیاسی\n\n"
        in final_message
    )

    # =====================================================
    # REMOVE BRANDING BEFORE BODY STRUCTURE CHECK
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

    assert (
        final_message.endswith(
            DEFAULT_BRANDING
        )
    )


# =========================================================
# TEST 04
# SINGLE MEDIA
# COMPACT MUST AVOID FOLLOWUP
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

    media_caption = (
        telegram[
            "media_caption"
        ]
    )

    # =====================================================
    # THIS NEWS HAS NO SOURCE BLOCKQUOTE
    # SO ENTITY MODE MUST NOT BE CREATED
    # =====================================================

    assert (
        telegram.get(
            "media_caption_entities",
            []
        )
        == []
    )

    # =====================================================
    # LEGACY HTML POSSIBILITY
    # =====================================================

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

    # =====================================================
    # NORMAL COMPACT PATH
    # =====================================================

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
