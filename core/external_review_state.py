"""Pending review state for external content ingestion."""

from __future__ import annotations

import logging
import os

from dataclasses import (
    dataclass,
    replace,
)
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from threading import RLock
from time import time
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Tuple,
)

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)


logger = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

PERSISTENT_EXTERNAL_REVIEW_ENV = (
    "ENABLE_PERSISTENT_EXTERNAL_REVIEW_STATE"
)

DEFAULT_EXTERNAL_REVIEW_TTL_SECONDS = 1800

EXTERNAL_REVIEW_TABLE = (
    "external_review_state"
)

EXTERNAL_REVIEW_UI_STATE_KEY = (
    "__external_review_ui_state__"
)

# Media presentation mode values.
#
# MEDIA_PRESENTATION_MODE_NORMAL preserves the pre-existing behavior:
# the bridge decides presentation from selected media (defaulting
# multiple compatible items to the existing slideshow path).
#
# MEDIA_PRESENTATION_MODE_ALBUM forces the shared Telegram
# media-group ("sendMediaGroup") path for 2+ selected images, the
# existing single-media path for exactly one, and no-media for zero.
MEDIA_PRESENTATION_MODE_NORMAL = "normal"
MEDIA_PRESENTATION_MODE_ALBUM = "album"

_VALID_MEDIA_PRESENTATION_MODES = (
    MEDIA_PRESENTATION_MODE_NORMAL,
    MEDIA_PRESENTATION_MODE_ALBUM,
)

MANUAL_IMAGE_SOURCE_PRIMARY = "primary"
MANUAL_IMAGE_SOURCE_REPLACE = "replace"
MANUAL_IMAGE_SOURCE_NONE = "none"

_VALID_MANUAL_IMAGE_SOURCES = (
    MANUAL_IMAGE_SOURCE_PRIMARY,
    MANUAL_IMAGE_SOURCE_REPLACE,
    MANUAL_IMAGE_SOURCE_NONE,
)

# Review-stage values.
#
# "select" (default):
#     the main mode-selection surface (standard / short / headline /
#     paragraphs / editorial / media / cancel).
#
# "short_preview":
#     a caption-safe SHORT draft has been generated and is waiting for
#     explicit approve / edit / regenerate / cancel. Nothing is
#     published while in this stage.
#
# "paragraph_select":
#     the user is picking paragraphs across a paginated, persistent
#     true multi-select surface. Nothing is published while in this
#     stage.
#
# "paragraph_preview":
#     the selected paragraphs have been assembled into a draft
#     (original headline + selected paragraphs, in source order) and
#     are waiting for explicit approve / edit / cancel.
REVIEW_STAGE_SELECT = "select"
REVIEW_STAGE_SHORT_PREVIEW = "short_preview"
REVIEW_STAGE_PARAGRAPH_SELECT = "paragraph_select"
REVIEW_STAGE_PARAGRAPH_PREVIEW = "paragraph_preview"

_VALID_REVIEW_STAGES = (
    REVIEW_STAGE_SELECT,
    REVIEW_STAGE_SHORT_PREVIEW,
    REVIEW_STAGE_PARAGRAPH_SELECT,
    REVIEW_STAGE_PARAGRAPH_PREVIEW,
)


def _normalize_media_presentation_mode(
    value: Any,
) -> str:
    """
    Normalize a media presentation mode value.

    Fails closed to the default (current) behavior for any
    unrecognized, missing, or malformed value so old persisted JSON
    without this field keeps behaving exactly as before.
    """

    normalized = str(
        value
        or ""
    ).strip().lower()

    if normalized in _VALID_MEDIA_PRESENTATION_MODES:
        return normalized

    return MEDIA_PRESENTATION_MODE_NORMAL


def _normalize_manual_image_source(
    value: Any,
) -> str:
    normalized = str(
        value
        or ""
    ).strip().lower()

    if normalized in _VALID_MANUAL_IMAGE_SOURCES:
        return normalized

    return MANUAL_IMAGE_SOURCE_PRIMARY


def _normalize_manual_image_file_id(
    value: Any,
) -> str:
    file_id = str(
        value
        or ""
    ).strip()

    if file_id.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return ""

    return file_id


def _normalize_review_stage(
    value: Any,
) -> str:
    """
    Normalize a review-stage value.

    Fails closed to REVIEW_STAGE_SELECT for any unrecognized, missing,
    or malformed value so old persisted JSON without this field keeps
    behaving exactly as before (the main selection surface).
    """

    normalized = str(
        value
        or ""
    ).strip().lower()

    if normalized in _VALID_REVIEW_STAGES:
        return normalized

    return REVIEW_STAGE_SELECT


def _normalize_draft_text(
    value: Any,
) -> str:
    return str(
        value
        or ""
    )


def _normalize_paragraph_page(
    value: Any,
) -> int:
    try:
        page = int(
            value
            or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0

    if page < 0:
        return 0

    return page


# =========================================================
# ERRORS
# =========================================================


class ExternalReviewStateError(
    RuntimeError
):
    """Base error for external review state."""


class ExternalReviewNotFound(
    ExternalReviewStateError
):
    """Raised when no active pending review exists."""


class ExternalReviewExpired(
    ExternalReviewStateError
):
    """Raised when a pending review has expired."""


class ExternalReviewConflict(
    ExternalReviewStateError
):
    """Raised when an active review would be overwritten."""


class ExternalReviewPersistenceError(
    ExternalReviewStateError
):
    """Raised when durable pending review storage fails."""


# =========================================================
# MODEL
# =========================================================


@dataclass(frozen=True)
class PendingExternalReview:
    """
    One external-content review waiting for user action.

    This state is intentionally platform-neutral.

    Media selection is review-state, not publication-state.

    selected_media_indexes:
        Persistent indexes selected by the user.

    media_selection_explicit=False:
        The user has not changed the default media choice.

    media_selection_explicit=True with indexes:
        The user explicitly selected those media items.

    media_selection_explicit=True with empty indexes:
        The user explicitly selected "no media".

    preview_message_id / preview_media_message_ids:
        Telegram message identity of the review surface. They let
        later callbacks edit the existing preview in place instead
        of accumulating new messages. Optional and platform-specific;
        stored inside the existing JSON content payload so durable
        stores require no schema migration.

    preview_media_file_ids:
        file_id values already staged for the preview media panel,
        aligned with the order of ``content.media``. They let media
        toggles re-display previously staged photos without
        downloading or staging them again. Never used for
        publication; final publication still materializes media
        through the existing boundary at execution time.

    media_presentation_mode:
        Backward-compatible review-only UI toggle controlling how
        the terminal decision/bridge presents 2+ selected media.

        "normal" (default, matches pre-existing behavior):
            the bridge keeps deciding presentation from selected
            media, defaulting multiple compatible items to the
            existing slideshow path.

        "album":
            forces the shared Telegram media-group path for 2+
            selected images, the existing single-media path for
            exactly one image, and no-media for zero.

        Missing/old persisted state without this field normalizes
        to "normal", so existing pending reviews are unaffected.

    manual_image_source:
        "primary" -> use the extracted trustworthy primary image.
        "replace" -> use the manually uploaded replacement image.
        "none" -> publish without image.

    manual_image_file_id:
        Reusable Telegram file_id for the manually uploaded image.

    manual_image_waiting:
        The review is waiting for the next same-chat photo upload and
        must intercept it before ordinary publication routing.

    review_stage:
        One of REVIEW_STAGE_SELECT (default), REVIEW_STAGE_SHORT_PREVIEW,
        REVIEW_STAGE_PARAGRAPH_SELECT, REVIEW_STAGE_PARAGRAPH_PREVIEW.
        Drives which review surface is currently rendered.

    draft_text:
        The currently previewed/editable text for SHORT or PARAGRAPHS
        (original headline plus selected paragraphs, in source order)
        while review_stage is a "_preview" stage. Approving publishes
        exactly this text; nothing is published before an explicit
        approve.

    paragraph_selected_indexes:
        Persistent, paginated, true multi-select paragraph indexes for
        REVIEW_STAGE_PARAGRAPH_SELECT / REVIEW_STAGE_PARAGRAPH_PREVIEW.
        Selections persist across page changes.

    paragraph_page:
        The currently displayed page of the paginated paragraph
        selector.

    awaiting_edit_text:
        The review is waiting for the next same-chat text message to
        replace `draft_text` and must intercept it before ordinary
        publication routing.
    """

    review_id: str
    chat_id: int
    content: NormalizedExternalContent
    created_at: float
    expires_at: float

    selected_media_indexes: Tuple[
        int,
        ...,
    ] = ()

    media_selection_explicit: bool = False

    preview_message_id: Optional[int] = None

    preview_media_message_ids: Tuple[
        int,
        ...,
    ] = ()

    preview_media_file_ids: Tuple[
        str,
        ...,
    ] = ()

    media_presentation_mode: str = (
        MEDIA_PRESENTATION_MODE_NORMAL
    )

    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    )

    manual_image_file_id: str = ""

    manual_image_waiting: bool = False

    review_stage: str = REVIEW_STAGE_SELECT

    draft_text: str = ""

    paragraph_selected_indexes: Tuple[
        int,
        ...,
    ] = ()

    paragraph_page: int = 0

    awaiting_edit_text: bool = False

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "media_presentation_mode",
            _normalize_media_presentation_mode(
                self.media_presentation_mode
            ),
        )
        object.__setattr__(
            self,
            "manual_image_source",
            _normalize_manual_image_source(
                self.manual_image_source
            ),
        )
        object.__setattr__(
            self,
            "manual_image_file_id",
            _normalize_manual_image_file_id(
                self.manual_image_file_id
            ),
        )
        object.__setattr__(
            self,
            "manual_image_waiting",
            bool(
                self.manual_image_waiting
            ),
        )
        object.__setattr__(
            self,
            "review_stage",
            _normalize_review_stage(
                self.review_stage
            ),
        )
        object.__setattr__(
            self,
            "draft_text",
            _normalize_draft_text(
                self.draft_text
            ),
        )
        object.__setattr__(
            self,
            "paragraph_selected_indexes",
            _normalize_media_indexes(
                self.paragraph_selected_indexes
            ),
        )
        object.__setattr__(
            self,
            "paragraph_page",
            _normalize_paragraph_page(
                self.paragraph_page
            ),
        )
        object.__setattr__(
            self,
            "awaiting_edit_text",
            bool(
                self.awaiting_edit_text
            ),
        )

    @property
    def expired(
        self,
    ) -> bool:
        return (
            time()
            >= self.expires_at
        )


# =========================================================
# SERIALIZATION HELPERS
# =========================================================


def _plain_value(
    value: Any,
) -> Any:
    """
    Convert immutable/frozen structures into JSON-safe values.

    NormalizedExternalContent metadata may contain MappingProxyType,
    tuples or frozensets.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): _plain_value(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (
            tuple,
            list,
            set,
            frozenset,
        ),
    ):
        return [
            _plain_value(item)
            for item in value
        ]

    return value


def _replace_pending(
    pending: PendingExternalReview,
    **changes: Any,
) -> PendingExternalReview:
    return replace(
        pending,
        **changes,
    )


def _media_to_dict(
    media: ExternalMedia,
) -> Dict[str, Any]:
    return {
        "type": media.type,
        "source_url": media.source_url,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration": media.duration,
        "alt_text": media.alt_text,
        "position": media.position,
        "presentation": media.presentation,
        "metadata": _plain_value(
            media.metadata
        ),
    }


def _media_from_dict(
    value: Mapping[str, Any],
) -> ExternalMedia:
    return ExternalMedia(
        type=str(
            value.get(
                "type",
                "",
            )
            or ""
        ),
        source_url=str(
            value.get(
                "source_url",
                "",
            )
            or ""
        ),
        mime_type=str(
            value.get(
                "mime_type",
                "",
            )
            or ""
        ),
        width=(
            int(value["width"])
            if value.get("width")
            is not None
            else None
        ),
        height=(
            int(value["height"])
            if value.get("height")
            is not None
            else None
        ),
        duration=(
            float(value["duration"])
            if value.get("duration")
            is not None
            else None
        ),
        alt_text=str(
            value.get(
                "alt_text",
                "",
            )
            or ""
        ),
        position=int(
            value.get(
                "position",
                0,
            )
            or 0
        ),
        presentation=str(
            value.get(
                "presentation",
                "",
            )
            or ""
        ),
        metadata=(
            value.get(
                "metadata",
                {},
            )
            or {}
        ),
    )


def _content_to_dict(
    content: NormalizedExternalContent,
) -> Dict[str, Any]:
    return {
        "source_type": (
            content.source_type
        ),
        "source_url": (
            content.source_url
        ),
        "canonical_url": (
            content.canonical_url
        ),
        "content_type": (
            content.content_type
        ),
        "title": (
            content.title
        ),
        "lead": (
            content.lead
        ),
        "body": (
            content.body
        ),
        "author": (
            content.author
        ),
        "published_at": (
            content.published_at
        ),
        "original_language": (
            content.original_language
        ),
        "source_name": (
            content.source_name
        ),
        "media": [
            _media_to_dict(item)
            for item in content.media
        ],
        "extraction_confidence": (
            content.extraction_confidence
        ),
        "warnings": list(
            content.warnings
        ),
        "metadata": _plain_value(
            content.metadata
        ),
    }


def _normalize_message_ids(
    ids: Any,
) -> Tuple[int, ...]:
    normalized: list = []

    for item in (
        ids
        or ()
    ):
        try:
            message_id = int(
                item
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if message_id <= 0:
            continue

        if message_id in normalized:
            continue

        normalized.append(
            message_id
        )

    return tuple(
        normalized
    )


def _normalize_file_ids(
    values: Any,
    *,
    expected_length: int,
) -> Tuple[str, ...]:
    """
    Normalize staged preview file_id slots.

    The result always has exactly ``expected_length`` entries; slots
    without a staged value remain empty strings so indexes stay
    aligned with ``content.media``.
    """

    normalized: list = []

    for item in (
        values
        or ()
    ):
        normalized.append(
            str(
                item
                or ""
            ).strip()
        )

    if len(normalized) < expected_length:
        normalized.extend(
            [""]
            * (expected_length - len(normalized))
        )

    return tuple(
        normalized[:expected_length]
    )


def _normalize_message_id(
    value: Any,
) -> Optional[int]:
    if value is None:
        return None

    try:
        message_id = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if message_id <= 0:
        return None

    return message_id


def _content_with_review_state_to_dict(
    content: NormalizedExternalContent,
    *,
    selected_media_indexes: Tuple[
        int,
        ...,
    ] = (),
    media_selection_explicit: bool = False,
    preview_message_id: Optional[
        int
    ] = None,
    preview_media_message_ids: Tuple[
        int,
        ...,
    ] = (),
    preview_media_file_ids: Tuple[
        str,
        ...,
    ] = (),
    media_presentation_mode: str = (
        MEDIA_PRESENTATION_MODE_NORMAL
    ),
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
    manual_image_waiting: bool = False,
    review_stage: str = REVIEW_STAGE_SELECT,
    draft_text: str = "",
    paragraph_selected_indexes: Tuple[
        int,
        ...,
    ] = (),
    paragraph_page: int = 0,
    awaiting_edit_text: bool = False,
) -> Dict[str, Any]:
    """
    Serialize external content plus review-only UI state.

    Review UI state is stored inside the existing JSON content column,
    avoiding a schema migration while remaining durable across workers.
    """

    payload = _content_to_dict(
        content
    )

    payload[
        EXTERNAL_REVIEW_UI_STATE_KEY
    ] = {
        "media_presentation_mode": (
            _normalize_media_presentation_mode(
                media_presentation_mode
            )
        ),
        "selected_media_indexes": [
            int(index)
            for index
            in selected_media_indexes
        ],
        "media_selection_explicit": bool(
            media_selection_explicit
        ),
        "preview_message_id": (
            _normalize_message_id(
                preview_message_id
            )
        ),
        "preview_media_message_ids": [
            int(message_id)
            for message_id
            in _normalize_message_ids(
                preview_media_message_ids
            )
        ],
        "preview_media_file_ids": [
            str(file_id)
            for file_id
            in _normalize_file_ids(
                preview_media_file_ids,
                expected_length=len(
                    content.media
                ),
            )
        ],
        "manual_image_source": (
            _normalize_manual_image_source(
                manual_image_source
            )
        ),
        "manual_image_file_id": (
            _normalize_manual_image_file_id(
                manual_image_file_id
            )
        ),
        "manual_image_waiting": bool(
            manual_image_waiting
        ),
        "review_stage": (
            _normalize_review_stage(
                review_stage
            )
        ),
        "draft_text": (
            _normalize_draft_text(
                draft_text
            )
        ),
        "paragraph_selected_indexes": [
            int(index)
            for index
            in paragraph_selected_indexes
        ],
        "paragraph_page": (
            _normalize_paragraph_page(
                paragraph_page
            )
        ),
        "awaiting_edit_text": bool(
            awaiting_edit_text
        ),
    }

    return payload


def _review_state_from_content_dict(
    value: Mapping[str, Any],
    *,
    media_count: int = 0,
) -> Tuple[
    Tuple[int, ...],
    bool,
    Optional[int],
    Tuple[int, ...],
    Tuple[str, ...],
    str,
    str,
    str,
    bool,
    str,
    str,
    Tuple[int, ...],
    int,
    bool,
]:
    raw_state = (
        value.get(
            EXTERNAL_REVIEW_UI_STATE_KEY,
            {},
        )
        or {}
    )

    if not isinstance(
        raw_state,
        Mapping,
    ):
        return (
            (),
            False,
            None,
            (),
            _normalize_file_ids(
                (),
                expected_length=media_count,
            ),
            MEDIA_PRESENTATION_MODE_NORMAL,
            MANUAL_IMAGE_SOURCE_PRIMARY,
            "",
            False,
            REVIEW_STAGE_SELECT,
            "",
            (),
            0,
            False,
        )

    raw_indexes = (
        raw_state.get(
            "selected_media_indexes",
            [],
        )
        or []
    )

    indexes = []

    for item in raw_indexes:
        try:
            index = int(
                item
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if index < 0:
            continue

        if index in indexes:
            continue

        indexes.append(
            index
        )

    raw_paragraph_indexes = (
        raw_state.get(
            "paragraph_selected_indexes",
            [],
        )
        or []
    )

    paragraph_indexes = []

    for item in raw_paragraph_indexes:
        try:
            index = int(
                item
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if index < 0:
            continue

        if index in paragraph_indexes:
            continue

        paragraph_indexes.append(
            index
        )

    return (
        tuple(
            indexes
        ),
        bool(
            raw_state.get(
                "media_selection_explicit",
                False,
            )
        ),
        _normalize_message_id(
            raw_state.get(
                "preview_message_id"
            )
        ),
        _normalize_message_ids(
            raw_state.get(
                "preview_media_message_ids",
                (),
            )
        ),
        _normalize_file_ids(
            raw_state.get(
                "preview_media_file_ids",
                (),
            ),
            expected_length=media_count,
        ),
        _normalize_media_presentation_mode(
            raw_state.get(
                "media_presentation_mode"
            )
        ),
        _normalize_manual_image_source(
            raw_state.get(
                "manual_image_source"
            )
        ),
        _normalize_manual_image_file_id(
            raw_state.get(
                "manual_image_file_id"
            )
        ),
        bool(
            raw_state.get(
                "manual_image_waiting",
                False,
            )
        ),
        _normalize_review_stage(
            raw_state.get(
                "review_stage"
            )
        ),
        _normalize_draft_text(
            raw_state.get(
                "draft_text"
            )
        ),
        tuple(
            paragraph_indexes
        ),
        _normalize_paragraph_page(
            raw_state.get(
                "paragraph_page"
            )
        ),
        bool(
            raw_state.get(
                "awaiting_edit_text",
                False,
            )
        ),
    )


def _content_from_dict(
    value: Mapping[str, Any],
) -> NormalizedExternalContent:
    raw_media = (
        value.get(
            "media",
            [],
        )
        or []
    )

    media = tuple(
        _media_from_dict(item)
        for item in raw_media
        if isinstance(
            item,
            Mapping,
        )
    )

    return NormalizedExternalContent(
        source_type=str(
            value.get(
                "source_type",
                "",
            )
            or ""
        ),
        source_url=str(
            value.get(
                "source_url",
                "",
            )
            or ""
        ),
        canonical_url=str(
            value.get(
                "canonical_url",
                "",
            )
            or ""
        ),
        content_type=str(
            value.get(
                "content_type",
                "",
            )
            or ""
        ),
        title=str(
            value.get(
                "title",
                "",
            )
            or ""
        ),
        lead=str(
            value.get(
                "lead",
                "",
            )
            or ""
        ),
        body=str(
            value.get(
                "body",
                "",
            )
            or ""
        ),
        author=str(
            value.get(
                "author",
                "",
            )
            or ""
        ),
        published_at=str(
            value.get(
                "published_at",
                "",
            )
            or ""
        ),
        original_language=str(
            value.get(
                "original_language",
                "",
            )
            or ""
        ),
        source_name=str(
            value.get(
                "source_name",
                "",
            )
            or ""
        ),
        media=media,
        extraction_confidence=float(
            value.get(
                "extraction_confidence",
                0.0,
            )
            or 0.0
        ),
        warnings=tuple(
            str(item)
            for item in (
                value.get(
                    "warnings",
                    [],
                )
                or []
            )
        ),
        metadata=(
            value.get(
                "metadata",
                {},
            )
            or {}
        ),
    )


# =========================================================
# MEDIA SELECTION NORMALIZATION
# =========================================================


def _normalize_media_indexes(
    indexes: Tuple[
        int,
        ...,
    ],
) -> Tuple[
    int,
    ...,
]:
    normalized = []

    for item in (
        indexes
        or ()
    ):
        try:
            index = int(
                item
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalReviewStateError(
                "selected media index is invalid"
            ) from exc

        if index < 0:
            raise ExternalReviewStateError(
                "selected media index must be >= 0"
            )

        if index in normalized:
            continue

        normalized.append(
            index
        )

    return tuple(
        normalized
    )


def _validate_media_indexes(
    pending: PendingExternalReview,
    indexes: Tuple[
        int,
        ...,
    ],
) -> None:
    media_count = len(
        pending.content.media
    )

    if any(
        index >= media_count
        for index in indexes
    ):
        raise ExternalReviewStateError(
            "selected media index is out of range"
        )


def _validate_paragraph_indexes(
    pending: PendingExternalReview,
    indexes: Tuple[
        int,
        ...,
    ],
) -> None:
    from core.external_content_review import (
        split_external_paragraphs,
    )

    paragraph_count = len(
        split_external_paragraphs(
            pending.content.body
        )
    )

    if any(
        index >= paragraph_count
        for index in indexes
    ):
        raise ExternalReviewStateError(
            "selected paragraph index is out of range"
        )


# =========================================================
# TIME HELPERS
# =========================================================


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _timestamp_to_iso(
    value: float,
) -> str:
    return (
        datetime.fromtimestamp(
            float(value),
            tz=timezone.utc,
        )
        .isoformat()
    )


def _iso_to_timestamp(
    value: Any,
) -> float:
    if isinstance(
        value,
        datetime,
    ):
        parsed = value

    else:
        text = str(
            value
            or ""
        ).strip()

        if not text:
            raise ValueError(
                "timestamp value is empty"
            )

        if text.endswith(
            "Z"
        ):
            text = (
                text[:-1]
                + "+00:00"
            )

        parsed = (
            datetime.fromisoformat(
                text
            )
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.timestamp()


# =========================================================
# IN-MEMORY STORE
# =========================================================


class ExternalReviewStateStore:
    """
    Thread-safe in-process pending-review store.

    Retained as the fallback/test implementation.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = (
            DEFAULT_EXTERNAL_REVIEW_TTL_SECONDS
        ),
    ) -> None:
        ttl = int(
            ttl_seconds
        )

        if ttl <= 0:
            raise ValueError(
                "ttl_seconds must be > 0"
            )

        self.ttl_seconds = ttl

        self._lock = RLock()

        self._by_chat: Dict[
            int,
            PendingExternalReview,
        ] = {}

        self._by_id: Dict[
            str,
            PendingExternalReview,
        ] = {}

    # -----------------------------------------------------
    # INTERNAL
    # -----------------------------------------------------

    def _remove(
        self,
        pending: PendingExternalReview,
    ) -> None:
        current_chat = (
            self._by_chat.get(
                pending.chat_id
            )
        )

        if (
            current_chat is pending
            or (
                current_chat
                is not None
                and current_chat.review_id
                == pending.review_id
            )
        ):
            self._by_chat.pop(
                pending.chat_id,
                None,
            )

        current_id = (
            self._by_id.get(
                pending.review_id
            )
        )

        if (
            current_id is pending
            or (
                current_id
                is not None
                and current_id.chat_id
                == pending.chat_id
            )
        ):
            self._by_id.pop(
                pending.review_id,
                None,
            )

    def _purge_if_expired(
        self,
        pending: Optional[
            PendingExternalReview
        ],
    ) -> Optional[
        PendingExternalReview
    ]:
        if pending is None:
            return None

        if not pending.expired:
            return pending

        self._remove(
            pending
        )

        return None

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    def create(
        self,
        *,
        review_id: str,
        chat_id: int,
        content: NormalizedExternalContent,
        replace_existing: bool = False,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            raise ValueError(
                "review_id is required"
            )

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise TypeError(
                "content must be NormalizedExternalContent"
            )

        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            existing_chat = (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

            existing_id = (
                self._purge_if_expired(
                    self._by_id.get(
                        normalized_review_id
                    )
                )
            )

            if (
                existing_id
                is not None
                and existing_id.chat_id
                != normalized_chat_id
            ):
                raise ExternalReviewConflict(
                    "review_id already belongs to another chat"
                )

            if (
                existing_chat
                is not None
                and existing_chat.review_id
                != normalized_review_id
            ):
                if not replace_existing:
                    raise ExternalReviewConflict(
                        "chat already has an active external review"
                    )

                self._remove(
                    existing_chat
                )

            if existing_id is not None:
                if not replace_existing:
                    raise ExternalReviewConflict(
                        "review_id already exists"
                    )

                self._remove(
                    existing_id
                )

            now = time()

            pending = (
                PendingExternalReview(
                    review_id=(
                        normalized_review_id
                    ),
                    chat_id=(
                        normalized_chat_id
                    ),
                    content=content,
                    created_at=now,
                    expires_at=(
                        now
                        + self.ttl_seconds
                    ),
                    manual_image_source=(
                        MANUAL_IMAGE_SOURCE_PRIMARY
                    ),
                )
            )

            self._by_chat[
                normalized_chat_id
            ] = pending

            self._by_id[
                normalized_review_id
            ] = pending

            return pending

    # -----------------------------------------------------
    # READ
    # -----------------------------------------------------

    def get_for_chat(
        self,
        chat_id: int,
    ) -> Optional[
        PendingExternalReview
    ]:
        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            return (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

    def get_by_id(
        self,
        review_id: str,
    ) -> Optional[
        PendingExternalReview
    ]:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            return None

        with self._lock:
            return (
                self._purge_if_expired(
                    self._by_id.get(
                        normalized_review_id
                    )
                )
            )

    def require(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            pending = (
                self._by_id.get(
                    normalized_review_id
                )
            )

            if pending is None:
                raise ExternalReviewNotFound(
                    "external review not found"
                )

            if pending.expired:
                self._remove(
                    pending
                )

                raise ExternalReviewExpired(
                    "external review expired"
                )

            if (
                pending.chat_id
                != normalized_chat_id
            ):
                raise ExternalReviewNotFound(
                    "external review does not belong to this chat"
                )

            return pending

    # -----------------------------------------------------
    # MEDIA SELECTION
    # -----------------------------------------------------

    def update_media_selection(
        self,
        *,
        review_id: str,
        chat_id: int,
        selected_media_indexes: Tuple[
            int,
            ...,
        ],
        explicit: bool = True,
    ) -> PendingExternalReview:
        normalized_indexes = (
            _normalize_media_indexes(
                selected_media_indexes
            )
        )

        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            _validate_media_indexes(
                pending,
                normalized_indexes,
            )

            updated = _replace_pending(
                pending,
                selected_media_indexes=(
                    normalized_indexes
                ),
                media_selection_explicit=bool(
                    explicit
                ),
                manual_image_source=(
                    MANUAL_IMAGE_SOURCE_PRIMARY
                ),
            )

            self._by_chat[
                updated.chat_id
            ] = updated

            self._by_id[
                updated.review_id
            ] = updated

            return updated

    # -----------------------------------------------------
    # MEDIA PRESENTATION MODE
    # -----------------------------------------------------

    def update_media_presentation_mode(
        self,
        *,
        review_id: str,
        chat_id: int,
        media_presentation_mode: str,
    ) -> PendingExternalReview:
        """
        Toggle the review-only media presentation mode.

        This is a non-terminal, state-only update: it never
        publishes anything and preserves every other pending field
        (media selection, preview message identity, ...).
        """

        normalized_mode = (
            _normalize_media_presentation_mode(
                media_presentation_mode
            )
        )

        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            updated = _replace_pending(
                pending,
                media_presentation_mode=(
                    normalized_mode
                ),
            )

            self._by_chat[
                updated.chat_id
            ] = updated

            self._by_id[
                updated.review_id
            ] = updated

            return updated

    # -----------------------------------------------------
    # PREVIEW MESSAGE IDENTITY
    # -----------------------------------------------------

    def update_preview_message_refs(
        self,
        *,
        review_id: str,
        chat_id: int,
        preview_message_id: Optional[
            int
        ] = None,
        preview_media_message_ids: Tuple[
            int,
            ...,
        ] = (),
        preview_media_file_ids: Optional[
            Tuple[str, ...]
        ] = None,
    ) -> PendingExternalReview:
        normalized_message_id = (
            _normalize_message_id(
                preview_message_id
            )
        )

        normalized_media_ids = (
            _normalize_message_ids(
                preview_media_message_ids
            )
        )

        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            if preview_media_file_ids is None:
                normalized_file_ids = (
                    pending.preview_media_file_ids
                )

            else:
                normalized_file_ids = (
                    _normalize_file_ids(
                        preview_media_file_ids,
                        expected_length=len(
                            pending.content.media
                        ),
                    )
                )

            updated = _replace_pending(
                pending,
                preview_message_id=(
                    normalized_message_id
                ),
                preview_media_message_ids=(
                    normalized_media_ids
                ),
                preview_media_file_ids=(
                    normalized_file_ids
                ),
            )

            self._by_chat[
                updated.chat_id
            ] = updated

            self._by_id[
                updated.review_id
            ] = updated

            return updated

    def update_manual_image_state(
        self,
        *,
        review_id: str,
        chat_id: int,
        manual_image_source: Optional[
            str
        ] = None,
        manual_image_file_id: Optional[
            str
        ] = None,
        manual_image_waiting: Optional[
            bool
        ] = None,
    ) -> PendingExternalReview:
        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            updated = _replace_pending(
                pending,
                manual_image_source=(
                    pending.manual_image_source
                    if manual_image_source is None
                    else _normalize_manual_image_source(
                        manual_image_source
                    )
                ),
                manual_image_file_id=(
                    pending.manual_image_file_id
                    if manual_image_file_id is None
                    else _normalize_manual_image_file_id(
                        manual_image_file_id
                    )
                ),
                manual_image_waiting=(
                    pending.manual_image_waiting
                    if manual_image_waiting is None
                    else bool(
                        manual_image_waiting
                    )
                ),
            )

            self._by_chat[
                updated.chat_id
            ] = updated

            self._by_id[
                updated.review_id
            ] = updated

            return updated

    # -----------------------------------------------------
    # REVIEW STAGE (SHORT / PARAGRAPHS draft lifecycle)
    # -----------------------------------------------------

    def update_review_stage(
        self,
        *,
        review_id: str,
        chat_id: int,
        review_stage: Optional[
            str
        ] = None,
        draft_text: Optional[
            str
        ] = None,
        paragraph_selected_indexes: Optional[
            Tuple[int, ...]
        ] = None,
        paragraph_page: Optional[
            int
        ] = None,
        awaiting_edit_text: Optional[
            bool
        ] = None,
    ) -> PendingExternalReview:
        """
        Non-terminal, state-only transition for the SHORT / PARAGRAPHS
        preview lifecycle (select -> draft preview -> approve/edit/
        regenerate/cancel). Never publishes anything.
        """

        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            normalized_paragraph_indexes = (
                pending.paragraph_selected_indexes
                if paragraph_selected_indexes is None
                else _normalize_media_indexes(
                    paragraph_selected_indexes
                )
            )

            if paragraph_selected_indexes is not None:
                _validate_paragraph_indexes(
                    pending,
                    normalized_paragraph_indexes,
                )

            updated = _replace_pending(
                pending,
                review_stage=(
                    pending.review_stage
                    if review_stage is None
                    else _normalize_review_stage(
                        review_stage
                    )
                ),
                draft_text=(
                    pending.draft_text
                    if draft_text is None
                    else _normalize_draft_text(
                        draft_text
                    )
                ),
                paragraph_selected_indexes=(
                    normalized_paragraph_indexes
                ),
                paragraph_page=(
                    pending.paragraph_page
                    if paragraph_page is None
                    else _normalize_paragraph_page(
                        paragraph_page
                    )
                ),
                awaiting_edit_text=(
                    pending.awaiting_edit_text
                    if awaiting_edit_text is None
                    else bool(
                        awaiting_edit_text
                    )
                ),
            )

            self._by_chat[
                updated.chat_id
            ] = updated

            self._by_id[
                updated.review_id
            ] = updated

            return updated

    # -----------------------------------------------------
    # COMPLETE / CANCEL
    # -----------------------------------------------------

    def pop(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            self._remove(
                pending
            )

            return pending

    def cancel_for_chat(
        self,
        chat_id: int,
    ) -> bool:
        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            pending = (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

            if pending is None:
                return False

            self._remove(
                pending
            )

            return True

    # -----------------------------------------------------
    # MAINTENANCE
    # -----------------------------------------------------

    def cleanup_expired(
        self,
    ) -> int:
        with self._lock:
            expired = tuple(
                pending
                for pending
                in self._by_id.values()
                if pending.expired
            )

            for pending in expired:
                self._remove(
                    pending
                )

            return len(
                expired
            )

    def reset(
        self,
    ) -> None:
        with self._lock:
            self._by_chat.clear()
            self._by_id.clear()

    def __len__(
        self,
    ) -> int:
        with self._lock:
            self.cleanup_expired()

            return len(
                self._by_id
            )

    def active_review_ids(
        self,
    ) -> Tuple[str, ...]:
        with self._lock:
            self.cleanup_expired()

            return tuple(
                sorted(
                    self._by_id.keys()
                )
            )


# =========================================================
# PERSISTENT SUPABASE STORE
# =========================================================


class PersistentExternalReviewStateStore:
    """
    Durable External Review store backed by Supabase.

    This keeps callback state valid across:
      - Render workers
      - process restarts
      - webhook requests handled by different processes

    The public API mirrors ExternalReviewStateStore.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = (
            DEFAULT_EXTERNAL_REVIEW_TTL_SECONDS
        ),
        client: Any = None,
    ) -> None:
        ttl = int(
            ttl_seconds
        )

        if ttl <= 0:
            raise ValueError(
                "ttl_seconds must be > 0"
            )

        self.ttl_seconds = ttl

        if client is None:
            from core import database

            client = (
                database
                .service_supabase
            )

        if client is None:
            raise ExternalReviewPersistenceError(
                (
                    "SUPABASE_SERVICE_ROLE_KEY "
                    "is required for persistent "
                    "external review state"
                )
            )

        self.client = client

    # -----------------------------------------------------
    # INTERNAL
    # -----------------------------------------------------

    def _table(
        self,
    ):
        return self.client.table(
            EXTERNAL_REVIEW_TABLE
        )

    def _row_to_pending(
        self,
        row: Mapping[str, Any],
    ) -> PendingExternalReview:
        content_value = (
            row.get(
                "content",
                {},
            )
            or {}
        )

        if not isinstance(
            content_value,
            Mapping,
        ):
            raise ExternalReviewPersistenceError(
                "stored external review content is invalid"
            )

        (
            selected_media_indexes,
            media_selection_explicit,
            preview_message_id,
            preview_media_message_ids,
            preview_media_file_ids,
            media_presentation_mode,
            manual_image_source,
            manual_image_file_id,
            manual_image_waiting,
            review_stage,
            draft_text,
            paragraph_selected_indexes,
            paragraph_page,
            awaiting_edit_text,
        ) = _review_state_from_content_dict(
            content_value,
            media_count=len(
                (
                    content_value.get(
                        "media",
                        [],
                    )
                    or []
                )
            ),
        )

        return PendingExternalReview(
            review_id=str(
                row.get(
                    "review_id",
                    "",
                )
                or ""
            ),
            chat_id=int(
                row.get(
                    "chat_id"
                )
            ),
            content=(
                _content_from_dict(
                    content_value
                )
            ),
            created_at=(
                _iso_to_timestamp(
                    row.get(
                        "created_at"
                    )
                )
            ),
            expires_at=(
                _iso_to_timestamp(
                    row.get(
                        "expires_at"
                    )
                )
            ),
            selected_media_indexes=(
                selected_media_indexes
            ),
            media_selection_explicit=(
                media_selection_explicit
            ),
            preview_message_id=(
                preview_message_id
            ),
            preview_media_message_ids=(
                preview_media_message_ids
            ),
            preview_media_file_ids=(
                preview_media_file_ids
            ),
            media_presentation_mode=(
                media_presentation_mode
            ),
            manual_image_source=(
                manual_image_source
            ),
            manual_image_file_id=(
                manual_image_file_id
            ),
            manual_image_waiting=(
                manual_image_waiting
            ),
            review_stage=(
                review_stage
            ),
            draft_text=(
                draft_text
            ),
            paragraph_selected_indexes=(
                paragraph_selected_indexes
            ),
            paragraph_page=(
                paragraph_page
            ),
            awaiting_edit_text=(
                awaiting_edit_text
            ),
        )

    def _select_one(
        self,
        *,
        field: str,
        value: Any,
    ) -> Optional[
        PendingExternalReview
    ]:
        try:
            response = (
                self._table()
                .select(
                    (
                        "review_id,"
                        "chat_id,"
                        "content,"
                        "created_at,"
                        "expires_at"
                    )
                )
                .eq(
                    field,
                    value,
                )
                .limit(1)
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to read persistent external review state"
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if not rows:
            return None

        pending = (
            self._row_to_pending(
                rows[0]
            )
        )

        if pending.expired:
            try:
                (
                    self._table()
                    .delete()
                    .eq(
                        "review_id",
                        pending.review_id,
                    )
                    .execute()
                )
            except Exception:
                logger.exception(
                    (
                        "Failed to cleanup expired "
                        "external review | review_id=%s"
                    ),
                    pending.review_id,
                )

            return None

        return pending

    def _delete_review(
        self,
        review_id: str,
    ) -> None:
        try:
            (
                self._table()
                .delete()
                .eq(
                    "review_id",
                    review_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to delete persistent external review state"
            ) from exc

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    def create(
        self,
        *,
        review_id: str,
        chat_id: int,
        content: NormalizedExternalContent,
        replace_existing: bool = False,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            raise ValueError(
                "review_id is required"
            )

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise TypeError(
                "content must be NormalizedExternalContent"
            )

        normalized_chat_id = int(
            chat_id
        )

        existing_id = (
            self.get_by_id(
                normalized_review_id
            )
        )

        existing_chat = (
            self.get_for_chat(
                normalized_chat_id
            )
        )

        if (
            existing_id is not None
            and existing_id.chat_id
            != normalized_chat_id
        ):
            raise ExternalReviewConflict(
                "review_id already belongs to another chat"
            )

        if (
            existing_chat is not None
            and existing_chat.review_id
            != normalized_review_id
            and not replace_existing
        ):
            raise ExternalReviewConflict(
                "chat already has an active external review"
            )

        if (
            existing_id is not None
            and not replace_existing
        ):
            raise ExternalReviewConflict(
                "review_id already exists"
            )

        if (
            replace_existing
            and existing_chat is not None
        ):
            self._delete_review(
                existing_chat.review_id
            )

        if (
            replace_existing
            and existing_id is not None
            and (
                existing_chat is None
                or existing_id.review_id
                != existing_chat.review_id
            )
        ):
            self._delete_review(
                existing_id.review_id
            )

        now = _utc_now()

        expires_at = (
            now
            + timedelta(
                seconds=(
                    self.ttl_seconds
                )
            )
        )

        payload = {
            "review_id": (
                normalized_review_id
            ),
            "chat_id": (
                normalized_chat_id
            ),
            "content": (
                _content_with_review_state_to_dict(
                    content
                )
            ),
            "created_at": (
                now.isoformat()
            ),
            "expires_at": (
                expires_at.isoformat()
            ),
        }

        try:
            response = (
                self._table()
                .insert(
                    payload
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to persist external review state"
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return PendingExternalReview(
            review_id=(
                normalized_review_id
            ),
            chat_id=(
                normalized_chat_id
            ),
            content=content,
            created_at=(
                now.timestamp()
            ),
            expires_at=(
                expires_at.timestamp()
            ),
            manual_image_source=(
                MANUAL_IMAGE_SOURCE_PRIMARY
            ),
        )

    # -----------------------------------------------------
    # READ
    # -----------------------------------------------------

    def get_for_chat(
        self,
        chat_id: int,
    ) -> Optional[
        PendingExternalReview
    ]:
        return self._select_one(
            field="chat_id",
            value=int(
                chat_id
            ),
        )

    def get_by_id(
        self,
        review_id: str,
    ) -> Optional[
        PendingExternalReview
    ]:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            return None

        return self._select_one(
            field="review_id",
            value=normalized_review_id,
        )

    def require(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        normalized_chat_id = int(
            chat_id
        )

        pending = (
            self._select_one(
                field="review_id",
                value=(
                    normalized_review_id
                ),
            )
        )

        if pending is None:
            raise ExternalReviewNotFound(
                "external review not found"
            )

        if (
            pending.chat_id
            != normalized_chat_id
        ):
            raise ExternalReviewNotFound(
                "external review does not belong to this chat"
            )

        if pending.expired:
            self._delete_review(
                pending.review_id
            )

            raise ExternalReviewExpired(
                "external review expired"
            )

        return pending

    # -----------------------------------------------------
    # MEDIA SELECTION
    # -----------------------------------------------------

    def update_media_selection(
        self,
        *,
        review_id: str,
        chat_id: int,
        selected_media_indexes: Tuple[
            int,
            ...,
        ],
        explicit: bool = True,
    ) -> PendingExternalReview:
        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        normalized_indexes = (
            _normalize_media_indexes(
                selected_media_indexes
            )
        )

        _validate_media_indexes(
            pending,
            normalized_indexes,
        )

        payload = {
            "content": (
                _content_with_review_state_to_dict(
                    pending.content,
                    selected_media_indexes=(
                        normalized_indexes
                    ),
                    media_selection_explicit=bool(
                        explicit
                    ),
                    preview_message_id=(
                        pending.preview_message_id
                    ),
                    preview_media_message_ids=(
                        pending.preview_media_message_ids
                    ),
                    preview_media_file_ids=(
                        pending.preview_media_file_ids
                    ),
                    media_presentation_mode=(
                        pending.media_presentation_mode
                    ),
                    manual_image_source=(
                        pending.manual_image_source
                    ),
                    manual_image_file_id=(
                        pending.manual_image_file_id
                    ),
                    manual_image_waiting=(
                        pending.manual_image_waiting
                    ),
                    review_stage=(
                        pending.review_stage
                    ),
                    draft_text=(
                        pending.draft_text
                    ),
                    paragraph_selected_indexes=(
                        pending.paragraph_selected_indexes
                    ),
                    paragraph_page=(
                        pending.paragraph_page
                    ),
                    awaiting_edit_text=(
                        pending.awaiting_edit_text
                    ),
                )
            )
        }

        try:
            response = (
                self._table()
                .update(
                    payload
                )
                .eq(
                    "review_id",
                    pending.review_id,
                )
                .eq(
                    "chat_id",
                    pending.chat_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                (
                    "failed to update persistent "
                    "external review media selection"
                )
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return _replace_pending(
            pending,
            selected_media_indexes=(
                normalized_indexes
            ),
            media_selection_explicit=bool(
                explicit
            ),
            manual_image_source=(
                MANUAL_IMAGE_SOURCE_PRIMARY
            ),
        )

    # -----------------------------------------------------
    # MEDIA PRESENTATION MODE
    # -----------------------------------------------------

    def update_media_presentation_mode(
        self,
        *,
        review_id: str,
        chat_id: int,
        media_presentation_mode: str,
    ) -> PendingExternalReview:
        """
        Toggle the review-only media presentation mode.

        This is a non-terminal, state-only update: it never
        publishes anything and preserves every other pending field
        (media selection, preview message identity, ...).
        """

        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        normalized_mode = (
            _normalize_media_presentation_mode(
                media_presentation_mode
            )
        )

        payload = {
            "content": (
                _content_with_review_state_to_dict(
                    pending.content,
                    selected_media_indexes=(
                        pending.selected_media_indexes
                    ),
                    media_selection_explicit=(
                        pending.media_selection_explicit
                    ),
                    preview_message_id=(
                        pending.preview_message_id
                    ),
                    preview_media_message_ids=(
                        pending.preview_media_message_ids
                    ),
                    preview_media_file_ids=(
                        pending.preview_media_file_ids
                    ),
                    media_presentation_mode=(
                        normalized_mode
                    ),
                    manual_image_source=(
                        pending.manual_image_source
                    ),
                    manual_image_file_id=(
                        pending.manual_image_file_id
                    ),
                    manual_image_waiting=(
                        pending.manual_image_waiting
                    ),
                    review_stage=(
                        pending.review_stage
                    ),
                    draft_text=(
                        pending.draft_text
                    ),
                    paragraph_selected_indexes=(
                        pending.paragraph_selected_indexes
                    ),
                    paragraph_page=(
                        pending.paragraph_page
                    ),
                    awaiting_edit_text=(
                        pending.awaiting_edit_text
                    ),
                )
            )
        }

        try:
            response = (
                self._table()
                .update(
                    payload
                )
                .eq(
                    "review_id",
                    pending.review_id,
                )
                .eq(
                    "chat_id",
                    pending.chat_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                (
                    "failed to update persistent "
                    "external review media presentation mode"
                )
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return _replace_pending(
            pending,
            media_presentation_mode=(
                normalized_mode
            ),
        )

    # -----------------------------------------------------
    # PREVIEW MESSAGE IDENTITY
    # -----------------------------------------------------

    def update_preview_message_refs(
        self,
        *,
        review_id: str,
        chat_id: int,
        preview_message_id: Optional[
            int
        ] = None,
        preview_media_message_ids: Tuple[
            int,
            ...,
        ] = (),
        preview_media_file_ids: Optional[
            Tuple[str, ...]
        ] = None,
    ) -> PendingExternalReview:
        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        normalized_message_id = (
            _normalize_message_id(
                preview_message_id
            )
        )

        normalized_media_ids = (
            _normalize_message_ids(
                preview_media_message_ids
            )
        )

        if preview_media_file_ids is None:
            normalized_file_ids = (
                pending.preview_media_file_ids
            )

        else:
            normalized_file_ids = (
                _normalize_file_ids(
                    preview_media_file_ids,
                    expected_length=len(
                        pending.content.media
                    ),
                )
            )

        payload = {
            "content": (
                _content_with_review_state_to_dict(
                    pending.content,
                    selected_media_indexes=(
                        pending.selected_media_indexes
                    ),
                    media_selection_explicit=(
                        pending.media_selection_explicit
                    ),
                    preview_message_id=(
                        normalized_message_id
                    ),
                    preview_media_message_ids=(
                        normalized_media_ids
                    ),
                    preview_media_file_ids=(
                        normalized_file_ids
                    ),
                    media_presentation_mode=(
                        pending.media_presentation_mode
                    ),
                    manual_image_source=(
                        pending.manual_image_source
                    ),
                    manual_image_file_id=(
                        pending.manual_image_file_id
                    ),
                    manual_image_waiting=(
                        pending.manual_image_waiting
                    ),
                    review_stage=(
                        pending.review_stage
                    ),
                    draft_text=(
                        pending.draft_text
                    ),
                    paragraph_selected_indexes=(
                        pending.paragraph_selected_indexes
                    ),
                    paragraph_page=(
                        pending.paragraph_page
                    ),
                    awaiting_edit_text=(
                        pending.awaiting_edit_text
                    ),
                )
            )
        }

        try:
            response = (
                self._table()
                .update(
                    payload
                )
                .eq(
                    "review_id",
                    pending.review_id,
                )
                .eq(
                    "chat_id",
                    pending.chat_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                (
                    "failed to update persistent "
                    "external review preview message refs"
                )
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return _replace_pending(
            pending,
            preview_message_id=(
                normalized_message_id
            ),
            preview_media_message_ids=(
                normalized_media_ids
            ),
            preview_media_file_ids=(
                normalized_file_ids
            ),
        )

    def update_manual_image_state(
        self,
        *,
        review_id: str,
        chat_id: int,
        manual_image_source: Optional[
            str
        ] = None,
        manual_image_file_id: Optional[
            str
        ] = None,
        manual_image_waiting: Optional[
            bool
        ] = None,
    ) -> PendingExternalReview:
        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        payload = {
            "content": (
                _content_with_review_state_to_dict(
                    pending.content,
                    selected_media_indexes=(
                        pending.selected_media_indexes
                    ),
                    media_selection_explicit=(
                        pending.media_selection_explicit
                    ),
                    preview_message_id=(
                        pending.preview_message_id
                    ),
                    preview_media_message_ids=(
                        pending.preview_media_message_ids
                    ),
                    preview_media_file_ids=(
                        pending.preview_media_file_ids
                    ),
                    media_presentation_mode=(
                        pending.media_presentation_mode
                    ),
                    manual_image_source=(
                        pending.manual_image_source
                        if manual_image_source is None
                        else _normalize_manual_image_source(
                            manual_image_source
                        )
                    ),
                    manual_image_file_id=(
                        pending.manual_image_file_id
                        if manual_image_file_id is None
                        else _normalize_manual_image_file_id(
                            manual_image_file_id
                        )
                    ),
                    manual_image_waiting=(
                        pending.manual_image_waiting
                        if manual_image_waiting is None
                        else bool(
                            manual_image_waiting
                        )
                    ),
                    review_stage=(
                        pending.review_stage
                    ),
                    draft_text=(
                        pending.draft_text
                    ),
                    paragraph_selected_indexes=(
                        pending.paragraph_selected_indexes
                    ),
                    paragraph_page=(
                        pending.paragraph_page
                    ),
                    awaiting_edit_text=(
                        pending.awaiting_edit_text
                    ),
                )
            )
        }

        try:
            response = (
                self._table()
                .update(
                    payload
                )
                .eq(
                    "review_id",
                    pending.review_id,
                )
                .eq(
                    "chat_id",
                    pending.chat_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                (
                    "failed to update persistent "
                    "external review manual image state"
                )
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return _replace_pending(
            pending,
            manual_image_source=(
                pending.manual_image_source
                if manual_image_source is None
                else _normalize_manual_image_source(
                    manual_image_source
                )
            ),
            manual_image_file_id=(
                pending.manual_image_file_id
                if manual_image_file_id is None
                else _normalize_manual_image_file_id(
                    manual_image_file_id
                )
            ),
            manual_image_waiting=(
                pending.manual_image_waiting
                if manual_image_waiting is None
                else bool(
                    manual_image_waiting
                )
            ),
        )

    # -----------------------------------------------------
    # REVIEW STAGE (SHORT / PARAGRAPHS draft lifecycle)
    # -----------------------------------------------------

    def update_review_stage(
        self,
        *,
        review_id: str,
        chat_id: int,
        review_stage: Optional[
            str
        ] = None,
        draft_text: Optional[
            str
        ] = None,
        paragraph_selected_indexes: Optional[
            Tuple[int, ...]
        ] = None,
        paragraph_page: Optional[
            int
        ] = None,
        awaiting_edit_text: Optional[
            bool
        ] = None,
    ) -> PendingExternalReview:
        """
        Non-terminal, state-only transition for the SHORT / PARAGRAPHS
        preview lifecycle (select -> draft preview -> approve/edit/
        regenerate/cancel). Never publishes anything.
        """

        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        normalized_paragraph_indexes = (
            pending.paragraph_selected_indexes
            if paragraph_selected_indexes is None
            else _normalize_media_indexes(
                paragraph_selected_indexes
            )
        )

        if paragraph_selected_indexes is not None:
            _validate_paragraph_indexes(
                pending,
                normalized_paragraph_indexes,
            )

        normalized_review_stage = (
            pending.review_stage
            if review_stage is None
            else _normalize_review_stage(
                review_stage
            )
        )

        normalized_draft_text = (
            pending.draft_text
            if draft_text is None
            else _normalize_draft_text(
                draft_text
            )
        )

        normalized_paragraph_page = (
            pending.paragraph_page
            if paragraph_page is None
            else _normalize_paragraph_page(
                paragraph_page
            )
        )

        normalized_awaiting_edit_text = (
            pending.awaiting_edit_text
            if awaiting_edit_text is None
            else bool(
                awaiting_edit_text
            )
        )

        payload = {
            "content": (
                _content_with_review_state_to_dict(
                    pending.content,
                    selected_media_indexes=(
                        pending.selected_media_indexes
                    ),
                    media_selection_explicit=(
                        pending.media_selection_explicit
                    ),
                    preview_message_id=(
                        pending.preview_message_id
                    ),
                    preview_media_message_ids=(
                        pending.preview_media_message_ids
                    ),
                    preview_media_file_ids=(
                        pending.preview_media_file_ids
                    ),
                    media_presentation_mode=(
                        pending.media_presentation_mode
                    ),
                    manual_image_source=(
                        pending.manual_image_source
                    ),
                    manual_image_file_id=(
                        pending.manual_image_file_id
                    ),
                    manual_image_waiting=(
                        pending.manual_image_waiting
                    ),
                    review_stage=(
                        normalized_review_stage
                    ),
                    draft_text=(
                        normalized_draft_text
                    ),
                    paragraph_selected_indexes=(
                        normalized_paragraph_indexes
                    ),
                    paragraph_page=(
                        normalized_paragraph_page
                    ),
                    awaiting_edit_text=(
                        normalized_awaiting_edit_text
                    ),
                )
            )
        }

        try:
            response = (
                self._table()
                .update(
                    payload
                )
                .eq(
                    "review_id",
                    pending.review_id,
                )
                .eq(
                    "chat_id",
                    pending.chat_id,
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                (
                    "failed to update persistent "
                    "external review stage"
                )
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        if rows:
            return self._row_to_pending(
                rows[0]
            )

        return _replace_pending(
            pending,
            review_stage=(
                normalized_review_stage
            ),
            draft_text=(
                normalized_draft_text
            ),
            paragraph_selected_indexes=(
                normalized_paragraph_indexes
            ),
            paragraph_page=(
                normalized_paragraph_page
            ),
            awaiting_edit_text=(
                normalized_awaiting_edit_text
            ),
        )

    # -----------------------------------------------------
    # COMPLETE / CANCEL
    # -----------------------------------------------------

    def pop(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        pending = self.require(
            review_id=review_id,
            chat_id=chat_id,
        )

        self._delete_review(
            pending.review_id
        )

        return pending

    def cancel_for_chat(
        self,
        chat_id: int,
    ) -> bool:
        pending = (
            self.get_for_chat(
                chat_id
            )
        )

        if pending is None:
            return False

        self._delete_review(
            pending.review_id
        )

        return True

    # -----------------------------------------------------
    # MAINTENANCE
    # -----------------------------------------------------

    def cleanup_expired(
        self,
    ) -> int:
        now_iso = (
            _utc_now()
            .isoformat()
        )

        try:
            existing = (
                self._table()
                .select(
                    "review_id"
                )
                .lt(
                    "expires_at",
                    now_iso,
                )
                .execute()
            )

            rows = (
                getattr(
                    existing,
                    "data",
                    None,
                )
                or []
            )

            if not rows:
                return 0

            (
                self._table()
                .delete()
                .lt(
                    "expires_at",
                    now_iso,
                )
                .execute()
            )

            return len(
                rows
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to cleanup persistent external reviews"
            ) from exc

    def reset(
        self,
    ) -> None:
        """
        Test/maintenance helper.

        Avoid calling this in ordinary production flow.
        """

        try:
            (
                self._table()
                .delete()
                .neq(
                    "review_id",
                    "",
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to reset persistent external review state"
            ) from exc

    def __len__(
        self,
    ) -> int:
        self.cleanup_expired()

        try:
            response = (
                self._table()
                .select(
                    "review_id"
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to count persistent external reviews"
            ) from exc

        return len(
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

    def active_review_ids(
        self,
    ) -> Tuple[str, ...]:
        self.cleanup_expired()

        try:
            response = (
                self._table()
                .select(
                    "review_id"
                )
                .execute()
            )

        except Exception as exc:
            raise ExternalReviewPersistenceError(
                "failed to list persistent external reviews"
            ) from exc

        rows = (
            getattr(
                response,
                "data",
                None,
            )
            or []
        )

        return tuple(
            sorted(
                str(
                    row.get(
                        "review_id",
                        "",
                    )
                    or ""
                )
                for row in rows
                if row.get(
                    "review_id"
                )
            )
        )


# =========================================================
# DEFAULT STORE RESOLUTION
# =========================================================


def persistent_external_review_enabled(
) -> bool:
    return (
        str(
            os.getenv(
                PERSISTENT_EXTERNAL_REVIEW_ENV,
                "",
            )
            or ""
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def _build_default_store():
    if not persistent_external_review_enabled():
        return ExternalReviewStateStore()

    try:
        store = (
            PersistentExternalReviewStateStore()
        )

        logger.info(
            (
                "✅ Persistent external review "
                "state enabled"
            )
        )

        return store

    except Exception:
        # Keep the application bootable if persistent state was enabled
        # before its required database configuration was available.
        # Production logs make the degraded mode explicit.
        logger.exception(
            (
                "❌ Persistent external review state "
                "unavailable | falling back to "
                "in-process state"
            )
        )

        return ExternalReviewStateStore()


DEFAULT_EXTERNAL_REVIEW_STATE_STORE = (
    _build_default_store()
)
