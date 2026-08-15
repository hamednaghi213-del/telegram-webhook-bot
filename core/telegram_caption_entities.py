import logging

from typing import (
    Dict,
    List,
    Any,
    Optional,
    Tuple
)

from core.cleaner import (
    clean_text
)


logger = logging.getLogger(__name__)


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


# =========================================================
# BLOCK CLEANER
# =========================================================

def normalize_block_text(
    text: Optional[str]
) -> str:
    """
    متن Blockquote را قبل از ساخت Caption Entity
    از Cleaner اصلی پروژه عبور می‌دهد.
    """

    text = normalize_text(
        text
    )

    if not text:
        return ""

    try:

        cleaned = clean_text(
            text
        )

        return normalize_text(
            cleaned
        )

    except Exception as e:

        logger.exception(
            f"❌ Telegram caption entity "
            f"block cleaning failed | {e}"
        )

        return text


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

    ترتیب نهایی:

        main_text

        blockquote / expandable_blockquote


        branding

    نکته مهم:
    اگر Blockquote وجود داشته باشد، Branding با سه newline
    از آن جدا می‌شود تا Telegram آن را به‌عنوان پاراگراف
    مستقل رندر کند.

    هیچ HTML استفاده نمی‌شود.
    هیچ parse_mode استفاده نمی‌شود.
    Branding خارج از تمام Entityها باقی می‌ماند.
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
    # BLOCKQUOTES
    # =====================================================

    for block in blocks:

        block_text = normalize_text(
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
    #
    # اگر Blockquote وجود دارد:
    # سه newline
    #
    # اگر Blockquote وجود ندارد:
    # همان دو newline قبلی
    #
    # هیچ RLM / LRM / Direction Mark استفاده نمی‌شود.
    # =====================================================

    if branding:

        if caption_parts:

            if blocks:

                caption_parts.append(
                    "\n\n\n"
                )

                current_length += 3

            else:

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
    # CAPTION ENTITIES
    # =====================================================

    caption_entities: List[
        Dict[str, Any]
    ] = []

    for (
        entity_type,
        start_index,
        end_index
    ) in block_ranges:

        entity = (
            build_message_entity(
                entity_type,
                caption,
                start_index,
                end_index
            )
        )

        if (
            entity.get(
                "length",
                0
            )
            > 0
        ):

            caption_entities.append(
                entity
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
    بررسی می‌کند Entityها از محدوده UTF-16
    کپشن خارج نشده باشند.
    """

    caption = normalize_text(
        caption
    )

    caption_utf16_length = (
        utf16_length(
            caption
        )
    )

    previous_end = 0

    for entity in (
        entities
        or []
    ):

        try:

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

        except (
            TypeError,
            ValueError
        ):

            return False

        if offset < 0:
            return False

        if length <= 0:
            return False

        entity_end = (
            offset
            + length
        )

        if (
            entity_end
            > caption_utf16_length
        ):

            return False

        if offset < previous_end:
            return False

        previous_end = (
            entity_end
        )

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
            "caption_entities": [
                {
                    "type": "expandable_blockquote",
                    "offset": ...,
                    "length": ...
                }
            ]
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

    caption = (
        result[
            "caption"
        ]
    )

    entities = (
        result[
            "caption_entities"
        ]
    )

    if not validate_caption_entities(
        caption,
        entities
    ):

        raise ValueError(
            "Invalid Telegram caption entities"
        )

    logger.info(
        f"✅ Telegram caption entities built | "
        f"caption={len(caption)} | "
        f"entities={len(entities)}"
    )

    return result
