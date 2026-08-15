from core.caption_manager import (
    analyze_content
)

from core.telegram_caption_entities import (
    utf16_length
)


DEFAULT_BRANDING = (
    "#دنیا_۲۴_نیوز\n"
    "@Donya24News"
)


# =========================================================
# HELPERS
# =========================================================

def utf16_slice(
    text: str,
    start_utf16: int,
    length_utf16: int
) -> str:
    """
    بخشی از متن را بر اساس UTF-16 offset/length
    برمی‌گرداند.
    """

    encoded = text.encode(
        "utf-16-le"
    )

    start_byte = (
        start_utf16
        * 2
    )

    end_byte = (
        (
            start_utf16
            + length_utf16
        )
        * 2
    )

    return (
        encoded[
            start_byte:end_byte
        ]
        .decode(
            "utf-16-le"
        )
    )


def unicode_dump(
    text: str
):
    """
    برای مشاهده دقیق کاراکترهای نامرئی.
    """

    return [
        {
            "char": repr(char),
            "code": f"U+{ord(char):04X}"
        }
        for char in text
    ]


# =========================================================
# FINAL CAPTION BOUNDARY DEBUG
# =========================================================

def test_final_caption_boundary_around_branding():

    main_text = (
        "❇️ فیروزآبادی: "
        "عده‌ای تندرو می‌خواهند "
        "اینترنت ایران را بالکانیزه کنند\n\n"
        "🔹 سیدابوالحسن فیروزآبادی، "
        "دبیر سابق شورای عالی فضای مجازی:"
    )

    expandable_text = (
        "برخی جریان‌های سیاسی در آمریکا نیز "
        "به‌دلیل نگرانی از قدرت‌گرفتن کشورهایی "
        "مانند ایران و چین در فضای دیجیتال، "
        "از تجزیه‌شدن اینترنت جهانی حمایت می‌کنند.\n"
        "عده‌ای تندرو می‌خواهند اینترنت ایران "
        "را بالکانیزه کنند و توسعه را در یک "
        "چارچوب ملی و محدود می‌خواهند.\n"
        "فیلتر بدون توضیح و بدون مسئولیت‌پذیری "
        "اقدامی قابل دفاع نیست."
    )

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=[
            {
                "type": (
                    "expandable_blockquote"
                ),
                "text": (
                    expandable_text
                ),
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

    caption = (
        telegram[
            "media_caption"
        ]
    )

    entities = (
        telegram.get(
            "media_caption_entities",
            []
        )
        or []
    )

    # =====================================================
    # BASIC EXPECTATIONS
    # =====================================================

    assert (
        telegram[
            "media_parse_mode"
        ]
        is None
    )

    assert (
        len(entities)
        == 1
    )

    entity = (
        entities[0]
    )

    assert (
        entity[
            "type"
        ]
        == "expandable_blockquote"
    )

    assert (
        caption.endswith(
            DEFAULT_BRANDING
        )
    )

    # =====================================================
    # FIND BRANDING
    # =====================================================

    hashtag_index = (
        caption.index(
            "#دنیا_۲۴_نیوز"
        )
    )

    channel_index = (
        caption.index(
            "@Donya24News"
        )
    )

    hashtag_utf16_offset = (
        utf16_length(
            caption[
                :hashtag_index
            ]
        )
    )

    channel_utf16_offset = (
        utf16_length(
            caption[
                :channel_index
            ]
        )
    )

    entity_start = int(
        entity[
            "offset"
        ]
    )

    entity_length = int(
        entity[
            "length"
        ]
    )

    entity_end = (
        entity_start
        + entity_length
    )

    entity_text = (
        utf16_slice(
            caption,
            entity_start,
            entity_length
        )
    )

    # =====================================================
    # CHARACTERS AROUND HASHTAG
    # =====================================================

    before_hashtag = (
        caption[
            max(
                0,
                hashtag_index - 10
            ):
            hashtag_index
        ]
    )

    hashtag_and_after = (
        caption[
            hashtag_index:
            min(
                len(caption),
                hashtag_index + 30
            )
        ]
    )

    # =====================================================
    # UTF-16 GAP BETWEEN ENTITY AND HASHTAG
    # =====================================================

    gap_utf16_length = (
        hashtag_utf16_offset
        - entity_end
    )

    gap_text = ""

    if gap_utf16_length > 0:

        gap_text = utf16_slice(
            caption,
            entity_end,
            gap_utf16_length
        )

    # =====================================================
    # DEBUG OUTPUT
    # =====================================================

    print()
    print(
        "=========================================="
    )
    print(
        "FINAL CAPTION BOUNDARY DEBUG"
    )
    print(
        "=========================================="
    )

    print(
        "CAPTION REPR:"
    )

    print(
        repr(
            caption
        )
    )

    print()
    print(
        "CAPTION LENGTH PYTHON:",
        len(
            caption
        )
    )

    print(
        "CAPTION LENGTH UTF16:",
        utf16_length(
            caption
        )
    )

    print()
    print(
        "ENTITY:"
    )

    print(
        entity
    )

    print(
        "ENTITY START UTF16:",
        entity_start
    )

    print(
        "ENTITY LENGTH UTF16:",
        entity_length
    )

    print(
        "ENTITY END UTF16:",
        entity_end
    )

    print()
    print(
        "ENTITY TEXT REPR:"
    )

    print(
        repr(
            entity_text
        )
    )

    print()
    print(
        "HASHTAG PYTHON INDEX:",
        hashtag_index
    )

    print(
        "HASHTAG UTF16 OFFSET:",
        hashtag_utf16_offset
    )

    print(
        "CHANNEL PYTHON INDEX:",
        channel_index
    )

    print(
        "CHANNEL UTF16 OFFSET:",
        channel_utf16_offset
    )

    print()
    print(
        "GAP UTF16 LENGTH:",
        gap_utf16_length
    )

    print(
        "GAP REPR:",
        repr(
            gap_text
        )
    )

    print(
        "GAP UNICODE:",
        unicode_dump(
            gap_text
        )
    )

    print()
    print(
        "BEFORE HASHTAG REPR:",
        repr(
            before_hashtag
        )
    )

    print(
        "BEFORE HASHTAG UNICODE:",
        unicode_dump(
            before_hashtag
        )
    )

    print()
    print(
        "HASHTAG AND AFTER REPR:",
        repr(
            hashtag_and_after
        )
    )

    print(
        "HASHTAG AND AFTER UNICODE:",
        unicode_dump(
            hashtag_and_after
        )
    )

    print(
        "=========================================="
    )

    # =====================================================
    # HARD ASSERTIONS
    # =====================================================

    # Branding نباید داخل Entity باشد.
    assert (
        entity_end
        <= hashtag_utf16_offset
    )

    # خود هشتگ قطعاً نباید داخل Expandable باشد.
    assert (
        hashtag_utf16_offset
        >= entity_end
    )

    # متن Entity باید فقط متن تحلیل باشد.
    assert (
        "#دنیا_۲۴_نیوز"
        not in entity_text
    )

    assert (
        "@Donya24News"
        not in entity_text
    )

    # بین پایان Expandable و هشتگ باید دقیقاً
    # دو newline وجود داشته باشد.
    assert (
        gap_text
        == "\n\n"
    )

    # هیچ Direction Mark نباید در Gap باشد.
    forbidden_marks = (
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069"
    )

    for mark in forbidden_marks:

        assert (
            mark
            not in gap_text
        )

    # قبل از هشتگ هم هیچ Direction Mark
    # نباید وجود داشته باشد.
    for mark in forbidden_marks:

        assert (
            mark
            not in before_hashtag
        )

    # کل Caption نیز نباید Direction Control
    # داشته باشد.
    for mark in forbidden_marks:

        assert (
            mark
            not in caption
        )
