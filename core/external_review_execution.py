"""Execution boundary for approved external-content review decisions."""

from __future__ import annotations

from dataclasses import dataclass
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

    A transformation-required result is intentionally not a publication
    success. The caller must pass it through the existing shared
    Smart Summary / Editorial service before publication.
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
    Execute an approved external-review decision.

    Standard deterministic selections:
        Review Decision
        -> External Publication Service
        -> PreparedContent
        -> Shared Publication Engine

    SHORT and EDITORIAL_REWRITE:
        stop here and signal that the existing shared transformation
        service must run first.

    No Telegram/Bale destination is contacted directly by this module.
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

    if (
        decision.requires_smart_summary
    ):
        return ExternalReviewExecutionResult(
            status=(
                STATUS_SMART_SUMMARY_REQUIRED
            ),
            decision=decision,
        )

    if (
        decision.requires_editorial_rewrite
    ):
        return ExternalReviewExecutionResult(
            status=(
                STATUS_EDITORIAL_REQUIRED
            ),
            decision=decision,
        )

    resolved_materializer = (
        materializer
    )

    if (
        decision.review.media
        and resolved_materializer is None
    ):
        resolved_materializer = (
            build_external_media_materializer(
                api_url=normalized_api_url,
            )
        )

    try:
        publication = (
            publish_reviewed_external_content(
                chat_id=decision.chat_id,
                api_url=normalized_api_url,
                content=decision.content,
                review=decision.review,
                materializer=(
                    resolved_materializer
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
