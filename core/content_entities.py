import bisect
import html
import logging

from typing import (
    Optional,
    Dict,
    Any,
    List,
    Tuple
)

logger = logging.getLogger(__name__)


# =========================================================
# UTF-16 MAPPING
# =========================================================

def build_utf16_positions(
    text: str
) -> List[int]:
    """
    ساخت جدول موقعیت‌های UTF-16 برای متن.

    خروجی:
    هر index پایتون -> موقعیت متناظر در UTF-16 code units

    مثال:
        Python index:      0  1  2 ...
        UTF-16 position:   0  1  3 ...

    برای Emojiهایی که دو UTF-16 code unit مصرف می‌کنند
    ضروری است.
    """

    if not text:
        return [0]

    positions: List[int] = []

    current_position = 0

    for char in text:

        positions.append(
            current_position
        )

        current_position += (
            len(
                char.encode(
                    "utf-16-le"
                )
            )
            // 2
        )

    # موقعیت انتهای متن
    positions.append(
        current_position
    )

    return positions


def utf16_to_python_index(
    text: str,
    offset: int,
    utf16_positions: Optional[
        List[int]
    ] = None
) -> int:
    """
    تبدیل offset مبتنی بر UTF-16 Telegram
    به index استاندارد Python.

    اگر offset داخل یک surrogate pair قرار بگیرد،
    index کاراکتر مربوطه برگردانده می‌شود.
    """

    if not text:

        return 0

    if offset <= 0:

        return 0

    if utf16_positions is None:

        utf16_positions = (
            build_utf16_positions(
                text
            )
        )

    total_utf16_units = (
        utf16_positions[-1]
    )

    if offset >= total_utf16_units:

        return len(text)

    index = bisect.bisect_left(
        utf16_positions,
        offset
    )

    return min(
        index,
        len(text)
    )


def utf16_range_to_python(
    text: str,
    offset: int,
    length: int,
    utf16_positions: Optional[
        List[int]
    ] = None
) -> Tuple[int, int]:
    """
    تبدیل offset + length تلگرام
    به start/end پایتون.
    """

    if utf16_positions is None:

        utf16_positions = (
            build_utf16_positions(
                text
            )
        )

    start = utf16_to_python_index(
        text,
        offset,
        utf16_positions
    )

    end = utf16_to_python_index(
        text,
        offset + length,
        utf16_positions
    )

    start = max(
        0,
        min(
            start,
            len(text)
        )
    )

    end = max(
        start,
        min(
            end,
            len(text)
        )
    )

    return (
        start,
        end
    )


# =========================================================
# RANGE MERGING
# =========================================================

def merge_ranges(
    ranges: List[
        Tuple[int, int]
    ]
) -> List[
    Tuple[int, int]
]:
    """
    ادغام Rangeهای همپوشان.

    این تابع برای حذف Blockquoteها
    از main_text استفاده می‌شود.

    Entityهای nested نباید باعث حذف دوباره
    یا خرابی main_text شوند.
    """

    if not ranges:

        return []

    normalized = sorted(
        (
            (
                max(0, start),
                max(0, end)
            )
            for start, end
            in ranges
            if end > start
        ),
        key=lambda item: (
            item[0],
            item[1]
        )
    )

    if not normalized:

        return []

    merged: List[
        List[int]
    ] = []

    for start, end in normalized:

        if not merged:

            merged.append(
                [start, end]
            )

            continue

        last_start, last_end = (
            merged[-1]
        )

        if start <= last_end:

            merged[-1][1] = max(
                last_end,
                end
            )

        else:

            merged.append(
                [start, end]
            )

    return [
        (
            start,
            end
        )
        for start, end
        in merged
    ]


# =========================================================
# MAIN TEXT BUILDER
# =========================================================

def remove_ranges_from_text(
    text: str,
    ranges: List[
        Tuple[int, int]
    ]
) -> str:
    """
    حذف Rangeهای مشخص از متن
    بدون دست‌زدن به سایر بخش‌ها.
    """

    if not text:

        return ""

    merged_ranges = merge_ranges(
        ranges
    )

    if not merged_ranges:

        return text.strip()

    parts: List[str] = []

    cursor = 0

    for start, end in merged_ranges:

        if start > cursor:

            parts.append(
                text[
                    cursor:start
                ]
            )

        cursor = max(
            cursor,
            end
        )

    if cursor < len(text):

        parts.append(
            text[
                cursor:
            ]
        )

    return "".join(
        parts
    ).strip()


# =========================================================
# TELEGRAM ENTITY PARSER
# =========================================================

def parse_telegram_entities(
    text: str,
    entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> Dict[str, Any]:
    """
    پردازش Entityهای Telegram.

    قرارداد خروجی:

    {
        "main_text": "...",

        "blockquote_blocks": [
            {
                "type": "blockquote",
                "text": "...",
                "offset": 0,
                "length": 10
            }
        ],

        "expandable_blocks": [
            {
                "type": "expandable_blockquote",
                "text": "...",
                "offset": 20,
                "length": 50
            }
        ],

        "other_entities": [
            ...
        ]
    }

    قوانین:

    - Blockquote معمولی و Expandable جدا هستند.
    - offset و length اصلی Telegram حفظ می‌شوند.
    - متن Blockquoteها از main_text حذف می‌شود.
    - سایر Entityها در main_text باقی می‌مانند.
    - nested entityها باعث خراب شدن متن نمی‌شوند.
    - UTF-16 به Python index تبدیل می‌شود.
    """

    if not text:

        return {
            "main_text": "",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }

    if not entities:

        return {
            "main_text": text,
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }

    try:

        utf16_positions = (
            build_utf16_positions(
                text
            )
        )

        sorted_entities = sorted(
            entities,
            key=lambda entity: (
                entity.get(
                    "offset",
                    0
                ),
                entity.get(
                    "length",
                    0
                )
            )
        )

        blockquote_blocks: List[
            Dict[str, Any]
        ] = []

        expandable_blocks: List[
            Dict[str, Any]
        ] = []

        other_entities: List[
            Dict[str, Any]
        ] = []

        consumed_ranges: List[
            Tuple[int, int]
        ] = []

        logger.info(
            f"🧩 Telegram entities | "
            f"count={len(sorted_entities)}"
        )

        for entity in sorted_entities:

            entity_type = (
                entity.get(
                    "type",
                    ""
                )
                or ""
            )

            offset = int(
                entity.get(
                    "offset",
                    0
                )
                or 0
            )

            length = int(
                entity.get(
                    "length",
                    0
                )
                or 0
            )

            if length <= 0:

                logger.debug(
                    f"⏭️ Invalid entity ignored | "
                    f"type={entity_type} | "
                    f"length={length}"
                )

                continue

            start, end = (
                utf16_range_to_python(
                    text,
                    offset,
                    length,
                    utf16_positions
                )
            )

            if end <= start:

                logger.warning(
                    f"⚠️ Invalid entity range | "
                    f"type={entity_type} | "
                    f"offset={offset} | "
                    f"length={length}"
                )

                continue

            entity_text = (
                text[
                    start:end
                ]
            )

            logger.info(
                f"📝 Entity detected | "
                f"type={entity_type} | "
                f"offset={offset} | "
                f"length={length} | "
                f"python_range="
                f"{start}:{end}"
            )

            # =================================================
            # NORMAL BLOCKQUOTE
            # =================================================

            if entity_type == "blockquote":

                blockquote_blocks.append({
                    "type": (
                        "blockquote"
                    ),

                    "text": (
                        entity_text
                    ),

                    "offset": (
                        offset
                    ),

                    "length": (
                        length
                    )
                })

                consumed_ranges.append(
                    (
                        start,
                        end
                    )
                )

                continue

            # =================================================
            # EXPANDABLE BLOCKQUOTE
            # =================================================

            if (
                entity_type
                == "expandable_blockquote"
            ):

                expandable_blocks.append({
                    "type": (
                        "expandable_blockquote"
                    ),

                    "text": (
                        entity_text
                    ),

                    "offset": (
                        offset
                    ),

                    "length": (
                        length
                    )
                })

                consumed_ranges.append(
                    (
                        start,
                        end
                    )
                )

                continue

            # =================================================
            # OTHER ENTITY
            # =================================================

            stored_entity = {
                "type": (
                    entity_type
                ),

                "text": (
                    entity_text
                ),

                "offset": (
                    offset
                ),

                "length": (
                    length
                )
            }

            # اطلاعات اضافه Entity
            # مثل url/user/language/custom_emoji_id
            for key, value in (
                entity.items()
            ):

                if key in (
                    "type",
                    "offset",
                    "length"
                ):

                    continue

                stored_entity[
                    key
                ] = value

            other_entities.append(
                stored_entity
            )

        # =================================================
        # MAIN TEXT
        # =================================================

        main_text = (
            remove_ranges_from_text(
                text,
                consumed_ranges
            )
        )

        logger.info(
            f"✅ Entity parsing completed | "
            f"main_length="
            f"{len(main_text)} | "
            f"blockquote="
            f"{len(blockquote_blocks)} | "
            f"expandable="
            f"{len(expandable_blocks)} | "
            f"other="
            f"{len(other_entities)}"
        )

        return {
            "main_text": (
                main_text
            ),

            "blockquote_blocks": (
                blockquote_blocks
            ),

            "expandable_blocks": (
                expandable_blocks
            ),

            "other_entities": (
                other_entities
            )
        }

    except Exception as e:

        logger.exception(
            f"❌ Telegram entity parsing failed | "
            f"{e}"
        )

        # =================================================
        # BACKWARD SAFE FALLBACK
        # =================================================

        return {
            "main_text": (
                text
            ),

            "blockquote_blocks": [],

            "expandable_blocks": [],

            "other_entities": []
        }


# =========================================================
# HTML ESCAPE
# =========================================================

def escape_html(
    text: str
) -> str:
    """
    Escape امن متن برای Telegram HTML.
    """

    if not text:

        return ""

    return html.escape(
        str(text),
        quote=True
    )


# =========================================================
# BLOCKQUOTE HTML
# =========================================================

def build_blockquote_html(
    text: str,
    expandable: bool = False
) -> str:
    """
    ساخت HTML استاندارد Telegram Blockquote.

    Normal:

        <blockquote>...</blockquote>

    Expandable:

        <blockquote expandable>...</blockquote>
    """

    if not text:

        return ""

    escaped_text = (
        escape_html(
            text
        )
    )

    if expandable:

        return (
            "<blockquote expandable>"
            f"{escaped_text}"
            "</blockquote>"
        )

    return (
        "<blockquote>"
        f"{escaped_text}"
        "</blockquote>"
    )


# =========================================================
# PRE HTML
# =========================================================

def build_pre_html(
    text: str,
    language: Optional[
        str
    ] = None
) -> str:
    """
    ساخت HTML برای Telegram pre/code.
    """

    escaped_text = (
        escape_html(
            text
        )
    )

    if not language:

        return (
            "<pre>"
            f"{escaped_text}"
            "</pre>"
        )

    language = str(
        language
    ).strip().lower()

    safe_language = "".join(
        char
        for char in language
        if (
            char.isalnum()
            or char in (
                "_",
                "-",
                "+"
            )
        )
    )

    if not safe_language:

        return (
            "<pre>"
            f"{escaped_text}"
            "</pre>"
        )

    return (
        "<pre>"
        f'<code class="language-{safe_language}">'
        f"{escaped_text}"
        "</code>"
        "</pre>"
    )


# =========================================================
# ENTITY HTML
# =========================================================

def build_entity_html(
    entity_type: str,
    text: str,
    extra_data: Optional[
        Dict[str, Any]
    ] = None
) -> str:
    """
    تبدیل یک Entity به Telegram HTML.

    این تابع برای توسعه آینده حفظ شده است.
    """

    if not text:

        return ""

    if not entity_type:

        return escape_html(
            text
        )

    extra_data = (
        extra_data
        or {}
    )

    entity_type = (
        str(
            entity_type
        )
        .strip()
        .lower()
    )

    escaped_text = (
        escape_html(
            text
        )
    )

    if entity_type == "bold":

        return (
            f"<b>{escaped_text}</b>"
        )

    if entity_type == "italic":

        return (
            f"<i>{escaped_text}</i>"
        )

    if entity_type == "underline":

        return (
            f"<u>{escaped_text}</u>"
        )

    if entity_type == "strikethrough":

        return (
            f"<s>{escaped_text}</s>"
        )

    if entity_type == "spoiler":

        return (
            '<span class="tg-spoiler">'
            f"{escaped_text}"
            "</span>"
        )

    if entity_type == "code":

        return (
            f"<code>{escaped_text}</code>"
        )

    if entity_type == "pre":

        return build_pre_html(
            text,
            extra_data.get(
                "language"
            )
        )

    if entity_type == "text_link":

        url = (
            extra_data.get(
                "url",
                ""
            )
            or ""
        )

        if not url:

            return escaped_text

        escaped_url = (
            escape_html(
                url
            )
        )

        return (
            f'<a href="{escaped_url}">'
            f"{escaped_text}"
            "</a>"
        )

    if entity_type == "text_mention":

        user = (
            extra_data.get(
                "user"
            )
            or {}
        )

        user_id = (
            user.get(
                "id"
            )
            if isinstance(
                user,
                dict
            )
            else None
        )

        # Backward compatibility
        if not user_id:

            user_id = (
                extra_data.get(
                    "user_id"
                )
            )

        if not user_id:

            return escaped_text

        return (
            f'<a href="tg://user?id={user_id}">'
            f"{escaped_text}"
            "</a>"
        )

    if entity_type == "email":

        escaped_email = (
            escape_html(
                text
            )
        )

        return (
            f'<a href="mailto:{escaped_email}">'
            f"{escaped_text}"
            "</a>"
        )

    if entity_type == "url":

        escaped_url = (
            escape_html(
                text
            )
        )

        return (
            f'<a href="{escaped_url}">'
            f"{escaped_text}"
            "</a>"
        )

    # =====================================================
    # UNKNOWN / CURRENTLY UNSUPPORTED
    # =====================================================
    #
    # متن از بین نمی‌رود.
    # فقط Formatting آن Entity اعمال نمی‌شود.
    # =====================================================

    return escaped_text


# =========================================================
# BUILD FULL HTML
# =========================================================

def build_full_html(
    text: str,
    entities: Optional[
        List[Dict[str, Any]]
    ] = None,
    include_blockquotes: bool = True
) -> str:
    """
    Builder سازگار با کدهای قدیمی.

    نکته:

    مسیر اصلی جدید پروژه باید از:

        parse_telegram_entities()
            ↓
        Formatter
            ↓
        Caption Manager

    استفاده کند.

    این تابع فقط برای Backward Compatibility
    و مسیرهای متنی قدیمی حفظ شده است.

    Entityهای Blockquote در انتهای خروجی قرار می‌گیرند.
    """

    if not text:

        return ""

    entities = list(
        entities
        or []
    )

    parsed = (
        parse_telegram_entities(
            text,
            entities
        )
    )

    # =====================================================
    # MAIN
    # =====================================================
    #
    # فعلاً متن اصلی را HTML Escape می‌کنیم.
    #
    # سایر Entityهای inline در مسیر جدید
    # هنوز به Formatter متصل نشده‌اند.
    # =====================================================

    main_html = (
        escape_html(
            parsed.get(
                "main_text",
                ""
            )
        )
    )

    if not include_blockquotes:

        return main_html

    blocks: List[
        Dict[str, Any]
    ] = []

    for block in (
        parsed.get(
            "blockquote_blocks",
            []
        )
    ):

        blocks.append({
            "offset": (
                block.get(
                    "offset",
                    0
                )
            ),

            "html": (
                build_blockquote_html(
                    block.get(
                        "text",
                        ""
                    ),
                    expandable=False
                )
            )
        })

    for block in (
        parsed.get(
            "expandable_blocks",
            []
        )
    ):

        blocks.append({
            "offset": (
                block.get(
                    "offset",
                    0
                )
            ),

            "html": (
                build_blockquote_html(
                    block.get(
                        "text",
                        ""
                    ),
                    expandable=True
                )
            )
        })

    blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    block_html_parts = [
        item.get(
            "html",
            ""
        )
        for item in blocks
        if item.get(
            "html"
        )
    ]

    if (
        main_html
        and block_html_parts
    ):

        return (
            main_html
            + "\n\n"
            + "\n\n".join(
                block_html_parts
            )
        )

    if block_html_parts:

        return "\n\n".join(
            block_html_parts
        )

    return main_html
