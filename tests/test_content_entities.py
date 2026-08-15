from core.content_entities import (
    build_utf16_positions,
    utf16_to_python_index,
    utf16_range_to_python,
    merge_ranges,
    remove_ranges_from_text,
    parse_telegram_entities,
    escape_html,
    build_blockquote_html,
    build_pre_html,
    build_entity_html,
    build_full_html,
)


# =========================================================
# TEST 01
# UTF-16 SIMPLE ASCII
# =========================================================

def test_utf16_positions_ascii():

    text = "abc"

    positions = build_utf16_positions(
        text
    )

    assert positions == [
        0,
        1,
        2,
        3
    ]


# =========================================================
# TEST 02
# UTF-16 PERSIAN
# =========================================================

def test_utf16_positions_persian():

    text = "سلام"

    positions = build_utf16_positions(
        text
    )

    assert positions == [
        0,
        1,
        2,
        3,
        4
    ]


# =========================================================
# TEST 03
# UTF-16 EMOJI
# =========================================================

def test_utf16_positions_emoji():

    text = "A😀B"

    positions = build_utf16_positions(
        text
    )

    assert positions == [
        0,
        1,
        3,
        4
    ]


# =========================================================
# TEST 04
# UTF-16 OFFSET TO PYTHON INDEX
# =========================================================

def test_utf16_to_python_index_with_emoji():

    text = "A😀B"

    positions = build_utf16_positions(
        text
    )

    assert (
        utf16_to_python_index(
            text,
            0,
            positions
        )
        == 0
    )

    assert (
        utf16_to_python_index(
            text,
            1,
            positions
        )
        == 1
    )

    assert (
        utf16_to_python_index(
            text,
            3,
            positions
        )
        == 2
    )

    assert (
        utf16_to_python_index(
            text,
            4,
            positions
        )
        == 3
    )


# =========================================================
# TEST 05
# UTF-16 RANGE WITH EMOJI
# =========================================================

def test_utf16_range_with_emoji():

    text = "سلام 😀 دنیا"

    positions = build_utf16_positions(
        text
    )

    emoji_python_index = text.index(
        "😀"
    )

    emoji_utf16_offset = (
        positions[
            emoji_python_index
        ]
    )

    start, end = (
        utf16_range_to_python(
            text,
            emoji_utf16_offset,
            2,
            positions
        )
    )

    assert (
        text[
            start:end
        ]
        == "😀"
    )


# =========================================================
# TEST 06
# MERGE RANGES
# =========================================================

def test_merge_overlapping_ranges():

    ranges = [
        (0, 5),
        (3, 10),
        (12, 15),
        (14, 20)
    ]

    result = merge_ranges(
        ranges
    )

    assert result == [
        (0, 10),
        (12, 20)
    ]


# =========================================================
# TEST 07
# REMOVE RANGES
# =========================================================

def test_remove_ranges_from_text():

    text = "AAA BBB CCC"

    result = remove_ranges_from_text(
        text,
        [
            (4, 7)
        ]
    )

    assert result == "AAA  CCC"


# =========================================================
# TEST 08
# NO ENTITIES
# =========================================================

def test_parse_without_entities():

    text = "خبر بدون Entity"

    parsed = parse_telegram_entities(
        text,
        []
    )

    assert (
        parsed[
            "main_text"
        ]
        == text
    )

    assert (
        parsed[
            "blockquote_blocks"
        ]
        == []
    )

    assert (
        parsed[
            "expandable_blocks"
        ]
        == []
    )

    assert (
        parsed[
            "other_entities"
        ]
        == []
    )


# =========================================================
# TEST 09
# NORMAL BLOCKQUOTE
# =========================================================

def test_parse_normal_blockquote():

    text = (
        "خبر اصلی\n"
        "نقل قول"
    )

    offset = len(
        "خبر اصلی\n"
    )

    entities = [
        {
            "type": "blockquote",
            "offset": offset,
            "length": len(
                "نقل قول"
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        parsed[
            "main_text"
        ]
        == "خبر اصلی"
    )

    assert (
        len(
            parsed[
                "blockquote_blocks"
            ]
        )
        == 1
    )

    block = (
        parsed[
            "blockquote_blocks"
        ][0]
    )

    assert (
        block[
            "type"
        ]
        == "blockquote"
    )

    assert (
        block[
            "text"
        ]
        == "نقل قول"
    )

    assert (
        parsed[
            "expandable_blocks"
        ]
        == []
    )


# =========================================================
# TEST 10
# EXPANDABLE BLOCKQUOTE
# =========================================================

def test_parse_expandable_blockquote():

    text = (
        "خبر\n"
        "تحلیل تکمیلی"
    )

    offset = len(
        "خبر\n"
    )

    entities = [
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": offset,
            "length": len(
                "تحلیل تکمیلی"
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        parsed[
            "main_text"
        ]
        == "خبر"
    )

    assert (
        parsed[
            "blockquote_blocks"
        ]
        == []
    )

    assert (
        len(
            parsed[
                "expandable_blocks"
            ]
        )
        == 1
    )

    assert (
        parsed[
            "expandable_blocks"
        ][0][
            "text"
        ]
        == "تحلیل تکمیلی"
    )


# =========================================================
# TEST 11
# NORMAL + EXPANDABLE SEPARATED
# =========================================================

def test_normal_and_expandable_are_separated():

    text = (
        "تیتر\n"
        "بلوک عادی\n"
        "بلوک بازشونده"
    )

    normal_text = (
        "بلوک عادی"
    )

    expandable_text = (
        "بلوک بازشونده"
    )

    normal_start = (
        text.index(
            normal_text
        )
    )

    expandable_start = (
        text.index(
            expandable_text
        )
    )

    entities = [
        {
            "type": "blockquote",
            "offset": normal_start,
            "length": len(
                normal_text
            )
        },
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": expandable_start,
            "length": len(
                expandable_text
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        len(
            parsed[
                "blockquote_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            parsed[
                "expandable_blocks"
            ]
        )
        == 1
    )


# =========================================================
# TEST 12
# BLOCKQUOTE OFFSET PRESERVED
# =========================================================

def test_blockquote_offset_and_length_preserved():

    text = "AAA BBB"

    entity = {
        "type": "blockquote",
        "offset": 4,
        "length": 3
    }

    parsed = parse_telegram_entities(
        text,
        [
            entity
        ]
    )

    block = (
        parsed[
            "blockquote_blocks"
        ][0]
    )

    assert (
        block[
            "offset"
        ]
        == 4
    )

    assert (
        block[
            "length"
        ]
        == 3
    )


# =========================================================
# TEST 13
# OTHER ENTITY STAYS IN MAIN TEXT
# =========================================================

def test_other_entity_remains_in_main_text():

    text = "سلام دنیا"

    entities = [
        {
            "type": "bold",
            "offset": 0,
            "length": 4
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        parsed[
            "main_text"
        ]
        == text
    )

    assert (
        len(
            parsed[
                "other_entities"
            ]
        )
        == 1
    )


# =========================================================
# TEST 14
# OTHER ENTITY EXTRA DATA PRESERVED
# =========================================================

def test_text_link_extra_data_preserved():

    text = "لینک"

    entities = [
        {
            "type": "text_link",
            "offset": 0,
            "length": 4,
            "url": (
                "https://example.com"
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    entity = (
        parsed[
            "other_entities"
        ][0]
    )

    assert (
        entity[
            "url"
        ]
        == "https://example.com"
    )


# =========================================================
# TEST 15
# EMOJI BEFORE BLOCKQUOTE
# =========================================================

def test_emoji_before_blockquote_utf16():

    text = (
        "خبر 😀\n"
        "تحلیل"
    )

    block_text = "تحلیل"

    python_start = (
        text.index(
            block_text
        )
    )

    positions = (
        build_utf16_positions(
            text
        )
    )

    utf16_start = (
        positions[
            python_start
        ]
    )

    entities = [
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": (
                utf16_start
            ),
            "length": len(
                block_text
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        parsed[
            "expandable_blocks"
        ][0][
            "text"
        ]
        == block_text
    )

    assert (
        "تحلیل"
        not in parsed[
            "main_text"
        ]
    )


# =========================================================
# TEST 16
# NESTED ENTITY INSIDE BLOCKQUOTE
# =========================================================

def test_nested_entity_inside_blockquote_does_not_restore_text():

    text = (
        "خبر\n"
        "تحلیل مهم"
    )

    block_text = (
        "تحلیل مهم"
    )

    block_start = (
        text.index(
            block_text
        )
    )

    bold_start = (
        text.index(
            "مهم"
        )
    )

    entities = [
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": block_start,
            "length": len(
                block_text
            )
        },
        {
            "type": "bold",
            "offset": bold_start,
            "length": len(
                "مهم"
            )
        }
    ]

    parsed = parse_telegram_entities(
        text,
        entities
    )

    assert (
        parsed[
            "main_text"
        ]
        == "خبر"
    )

    assert (
        len(
            parsed[
                "expandable_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            parsed[
                "other_entities"
            ]
        )
        == 1
    )


# =========================================================
# TEST 17
# HTML ESCAPE
# =========================================================

def test_escape_html():

    text = (
        '<tag attr="x">'
        '&'
        "</tag>"
    )

    escaped = escape_html(
        text
    )

    assert (
        "&lt;tag"
        in escaped
    )

    assert (
        "&amp;"
        in escaped
    )

    assert (
        "&quot;x&quot;"
        in escaped
    )


# =========================================================
# TEST 18
# NORMAL BLOCKQUOTE HTML
# =========================================================

def test_build_normal_blockquote_html():

    result = (
        build_blockquote_html(
            "متن"
        )
    )

    assert (
        result
        == (
            "<blockquote>"
            "متن"
            "</blockquote>"
        )
    )


# =========================================================
# TEST 19
# EXPANDABLE BLOCKQUOTE HTML
# =========================================================

def test_build_expandable_blockquote_html():

    result = (
        build_blockquote_html(
            "تحلیل",
            expandable=True
        )
    )

    assert (
        result
        == (
            "<blockquote expandable>"
            "تحلیل"
            "</blockquote>"
        )
    )


# =========================================================
# TEST 20
# BLOCKQUOTE HTML ESCAPES CONTENT
# =========================================================

def test_blockquote_html_escapes_content():

    result = (
        build_blockquote_html(
            "<b>unsafe</b>",
            expandable=True
        )
    )

    assert (
        "<b>unsafe</b>"
        not in result
    )

    assert (
        "&lt;b&gt;unsafe&lt;/b&gt;"
        in result
    )


# =========================================================
# TEST 21
# BUILD BOLD ENTITY
# =========================================================

def test_build_bold_entity_html():

    result = (
        build_entity_html(
            "bold",
            "سلام"
        )
    )

    assert (
        result
        == "<b>سلام</b>"
    )


# =========================================================
# TEST 22
# BUILD TEXT LINK
# =========================================================

def test_build_text_link_entity_html():

    result = (
        build_entity_html(
            "text_link",
            "کلیک",
            {
                "url": (
                    "https://example.com"
                )
            }
        )
    )

    assert (
        '<a href="https://example.com">'
        in result
    )

    assert (
        "کلیک"
        in result
    )


# =========================================================
# TEST 23
# PRE HTML
# =========================================================

def test_build_pre_html_with_language():

    result = (
        build_pre_html(
            'print("hello")',
            "python"
        )
    )

    assert (
        '<code class="language-python">'
        in result
    )

    assert (
        "&quot;hello&quot;"
        in result
    )


# =========================================================
# TEST 24
# UNKNOWN ENTITY SAFE FALLBACK
# =========================================================

def test_unknown_entity_returns_escaped_text():

    result = (
        build_entity_html(
            "unknown_type",
            "<unsafe>"
        )
    )

    assert (
        result
        == "&lt;unsafe&gt;"
    )


# =========================================================
# TEST 25
# FULL HTML WITHOUT ENTITIES
# =========================================================

def test_build_full_html_without_entities():

    result = (
        build_full_html(
            "سلام دنیا",
            []
        )
    )

    assert (
        result
        == "سلام دنیا"
    )


# =========================================================
# TEST 26
# FULL HTML WITH NORMAL BLOCKQUOTE
# =========================================================

def test_build_full_html_with_normal_blockquote():

    text = (
        "خبر\n"
        "نقل قول"
    )

    entities = [
        {
            "type": "blockquote",
            "offset": len(
                "خبر\n"
            ),
            "length": len(
                "نقل قول"
            )
        }
    ]

    result = build_full_html(
        text,
        entities
    )

    assert (
        "خبر"
        in result
    )

    assert (
        "<blockquote>"
        in result
    )

    assert (
        "<blockquote expandable>"
        not in result
    )


# =========================================================
# TEST 27
# FULL HTML WITH EXPANDABLE BLOCKQUOTE
# =========================================================

def test_build_full_html_with_expandable_blockquote():

    text = (
        "خبر\n"
        "تحلیل"
    )

    entities = [
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": len(
                "خبر\n"
            ),
            "length": len(
                "تحلیل"
            )
        }
    ]

    result = build_full_html(
        text,
        entities
    )

    assert (
        "<blockquote expandable>"
        in result
    )


# =========================================================
# TEST 28
# FULL HTML BLOCKQUOTE ORDER
# =========================================================

def test_build_full_html_preserves_block_order():

    text = (
        "خبر\n"
        "اول\n"
        "دوم"
    )

    first = "اول"
    second = "دوم"

    first_start = (
        text.index(
            first
        )
    )

    second_start = (
        text.index(
            second
        )
    )

    entities = [
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": second_start,
            "length": len(
                second
            )
        },
        {
            "type": "blockquote",
            "offset": first_start,
            "length": len(
                first
            )
        }
    ]

    result = build_full_html(
        text,
        entities
    )

    first_position = (
        result.index(
            "اول"
        )
    )

    second_position = (
        result.index(
            "دوم"
        )
    )

    assert (
        first_position
        < second_position
    )


# =========================================================
# TEST 29
# EMPTY INPUT
# =========================================================

def test_empty_input_is_safe():

    parsed = (
        parse_telegram_entities(
            "",
            []
        )
    )

    assert (
        parsed[
            "main_text"
        ]
        == ""
    )

    assert (
        parsed[
            "blockquote_blocks"
        ]
        == []
    )

    assert (
        parsed[
            "expandable_blocks"
        ]
        == []
    )


# =========================================================
# TEST 30
# COMPLETE MIXED CONTENT
# =========================================================

def test_complete_mixed_entity_structure():

    text = (
        "تیتر 😀\n"
        "متن اصلی\n"
        "نقل قول\n"
        "تحلیل تکمیلی"
    )

    normal_block = (
        "نقل قول"
    )

    expandable_block = (
        "تحلیل تکمیلی"
    )

    positions = (
        build_utf16_positions(
            text
        )
    )

    normal_python_start = (
        text.index(
            normal_block
        )
    )

    expandable_python_start = (
        text.index(
            expandable_block
        )
    )

    normal_offset = (
        positions[
            normal_python_start
        ]
    )

    expandable_offset = (
        positions[
            expandable_python_start
        ]
    )

    entities = [
        {
            "type": "bold",
            "offset": 0,
            "length": 4
        },
        {
            "type": "blockquote",
            "offset": normal_offset,
            "length": len(
                normal_block
            )
        },
        {
            "type": (
                "expandable_blockquote"
            ),
            "offset": (
                expandable_offset
            ),
            "length": len(
                expandable_block
            )
        }
    ]

    parsed = (
        parse_telegram_entities(
            text,
            entities
        )
    )

    assert (
        "متن اصلی"
        in parsed[
            "main_text"
        ]
    )

    assert (
        normal_block
        not in parsed[
            "main_text"
        ]
    )

    assert (
        expandable_block
        not in parsed[
            "main_text"
        ]
    )

    assert (
        len(
            parsed[
                "blockquote_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            parsed[
                "expandable_blocks"
            ]
        )
        == 1
    )

    assert (
        len(
            parsed[
                "other_entities"
            ]
        )
        == 1
    )
