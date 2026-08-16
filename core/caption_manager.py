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
                "blockquote_messages": [],
                "inline_html_message": "",
                "inline_html_parse_mode": None,
                "inline_html_smart_summary": False
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

    result = (
        caption
        + "\n\n"
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
