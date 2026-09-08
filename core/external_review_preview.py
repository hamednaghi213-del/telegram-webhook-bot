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
from core.external_review_state import (
    MANUAL_IMAGE_SOURCE_NONE,
    MANUAL_IMAGE_SOURCE_PRIMARY,
    MANUAL_IMAGE_SOURCE_REPLACE,
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
    media_file_ids: Tuple[str, ...] = ()


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
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
) -> Tuple[
    Tuple[ExternalMedia, ...],
    Tuple[str, ...],
]:
    if (
        manual_image_source
        == MANUAL_IMAGE_SOURCE_REPLACE
        and str(
            manual_image_file_id
            or ""
        ).strip()
    ):
        return (
            (
                ExternalMedia(
                    type="photo",
                    source_url="",
                    position=0,
                    presentation="cover",
                    metadata={
                        "source_kind": "manual",
                    },
                ),
            ),
            (str(manual_image_file_id).strip(),),
        )

    if (
        manual_image_source
        == MANUAL_IMAGE_SOURCE_NONE
    ):
        return (), ()

    media = tuple(
        content.media
        or ()
    )

    if not media_selection_explicit:
        return media, ()

    selected = []

    for index in selected_media_indexes:
        if 0 <= index < len(media):
            selected.append(
                media[index]
            )

    return (
        tuple(
            selected
        ),
        (),
    )


def _selection_status_line(
    *,
    media_count: int,
    selected_media_indexes: Tuple[int, ...],
    media_selection_explicit: bool,
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
    manual_image_waiting: bool = False,
) -> str:
    if manual_image_waiting:
        return (
            "⏳ منتظر دریافت عکس بعدی شما برای جایگزینی هستم."
        )

    if (
        manual_image_source
        == MANUAL_IMAGE_SOURCE_REPLACE
        and str(
            manual_image_file_id
            or ""
        ).strip()
    ):
        return (
            "🖼 تصویر دستی جایگزین تصویر مطلب خواهد شد."
        )

    if (
        manual_image_source
        == MANUAL_IMAGE_SOURCE_NONE
    ):
        return (
            "🚫 بدون تصویر انتخاب شده است."
        )

    if media_count <= 0:
        return (
            "🖼 تصویر دستی اضافه نشده است."
        )

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
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
    manual_image_waiting: bool = False,
) -> dict:
    """
    Build the simplified review inline keyboard.

    Only high-level, non-technical choices are exposed:
      - content mode (standard / short / headline / headline+lead /
        paragraphs / editorial rewrite)
      - image source (trusted automatic primary image / no image /
        one manual add-or-replace button)
      - cancel

    Per-candidate media buttons and the album/normal presentation
    toggle are intentionally not rendered. Their callback actions
    ("media", "nomedia", "mode") remain supported for backward
    compatibility but are considered internal/technical and are no
    longer surfaced on the keyboard.

    Callback data format is unchanged:

        extrev:<action>:<review_id>
        extrev:manual:<review_id>:<waiting|cancel|replace|primary|none>
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
        [
            {
                "text": "📄 پاراگراف‌ها",
                "callback_data": (
                    "extrev:para_start:"
                    f"{review_id}"
                ),
            },
        ],
    ]

    manual_has_file = bool(
        str(
            manual_image_file_id
            or ""
        ).strip()
    )

    review_rows.append(
        [
            {
                "text": (
                    "🖼 تصویر اصلی ✅"
                    if (
                        manual_image_source
                        == MANUAL_IMAGE_SOURCE_PRIMARY
                    )
                    else "🖼 تصویر اصلی"
                ),
                "callback_data": (
                    "extrev:manual:"
                    f"{review_id}:primary"
                ),
            },
            {
                "text": (
                    "🚫 بدون تصویر ✅"
                    if (
                        manual_image_source
                        == MANUAL_IMAGE_SOURCE_NONE
                    )
                    else "🚫 بدون تصویر"
                ),
                "callback_data": (
                    "extrev:manual:"
                    f"{review_id}:none"
                ),
            },
        ]
    )

    # =====================================================
    # SINGLE MANUAL ADD/REPLACE BUTTON
    #
    # One dynamic button replaces the previous two-button manual
    # image flow (separate "waiting" + "replace" buttons):
    #   - no manual image yet, not waiting -> "add" (starts waiting)
    #   - waiting for the next photo -> "cancel waiting"
    #   - manual image captured and active -> "replace" (re-enters
    #     waiting to capture a new photo)
    #   - manual image captured but not currently active -> "restore"
    #     (reactivates the previously captured photo without a new
    #     upload)
    # =====================================================

    if manual_image_waiting:
        manual_button = {
            "text": "⏳ لغو انتظار عکس",
            "callback_data": (
                "extrev:manual:"
                f"{review_id}:cancel"
            ),
        }

    elif (
        manual_has_file
        and manual_image_source
        == MANUAL_IMAGE_SOURCE_REPLACE
    ):
        manual_button = {
            "text": "🔁 تصویر دستی ✅",
            "callback_data": (
                "extrev:manual:"
                f"{review_id}:waiting"
            ),
        }

    elif manual_has_file:
        manual_button = {
            "text": "🔁 بازگرداندن تصویر دستی",
            "callback_data": (
                "extrev:manual:"
                f"{review_id}:replace"
            ),
        }

    else:
        manual_button = {
            "text": "➕ افزودن تصویر دستی",
            "callback_data": (
                "extrev:manual:"
                f"{review_id}:waiting"
            ),
        }

    review_rows.append(
        [
            manual_button,
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
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
    manual_image_waiting: bool = False,
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
            manual_image_source=(
                manual_image_source
            ),
            manual_image_file_id=(
                manual_image_file_id
            ),
            manual_image_waiting=(
                manual_image_waiting
            ),
        )
    )

    if selection_status:
        metadata_parts.append(
            selection_status
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
            manual_image_source=(
                manual_image_source
            ),
            manual_image_file_id=(
                manual_image_file_id
            ),
            manual_image_waiting=(
                manual_image_waiting
            ),
        )
    )

    selected_media, media_file_ids = _selected_media(
        content,
        selected_media_indexes=(
            selected_media_indexes
        ),
        media_selection_explicit=(
            media_selection_explicit
        ),
        manual_image_source=(
            manual_image_source
        ),
        manual_image_file_id=(
            manual_image_file_id
        ),
    )

    return ExternalReviewPreviewView(
        review_id=review_id,
        text=text,
        reply_markup=reply_markup,
        media=selected_media,
        media_file_ids=media_file_ids,
    )


# =========================================================
# SHORT / PARAGRAPHS DRAFT PREVIEW (approve / edit / cancel)
#
# Both SHORT (caption-safe Smart Summary) and PARAGRAPHS (paginated,
# persistent true multi-select) route through this shared draft
# preview surface once a draft body has been assembled. Nothing is
# published while a draft is shown; the user must explicitly approve.
# =========================================================


PARAGRAPH_PAGE_SIZE = 6


def _draft_heading_and_metadata(
    preview: ExternalContentPreview,
    *,
    heading: str,
    awaiting_edit_text: bool,
) -> Tuple[str, str]:
    metadata_parts = []

    if preview.title:
        metadata_parts.append(
            "تیتر اصلی: "
            f"{preview.title}"
        )

    if preview.source_name:
        metadata_parts.append(
            "منبع: "
            f"{preview.source_name}"
        )

    if awaiting_edit_text:
        metadata_parts.append(
            "⏳ منتظر متن جایگزین شما هستم."
        )

    metadata_text = "\n".join(
        part
        for part in metadata_parts
        if part
    ).strip()

    return heading, metadata_text


def build_external_review_short_keyboard(
    *,
    review_id: str,
    awaiting_edit_text: bool = False,
) -> dict:
    """
    Approve / edit / regenerate / cancel keyboard for a SHORT draft.

    Nothing publishes until "approve" is pressed explicitly.
    """

    rows = [
        [
            {
                "text": "✅ تأیید و انتشار",
                "callback_data": (
                    "extrev:short_approve:"
                    f"{review_id}"
                ),
            },
        ],
        [
            {
                "text": (
                    "⏳ منتظر متن شما ..."
                    if awaiting_edit_text
                    else "✍️ ویرایش متن"
                ),
                "callback_data": (
                    "extrev:short_edit:"
                    f"{review_id}"
                ),
            },
            {
                "text": "🔄 بازتولید",
                "callback_data": (
                    "extrev:short_regenerate:"
                    f"{review_id}"
                ),
            },
        ],
        [
            {
                "text": "❌ لغو",
                "callback_data": (
                    "extrev:cancel:"
                    f"{review_id}"
                ),
            },
        ],
    ]

    return {
        "inline_keyboard": rows
    }


def build_external_review_short_preview(
    *,
    review_id: str,
    content: NormalizedExternalContent,
    preview: ExternalContentPreview,
    draft_text: str,
    awaiting_edit_text: bool = False,
    selected_media_indexes: Tuple[int, ...] = (),
    media_selection_explicit: bool = False,
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
) -> ExternalReviewPreviewView:
    """
    Render the SHORT caption-safe draft awaiting explicit approval.

    Shows the original headline and source alongside the generated
    draft so the admin can verify faithfulness before approving.
    Nothing is published until "approve" is pressed.
    """

    heading, metadata_text = (
        _draft_heading_and_metadata(
            preview,
            heading="✂️ پیش‌نمایش نسخه کوتاه (تأیید نشده)",
            awaiting_edit_text=(
                awaiting_edit_text
            ),
        )
    )

    body_text = str(
        draft_text
        or ""
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
        build_external_review_short_keyboard(
            review_id=review_id,
            awaiting_edit_text=(
                awaiting_edit_text
            ),
        )
    )

    selected_media, media_file_ids = _selected_media(
        content,
        selected_media_indexes=(
            selected_media_indexes
        ),
        media_selection_explicit=(
            media_selection_explicit
        ),
        manual_image_source=(
            manual_image_source
        ),
        manual_image_file_id=(
            manual_image_file_id
        ),
    )

    return ExternalReviewPreviewView(
        review_id=review_id,
        text=text,
        reply_markup=reply_markup,
        media=selected_media,
        media_file_ids=media_file_ids,
    )


# =========================================================
# PARAGRAPH SELECTION (paginated, persistent, true multi-select)
# =========================================================


def build_external_review_paragraph_select_keyboard(
    *,
    review_id: str,
    paragraph_count: int,
    paragraph_page: int,
    paragraph_selected_indexes: Tuple[int, ...],
    page_size: int = PARAGRAPH_PAGE_SIZE,
) -> dict:
    """
    Paginated, persistent, true multi-select paragraph keyboard.

    Selections persist across page changes (they are stored on the
    pending review, not on the rendered keyboard). Confirming with no
    paragraph selected is blocked by the caller.
    """

    page_count = max(
        1,
        (
            paragraph_count
            + page_size
            - 1
        )
        // page_size,
    )

    normalized_page = max(
        0,
        min(
            paragraph_page,
            page_count - 1,
        ),
    )

    selected_set = set(
        paragraph_selected_indexes
        or ()
    )

    start = normalized_page * page_size
    end = min(
        start + page_size,
        paragraph_count,
    )

    rows = []

    for index in range(start, end):
        checked = (
            index in selected_set
        )

        rows.append(
            [
                {
                    "text": (
                        f"{'✅' if checked else '⬜'} "
                        f"پاراگراف {index + 1}"
                    ),
                    "callback_data": (
                        "extrev:para_toggle:"
                        f"{review_id}:{index}"
                    ),
                },
            ]
        )

    if page_count > 1:
        pagination_row = []

        if normalized_page > 0:
            pagination_row.append(
                {
                    "text": "◀ قبلی",
                    "callback_data": (
                        "extrev:para_page:"
                        f"{review_id}:"
                        f"{normalized_page - 1}"
                    ),
                }
            )

        pagination_row.append(
            {
                "text": (
                    f"صفحه {normalized_page + 1}"
                    f"/{page_count}"
                ),
                "callback_data": (
                    "extrev:para_page:"
                    f"{review_id}:"
                    f"{normalized_page}"
                ),
            }
        )

        if normalized_page < page_count - 1:
            pagination_row.append(
                {
                    "text": "بعدی ▶",
                    "callback_data": (
                        "extrev:para_page:"
                        f"{review_id}:"
                        f"{normalized_page + 1}"
                    ),
                }
            )

        rows.append(
            pagination_row
        )

    rows.append(
        [
            {
                "text": (
                    "✅ تأیید انتخاب "
                    f"({len(selected_set)})"
                ),
                "callback_data": (
                    "extrev:para_confirm:"
                    f"{review_id}"
                ),
            },
        ]
    )

    rows.append(
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
        "inline_keyboard": rows
    }


def build_external_review_paragraph_select_view(
    *,
    review_id: str,
    content: NormalizedExternalContent,
    preview: ExternalContentPreview,
    paragraph_page: int = 0,
    paragraph_selected_indexes: Tuple[int, ...] = (),
    selected_media_indexes: Tuple[int, ...] = (),
    media_selection_explicit: bool = False,
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
    page_size: int = PARAGRAPH_PAGE_SIZE,
) -> ExternalReviewPreviewView:
    """
    Render the paginated, persistent, true multi-select paragraph
    picker. Nothing is published from this surface; confirming with
    at least one paragraph selected moves to the draft preview.
    """

    paragraphs = preview.paragraphs

    page_count = max(
        1,
        (
            len(paragraphs)
            + page_size
            - 1
        )
        // page_size,
    )

    normalized_page = max(
        0,
        min(
            paragraph_page,
            page_count - 1,
        ),
    )

    start = normalized_page * page_size
    end = min(
        start + page_size,
        len(paragraphs),
    )

    heading = (
        "📄 انتخاب پاراگراف‌ها "
        f"(صفحه {normalized_page + 1}"
        f"/{page_count})"
    )

    numbered_paragraphs = "\n\n".join(
        f"{index + 1}. {paragraphs[index]}"
        for index in range(start, end)
    )

    metadata_parts = []

    if preview.title:
        metadata_parts.append(
            "تیتر اصلی: "
            f"{preview.title}"
        )

    if preview.source_name:
        metadata_parts.append(
            "منبع: "
            f"{preview.source_name}"
        )

    if not paragraph_selected_indexes:
        metadata_parts.append(
            "حداقل یک پاراگراف را انتخاب کنید."
        )

    metadata_text = "\n".join(
        metadata_parts
    ).strip()

    text_parts = [heading]

    if numbered_paragraphs:
        text_parts.append(
            numbered_paragraphs
        )

    if metadata_text:
        text_parts.append(
            metadata_text
        )

    text = "\n\n".join(
        text_parts
    ).strip()

    reply_markup = (
        build_external_review_paragraph_select_keyboard(
            review_id=review_id,
            paragraph_count=len(
                paragraphs
            ),
            paragraph_page=(
                normalized_page
            ),
            paragraph_selected_indexes=(
                paragraph_selected_indexes
            ),
            page_size=page_size,
        )
    )

    selected_media, media_file_ids = _selected_media(
        content,
        selected_media_indexes=(
            selected_media_indexes
        ),
        media_selection_explicit=(
            media_selection_explicit
        ),
        manual_image_source=(
            manual_image_source
        ),
        manual_image_file_id=(
            manual_image_file_id
        ),
    )

    return ExternalReviewPreviewView(
        review_id=review_id,
        text=text,
        reply_markup=reply_markup,
        media=selected_media,
        media_file_ids=media_file_ids,
    )


def build_external_review_paragraph_keyboard(
    *,
    review_id: str,
    awaiting_edit_text: bool = False,
) -> dict:
    """
    Approve / edit / cancel keyboard for a PARAGRAPHS draft.

    No regenerate button: paragraph selection is deterministic, not
    AI-generated.
    """

    rows = [
        [
            {
                "text": "✅ تأیید و انتشار",
                "callback_data": (
                    "extrev:para_approve:"
                    f"{review_id}"
                ),
            },
        ],
        [
            {
                "text": (
                    "⏳ منتظر متن شما ..."
                    if awaiting_edit_text
                    else "✍️ ویرایش متن"
                ),
                "callback_data": (
                    "extrev:para_edit:"
                    f"{review_id}"
                ),
            },
        ],
        [
            {
                "text": "❌ لغو",
                "callback_data": (
                    "extrev:cancel:"
                    f"{review_id}"
                ),
            },
        ],
    ]

    return {
        "inline_keyboard": rows
    }


def build_external_review_paragraph_preview(
    *,
    review_id: str,
    content: NormalizedExternalContent,
    preview: ExternalContentPreview,
    draft_text: str,
    awaiting_edit_text: bool = False,
    selected_media_indexes: Tuple[int, ...] = (),
    media_selection_explicit: bool = False,
    manual_image_source: str = (
        MANUAL_IMAGE_SOURCE_PRIMARY
    ),
    manual_image_file_id: str = "",
) -> ExternalReviewPreviewView:
    """
    Render the assembled PARAGRAPHS draft (original headline plus the
    selected paragraphs, in source order) awaiting explicit approval.
    """

    heading, metadata_text = (
        _draft_heading_and_metadata(
            preview,
            heading=(
                "📄 پیش‌نمایش پاراگراف‌های "
                "انتخابی (تأیید نشده)"
            ),
            awaiting_edit_text=(
                awaiting_edit_text
            ),
        )
    )

    body_text = str(
        draft_text
        or ""
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
        build_external_review_paragraph_keyboard(
            review_id=review_id,
            awaiting_edit_text=(
                awaiting_edit_text
            ),
        )
    )

    selected_media, media_file_ids = _selected_media(
        content,
        selected_media_indexes=(
            selected_media_indexes
        ),
        media_selection_explicit=(
            media_selection_explicit
        ),
        manual_image_source=(
            manual_image_source
        ),
        manual_image_file_id=(
            manual_image_file_id
        ),
    )

    return ExternalReviewPreviewView(
        review_id=review_id,
        text=text,
        reply_markup=reply_markup,
        media=selected_media,
        media_file_ids=media_file_ids,
    )

