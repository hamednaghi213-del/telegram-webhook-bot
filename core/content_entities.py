import logging
import html

logger = logging.getLogger(__name__)


# =========================================================
# TELEGRAM ENTITY PARSER
# =========================================================

def parse_telegram_entities(text, entities):
    """
    پردازش Entityهای دریافتی از Telegram.

    Telegram offset و length را بر اساس UTF-16
    ارسال می‌کند، بنابراین برای متن فارسی و ایموجی
    باید تبدیل UTF-16 به index پایتون به‌درستی انجام شود.

    خروجی:

    {
        "main_text": "...",
        "expandable_blocks": [
            {
                "type": "expandable_blockquote",
                "text": "..."
            }
        ],
        "other_entities": [...]
    }
    """

    if not text:
        return {
            "main_text": "",
            "expandable_blocks": [],
            "other_entities": []
        }

    if not entities:
        return {
            "main_text": text,
            "expandable_blocks": [],
            "other_entities": []
        }

    # -----------------------------------------------------
    # ساخت جدول تبدیل UTF-16 offset به Python index
    # -----------------------------------------------------

    utf16_positions = []

    current_position = 0

    for index, char in enumerate(text):
        utf16_positions.append(
            current_position
        )

        current_position += (
            len(char.encode("utf-16-le")) // 2
        )

    # موقعیت انتهای متن
    utf16_positions.append(current_position)

    def utf16_to_python_index(offset):
        """
        تبدیل offset مبتنی بر UTF-16 به index پایتون.
        """

        if offset <= 0:
            return 0

        if offset >= current_position:
            return len(text)

        # جستجوی ساده و مطمئن
        for index, position in enumerate(
            utf16_positions
        ):
            if position >= offset:
                return index

        return len(text)

    # -----------------------------------------------------
    # مرتب‌سازی Entityها
    # -----------------------------------------------------

    sorted_entities = sorted(
        entities,
        key=lambda entity: (
            entity.get("offset", 0),
            entity.get("length", 0)
        )
    )

    main_parts = []
    expandable_blocks = []
    other_entities = []

    last_python_end = 0

    # -----------------------------------------------------
    # پردازش Entityها
    # -----------------------------------------------------

    for entity in sorted_entities:

        entity_type = entity.get(
            "type",
            ""
        )

        offset = entity.get(
            "offset",
            0
        )

        length = entity.get(
            "length",
            0
        )

        if length <= 0:
            continue

        start = utf16_to_python_index(
            offset
        )

        end = utf16_to_python_index(
            offset + length
        )

        # جلوگیری از محدوده نامعتبر
        start = max(
            0,
            min(start, len(text))
        )

        end = max(
            start,
            min(end, len(text))
        )

        # -------------------------------------------------
        # Entityهایی که قبل از Entity فعلی هستند
        # -------------------------------------------------

        if start > last_python_end:
            main_parts.append(
                text[
                    last_python_end:start
                ]
            )

        entity_text = text[
            start:end
        ]

        # -------------------------------------------------
        # Blockquote
        # -------------------------------------------------

        if entity_type in (
            "blockquote",
            "expandable_blockquote"
        ):

            expandable_blocks.append({
                "type": entity_type,
                "text": entity_text
            })

        # -------------------------------------------------
        # سایر Entityها
        # -------------------------------------------------

        else:

            other_entities.append({
                "type": entity_type,
                "offset": offset,
                "length": length,
                "text": entity_text
            })

            # فعلاً Entityهای دیگر را از متن حذف نمی‌کنیم
            main_parts.append(
                entity_text
            )

        last_python_end = max(
            last_python_end,
            end
        )

    # -----------------------------------------------------
    # متن بعد از آخرین Entity
    # -----------------------------------------------------

    if last_python_end < len(text):
        main_parts.append(
            text[last_python_end:]
        )

    main_text = "".join(
        main_parts
    ).strip()

    return {
        "main_text": main_text,
        "expandable_blocks": expandable_blocks,
        "other_entities": other_entities
    }


# =========================================================
# HTML ESCAPE
# =========================================================

def escape_html(text):
    """
    Escape کردن کاراکترهای HTML برای استفاده
    امن در Telegram parse_mode=HTML.
    """

    if not text:
        return ""

    return html.escape(
        str(text),
        quote=True
    )


# =========================================================
# BUILD BLOCKQUOTE HTML
# =========================================================

def build_blockquote_html(
    text,
    expandable=False
):
    """
    تبدیل متن Blockquote به HTML قابل ارسال
    به Telegram.

    expandable=False:

        <blockquote>...</blockquote>

    expandable=True:

        <blockquote expandable>...</blockquote>
    """

    if not text:
        return ""

    escaped_text = escape_html(
        text
    )

    if expandable:
        return (
            f"<blockquote expandable>"
            f"{escaped_text}"
            f"</blockquote>"
        )

    return (
        f"<blockquote>"
        f"{escaped_text}"
        f"</blockquote>"
    )
