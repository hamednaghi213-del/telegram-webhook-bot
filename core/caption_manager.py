import logging
import os
import re

from html import escape, unescape
from typing import Dict, List, Optional, Any, Tuple

from core.content_entities import build_blockquote_html
from core.cleaner import clean_text

from core.telegram_caption_entities import (
    build_telegram_caption_entities
)

from core.smart_summarizer import (
    summarize_text_safely
)

from core.ai_summarizer_provider import (
    gemini_provider_configured,
    summarize_with_gemini
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
# SMART SUMMARIZER CONFIG
# =========================================================

SMART_SUMMARIZER_ENV = (
    "ENABLE_SMART_SUMMARIZER"
)

SMART_MAIN_PRESERVE_LIMIT = 320


def smart_summarizer_enabled() -> bool:

    value = (
        os.getenv(
            SMART_SUMMARIZER_ENV,
            "false"
        )
        or ""
    )

    return (
        value
        .strip()
        .lower()
        in (
            "1",
            "true",
            "yes",
            "on"
        )
    )


# =========================================================
# PUBLICATION PLAN
# =========================================================

class PublicationPlan:

    def __init__(self):

        self.telegram: Dict[str, Any] = {
            "media_caption": "",
            "media_parse_mode": None,
            "media_caption_entities": [],
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
# TELEGRAM MEDIA FINAL BRANDING
# =========================================================

def append_final_telegram_media_branding(
    caption: str,
    branding: str,
    has_expandable: bool = False
) -> str:

    caption = normalize_text(
        caption
    )

    branding = normalize_text(
        branding
    )

    if not branding:
        return caption

    if not caption:
        return branding

    separator = "\n\n"

    result = (
        caption
        + separator
        + branding
    )

    logger.info(
        f"🏷️ Telegram final branding appended | "
        f"expandable={has_expandable} | "
        f"caption_before={len(caption)} | "
        f"branding={len(branding)} | "
        f"caption_after={len(result)} | "
        f"branding_entities=False"
    )

    return result


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

    lines = text.splitlines()

    cleaned_lines: List[str] = []

    for line in lines:

        value = line.strip()

        if not value:
            continue

        if value.startswith("🔹"):

            value = (
                value[1:]
                .lstrip()
            )

        if value:

            cleaned_lines.append(
                value
            )

    if not cleaned_lines:
        return ""

    title = cleaned_lines[0]

    if len(cleaned_lines) == 1:
        return title

    body = "\n".join(
        cleaned_lines[1:]
    )

    result = (
        title
        + "\n\n"
        + body
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

        result[
            "media_caption"
        ] = compact_text

        return result

    position = find_media_split_position(
        compact_text,
        caption_limit
    )

    if position <= 0:
        position = caption_limit

    result[
        "media_caption"
    ] = (
        compact_text[:position]
        .strip()
    )

    remaining = (
        compact_text[position:]
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
            "media_caption":
                media_caption,
            "followup_messages":
                messages
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

            if (
                len(candidate)
                <= message_limit
            ):

                branded_messages.append(
                    candidate
                )

            else:

                branded_messages.append(
                    message
                )

        return {
            "media_caption":
                media_caption,
            "followup_messages":
                branded_messages
        }

    candidate = append_branding(
        media_caption,
        branding
    )

    if len(candidate) <= caption_limit:

        media_caption = candidate

    else:

        messages.append(
            branding
        )

    return {
        "media_caption":
            media_caption,
        "followup_messages":
            messages
    }


def brand_every_message(
    messages: List[str],
    branding: str,
    message_limit: int
) -> List[str]:

    branding = normalize_text(
        branding
    )

    result: List[str] = []

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

        candidate = append_branding(
            message,
            branding
        )

        if len(candidate) <= message_limit:

            result.append(
                candidate
            )

        else:

            result.append(
                message
            )

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
    message_limit: int = (
        TELEGRAM_MESSAGE_LIMIT
    )
) -> List[str]:

    return brand_every_message(
        messages,
        branding,
        message_limit
    )


# =========================================================
# TELEGRAM MEDIA BRANDING HELPERS
# =========================================================

def append_telegram_media_branding(
    text: str,
    branding: str
) -> str:

    return append_final_telegram_media_branding(
        text,
        branding,
        has_expandable=False
    )


def brand_telegram_media_messages(
    messages: List[str],
    branding: str,
    message_limit: int
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
            "offset":
                block.get(
                    "offset",
                    0
                ),
            "text":
                block.get(
                    "text",
                    ""
                ),
            "expandable":
                False
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined.append({
            "offset":
                block.get(
                    "offset",
                    0
                ),
            "text":
                block.get(
                    "text",
                    ""
                ),
            "expandable":
                True
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
# SMART TELEGRAM MEDIA SUMMARY
# =========================================================

def try_smart_telegram_media_summary(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str,
    caption_limit: int
) -> Optional[Dict[str, Any]]:

    if not smart_summarizer_enabled():

        logger.info(
            "ℹ️ Smart summarizer disabled | "
            "legacy overflow preserved"
        )

        return None

    if not gemini_provider_configured():

        logger.warning(
            "⚠️ Smart summarizer enabled but "
            "Gemini provider is not configured | "
            "legacy overflow preserved"
        )

        return None

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    combined_blocks = (
        _combined_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    source_parts: List[
        Dict[str, Any]
    ] = []

    preserve_short_main = bool(
        main_text
        and combined_blocks
        and len(main_text)
        <= SMART_MAIN_PRESERVE_LIMIT
    )

    if main_text:

        source_parts.append({
            "kind":
                "main",
            "text":
                main_text,
            "offset":
                0,
            "expandable":
                False,
            "preserve":
                preserve_short_main
        })

    for block in combined_blocks:

        cleaned = (
            clean_blockquote_text(
                block.get(
                    "text",
                    ""
                )
            )
        )

        if not cleaned:
            continue

        source_parts.append({
            "kind":
                "block",
            "text":
                cleaned,
            "offset":
                block.get(
                    "offset",
                    0
                ),
            "expandable":
                bool(
                    block.get(
                        "expandable",
                        False
                    )
                ),
            "preserve":
                False
        })

    if not source_parts:
        return None

    branding_cost = (
        len(branding)
        + 2
        if branding
        else 0
    )

    available_content = (
        caption_limit
        - branding_cost
    )

    if available_content <= 0:

        logger.warning(
            "⚠️ Smart summary skipped | "
            "branding consumes caption capacity"
        )

        return None

    separator_cost = (
        2
        * max(
            0,
            len(source_parts)
            - 1
        )
    )

    available_text_capacity = (
        available_content
        - separator_cost
    )

    if available_text_capacity <= 0:
        return None

    total_source_text_length = sum(
        len(
            item[
                "text"
            ]
        )
        for item
        in source_parts
    )

    if total_source_text_length <= 0:
        return None

    visible_source_length = (
        total_source_text_length
        + separator_cost
    )

    if (
        visible_source_length
        <= available_content
    ):

        return None

    required_reduction_ratio = (
        (
            visible_source_length
            - available_content
        )
        / visible_source_length
    )

    logger.info(
        f"🧠 Smart media summarization candidate | "
        f"parts={len(source_parts)} | "
        f"source_visible="
        f"{visible_source_length} | "
        f"capacity={available_content} | "
        f"required_reduction="
        f"{required_reduction_ratio:.3f} | "
        f"preserve_short_main="
        f"{preserve_short_main} | "
        f"policy=AI_ADAPTIVE"
    )

    preserved_length = sum(
        len(
            item[
                "text"
            ]
        )
        for item
        in source_parts
        if item.get(
            "preserve"
        )
    )

    summarizable_parts = [
        item
        for item
        in source_parts
        if not item.get(
            "preserve"
        )
    ]

    summarizable_source_length = sum(
        len(
            item[
                "text"
            ]
        )
        for item
        in summarizable_parts
    )

    summarizable_budget = (
        available_text_capacity
        - preserved_length
    )

    if summarizable_budget <= 0:

        logger.warning(
            f"⚠️ Smart summary unavailable | "
            f"preserved={preserved_length} | "
            f"available="
            f"{available_text_capacity}"
        )

        return None

    if (
        summarizable_source_length
        <= summarizable_budget
    ):

        return None

    logger.info(
        f"🛡️ Smart preserved content | "
        f"main_preserved="
        f"{preserve_short_main} | "
        f"preserved_length="
        f"{preserved_length} | "
        f"summarizable_source="
        f"{summarizable_source_length} | "
        f"summarizable_budget="
        f"{summarizable_budget}"
    )

    summarized_parts: List[
        Dict[str, Any]
    ] = []

    remaining_budget = (
        summarizable_budget
    )

    remaining_source_length = (
        summarizable_source_length
    )

    summarizable_index = 0

    total_summarizable_parts = len(
        summarizable_parts
    )

    for item in source_parts:

        source_text = (
            item[
                "text"
            ]
        )

        source_length = len(
            source_text
        )

        if item.get(
            "preserve"
        ):

            summarized_parts.append({
                "kind":
                    item[
                        "kind"
                    ],
                "text":
                    source_text,
                "offset":
                    item[
                        "offset"
                    ],
                "expandable":
                    item[
                        "expandable"
                    ],
                "content_type":
                    "preserved"
            })

            logger.info(
                f"🛡️ Smart summary part preserved | "
                f"kind={item['kind']} | "
                f"length={source_length}"
            )

            continue

        summarizable_index += 1

        is_last = (
            summarizable_index
            == total_summarizable_parts
        )

        if is_last:

            target_length = max(
                1,
                remaining_budget
            )

        else:

            if remaining_source_length <= 0:
                return None

            proportional_target = int(
                remaining_budget
                * (
                    source_length
                    / remaining_source_length
                )
            )

            target_length = max(
                1,
                min(
                    source_length,
                    proportional_target
                )
            )

        if source_length <= target_length:

            summarized_parts.append({
                "kind":
                    item[
                        "kind"
                    ],
                "text":
                    source_text,
                "offset":
                    item[
                        "offset"
                    ],
                "expandable":
                    item[
                        "expandable"
                    ],
                "content_type":
                    "unchanged"
            })

            remaining_budget -= (
                source_length
            )

            remaining_source_length -= (
                source_length
            )

            continue

        logger.info(
            f"🧠 Smart summary part prepared | "
            f"part={summarizable_index}/"
            f"{total_summarizable_parts} | "
            f"kind={item['kind']} | "
            f"source={source_length} | "
            f"target={target_length}"
        )

        result = (
            summarize_text_safely(
                original_text=(
                    source_text
                ),
                target_length=(
                    target_length
                ),
                summarizer=(
                    summarize_with_gemini
                )
            )
        )

        if not result.success:

            logger.warning(
                f"⚠️ Smart media summary rejected | "
                f"part={summarizable_index} | "
                f"kind={item['kind']} | "
                f"reason={result.reason} | "
                f"content_type="
                f"{result.metadata.get('content_type', '-')} | "
                f"required="
                f"{result.metadata.get('required_reduction_ratio', '-')} | "
                f"allowed="
                f"{result.metadata.get('effective_max_reduction_ratio', '-')}"
            )

            return None

        summarized_text = normalize_text(
            result.summary_text
        )

        if not summarized_text:

            logger.warning(
                f"⚠️ Smart summary produced "
                f"empty part | "
                f"index={summarizable_index}"
            )

            return None

        if (
            len(summarized_text)
            > target_length
        ):

            logger.warning(
                f"⚠️ Smart summary part exceeds "
                f"target after provider | "
                f"part={summarizable_index} | "
                f"summary="
                f"{len(summarized_text)} | "
                f"target={target_length}"
            )

            return None

        summarized_parts.append({
            "kind":
                item[
                    "kind"
                ],
            "text":
                summarized_text,
            "offset":
                item[
                    "offset"
                ],
            "expandable":
                item[
                    "expandable"
                ],
            "content_type":
                result.metadata.get(
                    "content_type",
                    ""
                )
        })

        remaining_budget -= len(
            summarized_text
        )

        remaining_source_length -= (
            source_length
        )

        if remaining_budget < 0:

            logger.warning(
                "⚠️ Smart summary exceeded "
                "allocated text capacity"
            )

            return None

    summarized_main = ""

    summarized_normal_blocks: List[
        Dict[str, Any]
    ] = []

    summarized_expandable_blocks: List[
        Dict[str, Any]
    ] = []

    for item in summarized_parts:

        if (
            item[
                "kind"
            ]
            == "main"
        ):

            summarized_main = (
                item[
                    "text"
                ]
            )

            continue

        rebuilt_block = {
            "offset":
                item[
                    "offset"
                ],
            "text":
                item[
                    "text"
                ]
        }

        if item[
            "expandable"
        ]:

            rebuilt_block[
                "type"
            ] = (
                "expandable_blockquote"
            )

            summarized_expandable_blocks.append(
                rebuilt_block
            )

        else:

            rebuilt_block[
                "type"
            ] = "blockquote"

            summarized_normal_blocks.append(
                rebuilt_block
            )

    try:

        entity_result = (
            build_telegram_caption_entities(
                main_text=(
                    summarized_main
                ),
                blockquote_blocks=(
                    summarized_normal_blocks
                ),
                expandable_blocks=(
                    summarized_expandable_blocks
                ),
                branding=(
                    branding
                ),
                include_branding_entities=True
            )
        )

    except Exception as e:

        logger.exception(
            f"❌ Smart summary entity rebuild failed | "
            f"{e}"
        )

        return None

    final_caption = (
        entity_result.get(
            "caption",
            ""
        )
        or ""
    )

    caption_entities = list(
        entity_result.get(
            "caption_entities",
            []
        )
        or []
    )

    if len(final_caption) > caption_limit:

        logger.warning(
            f"⚠️ Smart summary final caption "
            f"still too long | "
            f"caption={len(final_caption)} | "
            f"limit={caption_limit}"
        )

        return None

    logger.info(
        f"✅ Smart media summary accepted | "
        f"caption={len(final_caption)} | "
        f"entities="
        f"{len(caption_entities)} | "
        f"parts="
        f"{len(summarized_parts)} | "
        f"main_preserved="
        f"{preserve_short_main} | "
        f"followups=0 | "
        f"branding_entities=True | "
        f"required_reduction="
        f"{required_reduction_ratio:.3f}"
    )

    return {
        "media_caption":
            final_caption,
        "media_parse_mode":
            None,
        "media_caption_entities":
            caption_entities,
        "followup_messages":
            [],
        "blockquote_messages":
            [],
        "document_fallback":
            False
    }


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
    branding: str = ""
) -> str:

    parts: List[str] = []

    main_text = normalize_text(
        main_text
    )

    if main_text:

        parts.append(
            escape(
                main_text
            )
        )

    blocks = (
        build_inline_telegram_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if blocks:

        parts.append(
            blocks
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

        position = (
            find_media_split_position(
                text,
                available,
                minimum_fill_ratio=0.50
            )
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
                "offset":
                    block.get(
                        "offset",
                        0
                    ),
                "text":
                    remaining_part,
                "expandable":
                    bool(
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

                html_message = (
                    append_branding(
                        html_message,
                        escape(
                            branding
                        )
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

    text = normalize_text(
        text
    )

    if not text:
        return ""

    result: List[str] = []

    for line in text.splitlines():

        line = line.strip()

        if line:

            result.append(
                f"▌ {line}"
            )

    return "\n".join(
        result
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
        "media_caption_entities": [],
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    has_blockquotes = bool(
        blockquote_blocks
        or expandable_blocks
    )

    has_expandable = bool(
        expandable_blocks
    )

    if has_blockquotes:

        try:

            entity_result = (
                build_telegram_caption_entities(
                    main_text=(
                        main_text
                    ),
                    blockquote_blocks=(
                        blockquote_blocks
                    ),
                    expandable_blocks=(
                        expandable_blocks
                    ),
                    branding=(
                        branding
                    ),
                    include_branding_entities=True
                )
            )

            entity_caption = (
                entity_result[
                    "caption"
                ]
            )

            entity_caption_entities = list(
                entity_result[
                    "caption_entities"
                ]
                or []
            )

            if (
                entity_caption
                and len(
                    entity_caption
                )
                <= TELEGRAM_CAPTION_LIMIT
            ):

                plan[
                    "media_caption"
                ] = entity_caption

                plan[
                    "media_parse_mode"
                ] = None

                plan[
                    "media_caption_entities"
                ] = (
                    entity_caption_entities
                )

                plan[
                    "followup_messages"
                ] = []

                plan[
                    "blockquote_messages"
                ] = []

                logger.info(
                    f"✅ Telegram ONE-MESSAGE entity caption | "
                    f"mode=FULL | "
                    f"caption="
                    f"{len(entity_caption)} | "
                    f"entities="
                    f"{len(entity_caption_entities)} | "
                    f"expandable="
                    f"{has_expandable} | "
                    f"branding_inside=True | "
                    f"branding_entities=True | "
                    f"followups=0"
                )

                return plan

        except Exception as e:

            logger.exception(
                f"❌ Telegram full entity caption "
                f"build failed | {e}"
            )

        compact_main = (
            compact_long_text(
                main_text
            )
            or main_text
        )

        try:

            compact_entity_result = (
                build_telegram_caption_entities(
                    main_text=(
                        compact_main
                    ),
                    blockquote_blocks=(
                        blockquote_blocks
                    ),
                    expandable_blocks=(
                        expandable_blocks
                    ),
                    branding=(
                        branding
                    ),
                    include_branding_entities=True
                )
            )

            compact_entity_caption = (
                compact_entity_result[
                    "caption"
                ]
            )

            compact_entity_entities = list(
                compact_entity_result[
                    "caption_entities"
                ]
                or []
            )

            if (
                compact_entity_caption
                and len(
                    compact_entity_caption
                )
                <= TELEGRAM_CAPTION_LIMIT
            ):

                plan[
                    "media_caption"
                ] = (
                    compact_entity_caption
                )

                plan[
                    "media_parse_mode"
                ] = None

                plan[
                    "media_caption_entities"
                ] = (
                    compact_entity_entities
                )

                plan[
                    "followup_messages"
                ] = []

                plan[
                    "blockquote_messages"
                ] = []

                logger.info(
                    f"✅ Telegram ONE-MESSAGE entity caption | "
                    f"mode=COMPACT | "
                    f"caption="
                    f"{len(compact_entity_caption)} | "
                    f"entities="
                    f"{len(compact_entity_entities)} | "
                    f"expandable="
                    f"{has_expandable} | "
                    f"branding_entities=True"
                )

                return plan

        except Exception as e:

            logger.exception(
                f"❌ Telegram compact entity caption "
                f"build failed | {e}"
            )

        smart_plan = (
            try_smart_telegram_media_summary(
                main_text=(
                    compact_main
                ),
                blockquote_blocks=(
                    blockquote_blocks
                ),
                expandable_blocks=(
                    expandable_blocks
                ),
                branding=(
                    branding
                ),
                caption_limit=(
                    TELEGRAM_CAPTION_LIMIT
                )
            )
        )

        if smart_plan is not None:

            logger.info(
                "✅ Telegram SMART ONE-MESSAGE "
                "plan selected"
            )

            return smart_plan

        logger.info(
            "ℹ️ Telegram smart one-message unavailable | "
            "using stable overflow path"
        )

        branding_cost = (
            len(branding)
            if branding
            else 0
        )

        branding_separator_cost = (
            2
            if branding
            else 0
        )

        fixed_cost = (
            branding_cost
            + branding_separator_cost
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

        if len(compact_main) <= main_capacity:

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

                position = (
                    main_capacity
                )

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

        used_visible = len(
            main_for_caption
        )

        block_capacity = (
            TELEGRAM_CAPTION_LIMIT
            - used_visible
            - fixed_cost
            - (
                2
                if main_for_caption
                else 0
            )
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

        candidate_without_branding = (
            "\n\n".join(
                caption_parts
            )
        )

        candidate = (
            append_final_telegram_media_branding(
                candidate_without_branding,
                branding,
                has_expandable=(
                    has_expandable
                )
            )
        )

        if (
            telegram_html_visible_length(
                candidate
            )
            > TELEGRAM_CAPTION_LIMIT
        ):

            logger.error(
                "❌ Telegram overflow caption still "
                "exceeds official visible limit"
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

        plan[
            "media_caption_entities"
        ] = []

        if remaining_main:

            replies = split_text(
                remaining_main,
                TELEGRAM_MESSAGE_SAFE_LIMIT
            )

            plan[
                "followup_messages"
            ] = replies

        if remaining_blocks:

            plan[
                "blockquote_messages"
            ] = (
                build_branded_blockquote_messages(
                    remaining_blocks,
                    branding
                )
            )

        logger.warning(
            f"⚠️ Telegram overflow required | "
            f"caption="
            f"{telegram_html_visible_length(candidate)} | "
            f"followups="
            f"{len(plan['followup_messages'])} | "
            f"blockquotes="
            f"{len(plan['blockquote_messages'])}"
        )

        return plan

    # =====================================================
    # NORMAL MEDIA WITHOUT BLOCKQUOTE
    # =====================================================

    normal_final = (
        append_final_telegram_media_branding(
            main_text,
            branding,
            has_expandable=False
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
        append_final_telegram_media_branding(
            compact_main,
            branding,
            has_expandable=False
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

    smart_plan = (
        try_smart_telegram_media_summary(
            main_text=(
                compact_main
            ),
            blockquote_blocks=[],
            expandable_blocks=[],
            branding=(
                branding
            ),
            caption_limit=(
                TELEGRAM_CAPTION_SAFE_LIMIT
            )
        )
    )

    if smart_plan is not None:

        logger.info(
            "✅ Telegram SMART normal-media "
            "plan selected"
        )

        return smart_plan

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
        append_final_telegram_media_branding(
            main_for_caption,
            branding,
            has_expandable=False
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
        ] = (
            brand_telegram_media_messages(
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

    parts: List[str] = []

    if main_text:

        parts.append(
            main_text
        )

    if inline_blocks:

        parts.append(
            inline_blocks
        )

    if branding:

        parts.append(
            branding
        )

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

        for message in (
            split_result[
                "followup_messages"
            ]
        ):

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
        ] = (
            brand_every_message(
                rebuilt,
                branding,
                BALE_MESSAGE_LIMIT
            )
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

            messages = (
                brand_every_message(
                    messages,
                    branding,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

    return {
        "messages":
            messages,
        "blockquote_messages":
            create_telegram_blockquote_messages(
                blockquote_blocks,
                expandable_blocks
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

    # =====================================================
    # FIRST TRY
    #
    # پیام کوتاه بدون Compact حفظ می‌شود.
    # بنابراین 🔹 و ساختار اصلی خبر باقی می‌ماند.
    # =====================================================

    inline_blocks = (
        build_inline_bale_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    normal_parts: List[str] = []

    if main_text:

        normal_parts.append(
            main_text
        )

    if inline_blocks:

        normal_parts.append(
            inline_blocks
        )

    normal_content = "\n\n".join(
        normal_parts
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

    # =====================================================
    # LONG TEXT
    #
    # فقط برای متن طولانی Compact فعال می‌شود.
    # =====================================================

    compact_main = (
        compact_long_text(
            main_text
        )
        or main_text
    )

    branding_cost = (
        len(branding)
        + 2
        if branding
        else 0
    )

    content_limit = max(
        500,
        BALE_MESSAGE_SAFE_LIMIT
        - branding_cost
    )

    messages: List[str] = []

    # =====================================================
    # MAIN TEXT
    # =====================================================

    if compact_main:

        main_parts = split_text(
            compact_main,
            content_limit
        )

        messages.extend(
            main_parts
        )

    # =====================================================
    # BLOCKQUOTES
    #
    # هر Blockquote جدا Split و دوباره ساخته می‌شود
    # تا علامت ▌ حفظ شود.
    # =====================================================

    for block in _combined_blockquotes(
        blockquote_blocks,
        expandable_blocks
    ):

        block_text = clean_blockquote_text(
            block.get(
                "text",
                ""
            )
        )

        if not block_text:
            continue

        quote_parts = split_text(
            block_text,
            max(
                500,
                content_limit - 10
            )
        )

        for quote_part in quote_parts:

            quote_message = (
                build_bale_blockquote(
                    quote_part
                )
            )

            if quote_message:

                messages.append(
                    quote_message
                )

    # =====================================================
    # BRANDING
    # =====================================================

    final_messages = (
        brand_every_message(
            messages,
            branding,
            BALE_MESSAGE_LIMIT
        )
    )

    return {
        "messages":
            final_messages,
        "blockquote_messages":
            []
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
        f"branding="
        f"{len(branding)} | "
        f"smart_summary="
        f"{smart_summarizer_enabled()} | "
        f"smart_policy=AI_ADAPTIVE"
    )

    plan = PublicationPlan()

    plan.metadata[
        "other_entities"
    ] = other_entities

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

        telegram_visible = len(
            telegram_caption
        )

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption_visible="
        f"{telegram_visible} | "
        f"tg_entities="
        f"{len(plan.telegram.get('media_caption_entities', []))} | "
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
        f"{len(plan.bale['followup_messages'])} | "
        f"smart_summary="
        f"{smart_summarizer_enabled()}"
    )

    return plan
