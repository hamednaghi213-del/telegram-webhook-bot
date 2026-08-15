import logging
import re
from typing import Optional, List

from core.cleaner import clean_text

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

CHANNEL_TAG: Optional[str] = None
HASHTAG: Optional[str] = None


# =========================================================
# FORMAT CONFIG
# =========================================================

TITLE_ICON = "❇️"
BODY_BULLET = "🔹"

KNOWN_BULLETS = (
    "🔹",
    "🔷",
    "▪️",
    "▫️",
    "◾",
    "◽",
    "•",
    "▪",
    "▫",
)


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    channel_tag: str,
    hashtag: str
) -> None:

    global CHANNEL_TAG, HASHTAG

    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag

    logger.info(
        f"✅ Formatter initialized | "
        f"channel={CHANNEL_TAG} | "
        f"hashtag={HASHTAG}"
    )


# =========================================================
# NORMALIZE USERNAME
# =========================================================

def normalize_username(
    username: Optional[str]
) -> str:

    if not username:
        return ""

    username = str(
        username
    ).strip()

    if not username:
        return ""

    if not username.startswith("@"):
        username = (
            f"@{username}"
        )

    return username.lower()


# =========================================================
# STRIP LEADING DECORATION
# =========================================================

def strip_leading_decoration(
    text: str
) -> str:

    if not text:
        return ""

    value = (
        text.strip()
    )

    changed = True

    while changed:

        changed = False

        for bullet in KNOWN_BULLETS:

            if value.startswith(
                bullet
            ):

                value = (
                    value[
                        len(bullet):
                    ]
                    .strip()
                )

                changed = True
                break

    value = re.sub(
        r"^(?:🆔|📡|📢|🔗|🌐|🇮🇷)\s*",
        "",
        value
    ).strip()

    return value


# =========================================================
# ORPHAN DECORATION / SEPARATOR
# =========================================================

def is_orphan_separator_line(
    line: str
) -> bool:
    """
    خطوط یتیم باقی‌مانده از امضای منبع را تشخیص می‌دهد.

    نمونه‌هایی که حذف می‌شوند:

        |
        ||
        🔹 |
        🔷 |
        🆔 |
        • |
        - |
        — |
    """

    if not line:
        return False

    value = (
        line.strip()
    )

    if not value:
        return False

    # حذف Bulletهای ابتدایی
    value = (
        strip_leading_decoration(
            value
        )
    )

    # حذف علامت‌های معرفی منبع
    value = re.sub(
        r"^(?:🆔|📡|📢|🔗|🌐|🇮🇷)\s*",
        "",
        value
    ).strip()

    if not value:
        return True

    # فقط Separator / Decoration
    if re.fullmatch(
        r"[\|\-–—_•·▪▫◾◽:؛,،.]+",
        value
    ):
        return True

    return False


# =========================================================
# REMOVE ORPHAN SEPARATORS
# =========================================================

def remove_orphan_separators(
    text: str
) -> str:

    if not text:
        return ""

    lines = (
        text.splitlines()
    )

    cleaned_lines: List[str] = []

    removed_count = 0

    for line in lines:

        if is_orphan_separator_line(
            line
        ):

            removed_count += 1
            continue

        cleaned_lines.append(
            line
        )

    # حذف خطوط خالی انتهایی
    while (
        cleaned_lines
        and not cleaned_lines[-1].strip()
    ):

        cleaned_lines.pop()

    if removed_count:

        logger.info(
            f"🧹 Orphan separators removed | "
            f"count={removed_count}"
        )

    return "\n".join(
        cleaned_lines
    )


# =========================================================
# IS SOURCE LINE
# =========================================================

def is_source_line(
    line: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> bool:

    if not line:
        return False

    stripped = (
        line.strip()
    )

    if not stripped:
        return False

    normalized_line = (
        strip_leading_decoration(
            stripped
        )
    )

    normalized_line_lower = (
        normalized_line.lower()
    )

    # =====================================================
    # SOURCE USERNAME
    # =====================================================

    normalized_source_username = (
        normalize_username(
            source_username
        )
    )

    if normalized_source_username:

        if (
            normalized_line_lower
            == normalized_source_username
        ):

            return True

        if (
            normalized_source_username
            in normalized_line_lower
            and len(
                normalized_line_lower
            )
            <= (
                len(
                    normalized_source_username
                )
                + 20
            )
        ):

            return True

    # =====================================================
    # SOURCE TITLE
    # =====================================================

    if source_title:

        source_title_clean = (
            str(
                source_title
            )
            .strip()
        )

        source_title_lower = (
            source_title_clean.lower()
        )

        if source_title_lower:

            if (
                normalized_line_lower
                == source_title_lower
            ):

                return True

            if (
                normalized_line_lower
                == (
                    f"کانال "
                    f"{source_title_lower}"
                )
            ):

                return True

            if (
                normalized_line_lower
                == (
                    f"{source_title_lower} "
                    f"کانال"
                )
            ):

                return True

    return False


# =========================================================
# REMOVE SOURCE SIGNATURE
# =========================================================

def remove_source_signature(
    text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:

    if not text:
        return ""

    lines = (
        text.splitlines()
    )

    if not lines:
        return text

    start_index = max(
        0,
        len(lines) - 8
    )

    removable_indexes = set()

    for index in range(
        start_index,
        len(lines)
    ):

        line = (
            lines[index]
        )

        if is_source_line(
            line,
            source_title=source_title,
            source_username=source_username
        ):

            removable_indexes.add(
                index
            )

    # =====================================================
    # NEIGHBOR DECORATION CLEANUP
    # =====================================================

    if removable_indexes:

        changed = True

        while changed:

            changed = False

            current_indexes = list(
                removable_indexes
            )

            for index in current_indexes:

                for neighbor in (
                    index - 1,
                    index + 1
                ):

                    if (
                        neighbor < start_index
                        or neighbor >= len(lines)
                        or neighbor
                        in removable_indexes
                    ):

                        continue

                    candidate = (
                        lines[
                            neighbor
                        ].strip()
                    )

                    if not candidate:

                        removable_indexes.add(
                            neighbor
                        )

                        changed = True
                        continue

                    if is_orphan_separator_line(
                        candidate
                    ):

                        removable_indexes.add(
                            neighbor
                        )

                        changed = True
                        continue

                    decoration_only = (
                        re.fullmatch(
                            r"[\s🔹🔷▪▫◾◽•🆔📡📢🔗🌐🇮🇷\|]+",
                            candidate
                        )
                    )

                    if decoration_only:

                        removable_indexes.add(
                            neighbor
                        )

                        changed = True

    if not removable_indexes:

        # حتی بدون Source match ممکن است | یتیم مانده باشد.
        return remove_orphan_separators(
            text
        )

    cleaned_lines = [
        line

        for index, line
        in enumerate(
            lines
        )

        if index
        not in removable_indexes
    ]

    while (
        cleaned_lines
        and not cleaned_lines[-1].strip()
    ):

        cleaned_lines.pop()

    cleaned_text = (
        "\n".join(
            cleaned_lines
        )
    )

    cleaned_text = (
        remove_orphan_separators(
            cleaned_text
        )
    )

    logger.info(
        f"🧹 Source signature removed | "
        f"title={source_title or '-'} | "
        f"username={source_username or '-'}"
    )

    return cleaned_text


# =========================================================
# SPLIT LINES
# =========================================================

def split_lines(
    text: str
) -> List[str]:

    if not text:
        return []

    return (
        text.splitlines()
    )


# =========================================================
# HAS BULLET
# =========================================================

def has_known_bullet(
    text: str
) -> bool:

    if not text:
        return False

    stripped = (
        text.strip()
    )

    return any(
        stripped.startswith(
            bullet
        )

        for bullet
        in KNOWN_BULLETS
    )


# =========================================================
# NORMALIZE BODY LINE
# =========================================================

def normalize_body_line(
    line: str,
    bullet: str = BODY_BULLET
) -> str:

    if not line:
        return ""

    stripped = (
        line.strip()
    )

    if not stripped:
        return ""

    # یتیم‌های منبع نباید تبدیل به 🔹 | شوند.
    if is_orphan_separator_line(
        stripped
    ):

        return ""

    if has_known_bullet(
        stripped
    ):

        cleaned = (
            stripped
        )

        changed = True

        while changed:

            changed = False

            for existing_bullet in KNOWN_BULLETS:

                if cleaned.startswith(
                    existing_bullet
                ):

                    cleaned = (
                        cleaned[
                            len(
                                existing_bullet
                            ):
                        ]
                        .strip()
                    )

                    changed = True
                    break

        if (
            not cleaned
            or is_orphan_separator_line(
                cleaned
            )
        ):

            return ""

        return (
            f"{bullet} {cleaned}"
        )

    return (
        f"{bullet} {stripped}"
    )


# =========================================================
# FORMAT PARAGRAPH
# =========================================================

def format_paragraph(
    lines: List[str],
    bullet: str = BODY_BULLET
) -> str:

    if not lines:
        return ""

    formatted_lines = []

    for line in lines:

        formatted_line = (
            normalize_body_line(
                line,
                bullet=bullet
            )
        )

        if formatted_line:

            formatted_lines.append(
                formatted_line
            )

    return "\n".join(
        formatted_lines
    )


# =========================================================
# NORMALIZE TITLE
# =========================================================

def normalize_title(
    title: str
) -> str:

    if not title:
        return ""

    value = (
        title.strip()
    )

    if value.startswith(
        TITLE_ICON
    ):

        value = (
            value[
                len(
                    TITLE_ICON
                ):
            ]
            .strip()
        )

    return value


# =========================================================
# FORMAT NEWS
# =========================================================

def format_news(
    raw_text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:

    if not raw_text:
        return ""

    logger.debug(
        f"📝 Formatting news | "
        f"length={len(raw_text)} | "
        f"preview={raw_text[:80]!r}"
    )

    # =====================================================
    # STEP 1
    # CLEAN TEXT
    # =====================================================

    cleaned = (
        clean_text(
            raw_text
        )
    )

    if not cleaned:

        logger.warning(
            "⚠️ Text is empty after cleaning"
        )

        return ""

    # =====================================================
    # STEP 2
    # SOURCE CLEANUP
    # =====================================================

    cleaned = (
        remove_source_signature(
            cleaned,
            source_title=source_title,
            source_username=source_username
        )
    )

    # =====================================================
    # STEP 3
    # ORPHAN SEPARATOR CLEANUP
    # =====================================================

    cleaned = (
        remove_orphan_separators(
            cleaned
        )
    )

    if not cleaned:

        logger.warning(
            "⚠️ Text empty after source cleanup"
        )

        return ""

    # =====================================================
    # STEP 4
    # SPLIT LINES
    # =====================================================

    all_lines = (
        split_lines(
            cleaned
        )
    )

    if not all_lines:

        logger.warning(
            "⚠️ No lines found"
        )

        return ""

    # =====================================================
    # STEP 5
    # FIND TITLE
    # =====================================================

    title = None
    title_index = None

    for index, line in enumerate(
        all_lines
    ):

        stripped = (
            line.strip()
        )

        if not stripped:
            continue

        if is_orphan_separator_line(
            stripped
        ):
            continue

        title = (
            normalize_title(
                stripped
            )
        )

        title_index = (
            index
        )

        break

    if (
        title is None
        or title_index is None
    ):

        logger.warning(
            "⚠️ No title found"
        )

        return ""

    # =====================================================
    # STEP 6
    # BODY
    # =====================================================

    body_lines = (
        all_lines[
            title_index + 1:
        ]
    )

    # =====================================================
    # STEP 7
    # BUILD RESULT
    # =====================================================

    result = (
        f"{TITLE_ICON} {title}"
    )

    if body_lines:

        current_paragraph = []

        for line in body_lines:

            stripped = (
                line.strip()
            )

            if not stripped:

                if current_paragraph:

                    formatted_paragraph = (
                        format_paragraph(
                            current_paragraph
                        )
                    )

                    if formatted_paragraph:

                        result += (
                            "\n\n"
                            + formatted_paragraph
                        )

                    current_paragraph = []

                continue

            if is_orphan_separator_line(
                stripped
            ):

                continue

            current_paragraph.append(
                stripped
            )

        if current_paragraph:

            formatted_paragraph = (
                format_paragraph(
                    current_paragraph
                )
            )

            if formatted_paragraph:

                result += (
                    "\n\n"
                    + formatted_paragraph
                )

    # Safety نهایی
    result = (
        remove_orphan_separators(
            result
        )
    )

    logger.debug(
        f"✅ Formatted news | "
        f"length={len(result)}"
    )

    return result


# =========================================================
# ADD BRANDING
# =========================================================

def add_branding(
    formatted_text: str,
    include_hashtag: bool = True,
    include_channel: bool = True
) -> str:

    if not formatted_text:
        return ""

    result = (
        formatted_text.rstrip()
    )

    branding_lines = []

    if (
        include_hashtag
        and HASHTAG
    ):

        branding_lines.append(
            HASHTAG
        )

    if (
        include_channel
        and CHANNEL_TAG
    ):

        branding_lines.append(
            CHANNEL_TAG
        )

    if branding_lines:

        result += (
            "\n\n"
            + "\n".join(
                branding_lines
            )
        )

    return result


# =========================================================
# PROCESS NEWS
# =========================================================

def process_news(
    raw_text: str,
    add_brand: bool = True,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:

    if not raw_text:
        return ""

    formatted = (
        format_news(
            raw_text,
            source_title=source_title,
            source_username=source_username
        )
    )

    if not formatted:
        return ""

    if add_brand:

        formatted = (
            add_branding(
                formatted
            )
        )

    return formatted
