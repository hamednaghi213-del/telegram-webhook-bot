from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.ai_runtime import timed_stage
from core.translation_pipeline import reuse_language_detection

from core.translation_controller import (
    RESULT_PREVIEW,
    TranslationControllerResult,
    select_translation_language,
    start_translation,
)

from core.translation_pipeline import (
    detect_pipeline_source_language,
)


logger = logging.getLogger(__name__)


# =========================================================
# AUTOMATIC TRANSLATION REVIEW
# =========================================================
#
# Purpose:
#
# Incoming content
#     ↓
# Detect source language automatically
#     ↓
# Persian?
#     ├── yes  → passthrough to existing publication/review path
#     └── no   → automatically translate to Persian
#                ↓
#              Translation quality validation
#                ↓
#              existing Translation Preview
#                ↓
#              user confirms / edits / cancels
#
#
# IMPORTANT:
#
# - The user does NOT select the source language.
# - The user does NOT press 🌐 Translate to start.
# - The target language for this temporary Production phase
#   is Persian.
# - Publication NEVER happens in this module.
# - Translation Preview remains mandatory.
# - Genuinely unknown/unsafe language detection is fail-closed.
# - Provider failure must NOT block content that deterministic
#   local evidence proves is clearly non-Persian.
#
# =========================================================


TARGET_LANGUAGE_CODE = "fa"

SOURCE_LANGUAGE_AUTO = "auto"


ACTION_PASSTHROUGH = "passthrough"

ACTION_PREVIEW = "preview"

ACTION_BLOCKED = "blocked"

ACTION_FAILED = "failed"


# =========================================================
# RESULT
# =========================================================

@dataclass(frozen=True)
class AutomaticTranslationReviewResult:
    success: bool

    action: str

    source_language: str = SOURCE_LANGUAGE_AUTO

    target_language: str = TARGET_LANGUAGE_CODE

    requires_translation: bool = False

    requires_preview: bool = False

    review_id: str = ""

    translated_text: str = ""

    controller_result: Optional[
        TranslationControllerResult
    ] = None

    reason: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# HELPERS
# =========================================================

def _normalize_language(
    value: Any,
) -> str:

    text = str(
        value
        or ""
    ).strip().lower()

    if not text:

        return SOURCE_LANGUAGE_AUTO

    text = text.replace(
        "_",
        "-",
    )

    aliases = {
        "persian": "fa",
        "farsi": "fa",
        "فارسی": "fa",
        "unknown": SOURCE_LANGUAGE_AUTO,
        "und": SOURCE_LANGUAGE_AUTO,
        "uncertain": SOURCE_LANGUAGE_AUTO,
    }

    if text in aliases:

        return aliases[
            text
        ]

    if text == SOURCE_LANGUAGE_AUTO:

        return SOURCE_LANGUAGE_AUTO

    base = (
        text
        .split(
            "-",
            1,
        )[0]
        .strip()
    )

    if (
        2 <= len(base) <= 3
        and base.isalpha()
    ):

        return base

    return SOURCE_LANGUAGE_AUTO


def _deterministic_clearly_non_persian(
    detection: Any,
) -> bool:
    """
    Return True only when the shared deterministic detector
    positively establishes that the text is not Persian.

    The exact language may still be unknown.

    This is intentionally separate from ordinary language
    identification so an unavailable provider does not force
    obvious Latin/Cyrillic/etc. content into the blocked path.
    """

    if detection is None:
        return False

    try:

        from core.language_detector import (
            detection_is_clearly_non_persian,
        )

        return bool(
            detection_is_clearly_non_persian(
                detection
            )
        )

    except Exception as exc:

        logger.warning(
            "⚠️ Deterministic non-Persian check unavailable | %s",
            exc,
        )

        return False


def _detection_metadata(
    detection_result: Dict[str, Any],
) -> Dict[str, Any]:

    return {
        "automatic_translation_review":
            True,

        "detected_source_language": (
            detection_result.get(
                "language",
                SOURCE_LANGUAGE_AUTO,
            )
        ),

        "language_detected_by": (
            detection_result.get(
                "detected_by",
                "unknown",
            )
        ),

        "automatic_target_language": (
            TARGET_LANGUAGE_CODE
        ),

        "clearly_non_persian": bool(
            detection_result.get(
                "clearly_non_persian",
                False,
            )
        ),
    }


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_automatic_review_language(
    text: str,
) -> Dict[str, Any]:
    """
    Use the existing shared language-detection pipeline.

    Normal flow:

        deterministic detection
            ↓
        provider fallback when uncertain

    Provider outage fallback:

        exact language still unknown
            +
        deterministic evidence proves non-Persian
            ↓
        return language=auto with clearly_non_persian=True

    The Translation Service already supports source_language=auto,
    so the translation engine may translate without inventing an
    exact source language.

    Truly ambiguous Arabic-script text remains fail-closed.
    """

    content = str(
        text
        or ""
    ).strip()

    if not content:

        return {
            "language":
                SOURCE_LANGUAGE_AUTO,

            "detection":
                None,

            "provider_detection":
                None,

            "detected_by":
                "unknown",

            "clearly_non_persian":
                False,
        }

    try:

        result = (
            detect_pipeline_source_language(
                content
            )
        )

    except Exception as exc:

        logger.exception(
            "❌ Automatic translation language detection failed | %s",
            exc,
        )

        return {
            "language":
                SOURCE_LANGUAGE_AUTO,

            "detection":
                None,

            "provider_detection":
                None,

            "detected_by":
                "error",

            "clearly_non_persian":
                False,

            "error":
                str(
                    exc
                ),
        }

    if not isinstance(
        result,
        dict,
    ):

        return {
            "language":
                SOURCE_LANGUAGE_AUTO,

            "detection":
                None,

            "provider_detection":
                None,

            "detected_by":
                "unknown",

            "clearly_non_persian":
                False,
        }

    normalized = (
        _normalize_language(
            result.get(
                "language"
            )
        )
    )

    output = dict(
        result
    )

    output[
        "language"
    ] = normalized

    deterministic_detection = (
        result.get(
            "detection"
        )
    )

    clearly_non_persian = (
        _deterministic_clearly_non_persian(
            deterministic_detection
        )
    )

    output[
        "clearly_non_persian"
    ] = clearly_non_persian

    # If provider detection did not resolve the exact language,
    # retain "auto" rather than guessing a code. The important
    # distinction is that we may still know safely that the text
    # is not Persian.
    if (
        normalized
        == SOURCE_LANGUAGE_AUTO
        and clearly_non_persian
    ):

        output[
            "detected_by"
        ] = (
            "deterministic_non_persian"
        )

        logger.info(
            "🌐 Exact source language unresolved, "
            "but content is deterministically non-Persian"
        )

    return output


# =========================================================
# SHOULD TRANSLATE?
# =========================================================

def automatic_translation_required(
    text: str,
) -> AutomaticTranslationReviewResult:
    """
    Decide whether incoming content requires Persian translation.

    Persian content:
        passthrough

    Known non-Persian content:
        translation required

    Exact language unknown but safely proven non-Persian:
        translation required with source_language=auto

    Truly ambiguous language:
        blocked
    """

    content = str(
        text
        or ""
    ).strip()

    if not content:

        return AutomaticTranslationReviewResult(
            success=False,
            action=ACTION_FAILED,
            reason="empty_translation_source",
        )

    detection = (
        detect_automatic_review_language(
            content
        )
    )

    source_language = (
        _normalize_language(
            detection.get(
                "language"
            )
        )
    )

    clearly_non_persian = bool(
        detection.get(
            "clearly_non_persian",
            False,
        )
    )

    metadata = (
        _detection_metadata(
            detection
        )
    )

    # =====================================================
    # PERSIAN → PASSTHROUGH
    # =====================================================

    if source_language == "fa":

        logger.info(
            "🌐 Automatic translation not required | "
            "source_language=fa"
        )

        return AutomaticTranslationReviewResult(
            success=True,

            action=ACTION_PASSTHROUGH,

            source_language="fa",

            target_language=TARGET_LANGUAGE_CODE,

            requires_translation=False,

            requires_preview=False,

            reason=(
                "source_already_matches_destination_language"
            ),

            metadata=metadata,
        )

    # =====================================================
    # EXACT LANGUAGE UNKNOWN BUT DEFINITELY NON-PERSIAN
    # =====================================================
    #
    # Example:
    #
    # Gemini language-detection provider → 503
    #
    # Local detector:
    #
    #     script=latin
    #     exact language uncertain
    #     clearly_non_persian=True
    #
    # The Translation Service accepts source_language="auto".
    #
    # Therefore do NOT block this content.
    # =====================================================

    if (
        source_language
        == SOURCE_LANGUAGE_AUTO
        and clearly_non_persian
    ):

        logger.info(
            "🌐 Automatic Persian translation required | "
            "source_language=auto | "
            "reason=clearly_non_persian"
        )

        return AutomaticTranslationReviewResult(
            success=True,

            action=ACTION_PREVIEW,

            source_language=(
                SOURCE_LANGUAGE_AUTO
            ),

            target_language=(
                TARGET_LANGUAGE_CODE
            ),

            requires_translation=True,

            requires_preview=True,

            reason=(
                "clearly_non_persian_source_language_unresolved"
            ),

            metadata=metadata,
        )

    # =====================================================
    # GENUINELY AMBIGUOUS → FAIL CLOSED
    # =====================================================

    if source_language == SOURCE_LANGUAGE_AUTO:

        logger.warning(
            "⚠️ Automatic translation blocked | "
            "source language could not be determined"
        )

        return AutomaticTranslationReviewResult(
            success=False,

            action=ACTION_BLOCKED,

            source_language=(
                SOURCE_LANGUAGE_AUTO
            ),

            target_language=(
                TARGET_LANGUAGE_CODE
            ),

            requires_translation=False,

            requires_preview=False,

            reason="source_language_uncertain",

            metadata=metadata,
        )

    # =====================================================
    # KNOWN NON-PERSIAN LANGUAGE
    # =====================================================

    logger.info(
        "🌐 Automatic Persian translation required | "
        "source_language=%s",
        source_language,
    )

    return AutomaticTranslationReviewResult(
        success=True,

        action=ACTION_PREVIEW,

        source_language=source_language,

        target_language=TARGET_LANGUAGE_CODE,

        requires_translation=True,

        requires_preview=True,

        reason="destination_language_mismatch",

        metadata=metadata,
    )


# =========================================================
# START AUTOMATIC REVIEW
# =========================================================

@timed_stage(
    "automatic_translation_to_preview",
    provider="pipeline",
)
@reuse_language_detection()
def start_automatic_persian_translation_review(
    *,
    chat_id: int,
    user_id: int,
    original_text: str,
    source_kind: str = "message",
    source_key: str = "",
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> AutomaticTranslationReviewResult:
    """
    Automatically create a Persian Translation Preview when
    incoming content is non-Persian.

    This function does NOT publish anything.

    Return behavior:

        Persian:
            ACTION_PASSTHROUGH

        Non-Persian:
            ACTION_PREVIEW

        Clearly non-Persian but exact language unresolved:
            ACTION_PREVIEW with source_language="auto"

        Genuinely ambiguous detection:
            ACTION_BLOCKED

        Translation failure:
            ACTION_FAILED

    The resulting Translation state uses the existing
    persistent Translation Review system, so Confirm/Edit/
    Cancel continue through the already implemented workflow.
    """

    content = str(
        original_text
        or ""
    )

    decision = (
        automatic_translation_required(
            content
        )
    )

    if decision.action != ACTION_PREVIEW:

        return decision

    state_metadata: Dict[
        str,
        Any,
    ] = {}

    if isinstance(
        metadata,
        dict,
    ):

        state_metadata.update(
            metadata
        )

    state_metadata.update(
        decision.metadata
    )

    state_metadata[
        "automatic_translation"
    ] = True

    state_metadata[
        "automatic_translation_target"
    ] = TARGET_LANGUAGE_CODE

    # =====================================================
    # CREATE PERSISTENT TRANSLATION REVIEW STATE
    # =====================================================

    started = (
        start_translation(
            chat_id=chat_id,

            user_id=user_id,

            original_text=content,

            source_language=(
                decision.source_language
            ),

            source_kind=source_kind,

            source_key=source_key,

            metadata=state_metadata,
        )
    )

    if (
        not started.success
        or not started.review_id
    ):

        logger.warning(
            "⚠️ Automatic translation review could not start | "
            "chat_id=%s | user_id=%s | reason=%s",
            chat_id,
            user_id,
            started.reason,
        )

        return AutomaticTranslationReviewResult(
            success=False,

            action=ACTION_FAILED,

            source_language=(
                decision.source_language
            ),

            target_language=(
                TARGET_LANGUAGE_CODE
            ),

            requires_translation=True,

            requires_preview=True,

            controller_result=started,

            reason=(
                started.reason
                or (
                    "automatic_translation_"
                    "state_creation_failed"
                )
            ),

            metadata=state_metadata,
        )

    # =====================================================
    # AUTOMATICALLY SELECT PERSIAN DESTINATION
    # =====================================================
    #
    # This invokes the existing Shared Translation Pipeline:
    #
    # - Translation Policy
    # - Translation Provider
    # - validation
    # - semantic quality
    # - bounded retry
    #
    # No separate translation engine is introduced here.
    # =====================================================

    translated = (
        select_translation_language(
            review_id=(
                started.review_id
            ),

            chat_id=chat_id,

            user_id=user_id,

            language_code=(
                TARGET_LANGUAGE_CODE
            ),
        )
    )

    if (
        not translated.success
        or translated.action
        != RESULT_PREVIEW
    ):

        logger.warning(
            "⚠️ Automatic Persian translation failed | "
            "review_id=%s | source_language=%s | "
            "reason=%s",
            started.review_id,
            decision.source_language,
            translated.reason,
        )

        return AutomaticTranslationReviewResult(
            success=False,

            action=ACTION_FAILED,

            source_language=(
                decision.source_language
            ),

            target_language=(
                TARGET_LANGUAGE_CODE
            ),

            requires_translation=True,

            requires_preview=True,

            review_id=(
                started.review_id
            ),

            controller_result=(
                translated
            ),

            reason=(
                translated.reason
                or (
                    "automatic_translation_failed"
                )
            ),

            metadata=state_metadata,
        )

    logger.info(
        "✅ Automatic Persian Translation Preview ready | "
        "review_id=%s | source_language=%s",
        translated.review_id,
        decision.source_language,
    )

    return AutomaticTranslationReviewResult(
        success=True,

        action=ACTION_PREVIEW,

        source_language=(
            decision.source_language
        ),

        target_language=(
            TARGET_LANGUAGE_CODE
        ),

        requires_translation=True,

        requires_preview=True,

        review_id=(
            translated.review_id
        ),

        translated_text=(
            translated.translated_text
        ),

        controller_result=(
            translated
        ),

        reason=(
            "automatic_translation_preview_ready"
        ),

        metadata=state_metadata,
    )
