"""Flexible Unicode icon extraction and application for Phase 10."""

import unicodedata
from typing import Iterable, List

MAX_ICONS = 32
MAX_ICON_LENGTH = 64


def _looks_like_icon(token: str) -> bool:
    if not token or token.startswith(("#", "@")):
        return False
    return any(
        unicodedata.category(character) in {"So", "Sk"}
        for character in token
    )


def normalize_icons(icons: Iterable[str]) -> List[str]:
    normalized = []
    for value in icons:
        token = str(value or "").strip()
        if token and len(token) <= MAX_ICON_LENGTH and _looks_like_icon(token):
            normalized.append(token)
        if len(normalized) >= MAX_ICONS:
            break
    return normalized


def extract_icons(text: str) -> List[str]:
    """Extract icon-bearing tokens from a user's branding message."""
    return normalize_icons((text or "").split())


def apply_icons(content: str, icons: Iterable[str], enabled: bool = True) -> str:
    value = (content or "").strip()
    selected = normalize_icons(icons)
    if not enabled or not selected:
        return value
    prefix = " ".join(selected)
    return f"{prefix}\n{value}" if value else prefix
