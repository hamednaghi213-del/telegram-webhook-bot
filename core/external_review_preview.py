"""Single renderer for the External Content Review preview surface.

Both the initial preview (after URL ingestion) and every later
state refresh (media toggle / no-media) are rendered here so the
review interface stays coherent and is edited in place instead of
accumulating new messages.

Design:
  - one optional media panel (photos only, album when possible)
  - one persistent control message (capped text + inline keyboard)

Preview text capping is presentation-only. The stored
NormalizedExternalContent remains complete; final publication text
is assembled later from the stored content by the existing shared
bridge/engine and is never affected by this capping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Optional,
    Tuple,
)

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalContentPreview,
)


# =========================================================
# LIMITS
# =========================================================

# Telegram text messages allow 4096 characters. The control message
# keeps headroom for the heading, metadata lines and selection
# status so one editMessageText always stays valid.
CONTROL_TEXT_LIMIT = 3500


# =========================================================
# VIEW MODEL
# =========================================================


@dataclass(frozen=True)
class ExternalReviewPreviewView:
    """Everything the Telegram layer needs to render one review."""

    review_id: str
    text: str
    reply_markup: dict
    media: Tuple[ExternalMedia, ...]


# =========================================================
# INTERNAL HELPERS
# =========================================================


def _truncate_preserving_words(
    text: str,
    limit: int,
) -> str:
    value = str(
        text
        or ""
    ).strip()

    if limit <= 0:
        return ""

    if len(value) <= limit:
        return value

    cut = value[:limit]

    split_at = cut.rfind(
        "\n\n"
    )

    if split_at < limit // 2:
        split_at = cut.rfind("\n")

    if split_at < limit // 2:
        split_at = cut.rfind(" ")

    if split_at <= 0:
        split_at = limit

    return cut[:split_at].strip()


def _selected_media(
    content: NormalizedExternalContent,
    *,
    selected_media_indexes: Tuple[int, ...],
    media_selection_explicit: bool,
) -> Tuple[ExternalMedia, ...]:
    media = tuple(
        content.media
        or ()
    )

    if not media_selection_explicit:
        return media

    selected = []

    for index in selected_media_indexes:
        if 0 <= index < len(media):
            selected.append(
                media[index]
            )

    return tuple(
        selected
    )


def _selection_status_line(
    *,
    media_count: int,
    selected_media_indexes: Tuple[int, ...],
    media_selection_explicit: bool,
) -> str:
    if media_count <= 0:
        return ""

    if not media_selection_explicit:
        if media_count == 1:
            return (
                "🖼 تصویر شناسایی‌شده "
                "به‌طور پیش‌فرض استفاده می‌شود."
            )

        return (
            f"🖼 هر {media_count} تصویر در آلبوم "
            "انتشار استفاده می‌شوند."
        )

    if not selected_media_indexes:
        return (
            "🚫 بدون تصویر انتخاب شده است."
        )

    human_indexes = ", ".join(
        str(index + 1)
        for index
        in selected_media_indexes
    )

    return (
        "🖼 تصاویر آلبوم انتشار: "
        f"{human_indexes}"
    )


def _presentation_mode_status_line(
    *,
    media_count: int,
    media_presentation_mode: str,
) -> str:
    if media_count <= 1:
        return ""

    normalized_mode = str(
        media_presentation_mode
        or ""
    ).strip().lower()

    if normalized_mode == "album":
        return (
            "🖼 حالت انتشار: آلبوم "
            "(ارسال گروهی تصاویر)."
        )

    return (
        "🖼 حالت انتشار: عادی "
        "(اسلایدشو پیش‌فرض)."
    )


def _media_count_line(
    media_count: int,
) -> str:
    if media_count == 1:
        return (
            "🖼 یک تصویر برای این مطلب "
            "شناسایی شد."
        )

    if media_count > 1:
        return (
            f"🖼 {media_count} تصویر برای "
            "این مطلب شناسایی شد."
        )

    return (
        "🖼 تصویر معتبری برای این "
        "مطلب شناسایی نشد."
    )


# =========================================================
# KEYBOARD
# =========================================================


def build_external_review_keyboard(
    *,
    review_id: str,
    media_count: int,
    selected_media_indexes: Tuple[int, ...] = (),
    media_selection_explicit: bool = False,
    media_presentation_mode: str = "normal",
) -> dict:
    """
    Build the review inline keyboard.

    Callback data format is unchanged:

        extrev:<action>:<review_id>
        extrev:media:<review_id>:<index>
        extrev:mode:<review_id>:<normal|album>
    """

    review_rows = [
        [
            {
                "text": "✅ استاندارد",
                "callback_data": (
                    "extrev:standard:"
                    f"{review_id}"
                ),
            },
            {
                "text": "✂️ کوتاه",
                "callback_data": (
                    "extrev:short:"
                    f"{review_id}"
                ),
            },
        ],
        [
            {
                "text": "📰 تیتر",
                "callback_data": (
                    "extrev:headline:"
                    f"{review_id}"
                ),
            },
            {
                "text": "📝 تیتر و لید",
                "callback_data": (
                    "extrev:lead:"
                    f"{review_id}"
                ),
            },
        ],
    ]

    if media_count > 0:
        selected_set = set(
            selected_media_indexes
            or ()
        )

        def media_label(
            base: str,
            index: int,
        ) -> str:
            if (
                media_selection_explicit
                and index in selected_set
            ):
                return f"{base} ✅"

            return base

        review_rows.append(
            [
                {
                    "text": media_label(
                        "🖼 تصویر اصلی",
                        0,
                    ),
                    "callback_data": (
                        "extrev:media:"
                        f"{review_id}:0"
                    ),
                },
                {
                    "text": (
                        "🚫 بدون تصویر ✅"
                        if (
                            media_selection_explicit
                            and not selected_media_indexes
                        )
                        else "🚫 بدون تصویر"
                    ),
                    "callback_data": (
                        "extrev:nomedia:"
                        f"{review_id}"
                    ),
                },
            ]
        )

        additional_media_buttons = []

        for media_index in range(
            1,
            media_count,
        ):
            additional_media_buttons.append(
                {
                    "text": media_label(
                        (
                            "🖼 "
                            f"تصویر {media_index + 1}"
                        ),
                        media_index,
                    ),
                    "callback_data": (
                        "extrev:media:"
                        f"{review_id}:"
                        f"{media_index}"
                    ),
                }
            )

        if additional_media_buttons:
            for index in range(
                0,
                len(
                    additional_media_buttons
                ),
                2,
            ):
                review_rows.append(
                    additional_media_buttons[
                        index:index + 2
                    ]
                )

        if media_count > 1:
            normalized_mode = str(
                media_presentation_mode
                or ""
            ).strip().lower()

            is_album = (
                normalized_mode == "album"
            )

            review_rows.append(
                [
                    {
                        "text": (
                            "🖼 آلبوم ✅"
                            if is_album
                            else "🖼 آلبوم"
                        ),
                        "callback_data": (
                            "extrev:mode:"
                            f"{review_id}:album"
                        ),
                    },
                    {
                        "text": (
                            "🖼 عادی ✅"
                            if not is_album
                            else "🖼 عادی"
                        ),
                        "callback_data": (
                            "extrev:mode:"
                            f"{review_id}:normal"
                        ),
                    },
                ]
            )

    review_rows.append(
        [
            {
                "text": "✍️ بازنویسی تحریریه",
                "callback_data": (
                    "extrev:editorial:"
                    f"{review_id}"
                ),
            },
        ]
    )

    review_rows.append(
        [
            {
                "text": "❌ لغو",
                "callback_data": (
                    "extrev:cancel:"
                    f"{review_id}"
                ),
            },
        ]
    )

    return {
        "inline_keyboard": (
            review_rows
        )
    }


# =========================================================
# RENDERER
# =========================================================


def build_external_review_preview(
    *,
    review_id: str,
    content: NormalizedExternalContent,
    preview: ExternalContentPreview,
    selected_media_indexes: Tuple[int, ...] = (),
    media_selection_explicit: bool = False,
    media_presentation_mode: str = "normal",
) -> ExternalReviewPreviewView:
    """
    Render one coherent review preview.

    The control-message text is capped so it always fits one
    editable Telegram text message. Capping is presentation-only:
    pending review content keeps the complete article.
    """

    media_count = int(
        preview.media_count
    )

    heading = "🔎 پیش‌نمایش مطلب"

    metadata_parts = []

    if preview.source_name:
        metadata_parts.append(
            "منبع: "
            f"{preview.source_name}"
        )

    metadata_parts.append(
        "اطمینان استخراج: "
        f"{round(preview.extraction_confidence * 100)}٪"
    )

    metadata_parts.append(
        _media_count_line(
            media_count
        )
    )

    if preview.warnings:
        metadata_parts.append(
            "⚠️ استخراج نیازمند بررسی است."
        )

    selection_status = (
        _selection_status_line(
            media_count=media_count,
            selected_media_indexes=(
                selected_media_indexes
            ),
            media_selection_explicit=(
                media_selection_explicit
            ),
        )
    )

    if selection_status:
        metadata_parts.append(
            selection_status
        )

    presentation_mode_status = (
        _presentation_mode_status_line(
            media_count=media_count,
            media_presentation_mode=(
                media_presentation_mode
            ),
        )
    )

    if presentation_mode_status:
        metadata_parts.append(
            presentation_mode_status
        )

    metadata_text = "\n".join(
        part
        for part in metadata_parts
        if part
    ).strip()

    preview_parts = []

    if preview.title:
        preview_parts.append(
            preview.title
        )

    if preview.lead:
        preview_parts.append(
            preview.lead
        )

    if preview.paragraphs:
        preview_parts.append(
            "\n\n".join(
                preview.paragraphs
            )
        )

    body_text = "\n\n".join(
        part
        for part in preview_parts
        if part
    ).strip()

    reserved = (
        len(heading)
        + len(metadata_text)
        + 8
    )

    body_budget = max(
        CONTROL_TEXT_LIMIT - reserved,
        0,
    )

    capped_body = (
        _truncate_preserving_words(
            body_text,
            body_budget,
        )
    )

    text_parts = [heading]

    if capped_body:
        text_parts.append(
            capped_body
        )

    if metadata_text:
        text_parts.append(
            metadata_text
        )

    text = "\n\n".join(
        text_parts
    ).strip()

    reply_markup = (
        build_external_review_keyboard(
            review_id=review_id,
            media_count=media_count,
            selected_media_indexes=(
                selected_media_indexes
            ),
            media_selection_explicit=(
                media_selection_explicit
            ),
            media_presentation_mode=(
                media_presentation_mode
            ),
        )
    )

    return ExternalReviewPreviewView(
        review_id=review_id,
        text=text,
        reply_markup=reply_markup,
        media=_selected_media(
            content,
            selected_media_indexes=(
                selected_media_indexes
            ),
            media_selection_explicit=(
                media_selection_explicit
            ),
        ),
    )
