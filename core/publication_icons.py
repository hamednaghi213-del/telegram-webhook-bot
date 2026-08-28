"""Flexible Unicode icon extraction and application for Phase 10."""

import re
import unicodedata
from typing import Any, Dict, Iterable, List

MAX_ICONS = 32
MAX_ICON_LENGTH = 64

_EMOJI_BASE_PATTERN = re.compile(
    "["
    "\U0001F100-\U0001FAFF"
    "\u2300-\u23FF"
    "\u2500-\u27BF"
    "\u2B00-\u2BFF"
    "]",
    flags=re.UNICODE,
)

_EMOJI_COMPONENTS = {
    "\u200d",  # zero width joiner
    "\ufe0e",  # text variation selector
    "\ufe0f",  # emoji variation selector
    "\u20e3",  # combining enclosing keycap
}


def _looks_like_icon(token: str) -> bool:
    if not token or token.startswith(("#", "@")):
        return False

    return any(
        unicodedata.category(character) in {"So", "Sk"}
        for character in token
    )


def extract_icons(text: str) -> List[str]:
    """
    Extract ordered, unique Unicode icon sequences.

    Correctly keeps real composed emoji clusters together while separating
    adjacent independent emoji, e.g.:

        "🟩🔷" -> ["🟩", "🔷"]
        "👨‍👩‍👧‍👦" -> ["👨‍👩‍👧‍👦"]
        "👍🏽" -> ["👍🏽"]
    """
    value = text or ""
    icons: List[str] = []
    index = 0

    while index < len(value):
        character = value[index]

        is_keycap = (
            character in "#*0123456789"
            and index + 1 < len(value)
            and value[index + 1] in {"\ufe0f", "\u20e3"}
        )

        if not (
            _EMOJI_BASE_PATTERN.fullmatch(character)
            or is_keycap
        ):
            index += 1
            continue

        cluster = character
        index += 1

        while index < len(value):
            next_character = value[index]

            # Variation selectors, ZWJ and keycap components.
            if next_character in _EMOJI_COMPONENTS:
                cluster += next_character
                index += 1

                # A ZWJ joins the following base character into the same cluster.
                if (
                    next_character == "\u200d"
                    and index < len(value)
                ):
                    cluster += value[index]
                    index += 1

                continue

            # Fitzpatrick skin-tone modifiers.
            if "\U0001F3FB" <= next_character <= "\U0001F3FF":
                cluster += next_character
                index += 1
                continue

            break

        if (
            cluster not in icons
            and _looks_like_icon(cluster)
        ):
            icons.append(cluster)

        if len(icons) >= MAX_ICONS:
            break

    return icons


def _normalize_icon_value(value: Any) -> List[str]:
    """
    Normalize one stored icon value.

    Historical / malformed data may contain multiple adjacent icons inside
    a single list element:

        ["🟩🔷"]

    That must behave exactly like:

        ["🟩", "🔷"]

    Real composed emoji remain intact because extract_icons() respects
    Unicode emoji components and ZWJ sequences.
    """
    token = str(value or "").strip()

    if not token:
        return []

    # Hashtag/channel tokens are branding, not publication icons.
    if token.startswith(("#", "@")):
        return []

    extracted = extract_icons(token)

    if extracted:
        return extracted

    # Backward-compatible fallback for icon-like tokens that may not be
    # represented by the current extraction ranges.
    if (
        len(token) <= MAX_ICON_LENGTH
        and _looks_like_icon(token)
    ):
        return [token]

    return []


def normalize_icons(icons: Iterable[str]) -> List[str]:
    """
    Normalize an ordered icon collection.

    Important compatibility behavior:
    - ["🟩", "🔷"] stays ["🟩", "🔷"]
    - ["🟩🔷"] becomes ["🟩", "🔷"]
    - duplicate icons are removed while preserving order
    - real composed emoji clusters remain intact
    """
    normalized: List[str] = []

    for value in icons or []:
        for token in _normalize_icon_value(value):
            if token in normalized:
                continue

            if len(token) > MAX_ICON_LENGTH:
                continue

            normalized.append(token)

            if len(normalized) >= MAX_ICONS:
                return normalized

    return normalized


def strip_icons(text: str) -> str:
    """Remove source emoji decoration while preserving textual content."""
    value = text or ""

    for icon in extract_icons(value):
        value = value.replace(icon, "")

    value = (
        value
        .replace("\ufe0e", "")
        .replace("\ufe0f", "")
        .replace("\u200d", "")
        .replace("\u20e3", "")
    )

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in value.splitlines()
    ]

    return "\n".join(lines).strip()


def format_with_icons(
    content: str,
    icons: Iterable[str],
    enabled: bool = True,
) -> str:
    """
    Apply the sample style:
    first icon for title, remaining icons for body rows.
    """
    value = strip_icons(content)
    selected = normalize_icons(icons)

    if (
        not enabled
        or not selected
        or not value
    ):
        return value

    lines = value.splitlines()

    nonempty_indexes = [
        index
        for index, line in enumerate(lines)
        if line.strip()
    ]

    if not nonempty_indexes:
        return value

    first_index = nonempty_indexes[0]

    lines[first_index] = (
        f"{selected[0]} "
        f"{lines[first_index].strip()}"
    )

    body_icons = (
        selected[1:]
        or selected[:1]
    )

    for position, line_index in enumerate(
        nonempty_indexes[1:]
    ):
        icon = (
            body_icons[
                position % len(body_icons)
            ]
        )

        lines[line_index] = (
            f"{icon} "
            f"{lines[line_index].strip()}"
        )

    return "\n".join(lines).strip()


def format_with_profile(
    content: str,
    profile: Dict[str, Any],
    enabled: bool = True,
) -> str:
    """
    Apply role-aware icons and the confirmed CTA
    from an onboarding sample.
    """
    if not enabled or not profile:
        return (content or "").strip()

    structural: List[str] = []

    if profile.get("title_icon"):
        structural.append(
            profile["title_icon"]
        )

    structural.extend(
        profile.get("body_icons")
        or []
    )

    value = format_with_icons(
        content,
        structural,
        enabled=bool(structural),
    )

    cta_lines = [
        str(line).strip()
        for line in (
            profile.get("cta_lines")
            or []
        )
        if str(line).strip()
    ]

    if cta_lines:
        if value:
            value = (
                f"{value}\n\n"
                + "\n".join(cta_lines)
            )
        else:
            value = "\n".join(cta_lines)

    return value.strip()


def apply_icons(
    content: str,
    icons: Iterable[str],
    enabled: bool = True,
) -> str:
    """Keep the Phase 10 prefix contract for existing callers."""
    value = (content or "").strip()
    selected = normalize_icons(icons)

    if not enabled or not selected:
        return value

    prefix = " ".join(selected)

    return (
        f"{prefix}\n{value}"
        if value
        else prefix
    )
