"""Callback contract for external-content review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Optional,
    Tuple,
)

from core.external_content_review import (
    ExternalMediaMode,
    ExternalReviewMode,
    ExternalReviewSelection,
)
from core.external_review_controller import (
    DEFAULT_EXTERNAL_REVIEW_CONTROLLER,
    ExternalReviewController,
    ExternalReviewDecision,
)
from core.external_review_state import (
    PendingExternalReview,
)


# =========================================================
# CALLBACK PREFIX
# =========================================================


EXTERNAL_REVIEW_CALLBACK_PREFIX = "extrev:"


# =========================================================
# ERRORS
# =========================================================


class ExternalReviewCallbackError(
    ValueError
):
    """Raised when external-review callback data is invalid."""


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True)
class ExternalReviewCallbackResult:
    """
    Platform-neutral result of one external-review callback.

    A handled callback can:

      - update persistent review UI state
      - produce a publication/rewrite decision
      - cancel a pending review

    Media-selection callbacks are intentionally non-terminal.
    They must never publish by themselves.
    """

    handled: bool

    action: str = ""
    review_id: str = ""

    decision: Optional[
        ExternalReviewDecision
    ] = None

    cancelled: Optional[
        PendingExternalReview
    ] = None

    pending: Optional[
        PendingExternalReview
    ] = None

    message: str = ""

    @property
    def completed(
        self,
    ) -> bool:
        return bool(
            self.decision
            is not None
            or self.cancelled
            is not None
        )

    @property
    def state_updated(
        self,
    ) -> bool:
        return bool(
            self.pending
            is not None
            and self.decision
            is None
            and self.cancelled
            is None
        )


# =========================================================
# PARSING
# =========================================================


def _split_callback_data(
    callback_data: str,
) -> Tuple[str, ...]:
    value = str(
        callback_data
        or ""
    ).strip()

    if not value.startswith(
        EXTERNAL_REVIEW_CALLBACK_PREFIX
    ):
        return ()

    parts = tuple(
        item.strip()
        for item
        in value.split(":")
    )

    if len(parts) < 3:
        raise ExternalReviewCallbackError(
            "invalid external review callback"
        )

    return parts


def _parse_indexes(
    value: str,
) -> Tuple[int, ...]:
    normalized = str(
        value
        or ""
    ).strip()

    if not normalized:
        raise ExternalReviewCallbackError(
            "callback selection indexes are required"
        )

    result = []

    for part in normalized.split(","):
        item = part.strip()

        if not item:
            raise ExternalReviewCallbackError(
                "callback contains an empty index"
            )

        try:
            index = int(
                item
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalReviewCallbackError(
                "callback selection index is invalid"
            ) from exc

        if index < 0:
            raise ExternalReviewCallbackError(
                "callback selection index must be >= 0"
            )

        result.append(
            index
        )

    if len(
        set(result)
    ) != len(result):
        raise ExternalReviewCallbackError(
            "callback selection indexes must be unique"
        )

    return tuple(
        result
    )


# =========================================================
# MEDIA STATE
# =========================================================


def _toggle_media_selection(
    *,
    pending: PendingExternalReview,
    requested_indexes: Tuple[
        int,
        ...,
    ],
) -> Tuple[int, ...]:
    """
    Toggle one or more media indexes.

    Default state means all source media are available for publication.

    The first explicit media button starts a custom selection using
    exactly the requested media indexes.

    Further media buttons toggle items into/out of that custom set.
    """

    media_count = len(
        pending.content.media
    )

    if any(
        index >= media_count
        for index in requested_indexes
    ):
        raise ExternalReviewCallbackError(
            "callback media index is out of range"
        )

    if not pending.media_selection_explicit:
        return tuple(
            requested_indexes
        )

    current = list(
        pending.selected_media_indexes
    )

    for index in requested_indexes:
        if index in current:
            current.remove(
                index
            )

        else:
            current.append(
                index
            )

    return tuple(
        sorted(
            current
        )
    )


def _media_selection_for_final_action(
    pending: PendingExternalReview,
) -> Tuple[
    ExternalMediaMode,
    Tuple[int, ...],
]:
    """
    Resolve persistent media UI state for a terminal content action.

    No explicit selection:
        use DEFAULT, which keeps all extracted media.

    Explicit empty selection:
        NONE.

    Explicit indexes:
        SELECTED.
    """

    if not pending.media_selection_explicit:
        return (
            ExternalMediaMode.DEFAULT,
            (),
        )

    if not pending.selected_media_indexes:
        return (
            ExternalMediaMode.NONE,
            (),
        )

    return (
        ExternalMediaMode.SELECTED,
        tuple(
            pending.selected_media_indexes
        ),
    )


# =========================================================
# FINAL SELECTION
# =========================================================


def _build_final_selection(
    *,
    action: str,
    argument: str,
    pending: PendingExternalReview,
) -> ExternalReviewSelection:
    normalized_action = str(
        action
        or ""
    ).strip().lower()

    (
        media_mode,
        media_indexes,
    ) = _media_selection_for_final_action(
        pending
    )

    if normalized_action == "standard":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode.STANDARD
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    if normalized_action == "headline":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_ONLY
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    if normalized_action == "lead":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_LEAD
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    if normalized_action == "short":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode.SHORT
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    if normalized_action == "editorial":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .EDITORIAL_REWRITE
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    if normalized_action == "paragraphs":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .PARAGRAPHS
            ),
            paragraph_indexes=(
                _parse_indexes(
                    argument
                )
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

    raise ExternalReviewCallbackError(
        (
            "unsupported external review "
            f"callback action: {normalized_action}"
        )
    )


# =========================================================
# PUBLIC HANDLER
# =========================================================


def handle_external_review_callback(
    *,
    callback_data: str,
    chat_id: int,
    controller: Optional[
        ExternalReviewController
    ] = None,
) -> ExternalReviewCallbackResult:
    """
    Handle one external-content review callback.

    Callback format:

        extrev:<action>:<review_id>

    Optional selection argument:

        extrev:paragraphs:<review_id>:0,2
        extrev:media:<review_id>:0
        extrev:media:<review_id>:0,1

    Important:

        media
        nomedia

    are state-only actions.

    They DO NOT create a publication decision and DO NOT consume
    pending review state.

    Final actions:

        standard
        headline
        lead
        short
        editorial
        paragraphs

    inherit the currently persisted media selection.
    """

    parts = _split_callback_data(
        callback_data
    )

    if not parts:
        return ExternalReviewCallbackResult(
            handled=False,
        )

    action = str(
        parts[1]
        or ""
    ).strip().lower()

    review_id = str(
        parts[2]
        or ""
    ).strip()

    if not review_id:
        raise ExternalReviewCallbackError(
            "review_id is required"
        )

    argument = (
        parts[3]
        if len(parts) >= 4
        else ""
    )

    resolved_controller = (
        controller
        if controller is not None
        else DEFAULT_EXTERNAL_REVIEW_CONTROLLER
    )

    # =====================================================
    # CANCEL
    # =====================================================

    if action == "cancel":
        cancelled = (
            resolved_controller.cancel(
                review_id=review_id,
                chat_id=chat_id,
            )
        )

        return ExternalReviewCallbackResult(
            handled=True,
            action=action,
            review_id=review_id,
            cancelled=cancelled,
            message=(
                "بررسی این مطلب لغو شد."
            ),
        )

    # =====================================================
    # MEDIA SELECTION — STATE ONLY
    # =====================================================

    if action == "media":
        requested_indexes = (
            _parse_indexes(
                argument
            )
        )

        pending = (
            resolved_controller.get_pending(
                review_id=review_id,
                chat_id=chat_id,
            )
        )

        selected_indexes = (
            _toggle_media_selection(
                pending=pending,
                requested_indexes=(
                    requested_indexes
                ),
            )
        )

        updated = (
            resolved_controller
            .state_store
            .update_media_selection(
                review_id=review_id,
                chat_id=chat_id,
                selected_media_indexes=(
                    selected_indexes
                ),
                explicit=True,
            )
        )

        if updated.selected_media_indexes:
            human_indexes = ", ".join(
                str(index + 1)
                for index
                in updated.selected_media_indexes
            )

            message = (
                "تصاویر آلبوم انتشار: "
                f"{human_indexes}"
            )

        else:
            message = (
                "هیچ تصویری انتخاب نشده است."
            )

        return ExternalReviewCallbackResult(
            handled=True,
            action=action,
            review_id=review_id,
            pending=updated,
            message=message,
        )

    # =====================================================
    # NO MEDIA — STATE ONLY
    # =====================================================

    if action == "nomedia":
        updated = (
            resolved_controller
            .state_store
            .update_media_selection(
                review_id=review_id,
                chat_id=chat_id,
                selected_media_indexes=(),
                explicit=True,
            )
        )

        return ExternalReviewCallbackResult(
            handled=True,
            action=action,
            review_id=review_id,
            pending=updated,
            message=(
                "انتشار بدون تصویر انتخاب شد."
            ),
        )

    # =====================================================
    # FINAL CONTENT ACTION
    # =====================================================

    pending = (
        resolved_controller.get_pending(
            review_id=review_id,
            chat_id=chat_id,
        )
    )

    selection = (
        _build_final_selection(
            action=action,
            argument=argument,
            pending=pending,
        )
    )

    decision = (
        resolved_controller.apply_selection(
            review_id=review_id,
            chat_id=chat_id,
            selection=selection,
        )
    )

    return ExternalReviewCallbackResult(
        handled=True,
        action=action,
        review_id=review_id,
        decision=decision,
        message=(
            "انتخاب مطلب ثبت شد."
        ),
    )
