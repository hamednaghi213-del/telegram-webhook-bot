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
# TELEGRAM HTML LENGTH
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

        cleaned = (
            clean_text(
                text
            )
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

    content_lines: List[str] = []

    for line in (
        text.splitlines()
    ):

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

        if cleaned_line:

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

        if new_remaining == remaining:

            break

        remaining = (
            new_remaining
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
# BRANDING HELPERS
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
    branding: str
) -> List[str]:

    messages = list(
        messages
        or []
    )

    branding = normalize_text(
        branding
    )

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
# TELEGRAM BLOCKQUOTE HELPERS
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

            result.append(
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

    # Branding همیشه آخرین جزء Caption است.
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
# SMART ARTIFICIAL EXPANDABLE
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

    if (
        len(main_text)
        + (
            len(branding) + 2
            if branding
            else 0
        )
        > caption_limit
    ):

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
        find_split_position(
            main_text,
            target
        )
    )

    if position <= 0:

        position = (
            target
        )

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

    # Safe limit داخلی تست‌های فعلی
    if len(html_caption) > caption_limit:

        return None

    return html_caption


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


def create_bale_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    result = []

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

        for part in (
            split_text(
                text,
                BALE_MESSAGE_SAFE_LIMIT
                - 200
            )
        ):

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
    # REAL SOURCE EXPANDABLE / BLOCKQUOTE
    # =====================================================

    if has_source_blockquotes:

        # -------------------------------------------------
        # 1. FIRST PRIORITY:
        # FULL ORIGINAL MAIN + BLOCKQUOTE + BRANDING
        # -------------------------------------------------

        full_caption = (
            build_telegram_html_caption(
                main_text,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        full_visible = (
            telegram_html_visible_length(
                full_caption
            )
        )

        if (
            full_caption
            and full_visible
            <= TELEGRAM_CAPTION_LIMIT
            and len(full_caption)
            <= TELEGRAM_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = full_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🧩 Full source blockquote caption | "
                f"visible={full_visible} | "
                f"raw={len(full_caption)}"
            )

            return plan

        # -------------------------------------------------
        # 2. COMPACT MAIN, BUT KEEP ALL MAIN BEFORE BLOCK
        # -------------------------------------------------

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

        compact_visible = (
            telegram_html_visible_length(
                compact_caption
            )
        )

        if (
            compact_caption
            and compact_visible
            <= TELEGRAM_CAPTION_LIMIT
            and len(compact_caption)
            <= TELEGRAM_CAPTION_LIMIT
        ):

            plan[
                "media_caption"
            ] = compact_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🗜️ Compact main + source blockquote | "
                f"visible={compact_visible} | "
                f"raw={len(compact_caption)}"
            )

            return plan

        # -------------------------------------------------
        # 3. REAL OVERFLOW
        #
        # Caption order:
        #
        # main prefix
        # source expandable
        # branding
        #
        # Reply:
        #
        # remaining main
        # branding
        # -------------------------------------------------

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

        # از Visible length برای ظرفیت واقعی استفاده می‌کنیم.
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

            split_position = (
                find_split_position(
                    compact_main,
                    available_for_main
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

            html_parts: List[str] = []

            if main_for_caption:

                html_parts.append(
                    escape(
                        main_for_caption
                    )
                )

            if inline_blocks:

                html_parts.append(
                    inline_blocks
                )

            # Branding همیشه آخر
            if branding:

                html_parts.append(
                    escape(
                        branding
                    )
                )

            candidate = (
                "\n\n".join(
                    html_parts
                )
            )

            candidate_visible = (
                telegram_html_visible_length(
                    candidate
                )
            )

            if (
                candidate
                and candidate_visible
                <= TELEGRAM_CAPTION_LIMIT
            ):

                plan[
                    "media_caption"
                ] = candidate

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
                    f"🧩 Source blockquote overflow plan | "
                    f"caption_visible="
                    f"{candidate_visible} | "
                    f"main_in_caption="
                    f"{len(main_for_caption)} | "
                    f"remaining="
                    f"{len(remaining_main)} | "
                    f"followups="
                    f"{len(plan['followup_messages'])}"
                )

                return plan

        # -------------------------------------------------
        # EXTREME CASE:
        # Blockquote itself too large.
        #
        # Do not abort publication.
        # -------------------------------------------------

        logger.warning(
            "⚠️ Source blockquote is larger than "
            "Telegram media caption capacity"
        )

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
            find_split_position(
                compact_main,
                available
            )
        )

        if position <= 0:

            position = (
                available
            )

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

        # فقط Edge Case غیرقابل اجتناب
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
            "document_fallback"
        ] = False

        return plan

    # =====================================================
    # NO SOURCE BLOCKQUOTE
    # =====================================================

    normal_with_branding = (
        append_branding(
            main_text,
            branding
        )
    )

    if (
        normal_with_branding
        and len(normal_with_branding)
        <= TELEGRAM_CAPTION_SAFE_LIMIT
    ):

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

            return plan

        plan[
            "media_caption"
        ] = normal_with_branding

        return plan

    # =====================================================
    # TRY COMPACT
    # =====================================================

    compact_main = (
        compact_long_text(
            main_text
        )
        or main_text
    )

    compact_with_branding = (
        append_branding(
            compact_main,
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

            return plan

        plan[
            "media_caption"
        ] = compact_with_branding

        return plan

    # =====================================================
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

    available = (
        TELEGRAM_CAPTION_SAFE_LIMIT
        - branding_cost
    )

    if available <= 0:

        available = (
            TELEGRAM_CAPTION_LIMIT
            - branding_cost
        )

    if available <= 0:

        plan[
            "document_fallback"
        ] = True

        return plan

    position = (
        find_split_position(
            compact_main,
            available
        )
    )

    if position <= 0:

        position = (
            available
        )

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

    # Branding زیر خبر اصلی
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

        # Branding زیر Reply هم قرار می‌گیرد.
        plan[
            "followup_messages"
        ] = (
            brand_followup_messages(
                replies,
                branding
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

    split_result = (
        split_for_media(
            main_text,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    branded = (
        place_branding(
            split_result[
                "media_caption"
            ],
            split_result[
                "followup_messages"
            ],
            branding,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    plan[
        "media_caption"
    ] = (
        branded[
            "media_caption"
        ]
    )

    plan[
        "followup_messages"
    ] = (
        branded[
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

        plan[
            "document_fallback"
        ] = True

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

    normal_final = (
        append_branding(
            main_text,
            branding
        )
    )

    messages: List[str] = []

    if (
        normal_final
        and len(normal_final)
        <= TELEGRAM_MESSAGE_LIMIT
    ):

        messages = [
            normal_final
        ]

    else:

        compact = (
            compact_long_text(
                main_text
            )
        )

        compact_final = (
            append_branding(
                compact,
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

            messages = (
                split_text(
                    compact
                    or main_text,
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

    return {
        "messages": messages,
        "blockquote_messages": (
            create_bale_blockquote_messages(
                blockquote_blocks,
                expandable_blocks
            )
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

    caption = (
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

        visible_length = (
            telegram_html_visible_length(
                caption
            )
        )

    else:

        visible_length = (
            len(
                caption
            )
        )

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption_raw={len(caption)} | "
        f"tg_caption_visible={visible_length} | "
        f"tg_followup="
        f"{len(plan.telegram['followup_messages'])} | "
        f"tg_parse_mode="
        f"{plan.telegram.get('media_parse_mode') or 'NONE'} | "
        f"tg_fallback="
        f"{plan.telegram.get('document_fallback', False)}"
    )

    return plan
