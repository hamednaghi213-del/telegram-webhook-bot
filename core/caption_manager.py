import logging
import re

from html import (
    escape,
    unescape
)

from typing import (
    Dict,
    List,
    Optional,
    Any
)

from core.content_entities import (
    build_blockquote_html
)

from core.cleaner import (
    clean_text
)


logger = logging.getLogger(__name__)


# =========================================================
# PLATFORM LIMITS
# =========================================================

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096

BALE_CAPTION_LIMIT = 4096
BALE_MESSAGE_LIMIT = 4096


# =========================================================
# INTERNAL SAFE LIMITS
# =========================================================

TELEGRAM_CAPTION_SAFE_LIMIT = 1000
TELEGRAM_MESSAGE_SAFE_LIMIT = 4000

BALE_CAPTION_SAFE_LIMIT = 4000
BALE_MESSAGE_SAFE_LIMIT = 4000


# =========================================================
# PUBLICATION PLAN
# =========================================================

class PublicationPlan:

    def __init__(self):

        self.telegram: Dict[str, Any] = {
            "media_caption": "",
            "media_parse_mode": None,
            "followup_messages": [],
            "blockquote_messages": [],
            "document_fallback": False
        }

        self.bale: Dict[str, Any] = {
            "media_caption": "",
            "followup_messages": [],
            "blockquote_messages": [],
            "document_fallback": False
        }

        self.text: Dict[str, Any] = {
            "telegram": {
                "messages": [],
                "blockquote_messages": []
            },
            "bale": {
                "messages": [],
                "blockquote_messages": []
            }
        }

        self.metadata: Dict[str, Any] = {
            "other_entities": []
        }

    def to_dict(self) -> Dict[str, Any]:

        return {
            "telegram": self.telegram,
            "bale": self.bale,
            "metadata": self.metadata
        }


# =========================================================
# BASIC HELPERS
# =========================================================

def normalize_text(
    text: Optional[str]
) -> str:

    if not text:
        return ""

    return str(
        text
    ).strip()


def get_text_length(
    text: Optional[str]
) -> int:

    if not text:
        return 0

    return len(
        text
    )


def append_branding(
    text: str,
    branding: str
) -> str:

    text = normalize_text(
        text
    )

    branding = normalize_text(
        branding
    )

    if not branding:
        return text

    if not text:
        return branding

    return (
        f"{text}\n\n"
        f"{branding}"
    )


# =========================================================
# TELEGRAM HTML VISIBLE LENGTH
# =========================================================

def telegram_html_visible_text(
    html_text: str
) -> str:

    if not html_text:
        return ""

    value = re.sub(
        r"<[^>]+>",
        "",
        html_text
    )

    return unescape(
        value
    )


def telegram_html_visible_length(
    html_text: str
) -> int:

    return len(
        telegram_html_visible_text(
            html_text
        )
    )


# =========================================================
# CLEAN BLOCKQUOTE TEXT
# =========================================================

def clean_blockquote_text(
    text: str
) -> str:

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
            f"❌ Blockquote cleaning failed | "
            f"{e}"
        )

        return text


# =========================================================
# LONG TEXT COMPACT MODE
# =========================================================

def compact_long_text(
    text: str
) -> str:

    text = normalize_text(
        text
    )

    if not text:
        return ""

    raw_lines = (
        text.splitlines()
    )

    content_lines: List[str] = []

    for line in raw_lines:

        stripped = (
            line.strip()
        )

        if not stripped:
            continue

        content_lines.append(
            stripped
        )

    if not content_lines:
        return ""

    title = (
        content_lines[0]
    )

    if len(content_lines) == 1:
        return title

    body_lines: List[str] = []

    for line in content_lines[1:]:

        cleaned_line = (
            line.strip()
        )

        if cleaned_line.startswith(
            "🔹"
        ):

            cleaned_line = (
                cleaned_line[
                    len("🔹"):
                ]
                .lstrip()
            )

        if not cleaned_line:
            continue

        body_lines.append(
            cleaned_line
        )

    if not body_lines:
        return title

    result = (
        title
        + "\n\n"
        + "\n".join(
            body_lines
        )
    )

    logger.info(
        f"🗜️ Long text compacted | "
        f"before={len(text)} | "
        f"after={len(result)} | "
        f"saved={len(text) - len(result)}"
    )

    return result


# =========================================================
# FIND LOGICAL SPLIT POSITION
# =========================================================

def find_split_position(
    text: str,
    limit: int
) -> int:

    if not text:
        return 0

    if limit <= 0:
        return 0

    if len(text) <= limit:
        return len(text)

    search_text = (
        text[:limit]
    )

    # =====================================================
    # PARAGRAPH
    # =====================================================

    position = (
        search_text.rfind(
            "\n\n"
        )
    )

    if position > 0:
        return position

    # =====================================================
    # LINE
    # =====================================================

    position = (
        search_text.rfind(
            "\n"
        )
    )

    if position > 0:
        return position

    # =====================================================
    # SENTENCE
    # =====================================================

    sentence_marks = (
        "؟",
        "!",
        ".",
        "?",
        "۔",
        "…"
    )

    best_sentence_position = -1

    for mark in sentence_marks:

        position = (
            search_text.rfind(
                mark
            )
        )

        if (
            position
            > best_sentence_position
        ):

            best_sentence_position = (
                position
            )

    if best_sentence_position > 0:

        return (
            best_sentence_position
            + 1
        )

    # =====================================================
    # WORD
    # =====================================================

    position = (
        search_text.rfind(
            " "
        )
    )

    if position > 0:
        return position

    # =====================================================
    # HARD CUT
    # =====================================================

    logger.warning(
        f"⚠️ Hard split required | "
        f"limit={limit} | "
        f"preview={text[:80]!r}"
    )

    return limit


# =========================================================
# SMART TEXT SPLITTER
# =========================================================

def split_text(
    text: str,
    limit: int
) -> List[str]:

    text = normalize_text(
        text
    )

    if not text:
        return []

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero"
        )

    if len(text) <= limit:

        return [
            text
        ]

    parts: List[str] = []

    remaining = text

    safety_counter = 0

    while remaining:

        safety_counter += 1

        if safety_counter > 10000:

            logger.error(
                "❌ split_text safety limit reached"
            )

            break

        if len(remaining) <= limit:

            final_part = (
                remaining.strip()
            )

            if final_part:

                parts.append(
                    final_part
                )

            break

        split_position = (
            find_split_position(
                remaining,
                limit
            )
        )

        if split_position <= 0:

            split_position = (
                limit
            )

        part = (
            remaining[
                :split_position
            ]
            .strip()
        )

        if part:

            parts.append(
                part
            )

        new_remaining = (
            remaining[
                split_position:
            ]
            .strip()
        )

        if (
            new_remaining
            == remaining
        ):

            logger.error(
                "❌ split_text made no progress"
            )

            break

        remaining = (
            new_remaining
        )

    logger.info(
        f"✂️ Text split | "
        f"original={len(text)} | "
        f"limit={limit} | "
        f"parts={len(parts)}"
    )

    return parts


# =========================================================
# SPLIT MAIN TEXT FOR MEDIA
# =========================================================

def split_for_media(
    text: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:

    text = normalize_text(
        text
    )

    result = {
        "media_caption": "",
        "followup_messages": []
    }

    if not text:
        return result

    if len(text) <= caption_limit:

        result[
            "media_caption"
        ] = text

        return result

    compact_text = (
        compact_long_text(
            text
        )
    )

    if (
        compact_text
        and len(compact_text)
        <= caption_limit
    ):

        result[
            "media_caption"
        ] = compact_text

        logger.info(
            f"🗜️ Media compact mode used | "
            f"before={len(text)} | "
            f"after={len(compact_text)}"
        )

        return result

    source_text = (
        compact_text
        or text
    )

    split_position = (
        find_split_position(
            source_text,
            caption_limit
        )
    )

    if split_position <= 0:

        split_position = (
            caption_limit
        )

    first_part = (
        source_text[
            :split_position
        ]
        .strip()
    )

    remaining = (
        source_text[
            split_position:
        ]
        .strip()
    )

    result[
        "media_caption"
    ] = first_part

    if remaining:

        result[
            "followup_messages"
        ] = (
            split_text(
                remaining,
                message_limit
            )
        )

    return result


# =========================================================
# MEDIA BRANDING PLACEMENT
# =========================================================

def place_branding(
    media_caption: str,
    followup_messages: List[str],
    branding: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:

    media_caption = normalize_text(
        media_caption
    )

    branding = normalize_text(
        branding
    )

    messages = list(
        followup_messages
        or []
    )

    if not branding:

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    if messages:

        last_message = (
            messages[-1]
        )

        combined = (
            append_branding(
                last_message,
                branding
            )
        )

        if len(combined) <= message_limit:

            messages[-1] = (
                combined
            )

        elif len(branding) <= message_limit:

            messages.append(
                branding
            )

        else:

            messages.extend(
                split_text(
                    branding,
                    message_limit
                )
            )

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    combined_caption = (
        append_branding(
            media_caption,
            branding
        )
    )

    if len(combined_caption) <= caption_limit:

        media_caption = (
            combined_caption
        )

    elif len(branding) <= message_limit:

        messages.append(
            branding
        )

    else:

        messages.extend(
            split_text(
                branding,
                message_limit
            )
        )

    return {
        "media_caption": media_caption,
        "followup_messages": messages
    }


# =========================================================
# TEXT BRANDING PLACEMENT
# =========================================================

def place_branding_in_text_messages(
    messages: List[str],
    branding: str,
    message_limit: int
) -> List[str]:

    result = list(
        messages
        or []
    )

    branding = normalize_text(
        branding
    )

    if not branding:
        return result

    if not result:

        if len(branding) <= message_limit:

            return [
                branding
            ]

        return split_text(
            branding,
            message_limit
        )

    last_message = (
        result[-1]
    )

    combined = (
        append_branding(
            last_message,
            branding
        )
    )

    if len(combined) <= message_limit:

        result[-1] = (
            combined
        )

        return result

    if len(branding) <= message_limit:

        result.append(
            branding
        )

        return result

    result.extend(
        split_text(
            branding,
            message_limit
        )
    )

    return result


# =========================================================
# TELEGRAM BLOCKQUOTE MESSAGES
# =========================================================

def create_telegram_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    combined_blocks: List[
        Dict[str, Any]
    ] = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": False
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": True
        })

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    result: List[str] = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
            continue

        expandable = bool(
            block.get(
                "expandable",
                False
            )
        )

        raw_limit = (
            TELEGRAM_MESSAGE_SAFE_LIMIT
            - 100
        )

        raw_parts = (
            split_text(
                cleaned_text,
                raw_limit
            )
        )

        for raw_part in raw_parts:

            html_message = (
                build_blockquote_html(
                    raw_part,
                    expandable=expandable
                )
            )

            if (
                telegram_html_visible_length(
                    html_message
                )
                <= TELEGRAM_MESSAGE_SAFE_LIMIT
            ):

                result.append(
                    html_message
                )

    return result


# =========================================================
# BUILD INLINE TELEGRAM BLOCKQUOTES
# =========================================================

def build_inline_telegram_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> str:

    combined_blocks: List[
        Dict[str, Any]
    ] = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": False
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": True
        })

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    html_parts: List[str] = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
            continue

        html_parts.append(
            build_blockquote_html(
                cleaned_text,
                expandable=bool(
                    block.get(
                        "expandable",
                        False
                    )
                )
            )
        )

    return "\n\n".join(
        html_parts
    )


# =========================================================
# BUILD TELEGRAM HTML MEDIA CAPTION
# =========================================================

def build_telegram_html_caption(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> str:

    parts: List[str] = []

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    if main_text:

        parts.append(
            escape(
                main_text
            )
        )

    inline_blockquotes = (
        build_inline_telegram_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if inline_blockquotes:

        parts.append(
            inline_blockquotes
        )

    if branding:

        parts.append(
            escape(
                branding
            )
        )

    return "\n\n".join(
        parts
    )


# =========================================================
# BUILD SMART EXPANDABLE MEDIA CAPTION
# =========================================================

def build_smart_expandable_media_caption(
    main_text: str,
    branding: str,
    caption_limit: int
) -> Optional[str]:
    """
    برای خبرهایی که کل متن هنوز داخل Caption جا می‌شود،
    بخشی از متن عادی و ادامه داخل Expandable قرار می‌گیرد.

    Expandable فقط ظاهر را جمع‌وجور می‌کند و محدودیت
    Telegram را افزایش نمی‌دهد.
    """

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    if not main_text:
        return None

    visible_length = (
        len(main_text)
        + (
            len(branding)
            + 2
            if branding
            else 0
        )
    )

    if visible_length > caption_limit:
        return None

    # خبر خیلی کوتاه نیازی به Expandable مصنوعی ندارد.
    if len(main_text) < 350:
        return None

    target_position = max(
        200,
        int(
            len(main_text)
            * 0.55
        )
    )

    target_position = min(
        target_position,
        len(main_text) - 1
    )

    split_position = (
        find_split_position(
            main_text,
            target_position
        )
    )

    if split_position <= 0:

        split_position = (
            target_position
        )

    normal_part = (
        main_text[
            :split_position
        ]
        .strip()
    )

    expandable_part = (
        main_text[
            split_position:
        ]
        .strip()
    )

    if (
        not normal_part
        or not expandable_part
    ):

        return None

    parts: List[str] = [
        escape(
            normal_part
        ),
        build_blockquote_html(
            expandable_part,
            expandable=True
        )
    ]

    if branding:

        parts.append(
            escape(
                branding
            )
        )

    html_caption = (
        "\n\n".join(
            parts
        )
    )

    if (
        telegram_html_visible_length(
            html_caption
        )
        > caption_limit
    ):

        return None

    logger.info(
        f"🧩 Smart expandable media caption | "
        f"normal={len(normal_part)} | "
        f"expandable={len(expandable_part)} | "
        f"visible="
        f"{telegram_html_visible_length(html_caption)}"
    )

    return html_caption


# =========================================================
# BRAND FOLLOWUPS
# =========================================================

def brand_followup_messages(
    messages: List[str],
    branding: str
) -> List[str]:

    messages = list(
        messages
        or []
    )

    branding = normalize_text(
        branding
    )

    if not messages:
        return []

    if not branding:
        return messages

    result: List[str] = []

    for message in messages:

        combined = (
            append_branding(
                message,
                branding
            )
        )

        if (
            len(combined)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            result.append(
                combined
            )

        else:

            result.append(
                message
            )

    return result


# =========================================================
# BALE BLOCKQUOTE
# =========================================================

def build_bale_blockquote(
    text: str
) -> str:

    text = normalize_text(
        text
    )

    if not text:
        return ""

    lines = (
        text.splitlines()
    )

    output_lines = []

    for line in lines:

        line = (
            line.strip()
        )

        if not line:
            continue

        output_lines.append(
            f"▌ {line}"
        )

    return "\n".join(
        output_lines
    )


def create_bale_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    combined_blocks = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            )
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            )
        })

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    result = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
            continue

        raw_limit = (
            BALE_MESSAGE_SAFE_LIMIT
            - 200
        )

        raw_parts = (
            split_text(
                cleaned_text,
                raw_limit
            )
        )

        for raw_part in raw_parts:

            bale_message = (
                build_bale_blockquote(
                    raw_part
                )
            )

            if (
                len(bale_message)
                <= BALE_MESSAGE_SAFE_LIMIT
            ):

                result.append(
                    bale_message
                )

                continue

            retry_parts = (
                split_text(
                    raw_part,
                    max(
                        500,
                        raw_limit // 2
                    )
                )
            )

            for retry_part in retry_parts:

                retry_message = (
                    build_bale_blockquote(
                        retry_part
                    )
                )

                if (
                    len(retry_message)
                    <= BALE_MESSAGE_LIMIT
                ):

                    result.append(
                        retry_message
                    )

    return result


# =========================================================
# TELEGRAM MEDIA PLAN
# =========================================================

def create_telegram_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    plan = {
        "media_caption": "",
        "media_parse_mode": None,
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    has_source_blockquotes = bool(
        blockquote_blocks
        or expandable_blocks
    )

    # =====================================================
    # CASE 1
    # SOURCE HAS BLOCKQUOTE / EXPANDABLE
    # =====================================================

    if has_source_blockquotes:

        # -------------------------------------------------
        # NORMAL FULL VERSION
        # -------------------------------------------------

        normal_html_caption = (
            build_telegram_html_caption(
                main_text,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            normal_html_caption
            and telegram_html_visible_length(
                normal_html_caption
            )
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        ):

            plan[
                "media_caption"
            ] = normal_html_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🧩 Source blockquote preserved inline | "
                f"visible="
                f"{telegram_html_visible_length(normal_html_caption)}"
            )

            return plan

        # -------------------------------------------------
        # COMPACT MAIN + SOURCE BLOCKQUOTE
        # -------------------------------------------------

        compact_main = (
            compact_long_text(
                main_text
            )
        )

        compact_source = (
            compact_main
            or main_text
        )

        compact_html_caption = (
            build_telegram_html_caption(
                compact_source,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            compact_html_caption
            and telegram_html_visible_length(
                compact_html_caption
            )
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        ):

            plan[
                "media_caption"
            ] = compact_html_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🗜️ Source blockquote preserved "
                f"with compact main | "
                f"visible="
                f"{telegram_html_visible_length(compact_html_caption)}"
            )

            return plan

        # -------------------------------------------------
        # RESERVE SPACE FOR REAL SOURCE BLOCKQUOTE
        # -------------------------------------------------

        inline_blockquotes = (
            build_inline_telegram_blockquotes(
                blockquote_blocks,
                expandable_blocks
            )
        )

        suffix_parts: List[str] = []

        if inline_blockquotes:

            suffix_parts.append(
                inline_blockquotes
            )

        if branding:

            suffix_parts.append(
                escape(
                    branding
                )
            )

        suffix_html = (
            "\n\n".join(
                suffix_parts
            )
        )

        suffix_visible_length = (
            telegram_html_visible_length(
                suffix_html
            )
        )

        available_for_main = (
            TELEGRAM_CAPTION_SAFE_LIMIT
            - suffix_visible_length
            - (
                2
                if suffix_html
                else 0
            )
        )

        # -------------------------------------------------
        # اگر Safe Limit کافی نبود، تا سقف رسمی امتحان می‌کنیم.
        # -------------------------------------------------

        if available_for_main <= 0:

            available_for_main = (
                TELEGRAM_CAPTION_LIMIT
                - suffix_visible_length
                - (
                    2
                    if suffix_html
                    else 0
                )
            )

        # -------------------------------------------------
        # اگر خود Blockquote + Branding داخل Caption جا می‌شود،
        # بخشی از main text را قبل از آن قرار می‌دهیم.
        # -------------------------------------------------

        if available_for_main > 0:

            if (
                len(compact_source)
                <= available_for_main
            ):

                main_for_caption = (
                    compact_source
                )

                remaining_main = ""

            else:

                split_position = (
                    find_split_position(
                        compact_source,
                        available_for_main
                    )
                )

                if split_position <= 0:

                    split_position = (
                        available_for_main
                    )

                main_for_caption = (
                    compact_source[
                        :split_position
                    ]
                    .strip()
                )

                remaining_main = (
                    compact_source[
                        split_position:
                    ]
                    .strip()
                )

            html_parts: List[str] = []

            if main_for_caption:

                html_parts.append(
                    escape(
                        main_for_caption
                    )
                )

            if inline_blockquotes:

                html_parts.append(
                    inline_blockquotes
                )

            if branding:

                html_parts.append(
                    escape(
                        branding
                    )
                )

            final_html_caption = (
                "\n\n".join(
                    html_parts
                )
            )

            if (
                telegram_html_visible_length(
                    final_html_caption
                )
                <= TELEGRAM_CAPTION_LIMIT
            ):

                plan[
                    "media_caption"
                ] = final_html_caption

                plan[
                    "media_parse_mode"
                ] = "HTML"

                plan[
                    "blockquote_messages"
                ] = []

                if remaining_main:

                    replies = (
                        split_text(
                            remaining_main,
                            TELEGRAM_MESSAGE_SAFE_LIMIT
                        )
                    )

                    plan[
                        "followup_messages"
                    ] = (
                        brand_followup_messages(
                            replies,
                            branding
                        )
                    )

                logger.info(
                    f"🧩 Source blockquote kept inside "
                    f"long media caption | "
                    f"visible_caption="
                    f"{telegram_html_visible_length(final_html_caption)} | "
                    f"followups="
                    f"{len(plan['followup_messages'])}"
                )

                return plan

        # -------------------------------------------------
        # EXTREME EDGE CASE
        #
        # خود blockquote + branding از 1024 بیشتر است.
        # انتشار را Abort نمی‌کنیم.
        # -------------------------------------------------

        logger.warning(
            f"⚠️ Source blockquote itself cannot fit "
            f"Telegram media caption | "
            f"visible_suffix={suffix_visible_length}"
        )

        branding_cost = (
            len(branding)
            + (
                2
                if branding
                else 0
            )
        )

        available_for_caption = max(
            100,
            TELEGRAM_CAPTION_SAFE_LIMIT
            - branding_cost
        )

        split_position = (
            find_split_position(
                compact_source,
                available_for_caption
            )
        )

        if split_position <= 0:

            split_position = (
                available_for_caption
            )

        main_for_caption = (
            compact_source[
                :split_position
            ]
            .strip()
        )

        remaining_main = (
            compact_source[
                split_position:
            ]
            .strip()
        )

        plan[
            "media_caption"
        ] = (
            append_branding(
                main_for_caption,
                branding
            )
        )

        replies: List[str] = []

        if remaining_main:

            replies.extend(
                split_text(
                    remaining_main,
                    TELEGRAM_MESSAGE_SAFE_LIMIT
                )
            )

        # فقط در Edge Case بسیار بزرگ،
        # Blockquote مستقل Safety Net می‌شود.
        replies.extend(
            create_telegram_blockquote_messages(
                blockquote_blocks,
                expandable_blocks
            )
        )

        plan[
            "followup_messages"
        ] = (
            brand_followup_messages(
                replies,
                branding
            )
        )

        plan[
            "blockquote_messages"
        ] = []

        plan[
            "document_fallback"
        ] = False

        return plan

    # =====================================================
    # CASE 2
    # NO SOURCE BLOCKQUOTE
    # =====================================================

    normal_with_branding = (
        append_branding(
            main_text,
            branding
        )
    )

    # -----------------------------------------------------
    # SHORT NEWS
    # -----------------------------------------------------

    if (
        normal_with_branding
        and len(normal_with_branding)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    ):

        # اگر خبر کمی بلند است ولی هنوز جا می‌شود،
        # حالت Expandable مصنوعی را امتحان می‌کنیم.
        smart_caption = (
            build_smart_expandable_media_caption(
                main_text,
                branding,
                TELEGRAM_CAPTION_SAFE_LIMIT
            )
        )

        if smart_caption:

            plan[
                "media_caption"
            ] = smart_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                "🧩 Smart expandable caption selected"
            )

            return plan

        plan[
            "media_caption"
        ] = normal_with_branding

        return plan

    # =====================================================
    # CASE 3
    # TRY COMPACT
    # =====================================================

    compact_main = (
        compact_long_text(
            main_text
        )
    )

    compact_source = (
        compact_main
        or main_text
    )

    compact_with_branding = (
        append_branding(
            compact_source,
            branding
        )
    )

    if (
        compact_with_branding
        and len(compact_with_branding)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    ):

        smart_caption = (
            build_smart_expandable_media_caption(
                compact_source,
                branding,
                TELEGRAM_CAPTION_SAFE_LIMIT
            )
        )

        if smart_caption:

            plan[
                "media_caption"
            ] = smart_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                "🧩 Smart expandable compact caption selected"
            )

            return plan

        plan[
            "media_caption"
        ] = compact_with_branding

        return plan

    # =====================================================
    # CASE 4
    # TOO LONG EVEN AFTER COMPACT
    #
    # CAPTION + REPLY
    # =====================================================

    branding_cost = (
        len(branding)
        + (
            2
            if branding
            else 0
        )
    )

    available_for_caption = (
        TELEGRAM_CAPTION_SAFE_LIMIT
        - branding_cost
    )

    if available_for_caption <= 0:

        available_for_caption = (
            TELEGRAM_CAPTION_LIMIT
            - branding_cost
        )

    if available_for_caption <= 0:

        logger.error(
            "❌ Branding itself exceeds Telegram caption capacity"
        )

        plan[
            "document_fallback"
        ] = True

        return plan

    split_position = (
        find_split_position(
            compact_source,
            available_for_caption
        )
    )

    if split_position <= 0:

        split_position = (
            available_for_caption
        )

    main_for_caption = (
        compact_source[
            :split_position
        ]
        .strip()
    )

    remaining_main = (
        compact_source[
            split_position:
        ]
        .strip()
    )

    # -----------------------------------------------------
    # Branding زیر Caption اصلی
    # -----------------------------------------------------

    plan[
        "media_caption"
    ] = (
        append_branding(
            main_for_caption,
            branding
        )
    )

    # -----------------------------------------------------
    # ادامه خبر + Branding
    # -----------------------------------------------------

    if remaining_main:

        replies = (
            split_text(
                remaining_main,
                TELEGRAM_MESSAGE_SAFE_LIMIT
            )
        )

        plan[
            "followup_messages"
        ] = (
            brand_followup_messages(
                replies,
                branding
            )
        )

    plan[
        "blockquote_messages"
    ] = []

    plan[
        "document_fallback"
    ] = False

    # =====================================================
    # FINAL SAFETY
    # =====================================================

    if (
        len(
            plan[
                "media_caption"
            ]
        )
        > TELEGRAM_CAPTION_LIMIT
    ):

        logger.error(
            f"❌ Telegram caption safety violation | "
            f"length="
            f"{len(plan['media_caption'])}"
        )

        plan[
            "document_fallback"
        ] = True

    logger.info(
        f"📋 Telegram smart media plan | "
        f"caption="
        f"{len(plan['media_caption'])} | "
        f"parse_mode="
        f"{plan['media_parse_mode'] or 'NONE'} | "
        f"followup="
        f"{len(plan['followup_messages'])} | "
        f"fallback="
        f"{plan['document_fallback']}"
    )

    return plan


# =========================================================
# BALE MEDIA PLAN
# =========================================================

def create_bale_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    plan = {
        "media_caption": "",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    split_result = (
        split_for_media(
            main_text,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    media_caption = (
        split_result[
            "media_caption"
        ]
    )

    followup_messages = (
        split_result[
            "followup_messages"
        ]
    )

    branded_result = (
        place_branding(
            media_caption,
            followup_messages,
            branding,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    plan[
        "media_caption"
    ] = (
        branded_result[
            "media_caption"
        ]
    )

    plan[
        "followup_messages"
    ] = (
        branded_result[
            "followup_messages"
        ]
    )

    plan[
        "blockquote_messages"
    ] = (
        create_bale_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if (
        len(
            plan[
                "media_caption"
            ]
        )
        > BALE_CAPTION_LIMIT
    ):

        logger.error(
            "❌ Bale media caption exceeds "
            "configured platform limit"
        )

        plan[
            "document_fallback"
        ] = True

    valid_followups = []

    for message in (
        plan[
            "followup_messages"
        ]
    ):

        if (
            len(message)
            <= BALE_MESSAGE_LIMIT
        ):

            valid_followups.append(
                message
            )

        else:

            valid_followups.extend(
                split_text(
                    message,
                    BALE_MESSAGE_SAFE_LIMIT
                )
            )

    plan[
        "followup_messages"
    ] = valid_followups

    return plan


# =========================================================
# TELEGRAM TEXT PLAN
# =========================================================

def create_telegram_text_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    messages: List[str] = []

    normal_final = (
        append_branding(
            main_text,
            branding
        )
    )

    if (
        normal_final
        and len(normal_final)
        <= TELEGRAM_MESSAGE_LIMIT
    ):

        messages = [
            normal_final
        ]

    else:

        compact_text = (
            compact_long_text(
                main_text
            )
        )

        compact_final = (
            append_branding(
                compact_text,
                branding
            )
        )

        if (
            compact_final
            and len(compact_final)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            messages = [
                compact_final
            ]

        else:

            source_for_split = (
                compact_text
                or main_text
            )

            if source_for_split:

                messages = (
                    split_text(
                        source_for_split,
                        TELEGRAM_MESSAGE_LIMIT
                    )
                )

            messages = (
                place_branding_in_text_messages(
                    messages,
                    branding,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

    safe_messages: List[str] = []

    for message in messages:

        if not message:
            continue

        if (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            safe_messages.append(
                message
            )

        else:

            safe_messages.extend(
                split_text(
                    message,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

    blockquote_messages = (
        create_telegram_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    return {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }


# =========================================================
# BALE TEXT PLAN
# =========================================================

def create_bale_text_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    messages = []

    if main_text:

        messages = (
            split_text(
                main_text,
                BALE_MESSAGE_SAFE_LIMIT
            )
        )

    messages = (
        place_branding_in_text_messages(
            messages,
            branding,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    safe_messages = []

    for message in messages:

        if (
            len(message)
            <= BALE_MESSAGE_LIMIT
        ):

            safe_messages.append(
                message
            )

        else:

            safe_messages.extend(
                split_text(
                    message,
                    BALE_MESSAGE_SAFE_LIMIT
                )
            )

    blockquote_messages = (
        create_bale_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    return {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }


# =========================================================
# MAIN ANALYZER
# =========================================================

def analyze_content(
    main_text: str,
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    other_entities: Optional[
        List[Dict[str, Any]]
    ] = None,
    branding: str = ""
) -> PublicationPlan:

    main_text = normalize_text(
        main_text
    )

    blockquote_blocks = list(
        blockquote_blocks
        or []
    )

    expandable_blocks = list(
        expandable_blocks
        or []
    )

    other_entities = list(
        other_entities
        or []
    )

    branding = normalize_text(
        branding
    )

    logger.info(
        f"🔍 Caption Manager analyzing | "
        f"main={len(main_text)} | "
        f"blockquote="
        f"{len(blockquote_blocks)} | "
        f"expandable="
        f"{len(expandable_blocks)} | "
        f"other="
        f"{len(other_entities)} | "
        f"branding={len(branding)}"
    )

    plan = PublicationPlan()

    plan.metadata[
        "other_entities"
    ] = (
        other_entities
    )

    plan.telegram = (
        create_telegram_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.bale = (
        create_bale_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.text[
        "telegram"
    ] = (
        create_telegram_text_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.text[
        "bale"
    ] = (
        create_bale_text_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    telegram_caption = (
        plan.telegram[
            "media_caption"
        ]
    )

    if plan.telegram.get(
        "media_parse_mode"
    ) == "HTML":

        telegram_caption_visible = (
            telegram_html_visible_length(
                telegram_caption
            )
        )

    else:

        telegram_caption_visible = (
            len(
                telegram_caption
            )
        )

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption_raw="
        f"{len(telegram_caption)} | "
        f"tg_caption_visible="
        f"{telegram_caption_visible} | "
        f"tg_followup="
        f"{len(plan.telegram['followup_messages'])} | "
        f"tg_inline_html="
        f"{bool(plan.telegram.get('media_parse_mode'))} | "
        f"tg_fallback="
        f"{plan.telegram.get('document_fallback', False)}"
    )

    return plan
