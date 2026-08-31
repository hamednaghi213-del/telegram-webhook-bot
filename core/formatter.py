import logging
import re
import unicodedata
from typing import Optional, List

from core.cleaner import clean_text

logger = logging.getLogger(__name__)


CHANNEL_TAG: Optional[str] = None
HASHTAG: Optional[str] = None

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

SOURCE_ICONS = (
    "🆔",
    "📡",
    "📢",
    "🔗",
    "🌐",
    "🇮🇷",
)

INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\ufe0e\ufe0f]"
)

SEPARATOR_ONLY_RE = re.compile(
    r"^[\|\-–—_•·▪▫◾◽:؛,،.\\/]+$"
)

SUSPICIOUS_FOOTER_FRAGMENTS = {
    "|",
    "I",
    "l",
    "1",
    "ا",
}


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


def normalize_invisible_characters(
    text: str
) -> str:
    if not text:
        return ""

    return INVISIBLE_RE.sub(
        "",
        str(text)
    )


def normalize_username(
    username: Optional[str]
) -> str:
    if not username:
        return ""

    username = (
        normalize_invisible_characters(
            str(username)
        )
        .strip()
    )

    if not username:
        return ""

    if not username.startswith("@"):
        username = f"@{username}"

    return username.lower()


def strip_leading_decoration(
    text: str
) -> str:
    if not text:
        return ""

    value = (
        normalize_invisible_characters(
            text
        )
        .strip()
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

        if changed:
            continue

        for icon in SOURCE_ICONS:
            if value.startswith(
                icon
            ):
                value = (
                    value[
                        len(icon):
                    ]
                    .strip()
                )
                changed = True
                break

    return value


def is_orphan_separator_line(
    line: str
) -> bool:
    if not line:
        return False

    value = (
        normalize_invisible_characters(
            line
        )
        .strip()
    )

    if not value:
        return False

    value = (
        strip_leading_decoration(
            value
        )
    )

    if not value:
        return True

    return bool(
        SEPARATOR_ONLY_RE.fullmatch(
            value
        )
    )


def is_suspicious_footer_fragment(
    line: str
) -> bool:
    if not line:
        return False

    value = (
        strip_leading_decoration(
            line
        )
        .strip()
    )

    if not value:
        return True

    if is_orphan_separator_line(
        value
    ):
        return True

    return (
        value
        in SUSPICIOUS_FOOTER_FRAGMENTS
    )


def remove_orphan_separators(
    text: str
) -> str:
    if not text:
        return ""

    lines = text.splitlines()

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


def is_source_line(
    line: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> bool:
    if not line:
        return False

    stripped = (
        normalize_invisible_characters(
            line
        )
        .strip()
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

    # A trailing line explicitly introduced by a source/contact icon and
    # containing a Telegram handle is a channel signature even when Telegram
    # does not expose (or exposes a different) forward-source username.
    # Example: "🆔 @YjcNewsChannel".
    stripped_without_invisible = normalize_invisible_characters(stripped)
    has_source_icon = any(
        stripped_without_invisible.startswith(icon)
        for icon in SOURCE_ICONS
    )
    if has_source_icon and re.search(r"@[A-Za-z0-9_]{5,}", normalized_line):
        return True

    has_footer_decoration = any(
    stripped_without_invisible.startswith(decoration)
    for decoration in (KNOWN_BULLETS + SOURCE_ICONS)
    )

    standalone_handle = (
        strip_trailing_source_icons(
            normalized_line
        )
        .strip()
    )

    if (
        has_footer_decoration
        and re.fullmatch(
            r"@[A-Za-z0-9_]{5,}",
            standalone_handle,
        )
    ):
        return True
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

    if source_title:
        source_title_clean = (
            normalize_invisible_characters(
                str(source_title)
            )
            .strip()
        )

        source_title_lower = (
            source_title_clean.lower()
        )

        if source_title_lower:
            normalized_line_without_trailing_icons = (
                strip_trailing_source_icons(
                    normalized_line
                )
                .strip()
                .lower()
            )

            source_title_without_trailing_icons = (
                strip_trailing_source_icons(
                    source_title_clean
                )
                .strip()
                .lower()
            )

            if (
                normalized_line_lower
                == source_title_lower
                or (
                    source_title_without_trailing_icons
                    and normalized_line_without_trailing_icons
                    == source_title_without_trailing_icons
                )
            ):
                return True

            if (
                normalized_line_lower
                == f"کانال {source_title_lower}"
            ):
                return True

            if (
                normalized_line_lower
                == f"{source_title_lower} کانال"
            ):
                return True

            # Some channels use a linked promotional label instead of their
            # exact Telegram title, for example forward title
            # "دیپارتمان ZTE13" and footer
            # "کانال تحلیلی مالی دیپارتمان ZTE". Treat only a short,
            # trailing channel/media label with a distinctive title token as
            # a signature. Ordinary sentences mentioning the source remain.
            footer_words = {"کانال", "رسانه", "پیج", "صفحه"}
            line_tokens = set(re.findall(
                r"[A-Za-z0-9_\u0600-\u06ff]+", normalized_line_lower
            ))
            title_tokens = set(re.findall(
                r"[A-Za-z0-9_\u0600-\u06ff]+", source_title_lower
            ))
            distinctive_title_tokens = {
                token for token in title_tokens
                if len(token) >= 5 and token not in footer_words
            }
            looks_like_linked_channel_label = bool(
                line_tokens & footer_words
                and line_tokens & distinctive_title_tokens
                and len(normalized_line) <= len(source_title_clean) + 40
                and not re.search(r"[.!؟?]$", normalized_line)
            )
            if looks_like_linked_channel_label:
                return True

    return False


def is_promotional_source_footer_line(
    line: str,
    source_title: Optional[str] = None,
) -> bool:
    """
    Detect a trailing promotional/social-media footer belonging to the
    forwarded source.

    This intentionally requires source metadata plus promotional wording so
    an ordinary body sentence mentioning the source is not removed.
    """
    if not line or not source_title:
        return False

    value = (
        strip_leading_decoration(
            normalize_invisible_characters(
                line
            )
        )
        .strip()
    )

    if not value:
        return False

    value_lower = value.lower()

    source_title_clean = (
        strip_leading_decoration(
            normalize_invisible_characters(
                str(source_title)
            )
        )
        .strip()
        .lower()
    )

    if not source_title_clean:
        return False

    title_tokens = {
        token
        for token in re.findall(
            r"[A-Za-z0-9_\u0600-\u06ff]+",
            source_title_clean,
        )
        if len(token) >= 3
    }

    line_tokens = set(
        re.findall(
            r"[A-Za-z0-9_\u0600-\u06ff]+",
            value_lower,
        )
    )

    mentions_source = bool(
        title_tokens
        and line_tokens & title_tokens
    )

    promotional_phrases = (
        "دنبال کنید",
        "ما را دنبال کنید",
        "در فضای مجازی",
        "شبکه های اجتماعی",
        "شبکه‌های اجتماعی",
        "همراه ما باشید",
        "به ما بپیوندید",
        "عضویت در",
        "عضو شوید",
    )

    has_promotional_phrase = any(
        phrase in value_lower
        for phrase in promotional_phrases
    )

    return (
        mentions_source
        and has_promotional_phrase
    )


def strip_trailing_source_icons(
    text: str
) -> str:
    """
    Remove only icon/emoji decoration that remains after the final textual
    content.

    Internal emoji are preserved.

    Examples:
        "متن خبر ✳️" -> "متن خبر"
        "متن خبر 🔴🔷" -> "متن خبر"
        "متن 🔴 داخل خبر" -> unchanged
    """
    if not text:
        return ""

    value = text.rstrip()

    while value:
        changed = False

        while (
            value
            and value[-1].isspace()
        ):
            value = value[:-1]
            changed = True

        if not value:
            break

        character = value[-1]

        if (
            character in {
                "\ufe0e",
                "\ufe0f",
                "\u200d",
                "\u20e3",
            }
            or "\U0001F3FB"
            <= character
            <= "\U0001F3FF"
            or unicodedata.category(
                character
            ) in {"So", "Sk"}
        ):
            value = value[:-1]
            changed = True
            continue

        if not changed:
            break

    return value.rstrip()


def remove_source_signature(
    text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    if not text:
        return ""

    lines = text.splitlines()

    if not lines:
        return text

    start_index = max(
        0,
        len(lines) - 10
    )

    removable_indexes = set()

    standalone_source_url_pattern = re.compile(
        r"\s*(?:https?://|www\.)"
        r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
        r"(?:/[^\s]*)?\s*",
        flags=re.IGNORECASE,
    )

    adjacent_source_domain_pattern = re.compile(
        r"\s*(?:https?://)?(?:www\.)?"
        r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
        r"(?:/[^\s]*)?\s*",
        flags=re.IGNORECASE,
    )

    for index in range(
        start_index,
        len(lines)
    ):
        if is_source_line(
            lines[index],
            source_title=source_title,
            source_username=source_username
        ):
            removable_indexes.add(
                index
            )

    # Detect promotional/social-media source footers.
    #
    # Example:
    #
    #   🔷 هم‌میهن را در فضای مجازی دنبال کنید:
    #
    # Once a confirmed promotional footer belonging to the forwarded source
    # begins in the trailing section, everything after it belongs to that
    # footer and must not enter the neutral/shared publication content.
    if source_title:
        promotional_footer_start = None

        for index in range(
            start_index,
            len(lines)
        ):
            if is_promotional_source_footer_line(
                lines[index],
                source_title=source_title,
            ):
                promotional_footer_start = index
                break

        if promotional_footer_start is not None:
            for index in range(
                promotional_footer_start,
                len(lines)
            ):
                removable_indexes.add(
                    index
                )

    # The established Legacy cleaner removes external source URLs before
    # formatting. Workspace content keeps a neutral copy so destination icons
    # can be applied later; classify a standalone URL on the final line as the
    # same source footer. Requiring forwarded-source metadata, a preceding
    # content line, and final position preserves legitimate body links.
    if source_title or source_username:
        non_empty_indexes = [
            index
            for index in range(
                start_index,
                len(lines)
            )
            if lines[index].strip()
        ]

        if len(non_empty_indexes) >= 2:
            final_index = non_empty_indexes[-1]

            if standalone_source_url_pattern.fullmatch(
                normalize_invisible_characters(
                    lines[final_index]
                )
            ):
                removable_indexes.add(
                    final_index
                )

    if removable_indexes:
        changed = True

        while changed:
            changed = False

            for index in list(
                removable_indexes
            ):
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
                        ]
                    )

                    if not candidate.strip():
                        removable_indexes.add(
                            neighbor
                        )
                        changed = True
                        continue
                    looks_like_adjacent_source_label = False

                    if (
                        source_title
                        and neighbor < index
                    ):
                        candidate_label = (
                            strip_trailing_source_icons(
                                strip_leading_decoration(
                                    normalize_invisible_characters(
                                        candidate
                                    )
                                )
                            )
                            .strip()
                            .lower()
                        )

                        source_label = (
                            strip_trailing_source_icons(
                                strip_leading_decoration(
                                    normalize_invisible_characters(
                                        str(source_title)
                                    )
                                )
                            )
                            .strip()
                            .lower()
                        )

                        candidate_tokens = set(
                            re.findall(
                                r"[A-Za-z0-9_\u0600-\u06ff]+",
                                candidate_label,
                            )
                        )

                        source_tokens = set(
                            re.findall(
                                r"[A-Za-z0-9_\u0600-\u06ff]+",
                                source_label,
                            )
                        )

                        shared_tokens = (
                            candidate_tokens
                            & source_tokens
                        )

                        looks_like_adjacent_source_label = (
                            len(shared_tokens) >= 2
                            and bool(candidate_tokens)
                            and (
                                len(shared_tokens)
                                / len(candidate_tokens)
                            ) >= 0.75
                            and len(candidate_label) <= (
                                len(source_label) + 20
                            )
                            and not re.search(
                                r"[.!؟?]$",
                                candidate_label,
                            )
                        )
                    if (
                        looks_like_adjacent_source_label
                        or is_orphan_separator_line(
                            candidate
                        )
                        or is_suspicious_footer_fragment(
                            candidate
                        )
                        or bool(
                            re.fullmatch(
                                r"#[A-Za-z0-9_]{1,4}",
                                normalize_invisible_characters(
                                    candidate
                                ).strip(),
                            )
                        )
                        or (
                            # A standalone website immediately adjacent to a
                            # confirmed source handle/title is part of the
                            # same footer (e.g. asriran.com + @MyAsriran).
                            bool(
                                adjacent_source_domain_pattern.fullmatch(
                                    normalize_invisible_characters(
                                        candidate
                                    )
                                )
                            )
                        )
                        or (
                            neighbor < index
                            and bool(
                                re.fullmatch(
                                    r"\s*[^\w\s#@]+\s*"
                                    r"(?:#[\w\u0600-\u06ff]+|"
                                    r"@[A-Za-z0-9_]{5,})\s*",
                                    normalize_invisible_characters(
                                        candidate
                                    ),
                                    flags=re.UNICODE,
                                )
                            )
                        )
                    ):
                        removable_indexes.add(
                            neighbor
                        )
                        changed = True

    if (
        source_title
        or source_username
    ):
        non_empty_tail = [
            index
            for index in range(
                start_index,
                len(lines)
            )
            if lines[index].strip()
        ]

        for index in non_empty_tail[-4:]:
            if is_suspicious_footer_fragment(
                lines[index]
            ):
                removable_indexes.add(
                    index
                )

    cleaned_lines = [
        line
        for index, line
        in enumerate(lines)
        if index
        not in removable_indexes
    ]

    while (
        cleaned_lines
        and not cleaned_lines[-1].strip()
    ):
        cleaned_lines.pop()

    cleaned_text = "\n".join(
        cleaned_lines
    )

    cleaned_text = remove_orphan_separators(
        cleaned_text
    )

    # Final source-icon guard:
    # after footer cleanup, remove emoji/icon decoration that remains after
    # the final real textual content. Emoji inside the body are untouched.
    cleaned_text = strip_trailing_source_icons(
        cleaned_text
    )

    if removable_indexes:
        logger.info(
            f"🧹 Source/footer cleanup | "
            f"removed={len(removable_indexes)} | "
            f"title={source_title or '-'} | "
            f"username={source_username or '-'}"
        )

    return cleaned_text


def split_lines(
    text: str
) -> List[str]:
    if not text:
        return []

    return text.splitlines()


def has_known_bullet(
    text: str
) -> bool:
    if not text:
        return False

    stripped = text.strip()

    return any(
        stripped.startswith(
            bullet
        )
        for bullet
        in KNOWN_BULLETS
    )


def normalize_body_line(
    line: str,
    bullet: str = BODY_BULLET
) -> str:
    if not line:
        return ""

    stripped = line.strip()

    if not stripped:
        return ""

    if is_orphan_separator_line(
        stripped
    ):
        return ""

    if has_known_bullet(
        stripped
    ):
        cleaned = stripped
        changed = True

        while changed:
            changed = False

            for existing_bullet in KNOWN_BULLETS:
                if cleaned.startswith(
                    existing_bullet
                ):
                    cleaned = (
                        cleaned[
                            len(existing_bullet):
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

        return f"{bullet} {cleaned}"

    return f"{bullet} {stripped}"


def format_paragraph(
    lines: List[str],
    bullet: str = BODY_BULLET
) -> str:
    if not lines:
        return ""

    formatted_lines = []

    for line in lines:
        formatted_line = normalize_body_line(
            line,
            bullet=bullet
        )

        if formatted_line:
            formatted_lines.append(
                formatted_line
            )

    return "\n".join(
        formatted_lines
    )


def normalize_title(
    title: str
) -> str:
    if not title:
        return ""

    value = title.strip()

    if value.startswith(
        TITLE_ICON
    ):
        value = (
            value[
                len(TITLE_ICON):
            ]
            .strip()
        )

    return value


def format_news(
    raw_text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    if not raw_text:
        return ""

    cleaned = clean_text(
        raw_text
    )

    if not cleaned:
        return ""

    cleaned = remove_source_signature(
        cleaned,
        source_title=source_title,
        source_username=source_username
    )

    cleaned = remove_orphan_separators(
        cleaned
    )

    if not cleaned:
        return ""

    all_lines = split_lines(
        cleaned
    )

    if not all_lines:
        return ""

    title = None
    title_index = None

    for index, line in enumerate(
        all_lines
    ):
        stripped = line.strip()

        if not stripped:
            continue

        if is_orphan_separator_line(
            stripped
        ):
            continue

        title = normalize_title(
            stripped
        )

        title_index = index
        break

    if (
        title is None
        or title_index is None
    ):
        return ""

    body_lines = all_lines[
        title_index + 1:
    ]

    result = f"{TITLE_ICON} {title}"

    if body_lines:
        current_paragraph = []

        for line in body_lines:
            stripped = line.strip()

            if not stripped:
                if current_paragraph:
                    formatted_paragraph = format_paragraph(
                        current_paragraph
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
            formatted_paragraph = format_paragraph(
                current_paragraph
            )

            if formatted_paragraph:
                result += (
                    "\n\n"
                    + formatted_paragraph
                )

    result = remove_orphan_separators(
        result
    )

    return result


def add_branding(
    formatted_text: str,
    include_hashtag: bool = True,
    include_channel: bool = True
) -> str:
    if not formatted_text:
        return ""

    result = formatted_text.rstrip()

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


def process_news(
    raw_text: str,
    add_brand: bool = True,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    if not raw_text:
        return ""

    formatted = format_news(
        raw_text,
        source_title=source_title,
        source_username=source_username
    )

    if not formatted:
        return ""

    if add_brand:
        formatted = add_branding(
            formatted
        )

    return formatted
