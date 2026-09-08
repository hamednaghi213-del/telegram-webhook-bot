"""Bridge from reviewed external content into the Shared Publication Engine."""

from __future__ import annotations

import hashlib
import re

from dataclasses import dataclass
from typing import (
    Any,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from core.content_model import (
    PreparedContent,
)
from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalReviewResult,
)
from core.external_media_materializer import (
    ExternalMediaMaterializer,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalContentBridgeError(
    ValueError
):
    """Raised when reviewed external content cannot enter Shared Engine."""


# =========================================================
# BRIDGE RESULT
# =========================================================


@dataclass(frozen=True)
class ExternalPreparedBridgeResult:
    """
    Result of converting reviewed external content into PreparedContent.

    Smart Summary and Editorial remain explicit signals because those
    transformations belong to the existing Shared Engine services.
    """

    prepared_content: PreparedContent

    requires_smart_summary: bool = False
    requires_editorial_rewrite: bool = False

    source_type: str = ""
    source_url: str = ""
    canonical_url: str = ""
    original_language: str = ""

    extraction_confidence: float = 0.0
    warnings: Tuple[str, ...] = ()

    @property
    def publication_identity(
        self,
    ) -> str:
        return (
            self.prepared_content
            .publication_identity
        )


# =========================================================
# TEXT
# =========================================================


def _clean_block(
    value: Any,
) -> str:
    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ""

    lines = []

    for line in text.splitlines():
        cleaned = " ".join(
            line.split()
        ).strip()

        if cleaned:
            lines.append(
                cleaned
            )

    return "\n".join(
        lines
    ).strip()


_SOURCE_ATTRIBUTION_MARKER = "به گزارش"

_SOURCE_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\U0001F1E6-\U0001F1FF"
    "]+"
)

_SOURCE_SEPARATOR_RE = re.compile(
    r"[|\-\u2013\u2014:]+"
)


def clean_web_source_name(
    value: Any,
) -> str:
    """
    Reduce a raw extracted source string (which may contain raw IDs,
    separators, icons, or duplicate names such as
    "TABNAK | تابناک - 🔷") to a clean, human-readable source name.
    """

    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ""

    text = _SOURCE_EMOJI_RE.sub(
        "",
        text,
    ).strip()

    segments = [
        segment.strip()
        for segment in _SOURCE_SEPARATOR_RE.split(text)
        if segment.strip()
    ]

    if not segments:
        return text

    for segment in segments:
        if any(
            ord(char) > 127
            for char in segment
        ):
            return segment

    return segments[0]


def apply_web_source_attribution(
    text: str,
    source_name: Any,
) -> str:
    """
    Prepend a single newsroom-style "به گزارش {SOURCE}، " attribution to
    web-derived body text, in place of a raw source footer.

    Idempotent: if the text already carries the attribution marker
    anywhere (for example because an upstream step, such as the SHORT
    Smart Summary draft, already attributed it), it is returned
    unchanged to avoid duplicate wording.
    """

    body = str(
        text
        or ""
    ).strip()

    cleaned_source = clean_web_source_name(
        source_name
    )

    if not cleaned_source or not body:
        return body

    if _SOURCE_ATTRIBUTION_MARKER in body:
        return body

    return (
        f"{_SOURCE_ATTRIBUTION_MARKER} {cleaned_source}، {body}"
    )


def compose_reviewed_publication_text(
    review: ExternalReviewResult,
    source_name: Any = "",
) -> str:
    """
    Single final formatter for External Review publication text.

    Both the review preview and the final publishable output are
    generated from this same composition so they can never diverge:

      - headline stays bare (rendered bold downstream), never repeated
        below with a "تیتر اصلی:" prefix
      - the source appears exactly once, as the newsroom-style
        "به گزارش {clean_source}، " lead at the start of the body
      - no "منبع:" footer is ever appended
    """

    return _compose_reviewed_text(
        review,
        source_name,
    )


def _compose_reviewed_text(
    review: ExternalReviewResult,
    source_name: Any = "",
) -> str:
    """
    Compose user-selected external text without inventing content.

    Exact duplicate blocks are removed while source order is preserved.

    The headline (title) is kept bare so it can be rendered bold. Any
    remaining body content receives a single newsroom-style
    "به گزارش {SOURCE}، " attribution instead of a raw source footer.
    """

    headline = _clean_block(
        review.title
    )

    body_blocks = []

    for value in (
        review.lead,
        review.body,
    ):
        cleaned = _clean_block(
            value
        )

        if not cleaned:
            continue

        if cleaned == headline:
            continue

        if cleaned in body_blocks:
            continue

        body_blocks.append(
            cleaned
        )

    body_text = apply_web_source_attribution(
        "\n\n".join(body_blocks).strip(),
        source_name,
    )

    blocks = [
        block
        for block in (headline, body_text)
        if block
    ]

    return "\n\n".join(
        blocks
    ).strip()


# =========================================================
# SOURCE IDENTITY
# =========================================================


def _normalize_source_type(
    value: Any,
) -> str:
    source_type = str(
        value
        or "external"
    ).strip().lower()

    if not source_type:
        return "external"

    normalized = []

    for char in source_type:
        if (
            char.isalnum()
            or char in (
                "_",
                "-",
            )
        ):
            normalized.append(
                char
            )

        else:
            normalized.append(
                "_"
            )

    result = "".join(
        normalized
    ).strip(
        "_"
    )

    return (
        result
        or "external"
    )


def build_external_source_key(
    content: NormalizedExternalContent,
) -> str:
    """
    Build a platform-neutral stable idempotency source key.

    The same external article/post/newspaper candidate receives the same
    identity regardless of whether it arrived through Telegram, Bale,
    or a future input adapter.
    """

    if not isinstance(
        content,
        NormalizedExternalContent,
    ):
        raise TypeError(
            "content must be NormalizedExternalContent"
        )

    identity_url = str(
        content.best_url
        or ""
    ).strip()

    if not identity_url:
        raise ExternalContentBridgeError(
            "external content has no stable source URL"
        )

    digest = hashlib.sha256(
        identity_url.encode(
            "utf-8"
        )
    ).hexdigest()[
        :32
    ]

    source_type = (
        _normalize_source_type(
            content.source_type
        )
    )

    return (
        f"external:{source_type}:{digest}"
    )


# =========================================================
# MEDIA
# =========================================================


def _validate_prepared_files(
    files: Sequence[
        Mapping[str, Any]
    ],
) -> Tuple[
    Mapping[str, Any],
    ...
]:
    normalized = []

    for index, item in enumerate(
        files
        or ()
    ):
        if not isinstance(
            item,
            Mapping,
        ):
            raise ExternalContentBridgeError(
                "prepared external media item must be a mapping"
            )

        media_type = str(
            item.get(
                "type"
            )
            or ""
        ).strip().lower()

        file_id = str(
            item.get(
                "file_id"
            )
            or ""
        ).strip()

        if not media_type:
            raise ExternalContentBridgeError(
                f"prepared external media item {index} has no type"
            )

        if not file_id:
            raise ExternalContentBridgeError(
                f"prepared external media item {index} has no file_id"
            )

        if file_id.startswith(
            (
                "http://",
                "https://",
            )
        ):
            raise ExternalContentBridgeError(
                "external URL cannot be used as transport file_id"
            )

        normalized.append(
            dict(
                item
            )
        )

    return tuple(
        normalized
    )


def _normalize_review_media_type(
    value: Any,
) -> str:
    """
    Normalize external media types only for presentation decisions.

    Publication transport conversion remains owned by the existing
    materialization boundary.
    """

    media_type = str(
        value
        or ""
    ).strip().lower()

    aliases = {
        "image": "photo",
        "picture": "photo",
        "jpg": "photo",
        "jpeg": "photo",
        "png": "photo",
        "movie": "video",
        "reel": "video",
    }

    return aliases.get(
        media_type,
        media_type,
    )


def _can_default_to_slideshow(
    review: ExternalReviewResult,
) -> bool:
    """
    Decide whether a multi-selection can safely use slideshow semantics.

    The fallback is intentionally conservative:

      - at least two selected media items
      - every item must be photo or video

    Documents, audio, voice and unknown future media types are left to the
    normal Shared Engine media path.
    """

    media = tuple(
        review.media
        or ()
    )

    if len(media) < 2:
        return False

    supported_types = {
        "photo",
        "video",
    }

    for item in media:
        media_type = (
            _normalize_review_media_type(
                getattr(
                    item,
                    "type",
                    "",
                )
            )
        )

        if media_type not in supported_types:
            return False

    return True


def _resolve_media_presentation(
    review: ExternalReviewResult,
    *,
    media_presentation_mode: str = "normal",
) -> str:
    """
    Resolve the semantic media presentation for reviewed external content.

    media_presentation_mode="album" (opt-in, backward compatible):
        Force an empty presentation so 2+ selected media always enter
        the existing shared Telegram media-group ("sendMediaGroup")
        path, exactly one item uses the existing single-media path,
        and zero items remain no-media. This bypasses the slideshow
        default below entirely.

    media_presentation_mode="normal" (default, matches pre-existing
    behavior):

    Rules:

    1. Preserve an explicit slideshow/collage presentation when selected
       media declares one consistent supported presentation.

    2. If no explicit presentation exists and the user selected two or more
       compatible visual items, default to slideshow.

       This is important for ordinary web articles: extracted gallery images
       usually do not carry Telegram-specific presentation metadata, but a
       deliberate multi-image review selection should still enter the
       project's established Rich Slideshow path.

    3. Single media and unsupported mixed media remain on the normal media
       publication path.
    """

    normalized_mode = str(
        media_presentation_mode
        or ""
    ).strip().lower()

    if normalized_mode == "album":
        return ""

    media = tuple(
        review.media
        or ()
    )

    if not media:
        return ""

    presentations = {
        str(
            item.presentation
            or ""
        ).strip().lower()
        for item in media
        if str(
            item.presentation
            or ""
        ).strip()
    }

    if len(
        presentations
    ) == 1:
        presentation = next(
            iter(
                presentations
            )
        )

        if presentation in (
            "slideshow",
            "collage",
        ):
            return presentation

    routing_presentations = {
        item
        for item in presentations
        if item in (
            "slideshow",
            "collage",
        )
    }

    if not routing_presentations and _can_default_to_slideshow(
        review
    ):
        return "slideshow"

    return ""


# =========================================================
# BRIDGE
# =========================================================


def build_external_prepared_content(
    content: NormalizedExternalContent,
    review: ExternalReviewResult,
    *,
    materializer: Optional[
        ExternalMediaMaterializer
    ] = None,
    prepared_files: Optional[
        Sequence[
            Mapping[str, Any]
        ]
    ] = None,
    source_key: str = "",
    media_presentation_mode: str = "normal",
    editorial_rewrite_applied: bool = False,
) -> ExternalPreparedBridgeResult:
    """
    Convert reviewed external content into immutable PreparedContent.

    This function:
      - does not publish
      - does not translate
      - does not summarize
      - does not perform editorial rewriting
      - does not insert raw external URLs into PreparedContent.files

    External media must cross the materialization boundary first.

    media_presentation_mode ("normal" default / "album" opt-in) is a
    backward-compatible review-only toggle. See
    `_resolve_media_presentation` for exact routing semantics.
    """

    if not isinstance(
        content,
        NormalizedExternalContent,
    ):
        raise TypeError(
            "content must be NormalizedExternalContent"
        )

    if not isinstance(
        review,
        ExternalReviewResult,
    ):
        raise TypeError(
            "review must be ExternalReviewResult"
        )

    text = _compose_reviewed_text(
        review,
        (
            content.source_name
            if not editorial_rewrite_applied
            else ""
        ),
    )

    if (
        not text
        and not review.media
        and not prepared_files
    ):
        raise ExternalContentBridgeError(
            "reviewed external content has no text or media"
        )

    if (
        prepared_files is not None
        and materializer is not None
    ):
        raise ExternalContentBridgeError(
            "provide either prepared_files or materializer, not both"
        )

    files: Tuple[
        Mapping[str, Any],
        ...
    ] = ()

    validated_prepared_files: Optional[
        Tuple[Mapping[str, Any], ...]
    ] = None

    if prepared_files is not None:
        validated_prepared_files = (
            _validate_prepared_files(
                prepared_files
            )
        )

    if review.media:
        if validated_prepared_files is not None:
            files = validated_prepared_files

        elif materializer is not None:
            files = (
                _validate_prepared_files(
                    materializer.build_prepared_files(
                        review.media
                    )
                )
            )

        else:
            raise ExternalContentBridgeError(
                "reviewed external media must be materialized before PreparedContent"
            )

        if len(
            files
        ) != len(
            review.media
        ):
            raise ExternalContentBridgeError(
                "materialized media count does not match reviewed media count"
            )

    elif validated_prepared_files is not None:
        files = validated_prepared_files

    resolved_source_key = str(
        source_key
        or ""
    ).strip()

    if not resolved_source_key:
        resolved_source_key = (
            build_external_source_key(
                content
            )
        )

    prepared = PreparedContent(
        main_text=text,
        neutral_text=text,
        files=files,
        media_presentation=(
            _resolve_media_presentation(
                review,
                media_presentation_mode=(
                    media_presentation_mode
                ),
            )
        ),
        source_key=(
            resolved_source_key
        ),
    )

    return ExternalPreparedBridgeResult(
        prepared_content=prepared,
        requires_smart_summary=(
            bool(
                review.requires_smart_summary
            )
        ),
        requires_editorial_rewrite=(
            bool(
                review.requires_editorial_rewrite
            )
        ),
        source_type=str(
            content.source_type
            or ""
        ),
        source_url=str(
            content.source_url
            or ""
        ),
        canonical_url=str(
            content.best_url
            or ""
        ),
        original_language=str(
            content.original_language
            or ""
        ),
        extraction_confidence=float(
            content.extraction_confidence
        ),
        warnings=tuple(
            content.warnings
            or ()
        ),
    )
