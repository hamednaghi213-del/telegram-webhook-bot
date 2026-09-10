from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


from core.translation_pipeline import (
    PIPELINE_BLOCKED,
    PIPELINE_FAILED,
    PIPELINE_PASSTHROUGH,
    PIPELINE_REVIEW_REQUIRED,
    PIPELINE_TRANSLATED,
    TranslationPipelineResult,
    run_translation_pipeline,
)

from core.translation_policy import (
    TranslationPolicy,
)


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATED PREPARED CONTENT ADAPTER
# =========================================================
#
# Purpose:
#
# Existing PreparedContent
#       ↓
# Shared Translation Pipeline
#       ↓
# Translated PreparedContent Payload
#       ↓
# Existing Shared Publication Engine
#
# IMPORTANT:
#
# - This module does NOT publish.
# - This module does NOT call Telegram/Bale.
# - This module does NOT change idempotency.
# - This module does NOT resolve destinations.
# - This module does NOT apply branding.
# - This module does NOT mutate the source PreparedContent.
#
# Translation happens on the semantic/base content BEFORE
# destination branding and PublicationPlan.
#
# Files/media are preserved unchanged.
# =========================================================


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class TranslatedPreparedContentResult:
    success: bool

    status: str

    payload: Dict[str, Any]

    pipeline_result: TranslationPipelineResult

    requires_review: bool = False

    blocked: bool = False

    reason: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# CONTENT HELPERS
# =========================================================

def _safe_list(
    value: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:

    return [
        dict(item)
        for item in (
            value
            or []
        )
        if isinstance(
            item,
            dict,
        )
    ]


def _prepared_value(
    prepared: Any,
    name: str,
    default: Any = None,
) -> Any:
    """
    Supports both PreparedContent objects and dictionaries.

    This keeps the adapter isolated from implementation
    details of core.content_model.
    """

    if isinstance(
        prepared,
        dict,
    ):
        return prepared.get(
            name,
            default,
        )

    return getattr(
        prepared,
        name,
        default,
    )


def _base_text(
    prepared: Any,
) -> str:
    """
    Translation must start from semantic/base content.

    Prefer neutral_text, because Shared Engine uses this as
    the destination-neutral representation.

    Fall back to main_text when unavailable.
    """

    return str(
        _prepared_value(
            prepared,
            "neutral_text",
            "",
        )
        or _prepared_value(
            prepared,
            "main_text",
            "",
        )
        or ""
    ).strip()


# =========================================================
# BLOCKQUOTES
# =========================================================

def _translate_block_text(
    *,
    block: Dict[str, Any],
    policy: TranslationPolicy,
    content_kind: str,
    semantic_quality: bool,
    quality_retries: int,
) -> Dict[str, Any]:
    """
    Translate one detached blockquote while preserving all
    non-text metadata.

    If translation is not required, the original block is
    returned unchanged.

    Block failures are fail-closed to the caller.
    """

    copied = dict(
        block
    )

    text = str(
        copied.get(
            "text",
            "",
        )
        or ""
    ).strip()

    if not text:
        return copied

    result = run_translation_pipeline(
        text=text,
        policy=policy,
        content_kind=content_kind,
        semantic_quality=semantic_quality,
        quality_retries=quality_retries,
    )

    if (
        not result.success
        or result.blocked
    ):
        raise RuntimeError(
            "blockquote_translation_failed:"
            f"{result.reason}"
        )

    copied[
        "text"
    ] = result.output_text

    return copied


def _translate_blocks(
    *,
    blocks: List[Dict[str, Any]],
    policy: TranslationPolicy,
    content_kind: str,
    semantic_quality: bool,
    quality_retries: int,
) -> List[Dict[str, Any]]:

    translated: List[
        Dict[str, Any]
    ] = []

    for block in blocks:

        translated.append(
            _translate_block_text(
                block=block,
                policy=policy,
                content_kind=content_kind,
                semantic_quality=semantic_quality,
                quality_retries=quality_retries,
            )
        )

    return translated


# =========================================================
# MAIN ADAPTER
# =========================================================

def translate_prepared_content(
    *,
    prepared: Any,
    policy: TranslationPolicy,
    content_kind: str = "text",
    semantic_quality: bool = True,
    quality_retries: int = 1,
) -> TranslatedPreparedContentResult:
    """
    Translate destination-neutral PreparedContent data.

    Returns a dictionary compatible with the fields currently
    used to construct core.content_model.PreparedContent.

    No publication happens here.
    """

    source_text = _base_text(
        prepared
    )

    pipeline_result = (
        run_translation_pipeline(
            text=source_text,
            policy=policy,
            content_kind=content_kind,
            semantic_quality=semantic_quality,
            quality_retries=quality_retries,
        )
    )

    # =====================================================
    # BLOCK / FAILURE
    # =====================================================

    if (
        not pipeline_result.success
        or pipeline_result.status
        in {
            PIPELINE_BLOCKED,
            PIPELINE_FAILED,
        }
    ):

        return TranslatedPreparedContentResult(
            success=False,
            status=(
                pipeline_result.status
            ),
            payload={},
            pipeline_result=(
                pipeline_result
            ),
            requires_review=False,
            blocked=(
                pipeline_result.blocked
            ),
            reason=(
                pipeline_result.reason
            ),
            metadata={
                "translation_applied":
                    False,
            },
        )

    # =====================================================
    # ORIGINAL STRUCTURE
    # =====================================================

    blockquote_blocks = _safe_list(
        _prepared_value(
            prepared,
            "blockquote_blocks",
            [],
        )
    )

    expandable_blocks = _safe_list(
        _prepared_value(
            prepared,
            "expandable_blocks",
            [],
        )
    )

    other_entities = _safe_list(
        _prepared_value(
            prepared,
            "other_entities",
            [],
        )
    )

    files = _safe_list(
        _prepared_value(
            prepared,
            "files",
            [],
        )
    )

    translated_text = (
        pipeline_result.output_text
    )

    translation_applied = (
        pipeline_result.status
        in {
            PIPELINE_TRANSLATED,
            PIPELINE_REVIEW_REQUIRED,
        }
    )

    # =====================================================
    # TRANSLATE DETACHED BLOCKS
    # =====================================================
    #
    # Blockquotes can contain semantically important content
    # outside main_text, so they must follow the same target
    # language when translation actually occurred.
    # =====================================================

    if translation_applied:

        try:

            blockquote_blocks = (
                _translate_blocks(
                    blocks=blockquote_blocks,
                    policy=policy,
                    content_kind=content_kind,
                    semantic_quality=semantic_quality,
                    quality_retries=quality_retries,
                )
            )

            expandable_blocks = (
                _translate_blocks(
                    blocks=expandable_blocks,
                    policy=policy,
                    content_kind=content_kind,
                    semantic_quality=semantic_quality,
                    quality_retries=quality_retries,
                )
            )

        except Exception as exc:

            logger.exception(
                "❌ TRANSLATED-PREPARED-CONTENT | "
                "detached block translation failed"
            )

            return TranslatedPreparedContentResult(
                success=False,
                status=PIPELINE_BLOCKED,
                payload={},
                pipeline_result=(
                    pipeline_result
                ),
                requires_review=False,
                blocked=True,
                reason=str(
                    exc
                ),
                metadata={
                    "translation_applied":
                        True,

                    "block_translation_failed":
                        True,
                },
            )

    # =====================================================
    # ENTITY POLICY
    # =====================================================
    #
    # Existing offsets refer to the ORIGINAL source text.
    #
    # After natural translation, character offsets are no
    # longer valid.
    #
    # Therefore:
    #
    # - URLs / mentions / hashtags are already protected by
    #   Translation Service.
    # - text-position entities must NOT be blindly reused.
    #
    # The later entity-remapping stage can rebuild safe
    # entities for translated text.
    #
    # Passthrough content keeps original entities.
    # =====================================================

    if translation_applied:
        translated_entities: List[
            Dict[str, Any]
        ] = []
    else:
        translated_entities = (
            other_entities
        )

    # =====================================================
    # PAYLOAD
    # =====================================================

    payload: Dict[str, Any] = {
        "main_text":
            translated_text,

        "neutral_text":
            translated_text,

        "blockquote_blocks":
            blockquote_blocks,

        "expandable_blocks":
            expandable_blocks,

        "other_entities":
            translated_entities,

        "files":
            files,

        "media_presentation":
            str(
                _prepared_value(
                    prepared,
                    "media_presentation",
                    "",
                )
                or ""
            ),

        "editorial_finalized":
            bool(
                _prepared_value(
                    prepared,
                    "editorial_finalized",
                    False,
                )
            ),

        "require_single_message":
            bool(
                _prepared_value(
                    prepared,
                    "require_single_message",
                    False,
                )
            ),

        "source_key":
            str(
                _prepared_value(
                    prepared,
                    "source_key",
                    "",
                )
                or ""
            ),
    }

    logger.info(
        "✅ TRANSLATED-PREPARED-CONTENT | "
        "status=%s | "
        "source=%s | target=%s | "
        "review=%s | "
        "files=%s | "
        "blockquote=%s | expandable=%s",
        pipeline_result.status,
        pipeline_result.source_language,
        pipeline_result.target_language,
        pipeline_result.requires_review,
        len(
            files
        ),
        len(
            blockquote_blocks
        ),
        len(
            expandable_blocks
        ),
    )

    return TranslatedPreparedContentResult(
        success=True,
        status=(
            pipeline_result.status
        ),
        payload=payload,
        pipeline_result=(
            pipeline_result
        ),
        requires_review=(
            pipeline_result
            .requires_review
        ),
        blocked=False,
        reason=(
            pipeline_result.reason
        ),
        metadata={
            "translation_applied":
                translation_applied,

            "source_language":
                pipeline_result
                .source_language,

            "target_language":
                pipeline_result
                .target_language,

            "quality_score":
                (
                    pipeline_result
                    .quality_result
                    .score
                    if (
                        pipeline_result
                        .quality_result
                        is not None
                    )
                    else None
                ),
        },
    )


# =========================================================
# MANUAL TRANSLATION ADAPTER
# =========================================================

def translate_prepared_content_manually(
    *,
    prepared: Any,
    policy: TranslationPolicy,
    target_language: str,
    content_kind: str = "text",
    semantic_quality: bool = True,
    quality_retries: int = 1,
) -> TranslatedPreparedContentResult:
    """
    Manual 🌐 translation path.

    Manual translation always enters review before
    publication.
    """

    source_text = _base_text(
        prepared
    )

    pipeline_result = (
        run_translation_pipeline(
            text=source_text,
            policy=policy,
            content_kind=content_kind,
            manual_override=True,
            manual_target_language=(
                target_language
            ),
            semantic_quality=semantic_quality,
            quality_retries=quality_retries,
        )
    )

    if (
        not pipeline_result.success
        or pipeline_result.blocked
    ):

        return TranslatedPreparedContentResult(
            success=False,
            status=(
                pipeline_result.status
            ),
            payload={},
            pipeline_result=(
                pipeline_result
            ),
            requires_review=False,
            blocked=(
                pipeline_result.blocked
            ),
            reason=(
                pipeline_result.reason
            ),
        )

    blockquote_blocks = _safe_list(
        _prepared_value(
            prepared,
            "blockquote_blocks",
            [],
        )
    )

    expandable_blocks = _safe_list(
        _prepared_value(
            prepared,
            "expandable_blocks",
            [],
        )
    )

    try:

        blockquote_blocks = (
            _translate_blocks(
                blocks=blockquote_blocks,
                policy=policy,
                content_kind=content_kind,
                semantic_quality=semantic_quality,
                quality_retries=quality_retries,
            )
        )

        expandable_blocks = (
            _translate_blocks(
                blocks=expandable_blocks,
                policy=policy,
                content_kind=content_kind,
                semantic_quality=semantic_quality,
                quality_retries=quality_retries,
            )
        )

    except Exception as exc:

        return TranslatedPreparedContentResult(
            success=False,
            status=PIPELINE_BLOCKED,
            payload={},
            pipeline_result=(
                pipeline_result
            ),
            requires_review=False,
            blocked=True,
            reason=str(
                exc
            ),
        )

    payload = {
        "main_text":
            pipeline_result.output_text,

        "neutral_text":
            pipeline_result.output_text,

        "blockquote_blocks":
            blockquote_blocks,

        "expandable_blocks":
            expandable_blocks,

        # Original UTF-16 offsets cannot safely survive a
        # natural-language translation.
        "other_entities":
            [],

        "files":
            _safe_list(
                _prepared_value(
                    prepared,
                    "files",
                    [],
                )
            ),

        "media_presentation":
            str(
                _prepared_value(
                    prepared,
                    "media_presentation",
                    "",
                )
                or ""
            ),

        "editorial_finalized":
            bool(
                _prepared_value(
                    prepared,
                    "editorial_finalized",
                    False,
                )
            ),

        "require_single_message":
            bool(
                _prepared_value(
                    prepared,
                    "require_single_message",
                    False,
                )
            ),

        "source_key":
            str(
                _prepared_value(
                    prepared,
                    "source_key",
                    "",
                )
                or ""
            ),
    }

    return TranslatedPreparedContentResult(
        success=True,
        status=(
            pipeline_result.status
        ),
        payload=payload,
        pipeline_result=(
            pipeline_result
        ),
        requires_review=True,
        blocked=False,
        reason=(
            pipeline_result.reason
        ),
        metadata={
            "translation_applied":
                True,

            "manual_translation":
                True,

            "source_language":
                pipeline_result
                .source_language,

            "target_language":
                pipeline_result
                .target_language,
        },
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translated_prepared_content(
    result: TranslatedPreparedContentResult,
) -> Dict[str, Any]:
    """
    Safe diagnostic information.

    Message text is intentionally excluded.
    """

    return {
        "success":
            result.success,

        "status":
            result.status,

        "requires_review":
            result.requires_review,

        "blocked":
            result.blocked,

        "reason":
            result.reason,

        "source_language":
            result.pipeline_result
            .source_language,

        "target_language":
            result.pipeline_result
            .target_language,

        "has_files":
            bool(
                result.payload.get(
                    "files"
                )
                if result.payload
                else False
            ),

        "blockquote_count":
            len(
                result.payload.get(
                    "blockquote_blocks",
                    []
                )
                if result.payload
                else []
            ),

        "expandable_count":
            len(
                result.payload.get(
                    "expandable_blocks",
                    []
                )
                if result.payload
                else []
            ),

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }
