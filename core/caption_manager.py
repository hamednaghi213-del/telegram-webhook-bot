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
# CLEAN BLOCKQUOTE
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

        while cleaned_line.startswith(
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

    position = (
        search_text.rfind(
            "\n\n"
        )
    )

    if position > 0:
        return position

    position = (
        search_text.rfind(
            "\n"
        )
    )

    if position > 0:
        return position

    sentence_marks = (
        "؟",
        "!",
        ".",
        "?",
        "۔",
        "…"
    )

    best_position = -1

    for mark in sentence_marks:

        position = (
            search_text.rfind(
                mark
            )
        )

        if position > best_position:

            best_position = (
                position
            )

    if best_position > 0:

        return (
            best_position
            + 1
        )

    position = (
        search_text.rfind(
            " "
        )
    )

    if position > 0:
        return position

    return limit


# =========================================================
# NEW:
# FIND SPLIT CLOSE TO MEDIA CAPTION LIMIT
# =========================================================

def find_media_split_position(
    text: str,
    limit: int,
    minimum_fill_ratio: float = 0.60
) -> int:
    """
    مخصوص Caption رسانه.

    مشکل قبلی:
    اگر تنها \\n\\n موجود، فاصله بعد از تیتر بود،
    همان نقطه انتخاب می‌شد و تقریباً کل بدنه به Reply می‌رفت.

    سیاست جدید:
    فقط شکست‌هایی پذیرفته می‌شوند که به اندازه کافی
    نزدیک سقف Caption باشند.

    اولویت:
    1. Paragraph نزدیک انتهای ظرفیت
    2. Line نزدیک انتهای ظرفیت
    3. Sentence نزدیک انتهای ظرفیت
    4. Word نزدیک انتهای ظرفیت
    5. Hard cut
    """

    if not text:
        return 0

    if limit <= 0:
        return 0

    if len(text) <= limit:
        return len(text)

    search_text = (
        text[:limit]
    )

    minimum_position = max(
        1,
        int(
            limit
            * minimum_fill_ratio
        )
    )

    # =====================================================
    # 1. PARAGRAPH
    # =====================================================

    position = (
        search_text.rfind(
            "\n\n"
        )
    )

    if position >= minimum_position:

        return position

    # =====================================================
    # 2. LINE
    # =====================================================

    position = (
        search_text.rfind(
            "\n"
        )
    )

    if position >= minimum_position:

        return position

    # =====================================================
    # 3. SENTENCE
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

        current = (
            search_text.rfind(
                mark
            )
        )

        if (
            current
            > best_sentence_position
        ):

            best_sentence_position = (
                current
            )

    if (
        best_sentence_position
        >= minimum_position
    ):

        return (
            best_sentence_position
            + 1
        )

    # =====================================================
    # 4. WORD
    # =====================================================

    position = (
        search_text.rfind(
            " "
        )
    )

    if position >= minimum_position:

        return position

    # =====================================================
    # 5. LAST LINE FALLBACK
    # =====================================================

    position = (
        search_text.rfind(
            "\n"
        )
    )

    if position > 0:

        return position

    # =====================================================
    # 6. LAST WORD FALLBACK
    # =====================================================

    position = (
        search_text.rfind(
            " "
        )
    )

    if position > 0:

        return position

    # =====================================================
    # 7. HARD CUT
    # =====================================================

    return limit


# =========================================================
# SPLIT TEXT
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

    remaining = (
        text
    )

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
            split_position = limit

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

        if new_remaining == remaining:

            logger.error(
                "❌ split_text made no progress"
            )

            break

        remaining = (
            new_remaining
        )

    return parts


# =========================================================
# SPLIT MEDIA
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

        return result

    source_text = (
        compact_text
        or text
    )

    split_position = (
        find_media_split_position(
            source_text,
            caption_limit
        )
    )

    if split_position <= 0:
        split_position = caption_limit

    result[
        "media_caption"
    ] = (
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
# BRANDING
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

        combined = (
            append_branding(
                messages[-1],
                branding
            )
        )

        if len(combined) <= message_limit:

            messages[-1] = (
                combined
            )

        else:

            messages.append(
                branding
            )

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    combined = (
        append_branding(
            media_caption,
            branding
        )
    )

    if len(combined) <= caption_limit:

        media_caption = (
            combined
        )

    else:

        messages.append(
            branding
        )

    return {
        "media_caption": media_caption,
        "followup_messages": messages
    }


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

        return [
            branding
        ]

    combined = (
        append_branding(
            result[-1],
            branding
        )
    )

    if len(combined) <= message_limit:

        result[-1] = (
            combined
        )

    else:

        result.append(
            branding
        )

    return result


def brand_followup_messages(
    messages: List[str],
    branding: str,
    message_limit: int = TELEGRAM_MESSAGE_LIMIT
) -> List[str]:

    result: List[str] = []

    branding = normalize_text(
        branding
    )

    for message in (
        messages
        or []
    ):

        message = normalize_text(
            message
        )

        if not message:
            continue

        if not branding:

            result.append(
                message
            )

            continue

        combined = (
            append_branding(
                message,
                branding
            )
        )

        if len(combined) <= message_limit:

            result.append(
                combined
            )

        else:

            result.append(
                message
            )

    return result


# =========================================================
# BLOCKQUOTE COLLECTION
# =========================================================

def _combined_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[Dict[str, Any]]:

    combined: List[
        Dict[str, Any]
    ] = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined.append({
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

        combined.append({
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

    combined.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    return combined


# =========================================================
# TELEGRAM BLOCKQUOTES
# =========================================================

def create_telegram_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    result: List[str] = []

    for block in (
        _combined_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    ):

        text = (
            clean_blockquote_text(
                block.get(
                    "text",
                    ""
                )
            )
        )

        if not text:
            continue

        parts = (
            split_text(
                text,
                TELEGRAM_MESSAGE_SAFE_LIMIT
                - 100
            )
        )

        for part in parts:

            html_message = (
                build_blockquote_html(
                    part,
                    expandable=bool(
                        block.get(
                            "expandable",
                            False
                        )
                    )
                )
            )

            result.append(
                html_message
            )

    return result


def build_inline_telegram_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> str:

    result: List[str] = []

    for block in (
        _combined_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    ):

        text = (
            clean_blockquote_text(
                block.get(
                    "text",
                    ""
                )
            )
        )

        if not text:
            continue

        result.append(
            build_blockquote_html(
                text,
                expandable=bool(
                    block.get(
                        "expandable",
                        False
                    )
                )
            )
        )

    return "\n\n".join(
        result
    )


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

    inline_blocks = (
        build_inline_telegram_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if inline_blocks:

        parts.append(
            inline_blocks
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
# SMART EXPANDABLE
# =========================================================

def build_smart_expandable_media_caption(
    main_text: str,
    branding: str,
    caption_limit: int
) -> Optional[str]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    if not main_text:
        return None

    final_plain = (
        append_branding(
            main_text,
            branding
        )
    )

    if len(final_plain) > caption_limit:
        return None

    if len(main_text) < 350:
        return None

    target = max(
        200,
        int(
            len(main_text)
            * 0.55
        )
    )

    target = min(
        target,
        len(main_text) - 1
    )

    position = (
        find_media_split_position(
            main_text,
            target,
            minimum_fill_ratio=0.55
        )
    )

    if position <= 0:
        position = target

    normal_part = (
        main_text[
            :position
        ]
        .strip()
    )

    expandable_part = (
        main_text[
            position:
        ]
        .strip()
    )

    if (
        not normal_part
        or not expandable_part
    ):

        return None

    parts = [
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

    if len(html_caption) > caption_limit:
        return None

    return html_caption


# =========================================================
# BALE BLOCKQUOTES
# =========================================================

def build_bale_blockquote(
    text: str
) -> str:

    text = normalize_text(
        text
    )

    if not text:
        return ""

    output = []

    for line in (
        text.splitlines()
    ):

        line = (
            line.strip()
        )

        if line:

            output.append(
                f"▌ {line}"
            )

    return "\n".join(
        output
    )


def build_inline_bale_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> str:

    result: List[str] = []

    for block in (
        _combined_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    ):

        text = (
            clean_blockquote_text(
                block.get(
                    "text",
                    ""
                )
            )
        )

        if not text:
            continue

        rendered = (
            build_bale_blockquote(
                text
            )
        )

        if rendered:

            result.append(
                rendered
            )

    return "\n\n".join(
        result
    )


def create_bale_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    result: List[str] = []

    for block in (
        _combined_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    ):

        text = (
            clean_blockquote_text(
                block.get(
                    "text",
                    ""
                )
            )
        )

        if not text:
            continue

        parts = (
            split_text(
                text,
                BALE_MESSAGE_SAFE_LIMIT
                - 200
            )
        )

        for part in parts:

            result.append(
                build_bale_blockquote(
                    part
                )
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
    # SOURCE BLOCKQUOTE EXISTS
    # =====================================================

    if has_source_blockquotes:

        # =================================================
        # 1. FULL VERSION
        # =================================================

        full_caption = (
            build_telegram_html_caption(
                main_text,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            full_caption
            and telegram_html_visible_length(
                full_caption
            )
            <= TELEGRAM_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = full_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            return plan

        # =================================================
        # 2. COMPACT MAIN
        # =================================================

        compact_main = (
            compact_long_text(
                main_text
            )
            or main_text
        )

        compact_caption = (
            build_telegram_html_caption(
                compact_main,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            compact_caption
            and telegram_html_visible_length(
                compact_caption
            )
            <= TELEGRAM_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = compact_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            return plan

        # =================================================
        # 3. REAL OVERFLOW
        #
        # IMPORTANT:
        # بیشترین مقدار متن اصلی باید قبل از Blockquote
        # داخل Caption قرار بگیرد.
        # =================================================

        inline_blocks = (
            build_inline_telegram_blockquotes(
                blockquote_blocks,
                expandable_blocks
            )
        )

        suffix_parts: List[str] = []

        if inline_blocks:

            suffix_parts.append(
                inline_blocks
            )

        if branding:

            suffix_parts.append(
                escape(
                    branding
                )
            )

        suffix = (
            "\n\n".join(
                suffix_parts
            )
        )

        suffix_visible = (
            telegram_html_visible_length(
                suffix
            )
        )

        available_for_main = (
            TELEGRAM_CAPTION_LIMIT
            - suffix_visible
            - (
                2
                if suffix
                else 0
            )
        )

        if available_for_main > 0:

            # =============================================
            # FIX:
            # دیگر فاصله بعد از تیتر Split را نمی‌رباید.
            # =============================================

            split_position = (
                find_media_split_position(
                    compact_main,
                    available_for_main,
                    minimum_fill_ratio=0.60
                )
            )

            if split_position <= 0:

                split_position = (
                    available_for_main
                )

            main_for_caption = (
                compact_main[
                    :split_position
                ]
                .strip()
            )

            remaining_main = (
                compact_main[
                    split_position:
                ]
                .strip()
            )

            caption_parts: List[str] = []

            if main_for_caption:

                caption_parts.append(
                    escape(
                        main_for_caption
                    )
                )

            if inline_blocks:

                caption_parts.append(
                    inline_blocks
                )

            if branding:

                caption_parts.append(
                    escape(
                        branding
                    )
                )

            candidate = (
                "\n\n".join(
                    caption_parts
                )
            )

            if (
                candidate
                and telegram_html_visible_length(
                    candidate
                )
                <= TELEGRAM_CAPTION_LIMIT
            ):

                plan[
                    "media_caption"
                ] = candidate

                plan[
                    "media_parse_mode"
                ] = "HTML"

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
                            branding,
                            TELEGRAM_MESSAGE_LIMIT
                        )
                    )

                logger.info(
                    f"🧩 Telegram balanced media plan | "
                    f"main_in_caption="
                    f"{len(main_for_caption)} | "
                    f"remaining="
                    f"{len(remaining_main)} | "
                    f"blockquote_visible="
                    f"{telegram_html_visible_length(inline_blocks)} | "
                    f"caption_visible="
                    f"{telegram_html_visible_length(candidate)}"
                )

                return plan

        # =================================================
        # EXTREME CASE
        # =================================================

        branding_cost = (
            len(branding)
            + (
                2
                if branding
                else 0
            )
        )

        available = max(
            100,
            TELEGRAM_CAPTION_SAFE_LIMIT
            - branding_cost
        )

        position = (
            find_media_split_position(
                compact_main,
                available
            )
        )

        if position <= 0:
            position = available

        first_part = (
            compact_main[
                :position
            ]
            .strip()
        )

        remaining = (
            compact_main[
                position:
            ]
            .strip()
        )

        plan[
            "media_caption"
        ] = (
            append_branding(
                first_part,
                branding
            )
        )

        replies: List[str] = []

        if remaining:

            replies.extend(
                split_text(
                    remaining,
                    TELEGRAM_MESSAGE_SAFE_LIMIT
                )
            )

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
                branding,
                TELEGRAM_MESSAGE_LIMIT
            )
        )

        return plan

    # =====================================================
    # NORMAL MEDIA WITHOUT SOURCE BLOCKQUOTE
    # =====================================================

    normal_final = (
        append_branding(
            main_text,
            branding
        )
    )

    if (
        normal_final
        and len(normal_final)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    ):

        plan[
            "media_caption"
        ] = normal_final

        return plan

    # =====================================================
    # COMPACT BEFORE SPLIT
    # =====================================================

    compact_main = (
        compact_long_text(
            main_text
        )
        or main_text
    )

    compact_final = (
        append_branding(
            compact_main,
            branding
        )
    )

    if (
        compact_final
        and len(compact_final)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    ):

        smart_caption = (
            build_smart_expandable_media_caption(
                compact_main,
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

        else:

            plan[
                "media_caption"
            ] = compact_final

        return plan

    # =====================================================
    # REAL MEDIA OVERFLOW
    # =====================================================

    branding_cost = (
        len(branding)
        + (
            2
            if branding
            else 0
        )
    )

    available = (
        TELEGRAM_CAPTION_SAFE_LIMIT
        - branding_cost
    )

    if available <= 0:

        plan[
            "document_fallback"
        ] = True

        return plan

    position = (
        find_media_split_position(
            compact_main,
            available
        )
    )

    if position <= 0:
        position = available

    main_for_caption = (
        compact_main[
            :position
        ]
        .strip()
    )

    remaining = (
        compact_main[
            position:
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

    if remaining:

        replies = (
            split_text(
                remaining,
                TELEGRAM_MESSAGE_SAFE_LIMIT
            )
        )

        plan[
            "followup_messages"
        ] = (
            brand_followup_messages(
                replies,
                branding,
                TELEGRAM_MESSAGE_LIMIT
            )
        )

    if (
        len(
            plan[
                "media_caption"
            ]
        )
        > TELEGRAM_CAPTION_LIMIT
    ):

        plan[
            "document_fallback"
        ] = True

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

    inline_blocks = (
        build_inline_bale_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    full_parts: List[str] = []

    if main_text:

        full_parts.append(
            main_text
        )

    if inline_blocks:

        full_parts.append(
            inline_blocks
        )

    if branding:

        full_parts.append(
            branding
        )

    full_caption = (
        "\n\n".join(
            full_parts
        )
    )

    if (
        full_caption
        and len(full_caption)
        <= BALE_CAPTION_SAFE_LIMIT
    ):

        plan[
            "media_caption"
        ] = full_caption

        return plan

    compact_main = (
        compact_long_text(
            main_text
        )
        or main_text
    )

    compact_parts: List[str] = []

    if compact_main:

        compact_parts.append(
            compact_main
        )

    if inline_blocks:

        compact_parts.append(
            inline_blocks
        )

    if branding:

        compact_parts.append(
            branding
        )

    compact_caption = (
        "\n\n".join(
            compact_parts
        )
    )

    if (
        compact_caption
        and len(compact_caption)
        <= BALE_CAPTION_SAFE_LIMIT
    ):

        plan[
            "media_caption"
        ] = compact_caption

        return plan

    suffix_parts: List[str] = []

    if inline_blocks:

        suffix_parts.append(
            inline_blocks
        )

    if branding:

        suffix_parts.append(
            branding
        )

    suffix = (
        "\n\n".join(
            suffix_parts
        )
    )

    available_for_main = (
        BALE_CAPTION_SAFE_LIMIT
        - len(suffix)
        - (
            2
            if suffix
            else 0
        )
    )

    if available_for_main > 0:

        position = (
            find_media_split_position(
                compact_main,
                available_for_main
            )
        )

        if position <= 0:
            position = available_for_main

        main_for_caption = (
            compact_main[
                :position
            ]
            .strip()
        )

        remaining_main = (
            compact_main[
                position:
            ]
            .strip()
        )

        caption_parts: List[str] = []

        if main_for_caption:

            caption_parts.append(
                main_for_caption
            )

        if inline_blocks:

            caption_parts.append(
                inline_blocks
            )

        if branding:

            caption_parts.append(
                branding
            )

        candidate = (
            "\n\n".join(
                caption_parts
            )
        )

        if (
            candidate
            and len(candidate)
            <= BALE_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = candidate

            if remaining_main:

                followups = (
                    split_text(
                        remaining_main,
                        BALE_MESSAGE_SAFE_LIMIT
                    )
                )

                plan[
                    "followup_messages"
                ] = (
                    place_branding_in_text_messages(
                        followups,
                        branding,
                        BALE_MESSAGE_SAFE_LIMIT
                    )
                )

            return plan

    media_source = (
        compact_main
        or main_text
    )

    media_split = (
        split_for_media(
            media_source,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    plan[
        "media_caption"
    ] = (
        media_split[
            "media_caption"
        ]
    )

    continuation_parts: List[str] = []

    continuation_parts.extend(
        media_split[
            "followup_messages"
        ]
    )

    if inline_blocks:

        continuation_parts.append(
            inline_blocks
        )

    if continuation_parts:

        combined_continuation = (
            "\n\n".join(
                continuation_parts
            )
        )

        followups = (
            split_text(
                combined_continuation,
                BALE_MESSAGE_SAFE_LIMIT
            )
        )

        plan[
            "followup_messages"
        ] = (
            place_branding_in_text_messages(
                followups,
                branding,
                BALE_MESSAGE_SAFE_LIMIT
            )
        )

    else:

        branded_caption = (
            append_branding(
                plan[
                    "media_caption"
                ],
                branding
            )
        )

        if (
            len(branded_caption)
            <= BALE_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = branded_caption

    plan[
        "blockquote_messages"
    ] = []

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

    return {
        "messages": messages,
        "blockquote_messages": (
            create_telegram_blockquote_messages(
                blockquote_blocks,
                expandable_blocks
            )
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

    inline_blocks = (
        build_inline_bale_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    normal_content_parts: List[str] = []

    if main_text:

        normal_content_parts.append(
            main_text
        )

    if inline_blocks:

        normal_content_parts.append(
            inline_blocks
        )

    normal_content = (
        "\n\n".join(
            normal_content_parts
        )
    )

    normal_final = (
        append_branding(
            normal_content,
            branding
        )
    )

    if (
        normal_final
        and len(normal_final)
        <= BALE_MESSAGE_LIMIT
    ):

        return {
            "messages": [
                normal_final
            ],
            "blockquote_messages": []
        }

    compact_main = (
        compact_long_text(
            main_text
        )
        or main_text
    )

    compact_parts: List[str] = []

    if compact_main:

        compact_parts.append(
            compact_main
        )

    if inline_blocks:

        compact_parts.append(
            inline_blocks
        )

    compact_content = (
        "\n\n".join(
            compact_parts
        )
    )

    compact_final = (
        append_branding(
            compact_content,
            branding
        )
    )

    if (
        compact_final
        and len(compact_final)
        <= BALE_MESSAGE_LIMIT
    ):

        return {
            "messages": [
                compact_final
            ],
            "blockquote_messages": []
        }

    source_for_split = (
        compact_content
        or normal_content
    )

    messages = (
        split_text(
            source_for_split,
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

    return {
        "messages": messages,
        "blockquote_messages": []
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
        f"blockquote={len(blockquote_blocks)} | "
        f"expandable={len(expandable_blocks)} | "
        f"branding={len(branding)}"
    )

    plan = (
        PublicationPlan()
    )

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

    if (
        plan.telegram.get(
            "media_parse_mode"
        )
        == "HTML"
    ):

        telegram_visible = (
            telegram_html_visible_length(
                telegram_caption
            )
        )

    else:

        telegram_visible = (
            len(
                telegram_caption
            )
        )

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption_raw={len(telegram_caption)} | "
        f"tg_caption_visible={telegram_visible} | "
        f"tg_followup="
        f"{len(plan.telegram['followup_messages'])} | "
        f"tg_parse_mode="
        f"{plan.telegram.get('media_parse_mode') or 'NONE'} | "
        f"tg_fallback="
        f"{plan.telegram.get('document_fallback', False)} | "
        f"bale_caption="
        f"{len(plan.bale['media_caption'])} | "
        f"bale_followup="
        f"{len(plan.bale['followup_messages'])} | "
        f"bale_blockquote="
        f"{len(plan.bale['blockquote_messages'])}"
    )

    return plan
