"""Controller joining pending external reviews with review selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Optional,
)

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

    The controller does not publish anything.

    IMPORTANT:
    A valid selection does not mean publication succeeded.
    Pending state therefore remains available until the caller
    explicitly confirms successful execution.
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
      - explicitly consume state after successful execution

    It deliberately does NOT:
      - publish
      - send Telegram/Bale messages
      - summarize
      - perform Editorial AI work
      - translate

    State lifecycle:

        create_pending
              ↓
        apply_selection
              ↓
        decision returned
              ↓
        publication/execution
              ↓
        consume_after_success

    If execution fails, pending state remains available.
    """

    def __init__(
        self,
        *,
        state_store: Optional[
            Any
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

        IMPORTANT:

        Pending state is NOT removed here.

        A valid review selection can still fail later because of:

          - Smart Summary
          - Editorial processing
          - media acquisition/materialization
          - Shared Publication Engine
          - Telegram/Bale delivery
          - network errors

        Therefore selection and successful execution are separate
        lifecycle steps.
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
                (
                    "pending external review "
                    "content is unavailable"
                )
            )

        review = (
            apply_external_review_selection(
                content,
                selection,
            )
        )

        # =================================================
        # DO NOT POP HERE
        # =================================================
        #
        # Previously this method removed the pending record
        # immediately after validating the user's selection.
        #
        # That caused the review to disappear even when the
        # following execution failed.
        #
        # Example observed in real staging:
        #
        #   callback
        #       ↓
        #   selection valid
        #       ↓
        #   DELETE external_review_state
        #       ↓
        #   Smart Summary failed
        #       ↓
        #   preview permanently lost
        #
        # The record must survive until execution succeeds.
        # =================================================

        return ExternalReviewDecision(
            review_id=pending.review_id,
            chat_id=pending.chat_id,
            content=pending.content,
            review=review,
        )

    # -----------------------------------------------------
    # SUCCESSFUL EXECUTION
    # -----------------------------------------------------

    def consume_after_success(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        """
        Consume a pending review only after the caller has confirmed
        that review execution/publication completed successfully.

        This explicit method keeps state lifecycle independent from
        selection validation.
        """

        return self.state_store.pop(
            review_id=review_id,
            chat_id=chat_id,
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

        Cancellation is intentionally destructive because it is an
        explicit user decision.

        Ownership is checked before state removal.
        """

        return self.state_store.pop(
            review_id=review_id,
            chat_id=chat_id,
        )


# =========================================================
# DEFAULT CONTROLLER
# =========================================================


DEFAULT_EXTERNAL_REVIEW_CONTROLLER = (
    ExternalReviewController()
)
