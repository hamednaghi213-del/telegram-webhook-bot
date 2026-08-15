from core.telegram_caption_entities import (
    utf16_length,
    python_index_to_utf16_offset,
    combine_blocks,
    build_message_entity,
    build_plain_caption_with_entities,
    validate_caption_entities,
    build_telegram_caption_entities,
)


# =========================================================
# TEST 01
# UTF-16 ASCII
# =========================================================

def test_utf16_length_ascii():

    text = "hello"

    assert (
        utf16_length(text)
        == 5
    )


# =========================================================
# TEST 02
# UTF-16 PERSIAN
# =========================================================

def test_utf16_length_persian():

    text = "سلام"

    assert (
        utf16_length(text)
        == 4
    )


# =========================================================
# TEST 03
# UTF-16 EMOJI
# =========================================================

def test_utf16_length_emoji():

    text = "A😀B"

    assert (
        utf16_length(text)
        == 4
    )


# =========================================================
# TEST 04
# PYTHON INDEX TO UTF-16 OFFSET
# =========================================================

def test_python_index_to_utf16_offset_with_emoji():

    text = "A😀B"

    assert (
        python_index_to_utf16_offset(
            text,
            0
        )
        == 0
    )

    assert (
        python_index_to_utf16_offset(
            text,
            1
        )
        == 1
    )

    assert (
        python_index_to_utf16_offset(
            text,
            2
        )
        == 3
    )

    assert (
        python_index_to_utf16_offset(
            text,
            3
        )
        == 4
    )


# =========================================================
# TEST 05
# BLOCK ORDER
# =========================================================

def test_combine_blocks_preserves_offset_order():

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

    result = combine_blocks(
        normal,
        expandable
    )

    assert (
        len(result)
        == 2
    )

    assert (
        result[0]["text"]
        == "اول"
    )

    assert (
        result[0]["type"]
        == "expandable_blockquote"
    )

    assert (
        result[1]["text"]
        == "دوم"
    )

    assert (
        result[1]["type"]
        == "blockquote"
    )


# =========================================================
# TEST 06
# BASIC ENTITY
# =========================================================

def test_build_message_entity():

    caption = (
        "تیتر\n\n"
        "متن نقل قول"
    )

    start = caption.index(
        "متن نقل قول"
    )

    end = (
        start
        + len(
            "متن نقل قول"
        )
    )

    entity = build_message_entity(
        "blockquote",
        caption,
        start,
        end
    )

    assert (
        entity["type"]
        == "blockquote"
    )

    assert (
        entity["offset"]
        == utf16_length(
            caption[:start]
        )
    )

    assert (
        entity["length"]
        == utf16_length(
            "متن نقل قول"
        )
    )


# =========================================================
# TEST 07
# PLAIN CAPTION WITH NORMAL BLOCKQUOTE
# =========================================================

def test_build_plain_caption_with_normal_blockquote():

    result = (
        build_plain_caption_with_entities(
            main_text=(
                "❇️ تیتر خبر\n\n"
                "🔹 متن اصلی"
            ),
            blockquote_blocks=[
                {
                    "text": "متن نقل قول",
                    "offset": 100
                }
            ],
            branding=(
                "#دنیا_۲۴_نیوز\n"
                "@Donya24News"
            )
        )
    )

    caption = result[
        "caption"
    ]

    entities = result[
        "caption_entities"
    ]

    assert (
        caption
        == (
            "❇️ تیتر خبر\n\n"
            "🔹 متن اصلی\n\n"
            "متن نقل قول\n\n"
            "#دنیا_۲۴_نیوز\n"
            "@Donya24News"
        )
    )

    assert (
        len(entities)
        == 1
    )

    assert (
        entities[0]["type"]
        == "blockquote"
    )


# =========================================================
# TEST 08
# EXPANDABLE BLOCKQUOTE
# =========================================================

def test_build_plain_caption_with_expandable_blockquote():

    result = (
        build_plain_caption_with_entities(
            main_text=(
                "❇️ تیتر خبر\n\n"
                "🔹 متن اصلی"
            ),
            expandable_blocks=[
                {
                    "text": "تحلیل تکمیلی",
                    "offset": 100
                }
            ],
            branding=(
                "#دنیا_۲۴_نیوز\n"
                "@Donya24News"
            )
        )
    )

    caption = result[
        "caption"
    ]

    entities = result[
        "caption_entities"
    ]

    assert (
        "تحلیل تکمیلی"
        in caption
    )

    assert (
        len(entities)
        == 1
    )

    assert (
        entities[0]["type"]
        == "expandable_blockquote"
    )


# =========================================================
# TEST 09
# BRANDING MUST BE OUTSIDE BLOCKQUOTE
# =========================================================

def test_branding_is_outside_blockquote():

    branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    block_text = (
        "این بخش باید داخل "
        "Expandable باشد"
    )

    result = (
        build_telegram_caption_entities(
            main_text="❇️ خبر",
            expandable_blocks=[
                {
                    "text": block_text,
                    "offset": 100
                }
            ],
            branding=branding
        )
    )

    caption = result[
        "caption"
    ]

    entity = result[
        "caption_entities"
    ][0]

    assert (
        caption.endswith(
            branding
        )
    )

    assert (
        entity["type"]
        == "expandable_blockquote"
    )

    block_start = (
        caption.index(
            block_text
        )
    )

    block_end = (
        block_start
        + len(
            block_text
        )
    )

    assert (
        entity["offset"]
        == utf16_length(
            caption[:block_start]
        )
    )

    assert (
        entity["length"]
        == utf16_length(
            caption[
                block_start:block_end
            ]
        )
    )

    branding_start = (
        caption.index(
            "#دنیا_۲۴_نیوز"
        )
    )

    assert (
        utf16_length(
            caption[:branding_start]
        )
        >= (
            entity["offset"]
            + entity["length"]
        )
    )


# =========================================================
# TEST 10
# EMOJI BEFORE BLOCKQUOTE
# =========================================================

def test_emoji_before_expandable_blockquote_utf16():

    main_text = (
        "❇️ خبر فوری 😀"
    )

    block_text = (
        "تحلیل بعد از ایموجی"
    )

    result = (
        build_telegram_caption_entities(
            main_text=main_text,
            expandable_blocks=[
                {
                    "text": block_text,
                    "offset": 100
                }
            ]
        )
    )

    caption = result[
        "caption"
    ]

    entity = result[
        "caption_entities"
    ][0]

    block_start = (
        caption.index(
            block_text
        )
    )

    assert (
        entity["offset"]
        == utf16_length(
            caption[:block_start]
        )
    )


# =========================================================
# TEST 11
# MULTIPLE BLOCKS
# =========================================================

def test_multiple_blocks_keep_order():

    result = (
        build_telegram_caption_entities(
            main_text="تیتر",
            blockquote_blocks=[
                {
                    "text": "بخش دوم",
                    "offset": 200
                }
            ],
            expandable_blocks=[
                {
                    "text": "بخش اول",
                    "offset": 100
                }
            ],
            branding=(
                "#دنیا_۲۴_نیوز\n"
                "@Donya24News"
            )
        )
    )

    caption = result[
        "caption"
    ]

    entities = result[
        "caption_entities"
    ]

    assert (
        caption.index(
            "بخش اول"
        )
        < caption.index(
            "بخش دوم"
        )
    )

    assert (
        entities[0]["type"]
        == "expandable_blockquote"
    )

    assert (
        entities[1]["type"]
        == "blockquote"
    )


# =========================================================
# TEST 12
# VALIDATION PASSES
# =========================================================

def test_validate_caption_entities_passes():

    result = (
        build_telegram_caption_entities(
            main_text="خبر",
            expandable_blocks=[
                {
                    "text": "تحلیل",
                    "offset": 10
                }
            ]
        )
    )

    assert (
        validate_caption_entities(
            result["caption"],
            result["caption_entities"]
        )
        is True
    )


# =========================================================
# TEST 13
# VALIDATION REJECTS OUT OF RANGE
# =========================================================

def test_validate_caption_entities_rejects_out_of_range():

    caption = "سلام"

    entities = [
        {
            "type": "blockquote",
            "offset": 0,
            "length": 999
        }
    ]

    assert (
        validate_caption_entities(
            caption,
            entities
        )
        is False
    )


# =========================================================
# TEST 14
# EMPTY INPUT
# =========================================================

def test_empty_input():

    result = (
        build_telegram_caption_entities(
            main_text="",
            branding=""
        )
    )

    assert (
        result["caption"]
        == ""
    )

    assert (
        result["caption_entities"]
        == []
    )


# =========================================================
# TEST 15
# BRANDING ONLY
# =========================================================

def test_branding_only():

    branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    result = (
        build_telegram_caption_entities(
            main_text="",
            branding=branding
        )
    )

    assert (
        result["caption"]
        == branding
    )

    assert (
        result["caption_entities"]
        == []
    )


# =========================================================
# TEST 16
# EXACT TARGET STRUCTURE
# =========================================================

def test_exact_target_structure():

    branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    main_text = (
        "❇️ فیروزآبادی: "
        "اینترنت ایران\n\n"
        "🔹 سیدابوالحسن فیروزآبادی:"
    )

    expandable = (
        "برخی جریان‌های سیاسی "
        "در آمریکا از تجزیه‌شدن "
        "اینترنت جهانی حمایت می‌کنند."
    )

    result = (
        build_telegram_caption_entities(
            main_text=main_text,
            expandable_blocks=[
                {
                    "text": expandable,
                    "offset": 100
                }
            ],
            branding=branding
        )
    )

    caption = result[
        "caption"
    ]

    entities = result[
        "caption_entities"
    ]

    assert (
        caption
        == (
            main_text
            + "\n\n"
            + expandable
            + "\n\n"
            + branding
        )
    )

    assert (
        len(entities)
        == 1
    )

    assert (
        entities[0]["type"]
        == "expandable_blockquote"
    )

    assert (
        caption.endswith(
            branding
        )
    )

    assert (
        "<blockquote"
        not in caption
    )

    assert (
        "</blockquote>"
        not in caption
    )
