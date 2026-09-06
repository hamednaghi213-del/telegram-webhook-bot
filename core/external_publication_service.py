"""Shared publication entry point for reviewed external content."""

from __future__ import annotations

from dataclasses import replace
from typing import (
    Any,
    Mapping,
    Optional,
    Sequence,
)

from core.content_model import (
    PreparedContent,
    PublicationTarget,
)
from core.external_content_bridge import (
    ExternalPreparedBridgeResult,
    build_external_prepared_content,
)
from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalReviewResult,
)
from core.external_media_materializer import (
    ExternalMediaMaterializer,
)
from core.publication_state import (
    PublicationStateStore,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalPublicationError(
    RuntimeError
):
    """Raised when reviewed external content cannot enter Shared Engine."""


class ExternalTransformationRequired(
    ExternalPublicationError
):
    """
    Raised when the review requests a shared transformation that has not
    yet been applied.

    The service deliberately fails closed instead of implementing a second
    Smart Summary or Editorial engine.
    """


# =========================================================
# RESULT
# =========================================================


class ExternalPublicationResult:
    """
    Thin result wrapper preserving bridge provenance and the Shared Engine
    publication result.
    """

    def __init__(
        self,
        *,
        bridge: ExternalPreparedBridgeResult,
        publication_result: Any,
    ) -> None:
        self.bridge = bridge
        self.publication_result = (
            publication_result
        )

    @property
    def prepared_content(
        self,
    ) -> PreparedContent:
        return (
            self.bridge
            .prepared_content
        )

    @property
    def publication_identity(
        self,
    ) -> str:
        return (
            self.bridge
            .publication_identity
        )

    @property
    def ok(
        self,
    ) -> bool:
        result = (
            self.publication_result
        )

        if isinstance(
            result,
            Mapping,
        ):
            return bool(
                result.get(
                    "ok",
                    False,
                )
            )

        return bool(
            result
        )


# =========================================================
# VALIDATION
# =========================================================


def _validate_transformation_state(
    bridge: ExternalPreparedBridgeResult,
    *,
    smart_summary_applied: bool,
    editorial_rewrite_applied: bool,
) -> None:
    """
    Prevent bypassing review intent.

    A SHORT or EDITORIAL_REWRITE review must not silently publish the
    untransformed source text.
    """

    if (
        bridge.requires_smart_summary
        and not smart_summary_applied
    ):
        raise ExternalTransformationRequired(
            "external content requires shared Smart Summary before publication"
        )

    if (
        bridge.requires_editorial_rewrite
        and not editorial_rewrite_applied
    ):
        raise ExternalTransformationRequired(
            "external content requires shared Editorial processing before publication"
        )


def _finalize_prepared_flags(
    prepared: PreparedContent,
    *,
    editorial_rewrite_applied: bool,
) -> PreparedContent:
    """
    Preserve Shared Engine semantics after an approved Editorial rewrite.

    This does not perform Editorial processing itself.
    """

    if (
        editorial_rewrite_applied
        and not prepared.editorial_finalized
    ):
        return replace(
            prepared,
            editorial_finalized=True,
        )

    return prepared


# =========================================================
# SHARED ENGINE ENTRY
# =========================================================


def publish_reviewed_external_content(
    chat_id: int,
    api_url: str,
    content: NormalizedExternalContent,
    review: ExternalReviewResult,
    *,
    materializer: Optional[
        ExternalMediaMaterializer
    ] = None,
    prepared_files: Optional[
        Sequence[
            Mapping[str, Any]
        ]
    ] = None,
    source_key: str = "",
    targets: Optional[
        Sequence[
            PublicationTarget
        ]
    ] = None,
    state_store: Optional[
        PublicationStateStore
    ] = None,
    smart_summary_applied: bool = False,
    editorial_rewrite_applied: bool = False,
) -> ExternalPublicationResult:
    """
    Publish reviewed external content through the existing Shared Engine.

    Important boundaries:
      - no duplicate publication engine
      - no direct Telegram/Bale sending
      - no translation
      - no Smart Summary implementation
      - no Editorial implementation
      - no raw external URL in PreparedContent.files

    The caller must apply requested shared transformations before invoking
    publication.
    """

    bridge = build_external_prepared_content(
        content,
        review,
        materializer=materializer,
        prepared_files=prepared_files,
        source_key=source_key,
    )

    _validate_transformation_state(
        bridge,
        smart_summary_applied=(
            bool(
                smart_summary_applied
            )
        ),
        editorial_rewrite_applied=(
            bool(
                editorial_rewrite_applied
            )
        ),
    )

    prepared = (
        _finalize_prepared_flags(
            bridge.prepared_content,
            editorial_rewrite_applied=(
                bool(
                    editorial_rewrite_applied
                )
            ),
        )
    )

    if (
        prepared
        is not bridge.prepared_content
    ):
        bridge = (
            ExternalPreparedBridgeResult(
                prepared_content=prepared,
                requires_smart_summary=(
                    bridge.requires_smart_summary
                ),
                requires_editorial_rewrite=(
                    bridge.requires_editorial_rewrite
                ),
                source_type=(
                    bridge.source_type
                ),
                source_url=(
                    bridge.source_url
                ),
                canonical_url=(
                    bridge.canonical_url
                ),
                original_language=(
                    bridge.original_language
                ),
                extraction_confidence=(
                    bridge.extraction_confidence
                ),
                warnings=(
                    bridge.warnings
                ),
            )
        )

    from core.publication_engine import (
        publish_prepared_content,
    )

    args = [
        chat_id,
        api_url,
        prepared,
    ]

    kwargs = {}

    if targets is not None:
        kwargs[
            "targets"
        ] = list(
            targets
        )

    if state_store is not None:
        kwargs[
            "state_store"
        ] = state_store

    try:
        result = publish_prepared_content(
            *args,
            **kwargs,
        )

    except TypeError:
        # Compatibility with older/current signatures where optional
        # arguments may be positional.
        if (
            targets is not None
            and state_store is not None
        ):
            result = (
                publish_prepared_content(
                    chat_id,
                    api_url,
                    prepared,
                    list(
                        targets
                    ),
                    state_store,
                )
            )

        elif targets is not None:
            result = (
                publish_prepared_content(
                    chat_id,
                    api_url,
                    prepared,
                    list(
                        targets
                    ),
                )
            )

        else:
            raise

    return ExternalPublicationResult(
        bridge=bridge,
        publication_result=result,
    )
