"""Bridge from reviewed external content into the Shared Publication Engine."""

from __future__ import annotations

import hashlib

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


def _compose_reviewed_text(
    review: ExternalReviewResult,
) -> str:
    """
    Compose user-selected external text without inventing content.

    Exact duplicate blocks are removed while source order is preserved.
    """

    blocks = []

    for value in (
        review.title,
        review.lead,
        review.body,
    ):
        cleaned = _clean_block(
            value
        )

        if not cleaned:
            continue

        if cleaned in blocks:
            continue

        blocks.append(
            cleaned
        )

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
) -> str:
    """
    Resolve the semantic media presentation for reviewed external content.

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

    if not presentations:
        if _can_default_to_slideshow(
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
        review
    )

    if (
        not text
        and not review.media
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

    if review.media:
        if prepared_files is not None:
            files = (
                _validate_prepared_files(
                    prepared_files
                )
            )

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

    elif prepared_files:
        raise ExternalContentBridgeError(
            "prepared_files supplied for review with no selected media"
        )

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
                review
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
