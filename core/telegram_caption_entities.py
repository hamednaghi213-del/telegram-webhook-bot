from typing import Dict, List, Any, Optional, Tuple


# =========================================================
# UTF-16 HELPERS
# =========================================================

def utf16_length(
    text: str
) -> int:
    """
    Telegram offset/length را بر اساس UTF-16 code units
    محاسبه می‌کند.
    """

    if not text:
        return 0

    return (
        len(
            text.encode(
                "utf-16-le"
            )
        )
        // 2
    )


def python_index_to_utf16_offset(
    text: str,
    index: int
) -> int:
    """
    Python character index را به UTF-16 offset
    موردنیاز Telegram تبدیل می‌کند.
    """

    if not text:
        return 0

    index = max(
        0,
        min(
            index,
            len(text)
        )
    )

    return utf16_length(
        text[:index]
    )


# =========================================================
# BASIC NORMALIZATION
# =========================================================

def normalize_text(
    text: Optional[str]
) -> str:

    if not text:
        return ""

    return str(
        text
    ).strip()


def normalize_block_text(
    text: Optional[str]
) -> str:

    return normalize_text(
        text
    )


# =========================================================
# BLOCK COLLECTION
# =========================================================

def combine_blocks(
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None
) -> List[Dict[str, Any]]:
    """
    Blockquote و Expandable Blockquote را بر اساس offset
    مرتب می‌کند.

    خروجی داخلی:

        {
            "type": "blockquote",
            "text": "...",
            "offset": 100
        }

        {
            "type": "expandable_blockquote",
            "text": "...",
            "offset": 200
        }
    """

    result: List[
        Dict[str, Any]
    ] = []

    for block in (
        blockquote_blocks
        or []
    ):

        text = normalize_block_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        result.append({
            "type": "blockquote",
            "text": text,
            "offset": block.get(
                "offset",
                0
            )
        })

    for block in (
        expandable_blocks
        or []
    ):

        text = normalize_block_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        result.append({
            "type": "expandable_blockquote",
            "text": text,
            "offset": block.get(
                "offset",
                0
            )
        })

    result.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    return result


# =========================================================
# ENTITY BUILDER
# =========================================================

def build_message_entity(
    entity_type: str,
    caption: str,
    start_index: int,
    end_index: int
) -> Dict[str, Any]:
    """
    MessageEntity استاندارد Telegram را می‌سازد.

    offset و length به UTF-16 تبدیل می‌شوند.
    """

    start_offset = (
        python_index_to_utf16_offset(
            caption,
            start_index
        )
    )

    end_offset = (
        python_index_to_utf16_offset(
            caption,
            end_index
        )
    )

    return {
        "type": entity_type,
        "offset": start_offset,
        "length": (
            end_offset
            - start_offset
        )
    }


# =========================================================
# CAPTION BUILDER
# =========================================================

def build_plain_caption_with_entities(
    main_text: str,
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    branding: str = ""
) -> Dict[str, Any]:
    """
    کپشن Plain Text تولید می‌کند و Entityهای Telegram
    را جداگانه برمی‌گرداند.

    ترتیب:

        main_text

        blockquote / expandable

        branding

    هیچ HTML و هیچ parse_mode استفاده نمی‌شود.
    """

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    blocks = combine_blocks(
        blockquote_blocks,
        expandable_blocks
    )

    caption_parts: List[str] = []

    block_ranges: List[
        Tuple[
            str,
            int,
            int
        ]
    ] = []

    current_length = 0

    # =====================================================
    # MAIN TEXT
    # =====================================================

    if main_text:

        caption_parts.append(
            main_text
        )

        current_length += len(
            main_text
        )

    # =====================================================
    # BLOCKS
    # =====================================================

    for block in blocks:

        block_text = normalize_block_text(
            block.get(
                "text",
                ""
            )
        )

        if not block_text:
            continue

        if caption_parts:

            caption_parts.append(
                "\n\n"
            )

            current_length += 2

        start_index = (
            current_length
        )

        caption_parts.append(
            block_text
        )

        current_length += len(
            block_text
        )

        end_index = (
            current_length
        )

        block_ranges.append(
            (
                block.get(
                    "type",
                    "blockquote"
                ),
                start_index,
                end_index
            )
        )

    # =====================================================
    # BRANDING
    # =====================================================

    if branding:

        if caption_parts:

            caption_parts.append(
                "\n\n"
            )

            current_length += 2

        caption_parts.append(
            branding
        )

        current_length += len(
            branding
        )

    caption = "".join(
        caption_parts
    )

    # =====================================================
    # ENTITIES
    # =====================================================

    caption_entities: List[
        Dict[str, Any]
    ] = []

    for (
        entity_type,
        start_index,
        end_index
    ) in block_ranges:

        caption_entities.append(
            build_message_entity(
                entity_type,
                caption,
                start_index,
                end_index
            )
        )

    return {
        "caption": caption,
        "caption_entities": caption_entities
    }


# =========================================================
# VALIDATION
# =========================================================

def validate_caption_entities(
    caption: str,
    entities: List[
        Dict[str, Any]
    ]
) -> bool:
    """
    بررسی ساده برای جلوگیری از Entity خراب.

    Entity نباید از طول UTF-16 کپشن خارج شود.
    """

    caption_utf16_length = (
        utf16_length(
            caption
        )
    )

    for entity in (
        entities
        or []
    ):

        offset = int(
            entity.get(
                "offset",
                0
            )
        )

        length = int(
            entity.get(
                "length",
                0
            )
        )

        if offset < 0:
            return False

        if length < 0:
            return False

        if (
            offset
            + length
            > caption_utf16_length
        ):

            return False

    return True


# =========================================================
# PUBLIC API
# =========================================================

def build_telegram_caption_entities(
    main_text: str,
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    branding: str = ""
) -> Dict[str, Any]:
    """
    API اصلی ماژول.

    خروجی:

        {
            "caption": "...",
            "caption_entities": [...]
        }
    """

    result = (
        build_plain_caption_with_entities(
            main_text=main_text,
            blockquote_blocks=blockquote_blocks,
            expandable_blocks=expandable_blocks,
            branding=branding
        )
    )

    caption = result[
        "caption"
    ]

    entities = result[
        "caption_entities"
    ]

    if not validate_caption_entities(
        caption,
        entities
    ):

        raise ValueError(
            "Invalid Telegram caption entities"
        )

    return result
