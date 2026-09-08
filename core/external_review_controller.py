"""Controller joining pending external reviews with review selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Mapping,
    Optional,
    Tuple,
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
    ExternalReviewStateStore,
    MANUAL_IMAGE_SOURCE_NONE,
    MANUAL_IMAGE_SOURCE_REPLACE,
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
    Deterministic decision for one pending external review.

    The controller does not publish anything. The caller may pass
    `content` and `review` to the existing external publication service.
    """

    review_id: str
    chat_id: int
    content: NormalizedExternalContent
    review: ExternalReviewResult

    media_presentation_mode: str = "normal"
    prepared_files: Tuple[
        Mapping[str, Any],
        ...,
    ] = ()

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
      - consume state only after successful execution

    It deliberately does NOT:

      - publish
      - send Telegram/Bale messages
      - summarize
      - perform Editorial AI work
      - translate

    Important lifecycle rule:

      applying a valid selection MUST NOT remove pending state.

    The execution layer may still fail after the selection has been
    validated, for example because Smart Summary, Editorial processing,
    media acquisition, or publication fails.

    Pending state is therefore consumed explicitly only after successful
    execution by calling `consume_after_success`.
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

        Pending state is intentionally preserved here.

        A valid selection only creates a deterministic decision.

        Execution may still fail later, so consuming state at this
        point would make the preview unusable after a recoverable
        publication or transformation failure.
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

        prepared_files: Tuple[
            Mapping[str, Any],
            ...,
        ] = ()

        if (
            pending.manual_image_source
            == MANUAL_IMAGE_SOURCE_NONE
        ):
            review = ExternalReviewResult(
                title=review.title,
                lead=review.lead,
                body=review.body,
                media=(),
                selected_paragraph_indexes=(
                    review.selected_paragraph_indexes
                ),
                selected_media_indexes=(),
                requires_smart_summary=(
                    review.requires_smart_summary
                ),
                requires_editorial_rewrite=(
                    review.requires_editorial_rewrite
                ),
            )

        elif (
            pending.manual_image_source
            == MANUAL_IMAGE_SOURCE_REPLACE
            and pending.manual_image_file_id
        ):
            prepared_files = (
                {
                    "type": "photo",
                    "file_id": (
                        pending.manual_image_file_id
                    ),
                },
            )
            review = ExternalReviewResult(
                title=review.title,
                lead=review.lead,
                body=review.body,
                media=(),
                selected_paragraph_indexes=(
                    review.selected_paragraph_indexes
                ),
                selected_media_indexes=(),
                requires_smart_summary=(
                    review.requires_smart_summary
                ),
                requires_editorial_rewrite=(
                    review.requires_editorial_rewrite
                ),
            )

        return ExternalReviewDecision(
            review_id=pending.review_id,
            chat_id=pending.chat_id,
            content=content,
            review=review,
            media_presentation_mode=(
                pending.media_presentation_mode
            ),
            prepared_files=prepared_files,
        )

    # -----------------------------------------------------
    # SUCCESSFUL EXECUTION CONSUMPTION
    # -----------------------------------------------------

    def consume_after_success(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        """
        Remove pending state after successful execution.

        Ownership is revalidated by the state store before removal.

        This method must be called only after the external review
        decision has completed its required transformation/publication
        successfully.
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

        Cancellation intentionally consumes the pending state because
        it is an explicit terminal action by the user.

        Ownership is checked before state removal.
        """

        return self.state_store.pop(
            review_id=review_id,
            chat_id=chat_id,
        )


DEFAULT_EXTERNAL_REVIEW_CONTROLLER = (
    ExternalReviewController()
)
