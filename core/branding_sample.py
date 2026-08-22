"""Branding sample analysis and preview helpers."""

import re
from html import escape
from typing import Any, Dict, Iterable, List

from core.content_entities import build_utf16_positions, utf16_range_to_python
from core.publication_icons import extract_icons, format_with_icons

_BRANDING_TOKEN = re.compile(r"^(?:[@#][^\s]+|[|•·\-–—]+)$")
_BALE_URL = re.compile(
    r"https?://(?:www\.)?(?:ble\.ir|bale\.ai)/(?P<path>[^\s/?#]+)",
    re.IGNORECASE,
)
_BALE_CTA = re.compile(
    r"(?:در\s+بله\s+(?:دنبال|عضو)|بله\s+(?:دنبال|عضو)|"
    r"(?:دنبال|عضو)\s+.*\s+در\s+بله)",
    re.IGNORECASE,
)


def _entity_python_range(text: str, entity: Dict[str, Any]):
    return utf16_range_to_python(
        text,
        int(entity.get("offset", 0)),
        int(entity.get("length", 0)),
        build_utf16_positions(text),
    )


def extract_bale_candidate(
    text: str,
    entities: Iterable[Dict[str, Any]] = (),
) -> Dict[str, str]:
    """Extract a public Bale channel URL/handle from URL or text_link entities."""
    urls: List[str] = []
    for entity in entities or []:
        entity_type = str(entity.get("type") or "")
        if entity_type == "text_link" and entity.get("url"):
            urls.append(str(entity["url"]))
        elif entity_type == "url":
            start, end = _entity_python_range(text or "", entity)
            urls.append((text or "")[start:end])
    urls.extend(match.group(0) for match in _BALE_URL.finditer(text or ""))

    for url in urls:
        match = _BALE_URL.search(url)
        if not match:
            continue
        path = match.group("path").strip("/")
        if re.fullmatch(r"[A-Za-z0-9_]{4,}", path):
            return {"url": match.group(0), "channel": f"@{path}"}
    return {"url": "", "channel": ""}


def _is_bale_cta(line: str) -> bool:
    return bool(_BALE_CTA.search(line or "") or _BALE_URL.search(line or ""))


def _line_style_icon(line: str) -> str:
    value = (line or "").strip()
    icons = extract_icons(value)
    if not icons:
        return ""
    first = icons[0]
    # Accept both logical prefix and suffix because RTL clients may display the
    # same logical prefix on the visual right edge.
    if value.startswith(first) or value.endswith(first):
        return first
    return ""


def extract_style_icons(content: str) -> List[str]:
    """Select structural title/body icons, excluding CTA and inline decoration."""
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        return []
    title_icon = _line_style_icon(lines[0])
    body_icons = []
    for line in lines[1:]:
        icon = _line_style_icon(line)
        if icon and icon not in body_icons:
            body_icons.append(icon)
    result = ([title_icon] if title_icon else []) + [
        icon for icon in body_icons if icon != title_icon
    ]
    return result


def remove_trailing_source_branding(text: str) -> str:
    """Remove trailing source branding and Bale CTA without touching article text."""
    lines = (text or "").strip().splitlines()
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        tokens = tail.split()
        if tokens and all(_BRANDING_TOKEN.fullmatch(token) for token in tokens):
            lines.pop()
            continue
        if _is_bale_cta(tail):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def analyze_branding_sample(
    text: str,
    entities: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Return the original sample, its ordered icons, and clean textual content."""
    sample_text = (text or "").strip()
    entity_list = list(entities or [])
    content = remove_trailing_source_branding(sample_text)
    bale = extract_bale_candidate(sample_text, entity_list)
    all_icons = extract_icons(sample_text)
    sample_lines = [line.strip() for line in sample_text.splitlines() if line.strip()]
    cta_lines = [line for line in sample_lines if _is_bale_cta(line)]
    cta_icons = []
    for line in cta_lines:
        for icon in extract_icons(line):
            if icon not in cta_icons:
                cta_icons.append(icon)
    structural_icons = extract_style_icons(content)
    hashtags = list(dict.fromkeys(re.findall(r"(?<!\w)#[^\s#@|]+", sample_text)))
    mentions = list(dict.fromkeys(re.findall(r"(?<!\w)@[A-Za-z0-9_]{4,}", sample_text)))
    bold_texts = []
    for entity in entity_list:
        if entity.get("type") != "bold":
            continue
        start, end = _entity_python_range(sample_text, entity)
        value = sample_text[start:end]
        if value and value in content:
            bold_texts.append(value)
    return {
        "sample_text": sample_text,
        # Keep every icon from the approved sample. Role-specific lists prevent
        # CTA decoration from being incorrectly cycled through news paragraphs.
        "icons": all_icons,
        "structural_icons": structural_icons,
        "title_icon": structural_icons[0] if structural_icons else "",
        "body_icons": structural_icons[1:] if len(structural_icons) > 1 else [],
        "cta_icons": cta_icons,
        "cta_lines": cta_lines,
        "hashtags": hashtags,
        "mentions": mentions,
        "content": content,
        "bale_url": bale["url"],
        "bale_channel": bale["channel"],
        "bold_texts": bold_texts,
        "profile": {
            "all_icons": all_icons,
            "title_icon": structural_icons[0] if structural_icons else "",
            "body_icons": structural_icons[1:] if len(structural_icons) > 1 else [],
            "cta_icons": cta_icons,
            "cta_lines": cta_lines,
            "hashtags": hashtags,
            "mentions": mentions,
            "bale_url": bale["url"],
            "bale_channel": bale["channel"],
            "bold_texts": bold_texts,
        },
    }


def compose_branding_footer(branding: Dict[str, Any]) -> str:
    values = [
        (branding.get("hashtag") or "").strip(),
        (branding.get("channel_tag") or "").strip(),
    ]
    return "\n".join(value for value in values if value)


def build_branding_preview(
    sample_text: str,
    icons: Iterable[str],
    branding: Dict[str, Any],
) -> str:
    """Render the exact preview that will be presented for owner confirmation."""
    analysis = analyze_branding_sample(sample_text)
    structural = analysis["structural_icons"]
    formatted = format_with_icons(analysis["content"], structural, enabled=True)
    cta = "\n".join(analysis["cta_lines"])
    extracted_footer = "\n".join(analysis["hashtags"] + analysis["mentions"])
    footer = extracted_footer or compose_branding_footer(branding)
    if formatted and cta:
        formatted = f"{formatted}\n\n{cta}"
    if formatted and footer:
        return f"{formatted}\n\n{footer}"
    return formatted or footer


def build_branding_preview_html(
    sample_text: str,
    icons: Iterable[str],
    branding: Dict[str, Any],
    bold_texts: Iterable[str] = (),
) -> str:
    """Build a safe HTML preview while preserving detected bold fragments."""
    preview = build_branding_preview(sample_text, icons, branding)
    rendered = escape(preview)
    for value in bold_texts or []:
        escaped_value = escape(str(value or ""))
        if escaped_value:
            rendered = rendered.replace(
                escaped_value,
                f"<b>{escaped_value}</b>",
                1,
            )
    return rendered
