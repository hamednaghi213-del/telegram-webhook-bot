"""Review and selection contract for normalized external content."""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)


class ExternalReviewError(ValueError):
    """Raised when an external-content review selection is invalid."""


class ExternalReviewMode(str, Enum):
    STANDARD = "standard"
    HEADLINE_ONLY = "headline_only"
    HEADLINE_LEAD = "headline_lead"
    PARAGRAPHS = "paragraphs"
    SHORT = "short"
    EDITORIAL_REWRITE = "editorial_rewrite"


class ExternalMediaMode(str, Enum):
    DEFAULT = "default"
    NONE = "none"
    SELECTED = "selected"


@dataclass(frozen=True)
class ExternalReviewSelection:
    """
    User decision for one normalized external-content candidate.

    This object describes intent only. It does not publish anything,
    call AI providers, or interact with Telegram/Bale.
    """

    mode: ExternalReviewMode = (
        ExternalReviewMode.STANDARD
    )

    media_mode: ExternalMediaMode = (
        ExternalMediaMode.DEFAULT
    )

    paragraph_indexes: Tuple[int, ...] = field(
        default_factory=tuple
    )

    media_indexes: Tuple[int, ...] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mode",
            ExternalReviewMode(
                self.mode
            ),
        )

        object.__setattr__(
            self,
            "media_mode",
            ExternalMediaMode(
                self.media_mode
            ),
        )

        paragraphs = tuple(
            int(index)
            for index in (
                self.paragraph_indexes
                or ()
            )
        )

        media = tuple(
            int(index)
            for index in (
                self.media_indexes
                or ()
            )
        )

        if any(
            index < 0
            for index in paragraphs
        ):
            raise ExternalReviewError(
                "paragraph indexes must be >= 0"
            )

        if any(
            index < 0
            for index in media
        ):
            raise ExternalReviewError(
                "media indexes must be >= 0"
            )

        if len(
            set(paragraphs)
        ) != len(paragraphs):
            raise ExternalReviewError(
                "paragraph indexes must be unique"
            )

        if len(
            set(media)
        ) != len(media):
            raise ExternalReviewError(
                "media indexes must be unique"
            )

        if (
            self.mode
            == ExternalReviewMode.PARAGRAPHS
            and not paragraphs
        ):
            raise ExternalReviewError(
                "paragraph selection requires at least one paragraph"
            )

        if (
            self.media_mode
            == ExternalMediaMode.SELECTED
            and not media
        ):
            raise ExternalReviewError(
                "selected media mode requires at least one media index"
            )

        object.__setattr__(
            self,
            "paragraph_indexes",
            paragraphs,
        )

        object.__setattr__(
            self,
            "media_indexes",
            media,
        )


@dataclass(frozen=True)
class ExternalReviewResult:
    """
    Result after applying deterministic review choices.

    `requires_smart_summary` and `requires_editorial_rewrite` deliberately
    remain signals. Existing shared services perform those transformations
    later; this module never duplicates them.
    """

    title: str = ""
    lead: str = ""
    body: str = ""

    media: Tuple[ExternalMedia, ...] = field(
        default_factory=tuple
    )

    selected_paragraph_indexes: Tuple[
        int,
        ...
    ] = field(
        default_factory=tuple
    )

    selected_media_indexes: Tuple[
        int,
        ...
    ] = field(
        default_factory=tuple
    )

    requires_smart_summary: bool = False
    requires_editorial_rewrite: bool = False

    @property
    def has_text(self) -> bool:
        return bool(
            self.title.strip()
            or self.lead.strip()
            or self.body.strip()
        )

    @property
    def has_media(self) -> bool:
        return bool(
            self.media
        )


@dataclass(frozen=True)
class ExternalContentPreview:
    """
    Presentation-neutral preview information for a review UI.

    Telegram, Bale, web dashboards, or future clients can render this
    without changing review behavior.
    """

    title: str
    lead: str

    paragraphs: Tuple[str, ...]

    media: Tuple[ExternalMedia, ...]

    source_name: str
    original_language: str

    extraction_confidence: float

    warnings: Tuple[str, ...]

    canonical_url: str

    @property
    def paragraph_count(self) -> int:
        return len(
            self.paragraphs
        )

    @property
    def media_count(self) -> int:
        return len(
            self.media
        )


def split_external_paragraphs(
    body: str,
) -> Tuple[str, ...]:
    text = str(
        body
        or ""
    ).strip()

    if not text:
        return ()

    parts = re.split(
        r"\n\s*\n+",
        text,
    )

    paragraphs = []

    for part in parts:
        cleaned = " ".join(
            part.split()
        ).strip()

        if not cleaned:
            continue

        paragraphs.append(
            cleaned
        )

    return tuple(
        paragraphs
    )


def build_external_content_preview(
    content: NormalizedExternalContent,
) -> ExternalContentPreview:
    if not isinstance(
        content,
        NormalizedExternalContent,
    ):
        raise TypeError(
            "content must be NormalizedExternalContent"
        )

    return ExternalContentPreview(
        title=content.title,
        lead=content.lead,
        paragraphs=split_external_paragraphs(
            content.body
        ),
        media=tuple(
            content.media
        ),
        source_name=content.source_name,
        original_language=(
            content.original_language
        ),
        extraction_confidence=(
            content.extraction_confidence
        ),
        warnings=tuple(
            content.warnings
        ),
        canonical_url=(
            content.best_url
        ),
    )


def _select_paragraphs(
    paragraphs: Tuple[str, ...],
    indexes: Tuple[int, ...],
) -> Tuple[str, ...]:
    selected = []

    for index in indexes:
        if index >= len(
            paragraphs
        ):
            raise ExternalReviewError(
                f"paragraph index out of range: {index}"
            )

        selected.append(
            paragraphs[index]
        )

    return tuple(
        selected
    )


def _select_media(
    media: Tuple[ExternalMedia, ...],
    selection: ExternalReviewSelection,
) -> Tuple[
    Tuple[ExternalMedia, ...],
    Tuple[int, ...],
]:
    if (
        selection.media_mode
        == ExternalMediaMode.NONE
    ):
        return (
            (),
            (),
        )

    if (
        selection.media_mode
        == ExternalMediaMode.DEFAULT
    ):
        return (
            media,
            tuple(
                range(
                    len(media)
                )
            ),
        )

    selected = []

    for index in selection.media_indexes:
        if index >= len(
            media
        ):
            raise ExternalReviewError(
                f"media index out of range: {index}"
            )

        selected.append(
            media[index]
        )

    return (
        tuple(
            selected
        ),
        selection.media_indexes,
    )


def apply_external_review_selection(
    content: NormalizedExternalContent,
    selection: Optional[
        ExternalReviewSelection
    ] = None,
) -> ExternalReviewResult:
    """
    Apply user-controlled deterministic review choices.

    No publication, translation, summarization, or editorial AI work
    happens in this function.
    """

    if not isinstance(
        content,
        NormalizedExternalContent,
    ):
        raise TypeError(
            "content must be NormalizedExternalContent"
        )

    selection = (
        selection
        or ExternalReviewSelection()
    )

    if not isinstance(
        selection,
        ExternalReviewSelection,
    ):
        raise TypeError(
            "selection must be ExternalReviewSelection"
        )

    paragraphs = split_external_paragraphs(
        content.body
    )

    title = content.title
    lead = content.lead
    body = content.body

    selected_paragraph_indexes: Tuple[
        int,
        ...
    ] = ()

    requires_smart_summary = False
    requires_editorial_rewrite = False

    if (
        selection.mode
        == ExternalReviewMode.HEADLINE_ONLY
    ):
        lead = ""
        body = ""

    elif (
        selection.mode
        == ExternalReviewMode.HEADLINE_LEAD
    ):
        body = ""

    elif (
        selection.mode
        == ExternalReviewMode.PARAGRAPHS
    ):
        selected = _select_paragraphs(
            paragraphs,
            selection.paragraph_indexes,
        )

        body = "\n\n".join(
            selected
        )

        selected_paragraph_indexes = (
            selection.paragraph_indexes
        )

    elif (
        selection.mode
        == ExternalReviewMode.SHORT
    ):
        # Existing shared Smart Summary will perform this transformation.
        requires_smart_summary = True

    elif (
        selection.mode
        == ExternalReviewMode.EDITORIAL_REWRITE
    ):
        # Existing shared Editorial pipeline will perform this transformation.
        requires_editorial_rewrite = True

    selected_media, selected_media_indexes = (
        _select_media(
            tuple(
                content.media
            ),
            selection,
        )
    )

    return ExternalReviewResult(
        title=title,
        lead=lead,
        body=body,
        media=selected_media,
        selected_paragraph_indexes=(
            selected_paragraph_indexes
        ),
        selected_media_indexes=(
            selected_media_indexes
        ),
        requires_smart_summary=(
            requires_smart_summary
        ),
        requires_editorial_rewrite=(
            requires_editorial_rewrite
        ),
    )
