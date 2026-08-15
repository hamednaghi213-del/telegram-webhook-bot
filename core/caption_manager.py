import logging
import re

from html import escape, unescape
from typing import Dict, List, Optional, Any, Tuple

from core.content_entities import build_blockquote_html
from core.cleaner import clean_text


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

    return str(text).strip()


def get_text_length(
    text: Optional[str]
) -> int:

    return len(
        normalize_text(text)
    )


def append_branding(
    text: str,
    branding: str
) -> str:

    text = normalize_text(text)
    branding = normalize_text(branding)

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

    return unescape(value)


def telegram_html_visible_length(
    html_text: str
) -> int:

    return len(
        telegram_html_visible_text(
            html_text
        )
    )


# =========================================================
# BLOCKQUOTE CLEANER
# =========================================================

def clean_blockquote_text(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    try:

        return normalize_text(
            clean_text(text)
        )

    except Exception as e:

        logger.exception(
            f"❌ Blockquote cleaning failed | {e}"
        )

        return text


# =========================================================
# COMPACT LONG TEXT
# =========================================================

def compact_long_text(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    content_lines: List[str] = []

    for line in text.splitlines():

        value = line.strip()

        if value:
            content_lines.append(value)

    if not content_lines:
        return ""

    title = content_lines[0]

    if len(content_lines) == 1:
        return title

    body_lines: List[str] = []

    for line in content_lines[1:]:

        value = line.strip()

        while value.startswith("🔹"):

            value = (
                value[len("🔹"):]
                .lstrip()
            )

        if value:
            body_lines.append(value)

    if not body_lines:
        return title

    result = (
        title
        + "\n\n"
        + "\n".join(body_lines)
    )

    logger.info(
        f"🗜️ Long text compacted | "
        f"before={len(text)} | "
        f"after={len(result)}"
    )

    return result


# =========================================================
# GENERAL SPLIT
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

    search_text = text[:limit]

    position = search_text.rfind("\n\n")

    if position > 0:
        return position

    position = search_text.rfind("\n")

    if position > 0:
        return position

    best_sentence = -1

    for mark in (
        "؟",
        "!",
        ".",
        "?",
        "۔",
        "…"
    ):

        current = search_text.rfind(mark)

        if current > best_sentence:
            best_sentence = current

    if best_sentence > 0:
        return best_sentence + 1

    position = search_text.rfind(" ")

    if position > 0:
        return position

    return limit


# =========================================================
# MEDIA SPLIT
# =========================================================

def find_media_split_position(
    text: str,
    limit: int,
    minimum_fill_ratio: float = 0.70
) -> int:

    if not text:
        return 0

    if limit <= 0:
        return 0

    if len(text) <= limit:
        return len(text)

    search_text = text[:limit]

    minimum_position = max(
        1,
        int(
            limit
            * minimum_fill_ratio
        )
    )

    candidates: List[int] = []

    for token in (
        "\n\n",
        "\n"
    ):

        position = search_text.rfind(token)

        if position >= minimum_position:
            candidates.append(position)

    for mark in (
        "؟",
        "!",
        ".",
        "?",
        "۔",
        "…"
    ):

        position = search_text.rfind(mark)

        if position >= minimum_position:

            candidates.append(
                position + 1
            )

    position = search_text.rfind(" ")

    if position >= minimum_position:
        candidates.append(position)

    if candidates:
        return max(candidates)

    position = search_text.rfind(" ")

    if position > 0:
        return position

    return limit


def split_text(
    text: str,
    limit: int
) -> List[str]:

    text = normalize_text(text)

    if not text:
        return []

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero"
        )

    if len(text) <= limit:
        return [text]

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

            value = remaining.strip()

            if value:
                parts.append(value)

            break

        position = find_split_position(
            remaining,
            limit
        )

        if position <= 0:
            position = limit

        part = (
            remaining[:position]
            .strip()
        )

        if part:
            parts.append(part)

        new_remaining = (
            remaining[position:]
            .strip()
        )

        if new_remaining == remaining:

            logger.error(
                "❌ split_text made no progress"
            )

            break

        remaining = new_remaining

    return parts


# =========================================================
# MEDIA SPLITTER
# =========================================================

def split_for_media(
    text: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:

    text = normalize_text(text)

    result = {
        "media_caption": "",
        "followup_messages": []
    }

    if not text:
        return result

    if len(text) <= caption_limit:

        result["media_caption"] = text
        return result

    compact_text = (
        compact_long_text(text)
        or text
    )

    if len(compact_text) <= caption_limit:

        result["media_caption"] = compact_text
        return result

    position = find_media_split_position(
        compact_text,
        caption_limit
    )

    if position <= 0:
        position = caption_limit

    result["media_caption"] = (
        compact_text[:position]
        .strip()
    )

    remaining = (
        compact_text[position:]
        .strip()
    )

    if remaining:

        result["followup_messages"] = (
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

        candidate = append_branding(
            media_caption,
            branding
        )

        if len(candidate) <= caption_limit:
            media_caption = candidate

        branded_messages: List[str] = []

        for message in messages:

            candidate = append_branding(
                message,
                branding
            )

            if len(candidate) <= message_limit:
                branded_messages.append(candidate)
            else:
                branded_messages.append(message)

        return {
            "media_caption": media_caption,
            "followup_messages": branded_messages
        }

    candidate = append_branding(
        media_caption,
        branding
    )

    if len(candidate) <= caption_limit:

        media_caption = candidate

    else:

        messages.append(branding)

    return {
        "media_caption": media_caption,
        "followup_messages": messages
    }


def brand_every_message(
    messages: List[str],
    branding: str,
    message_limit: int
) -> List[str]:

    branding = normalize_text(branding)

    result: List[str] = []

    for message in (
        messages
        or []
    ):

        message = normalize_text(message)

        if not message:
            continue

        if not branding:

            result.append(message)
            continue

        candidate = append_branding(
            message,
            branding
        )

        if len(candidate) <= message_limit:

            result.append(candidate)

        else:

            result.append(message)

    return result


def place_branding_in_text_messages(
    messages: List[str],
    branding: str,
    message_limit: int
) -> List[str]:

    return brand_every_message(
        messages,
        branding,
        message_limit
    )


def brand_followup_messages(
    messages: List[str],
    branding: str,
    message_limit: int = TELEGRAM_MESSAGE_LIMIT
) -> List[str]:

    return brand_every_message(
        messages,
        branding,
        message_limit
    )


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

    for block in _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    ):

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        parts = split_text(
            text,
            TELEGRAM_MESSAGE_SAFE_LIMIT
            - 100
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

    for block in _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    ):

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
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

    return "\n\n".join(result)


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
            escape(main_text)
        )

    blocks = (
        build_inline_telegram_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if blocks:
        parts.append(blocks)

    # Branding همیشه آخر Caption است.
    if branding:

        parts.append(
            escape(branding)
        )

    return "\n\n".join(parts)


# =========================================================
# FIT BLOCKQUOTE INTO TELEGRAM CAPTION
# =========================================================

def fit_blockquotes_into_caption(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    visible_capacity: int
) -> Tuple[
    str,
    List[Dict[str, Any]]
]:

    if visible_capacity <= 0:

        return (
            "",
            _combined_blockquotes(
                blockquote_blocks,
                expandable_blocks
            )
        )

    blocks = _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    )

    included_html: List[str] = []

    remaining_blocks: List[
        Dict[str, Any]
    ] = []

    capacity = visible_capacity

    for index, block in enumerate(
        blocks
    ):

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        separator_cost = (
            2
            if included_html
            else 0
        )

        available = (
            capacity
            - separator_cost
        )

        if available <= 0:

            remaining_blocks.extend(
                blocks[index:]
            )

            break

        if len(text) <= available:

            included_html.append(
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

            capacity -= (
                len(text)
                + separator_cost
            )

            continue

        position = find_media_split_position(
            text,
            available,
            minimum_fill_ratio=0.50
        )

        if position <= 0:
            position = available

        first_part = (
            text[:position]
            .strip()
        )

        remaining_part = (
            text[position:]
            .strip()
        )

        if first_part:

            included_html.append(
                build_blockquote_html(
                    first_part,
                    expandable=bool(
                        block.get(
                            "expandable",
                            False
                        )
                    )
                )
            )

        if remaining_part:

            remaining_blocks.append({
                "offset": block.get(
                    "offset",
                    0
                ),
                "text": remaining_part,
                "expandable": bool(
                    block.get(
                        "expandable",
                        False
                    )
                )
            })

        remaining_blocks.extend(
            blocks[
                index + 1:
            ]
        )

        break

    return (
        "\n\n".join(
            included_html
        ),
        remaining_blocks
    )


def build_branded_blockquote_messages(
    blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> List[str]:

    result: List[str] = []

    branding = normalize_text(
        branding
    )

    for block in blocks:

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        branding_cost = (
            len(branding)
            + 2
            if branding
            else 0
        )

        raw_limit = max(
            500,
            TELEGRAM_MESSAGE_SAFE_LIMIT
            - branding_cost
            - 100
        )

        parts = split_text(
            text,
            raw_limit
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

            if branding:

                html_message += (
                    "\n\n"
                    + escape(
                        branding
                    )
                )

            result.append(
                html_message
            )

    return result


# =========================================================
# BALE BLOCKQUOTES
# =========================================================

def build_bale_blockquote(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    result: List[str] = []

    for line in text.splitlines():

        line = line.strip()

        if line:

            result.append(
                f"▌ {line}"
            )

    return "\n".join(result)


def build_inline_bale_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> str:

    result: List[str] = []

    for block in _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    ):

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if text:

            result.append(
                build_bale_blockquote(
                    text
                )
            )

    return "\n\n".join(result)


def create_bale_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    result: List[str] = []

    for block in _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    ):

        text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        for part in split_text(
            text,
            BALE_MESSAGE_SAFE_LIMIT
            - 200
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

    has_blockquotes = bool(
        blockquote_blocks
        or expandable_blocks
    )

    # =====================================================
    # SOURCE BLOCKQUOTE EXISTS
    # =====================================================

    if has_blockquotes:

        # =================================================
        # 1. FULL ORIGINAL
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

            logger.info(
                "✅ Telegram one-post mode | "
                "full source content fits"
            )

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

            logger.info(
                "✅ Telegram one-post mode | "
                "compact source content fits"
            )

            return plan

        # =================================================
        # 3. REAL OVERFLOW
        # MAIN TEXT PRIORITY
        # =================================================

        branding_cost = (
            len(branding)
            if branding
            else 0
        )

        fixed_cost = (
            branding_cost
            + (
                2
                if branding
                else 0
            )
        )

        main_capacity = (
            TELEGRAM_CAPTION_LIMIT
            - fixed_cost
        )

        if main_capacity <= 0:

            plan[
                "document_fallback"
            ] = True

            return plan

        # =================================================
        # MAIN TEXT FIRST
        # =================================================

        if (
            len(compact_main)
            <= main_capacity
        ):

            main_for_caption = (
                compact_main
            )

            remaining_main = ""

        else:

            position = (
                find_media_split_position(
                    compact_main,
                    main_capacity,
                    minimum_fill_ratio=0.70
                )
            )

            if position <= 0:
                position = main_capacity

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

        # =================================================
        # AVAILABLE SPACE FOR BLOCKQUOTE
        # =================================================

        used_visible = len(
            main_for_caption
        )

        if (
            main_for_caption
            and branding
        ):

            base_separator = 4

        elif (
            main_for_caption
            or branding
        ):

            base_separator = 2

        else:

            base_separator = 0

        block_capacity = (
            TELEGRAM_CAPTION_LIMIT
            - used_visible
            - branding_cost
            - base_separator
        )

        inline_blocks = ""

        remaining_blocks: List[
            Dict[str, Any]
        ] = []

        if (
            not remaining_main
            and block_capacity > 0
        ):

            (
                inline_blocks,
                remaining_blocks
            ) = (
                fit_blockquotes_into_caption(
                    blockquote_blocks,
                    expandable_blocks,
                    block_capacity
                )
            )

        else:

            remaining_blocks = (
                _combined_blockquotes(
                    blockquote_blocks,
                    expandable_blocks
                )
            )

        # =================================================
        # FIRST POST
        # =================================================

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

        # Branding همیشه آخر پست
        if branding:

            caption_parts.append(
                escape(
                    branding
                )
            )

        candidate = "\n\n".join(
            caption_parts
        )

        if (
            telegram_html_visible_length(
                candidate
            )
            > TELEGRAM_CAPTION_LIMIT
        ):

            logger.error(
                "❌ Telegram caption still exceeds "
                "official visible limit"
            )

            plan[
                "document_fallback"
            ] = True

            return plan

        plan[
            "media_caption"
        ] = candidate

        plan[
            "media_parse_mode"
        ] = "HTML"

        # =================================================
        # MAIN OVERFLOW
        # =================================================

        if remaining_main:

            branding_cost_reply = (
                len(branding)
                + 2
                if branding
                else 0
            )

            reply_limit = (
                TELEGRAM_MESSAGE_SAFE_LIMIT
                - branding_cost_reply
            )

            replies = split_text(
                remaining_main,
                max(
                    500,
                    reply_limit
                )
            )

            plan[
                "followup_messages"
            ] = []

            for reply in replies:

                if branding:

                    final_reply = (
                        append_branding(
                            reply,
                            branding
                        )
                    )

                else:

                    final_reply = reply

                plan[
                    "followup_messages"
                ].append(
                    final_reply
                )

        # =================================================
        # BLOCKQUOTE OVERFLOW
        # =================================================

        if remaining_blocks:

            plan[
                "blockquote_messages"
            ] = (
                build_branded_blockquote_messages(
                    remaining_blocks,
                    branding
                )
            )

        logger.info(
            f"✅ Telegram priority media plan | "
            f"caption_visible="
            f"{telegram_html_visible_length(candidate)} | "
            f"main_remaining="
            f"{len(remaining_main)} | "
            f"blockquote_remaining="
            f"{len(remaining_blocks)}"
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

        plan[
            "media_caption"
        ] = compact_final

        return plan

    branding_cost = (
        len(branding)
        + 2
        if branding
        else 0
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
            available,
            minimum_fill_ratio=0.70
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

        reply_limit = (
            TELEGRAM_MESSAGE_SAFE_LIMIT
            - branding_cost
        )

        replies = split_text(
            remaining,
            max(
                500,
                reply_limit
            )
        )

        plan[
            "followup_messages"
        ] = []

        for reply in replies:

            if branding:

                final_reply = (
                    append_branding(
                        reply,
                        branding
                    )
                )

            else:

                final_reply = reply

            plan[
                "followup_messages"
            ].append(
                final_reply
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

    parts: List[str] = []

    if main_text:
        parts.append(main_text)

    if inline_blocks:
        parts.append(inline_blocks)

    if branding:
        parts.append(branding)

    full_caption = "\n\n".join(
        parts
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

    content_parts: List[str] = []

    if compact_main:
        content_parts.append(
            compact_main
        )

    if inline_blocks:
        content_parts.append(
            inline_blocks
        )

    source_content = "\n\n".join(
        content_parts
    )

    branding_cost = (
        len(branding)
        + 2
        if branding
        else 0
    )

    media_limit = (
        BALE_CAPTION_SAFE_LIMIT
        - branding_cost
    )

    split_result = split_for_media(
        source_content,
        max(
            500,
            media_limit
        ),
        BALE_MESSAGE_SAFE_LIMIT
    )

    plan[
        "media_caption"
    ] = append_branding(
        split_result[
            "media_caption"
        ],
        branding
    )

    if split_result[
        "followup_messages"
    ]:

        followup_limit = (
            BALE_MESSAGE_SAFE_LIMIT
            - branding_cost
        )

        rebuilt: List[str] = []

        for message in split_result[
            "followup_messages"
        ]:

            rebuilt.extend(
                split_text(
                    message,
                    max(
                        500,
                        followup_limit
                    )
                )
            )

        plan[
            "followup_messages"
        ] = brand_every_message(
            rebuilt,
            branding,
            BALE_MESSAGE_LIMIT
        )

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

    normal_final = append_branding(
        main_text,
        branding
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
            or main_text
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

            branding_cost = (
                len(branding)
                + 2
                if branding
                else 0
            )

            content_limit = (
                TELEGRAM_MESSAGE_LIMIT
                - branding_cost
            )

            messages = split_text(
                compact_text,
                max(
                    500,
                    content_limit
                )
            )

            branded_messages: List[str] = []

            for message in messages:

                if branding:

                    branded_messages.append(
                        append_branding(
                            message,
                            branding
                        )
                    )

                else:

                    branded_messages.append(
                        message
                    )

            messages = branded_messages

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

    parts: List[str] = []

    if main_text:
        parts.append(main_text)

    if inline_blocks:
        parts.append(
            inline_blocks
        )

    normal_content = "\n\n".join(
        parts
    )

    normal_final = append_branding(
        normal_content,
        branding
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

    source_content = "\n\n".join(
        compact_parts
    )

    branding_cost = (
        len(branding)
        + 2
        if branding
        else 0
    )

    message_limit = (
        BALE_MESSAGE_SAFE_LIMIT
        - branding_cost
    )

    messages = split_text(
        source_content,
        max(
            500,
            message_limit
        )
    )

    messages = brand_every_message(
        messages,
        branding,
        BALE_MESSAGE_LIMIT
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

    plan = PublicationPlan()

    plan.metadata[
        "other_entities"
    ] = other_entities

    plan.telegram = create_telegram_plan(
        main_text,
        blockquote_blocks,
        expandable_blocks,
        branding
    )

    plan.bale = create_bale_plan(
        main_text,
        blockquote_blocks,
        expandable_blocks,
        branding
    )

    plan.text[
        "telegram"
    ] = create_telegram_text_plan(
        main_text,
        blockquote_blocks,
        expandable_blocks,
        branding
    )

    plan.text[
        "bale"
    ] = create_bale_text_plan(
        main_text,
        blockquote_blocks,
        expandable_blocks,
        branding
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

        telegram_visible = len(
            telegram_caption
        )

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption_visible={telegram_visible} | "
        f"tg_followup="
        f"{len(plan.telegram['followup_messages'])} | "
        f"tg_blockquote_followup="
        f"{len(plan.telegram['blockquote_messages'])} | "
        f"tg_parse_mode="
        f"{plan.telegram.get('media_parse_mode') or 'NONE'} | "
        f"tg_fallback="
        f"{plan.telegram.get('document_fallback', False)} | "
        f"bale_caption="
        f"{len(plan.bale['media_caption'])} | "
        f"bale_followup="
        f"{len(plan.bale['followup_messages'])}"
    )

    return plan
