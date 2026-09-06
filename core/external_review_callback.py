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

    `handled=False` means the callback belongs to another feature.

    A handled callback can either:
      - produce a review decision
      - cancel a pending review
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
# SELECTION
# =========================================================


def _build_selection(
    *,
    action: str,
    argument: str = "",
) -> ExternalReviewSelection:
    normalized_action = str(
        action
        or ""
    ).strip().lower()

    if normalized_action == "standard":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode.STANDARD
            ),
        )

    if normalized_action == "headline":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_ONLY
            ),
        )

    if normalized_action == "lead":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_LEAD
            ),
        )

    if normalized_action == "short":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode.SHORT
            ),
        )

    if normalized_action == "editorial":
        return ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .EDITORIAL_REWRITE
            ),
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
        )

    if normalized_action == "nomedia":
        return ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.NONE
            ),
        )

    if normalized_action == "media":
        return ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode
                .SELECTED
            ),
            media_indexes=(
                _parse_indexes(
                    argument
                )
            ),
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
        extrev:media:<review_id>:0,1

    Supported actions:

        standard
        headline
        lead
        short
        editorial
        paragraphs
        nomedia
        media
        cancel

    This function:
      - does not send Telegram/Bale messages
      - does not publish
      - does not summarize
      - does not run Editorial AI
      - does not translate
    """

    parts = _split_callback_data(
        callback_data
    )

    if not parts:
        return ExternalReviewCallbackResult(
            handled=False,
        )

    action = parts[1].lower()

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

    selection = _build_selection(
        action=action,
        argument=argument,
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
