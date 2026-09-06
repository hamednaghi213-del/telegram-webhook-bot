"""Execution boundary for approved external-content review decisions."""

from __future__ import annotations

from dataclasses import (
    dataclass,
    replace,
)
from typing import (
    Optional,
)

from core.external_media_factory import (
    build_external_media_materializer,
)
from core.external_media_materializer import (
    ExternalMediaMaterializer,
)
from core.external_publication_service import (
    ExternalPublicationResult,
    publish_reviewed_external_content,
)
from core.external_review_controller import (
    ExternalReviewDecision,
)
from core.smart_summarizer import (
    DEFAULT_TEXT_TARGET,
    summarize_text_safely,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalReviewExecutionError(
    RuntimeError
):
    """Base error for executing an approved external review."""


# =========================================================
# STATUS
# =========================================================


STATUS_PUBLISHED = "published"

STATUS_SMART_SUMMARY_REQUIRED = (
    "smart_summary_required"
)

STATUS_EDITORIAL_REQUIRED = (
    "editorial_required"
)


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True)
class ExternalReviewExecutionResult:
    """
    Result of executing one approved external-review decision.

    Standard and SHORT decisions may be published through the existing
    shared publication path.

    EDITORIAL_REWRITE remains fail-closed until it is handed to the
    existing shared Editorial workflow.
    """

    status: str

    decision: ExternalReviewDecision

    publication: Optional[
        ExternalPublicationResult
    ] = None

    @property
    def published(
        self,
    ) -> bool:
        return bool(
            self.status
            == STATUS_PUBLISHED
            and self.publication is not None
            and self.publication.ok
        )

    @property
    def requires_smart_summary(
        self,
    ) -> bool:
        return (
            self.status
            == STATUS_SMART_SUMMARY_REQUIRED
        )

    @property
    def requires_editorial_rewrite(
        self,
    ) -> bool:
        return (
            self.status
            == STATUS_EDITORIAL_REQUIRED
        )


# =========================================================
# REVIEW TEXT
# =========================================================


def _review_text(
    decision: ExternalReviewDecision,
) -> str:
    """
    Build the neutral text selected by the user.

    This text is used only as input to the existing Smart Summary.
    """

    parts = []

    review = decision.review

    if review.title:
        parts.append(
            str(
                review.title
            ).strip()
        )

    if review.lead:
        parts.append(
            str(
                review.lead
            ).strip()
        )

    if review.body:
        parts.append(
            str(
                review.body
            ).strip()
        )

    return "\n\n".join(
        part
        for part in parts
        if part
    ).strip()


# =========================================================
# SMART SUMMARY
# =========================================================


def _apply_shared_smart_summary(
    decision: ExternalReviewDecision,
) -> ExternalReviewDecision:
    """
    Apply the project's existing Smart Summary to a SHORT decision.

    Fail closed:
    if the shared summarizer cannot produce a validated summary,
    nothing is published.
    """

    original_text = (
        _review_text(
            decision
        )
    )

    if not original_text:
        raise ExternalReviewExecutionError(
            "external review has no text to summarize"
        )

    try:
        outcome = (
            summarize_text_safely(
                original_text=original_text,
                target_length=DEFAULT_TEXT_TARGET,
            )
        )

    except Exception as exc:
        raise ExternalReviewExecutionError(
            "shared smart summary failed"
        ) from exc

    summary_text = str(
        getattr(
            outcome,
            "summary_text",
            "",
        )
        or ""
    ).strip()

    success = bool(
        getattr(
            outcome,
            "success",
            False,
        )
    )

    validation_passed = bool(
        getattr(
            outcome,
            "validation_passed",
            False,
        )
    )

    if (
        not success
        or not validation_passed
        or not summary_text
    ):
        raise ExternalReviewExecutionError(
            "shared smart summary did not produce a valid result"
        )

    summarized_review = replace(
        decision.review,
        title="",
        lead="",
        body=summary_text,
        requires_smart_summary=False,
    )

    return replace(
        decision,
        review=summarized_review,
    )


# =========================================================
# PUBLICATION
# =========================================================


def _publish_decision(
    *,
    decision: ExternalReviewDecision,
    api_url: str,
    materializer: Optional[
        ExternalMediaMaterializer
    ],
    smart_summary_applied: bool = False,
) -> ExternalReviewExecutionResult:

    resolved_materializer = (
        materializer
    )

    if (
        decision.review.media
        and resolved_materializer is None
    ):
        resolved_materializer = (
            build_external_media_materializer(
                api_url=api_url,
            )
        )

    try:
        publication = (
            publish_reviewed_external_content(
                chat_id=decision.chat_id,
                api_url=api_url,
                content=decision.content,
                review=decision.review,
                materializer=(
                    resolved_materializer
                ),
                smart_summary_applied=(
                    smart_summary_applied
                ),
            )
        )

    except Exception as exc:
        raise ExternalReviewExecutionError(
            "external reviewed content publication failed"
        ) from exc

    return ExternalReviewExecutionResult(
        status=STATUS_PUBLISHED,
        decision=decision,
        publication=publication,
    )


# =========================================================
# EXECUTION
# =========================================================


def execute_external_review_decision(
    *,
    decision: ExternalReviewDecision,
    api_url: str,
    materializer: Optional[
        ExternalMediaMaterializer
    ] = None,
) -> ExternalReviewExecutionResult:
    """
    Execute one approved external-review decision.

    STANDARD:
        Review
        -> External Publication Service
        -> PreparedContent
        -> Shared Publication Engine

    SHORT:
        Review
        -> existing shared Smart Summary
        -> External Publication Service
        -> PreparedContent
        -> Shared Publication Engine

    EDITORIAL_REWRITE:
        remains fail-closed until the existing shared Editorial workflow
        has produced the approved rewritten content.

    No Telegram/Bale executor is called directly here.
    """

    if not isinstance(
        decision,
        ExternalReviewDecision,
    ):
        raise TypeError(
            "decision must be ExternalReviewDecision"
        )

    normalized_api_url = str(
        api_url
        or ""
    ).strip()

    if not normalized_api_url:
        raise ExternalReviewExecutionError(
            "api_url is required"
        )

    # =====================================================
    # EDITORIAL
    # =====================================================

    if (
        decision.requires_editorial_rewrite
    ):
        return ExternalReviewExecutionResult(
            status=STATUS_EDITORIAL_REQUIRED,
            decision=decision,
        )

    # =====================================================
    # SHORT / SHARED SMART SUMMARY
    # =====================================================

    if (
        decision.requires_smart_summary
    ):
        summarized_decision = (
            _apply_shared_smart_summary(
                decision
            )
        )

        return _publish_decision(
            decision=summarized_decision,
            api_url=normalized_api_url,
            materializer=materializer,
            smart_summary_applied=True,
        )

    # =====================================================
    # STANDARD
    # =====================================================

    return _publish_decision(
        decision=decision,
        api_url=normalized_api_url,
        materializer=materializer,
    )
