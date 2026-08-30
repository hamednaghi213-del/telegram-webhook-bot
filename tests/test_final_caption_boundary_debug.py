from core.telegram_caption_entities import (
    build_telegram_caption_entities,
    utf16_length,
)


def test_final_caption_boundary_around_branding():

    main_text = (
        "❇️ عنوان خبر\n\n"
        "🔹 متن اصلی خبر"
    )

    expandable_text = (
        "این بخش تحلیل تکمیلی خبر است "
        "و باید داخل expandable blockquote قرار بگیرد."
    )

    branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    result = build_telegram_caption_entities(
        main_text=main_text,
        blockquote_blocks=[],
        expandable_blocks=[
            {
                "type": "expandable_blockquote",
                "text": expandable_text,
                "offset": 100,
            }
        ],
        branding=branding,
    )

    caption = result["caption"]
    entities = result["caption_entities"]

    # -----------------------------------------------------
    # ساختار کلی کپشن
    # -----------------------------------------------------

    assert main_text in caption
    assert expandable_text in caption
    assert branding in caption

    # -----------------------------------------------------
    # فقط یک expandable entity باید وجود داشته باشد
    # -----------------------------------------------------

    assert len(entities) == 1

    entity = entities[0]

    assert (
        entity["type"]
        == "expandable_blockquote"
    )

    # -----------------------------------------------------
    # محل شروع و پایان واقعی expandable
    # -----------------------------------------------------

    expandable_start = caption.index(
        expandable_text
    )

    expandable_end = (
        expandable_start
        + len(expandable_text)
    )

    branding_start = caption.index(
        branding
    )

    # -----------------------------------------------------
    # فاصله بین پایان expandable و branding
    #
    # باید دقیقاً مانند مسیر عادی دو newline باشد تا پاراگراف
    # خالی اضافه بین متن RTL و branding مختلط RTL/LTR نسازیم.
    # -----------------------------------------------------

    gap_text = caption[
        expandable_end:
        branding_start
    ]

    assert (
        gap_text
        == "\n\n"
    )

    # -----------------------------------------------------
    # بررسی offset واقعی Telegram بر اساس UTF-16
    # -----------------------------------------------------

    expected_offset = utf16_length(
        caption[
            :expandable_start
        ]
    )

    expected_length = utf16_length(
        expandable_text
    )

    assert (
        entity["offset"]
        == expected_offset
    )

    assert (
        entity["length"]
        == expected_length
    )

    # -----------------------------------------------------
    # پایان entity باید دقیقاً قبل از فاصله branding باشد
    # -----------------------------------------------------

    entity_end_utf16 = (
        entity["offset"]
        + entity["length"]
    )

    expected_entity_end_utf16 = (
        utf16_length(
            caption[
                :expandable_end
            ]
        )
    )

    assert (
        entity_end_utf16
        == expected_entity_end_utf16
    )

    # -----------------------------------------------------
    # Branding نباید داخل expandable باشد
    # -----------------------------------------------------

    branding_start_utf16 = (
        utf16_length(
            caption[
                :branding_start
            ]
        )
    )

    assert (
        entity_end_utf16
        < branding_start_utf16
    )

    # -----------------------------------------------------
    # هیچ Direction Mark مخفی نباید وجود داشته باشد
    # -----------------------------------------------------

    forbidden_direction_chars = [
        "\u200e",  # LRM
        "\u200f",  # RLM
        "\u202a",  # LRE
        "\u202b",  # RLE
        "\u202c",  # PDF
        "\u202d",  # LRO
        "\u202e",  # RLO
        "\u2066",  # LRI
        "\u2067",  # RLI
        "\u2068",  # FSI
        "\u2069",  # PDI
    ]

    for char in forbidden_direction_chars:

        assert char not in caption

    # -----------------------------------------------------
    # بررسی نهایی ساختار مورد انتظار
    # -----------------------------------------------------

    expected_caption = (
        main_text
        + "\n\n"
        + expandable_text
        + "\n\n"
        + branding
    )

    assert (
        caption
        == expected_caption
    )
