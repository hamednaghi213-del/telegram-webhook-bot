"""Controller joining pending external reviews with review selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalContentPreview,
    ExternalReviewResult,
    ExternalReviewSelection,
    apply_external_review_selection,
    build_external_content_preview,
)
from core.external_review_state import (
    DEFAULT_EXTERNAL_REVIEW_STATE_STORE,
    ExternalReviewStateStore,
    PendingExternalReview,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalReviewControllerError(
    RuntimeError
):
    """Base error for external review controller."""


class ExternalReviewContentUnavailable(
    ExternalReviewControllerError
):
    """Raised when a pending review has no usable content."""


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True)
class ExternalReviewDecision:
    """
    Final deterministic decision for one pending external review.

    The controller does not publish anything. The caller may pass
    `content` and `review` to the existing external publication service.
    """

    review_id: str
    chat_id: int
    content: NormalizedExternalContent
    review: ExternalReviewResult

    @property
    def requires_smart_summary(
        self,
    ) -> bool:
        return bool(
            self.review.requires_smart_summary
        )

    @property
    def requires_editorial_rewrite(
        self,
    ) -> bool:
        return bool(
            self.review.requires_editorial_rewrite
        )


# =========================================================
# CONTROLLER
# =========================================================


class ExternalReviewController:
    """
    Platform-neutral controller for pending external-content review.

    Responsibilities:
      - create pending review state
      - expose preview data
      - apply deterministic user selection
      - cancel pending review
      - consume state only after a valid selection

    It deliberately does NOT:
      - publish
      - send Telegram/Bale messages
      - summarize
      - perform Editorial AI work
      - translate
    """

    def __init__(
        self,
        *,
        state_store: Optional[
            ExternalReviewStateStore
        ] = None,
    ) -> None:
        self.state_store = (
            DEFAULT_EXTERNAL_REVIEW_STATE_STORE
            if state_store is None
            else state_store
        )

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    def create_pending(
        self,
        *,
        review_id: str,
        chat_id: int,
        content: NormalizedExternalContent,
        replace_existing: bool = False,
    ) -> PendingExternalReview:
        return self.state_store.create(
            review_id=review_id,
            chat_id=chat_id,
            content=content,
            replace_existing=replace_existing,
        )

    # -----------------------------------------------------
    # READ / PREVIEW
    # -----------------------------------------------------

    def get_pending(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        return self.state_store.require(
            review_id=review_id,
            chat_id=chat_id,
        )

    def get_preview(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> ExternalContentPreview:
        pending = self.get_pending(
            review_id=review_id,
            chat_id=chat_id,
        )

        return build_external_content_preview(
            pending.content
        )

    # -----------------------------------------------------
    # DECISION
    # -----------------------------------------------------

    def apply_selection(
        self,
        *,
        review_id: str,
        chat_id: int,
        selection: Optional[
            ExternalReviewSelection
        ] = None,
    ) -> ExternalReviewDecision:
        """
        Validate and apply a review selection.

        Important:
        pending state is removed only AFTER selection validation succeeds.
        Invalid paragraph/media indexes therefore cannot destroy the
        user's pending review.
        """

        pending = self.get_pending(
            review_id=review_id,
            chat_id=chat_id,
        )

        content = pending.content

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise ExternalReviewContentUnavailable(
                "pending external review content is unavailable"
            )

        review = (
            apply_external_review_selection(
                content,
                selection,
            )
        )

        # Consume only after the selection has been successfully applied.
        consumed = self.state_store.pop(
            review_id=review_id,
            chat_id=chat_id,
        )

        return ExternalReviewDecision(
            review_id=consumed.review_id,
            chat_id=consumed.chat_id,
            content=consumed.content,
            review=review,
        )

    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    def cancel(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        """
        Explicitly cancel one owned pending review.

        Ownership is checked before state removal.
        """

        return self.state_store.pop(
            review_id=review_id,
            chat_id=chat_id,
        )


DEFAULT_EXTERNAL_REVIEW_CONTROLLER = (
    ExternalReviewController()
)
