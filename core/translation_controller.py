from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


from core.translation_pipeline import (
    PIPELINE_BLOCKED,
    PIPELINE_FAILED,
    PIPELINE_PASSTHROUGH,
    PIPELINE_REVIEW_REQUIRED,
    PIPELINE_TRANSLATED,
    TranslationPipelineResult,
    run_manual_translation_pipeline,
)

from core.translation_policy import (
    build_legacy_default_policy,
)

from core.translation_service import (
    TranslationResult,
)

from core.translation_state import (
    STATE_PREVIEW,
    STATE_WAITING_CUSTOM_LANGUAGE,
    STATE_WAITING_EDIT,
    TranslationState,
    apply_translation_edit,
    cancel_translation_state,
    confirm_translation_state,
    create_translation_state,
    get_active_translation_state,
    get_translation_state,
    mark_translation_failed,
    mark_waiting_custom_language,
    mark_waiting_translation_edit,
    remove_translation_state,
    set_translation_language,
    set_translation_preview,
    translation_state_belongs_to,
    translation_retry_available,
)

from core.translation_ui import (
    TranslationLanguage,
    build_custom_language_prompt,
    build_language_keyboard,
    build_language_selection_text,
    build_more_languages_keyboard,
    build_more_languages_text,
    build_translation_failed_text,
    build_translation_preview_keyboard,
    build_translation_preview_text,
    get_language,
    keyboard_to_telegram_markup,
)


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION CONTROLLER
# =========================================================
#
# EXISTING FILE — FULL REPLACEMENT
#
# Shared Translation workflow controller.
#
# New execution path:
#
# translation_controller.py
#          ↓
# translation_pipeline.py
#          ↓
# language_detector.py
#          ↓
# language_detection_provider.py
#          ↓
# translation_policy.py
#          ↓
# translation_service.py
#          ↓
# translation_quality.py
#          ↓
# translation_quality_provider.py
#
# State / UI remain controlled here:
#
# translation_controller.py
#          ↓
# translation_state.py
#          ↓
# translation_ui.py
#
# Responsibilities:
#
# - create translation review
# - language selection
# - custom language
# - execute MANUAL translation through shared pipeline
# - language detection
# - provider fallback when detection is uncertain
# - translation policy
# - deterministic translation validation
# - semantic / linguistic quality validation
# - bounded quality retry
# - preview
# - manual edit
# - confirmation
# - cancellation
#
# It intentionally DOES NOT:
#
# - publish directly to Telegram
# - publish directly to Bale
# - bypass PublicationPlan
# - modify Legacy / Workspace routing
# - apply destination branding
# - resolve destinations
#
# Confirmed translated content is handed to the existing
# Shared Publication Engine by the Telegram/webhook bridge.
#
# =========================================================


# =========================================================
# RESULT TYPES
# =========================================================

RESULT_LANGUAGE_MENU = "language_menu"

RESULT_MORE_LANGUAGES = "more_languages"

RESULT_CUSTOM_LANGUAGE_INPUT = "custom_language_input"

RESULT_PREVIEW = "preview"

RESULT_EDIT_INPUT = "edit_input"

RESULT_CONFIRMED = "confirmed"

RESULT_CANCELLED = "cancelled"

RESULT_FAILED = "failed"

RESULT_NOT_FOUND = "not_found"

RESULT_FORBIDDEN = "forbidden"

RESULT_INVALID_LANGUAGE = "invalid_language"

RESULT_INVALID_STATE = "invalid_state"

RESULT_ORIGINAL = "original"


# =========================================================
# CONTROLLER RESULT
# =========================================================

@dataclass(frozen=True)
class TranslationControllerResult:
    success: bool

    action: str

    text: str = ""

    reply_markup: Optional[
        Dict[str, Any]
    ] = None

    review_id: str = ""

    translated_text: str = ""

    target_language: str = ""

    state: Optional[
        TranslationState
    ] = None

    # Keep the existing public Controller API.
    #
    # The shared pipeline itself returns TranslationPipelineResult,
    # but this field continues exposing the underlying
    # TranslationResult for compatibility with existing callers.
    translation_result: Optional[
        TranslationResult
    ] = None

    reason: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# GENERIC HELPERS
# =========================================================

def _keyboard_markup(
    keyboard,
) -> Dict[str, Any]:

    return keyboard_to_telegram_markup(
        keyboard
    )


def _state_security_check(
    state: Optional[
        TranslationState
    ],
    *,
    chat_id: int,
    user_id: int,
) -> Optional[
    TranslationControllerResult
]:

    if state is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_NOT_FOUND,
            reason="translation_state_not_found",
        )

    if not translation_state_belongs_to(
        state,
        chat_id=chat_id,
        user_id=user_id,
    ):

        logger.warning(
            "⚠️ Translation state ownership rejected | "
            "review_id=%s | chat_id=%s | user_id=%s",
            state.review_id,
            chat_id,
            user_id,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FORBIDDEN,
            review_id=state.review_id,
            state=state,
            reason="translation_state_forbidden",
        )

    return None


def _pipeline_translation_result(
    result: TranslationPipelineResult,
) -> Optional[
    TranslationResult
]:

    value = getattr(
        result,
        "translation_result",
        None,
    )

    return value


def _pipeline_output_text(
    result: TranslationPipelineResult,
) -> str:

    return str(
        getattr(
            result,
            "output_text",
            "",
        )
        or ""
    ).strip()


def _pipeline_reason(
    result: TranslationPipelineResult,
) -> str:

    reason = str(
        getattr(
            result,
            "reason",
            "",
        )
        or ""
    ).strip()

    if reason:
        return reason

    if not getattr(
        result,
        "success",
        False,
    ):
        return "translation_pipeline_failed"

    return "translation_completed"


def _pipeline_attempts(
    result: TranslationPipelineResult,
) -> int:

    try:

        return max(
            0,
            int(
                getattr(
                    result,
                    "attempts",
                    0,
                )
                or 0
            ),
        )

    except (
        TypeError,
        ValueError,
    ):

        return 0


def _pipeline_warnings(
    result: TranslationPipelineResult,
) -> list:

    return list(
        getattr(
            result,
            "warnings",
            [],
        )
        or []
    )


def _pipeline_metadata(
    result: TranslationPipelineResult,
) -> Dict[str, Any]:

    metadata = getattr(
        result,
        "metadata",
        {},
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    return dict(
        metadata
    )


def _quality_metadata(
    result: TranslationPipelineResult,
) -> Dict[str, Any]:

    quality_result = getattr(
        result,
        "quality_result",
        None,
    )

    if quality_result is None:

        return {
            "quality_checked": False,
            "quality_passed": None,
            "quality_status": "",
            "quality_score": None,
        }

    quality_status = str(
        getattr(
            quality_result,
            "status",
            "",
        )
        or ""
    ).strip()

    quality_score = getattr(
        quality_result,
        "score",
        None,
    )

    quality_passed = bool(
        getattr(
            quality_result,
            "passed",
            False,
        )
    )

    return {
        "quality_checked": True,
        "quality_passed":
            quality_passed,
        "quality_status":
            quality_status,
        "quality_score":
            quality_score,
    }


def _detection_metadata(
    result: TranslationPipelineResult,
) -> Dict[str, Any]:

    source_language = str(
        getattr(
            result,
            "source_language",
            "auto",
        )
        or "auto"
    )

    provider_detection = getattr(
        result,
        "provider_detection",
        None,
    )

    provider_confidence = None

    if provider_detection is not None:

        provider_confidence = getattr(
            provider_detection,
            "confidence",
            None,
        )

    pipeline_metadata = (
        _pipeline_metadata(
            result
        )
    )

    return {
        "detected_source_language":
            source_language,

        "language_detected_by":
            pipeline_metadata.get(
                "detected_by",
                "",
            ),

        "provider_detection_confidence":
            provider_confidence,
    }


def _build_pipeline_state_metadata(
    result: TranslationPipelineResult,
    *,
    target_language: str,
    target_language_code: str,
) -> Dict[str, Any]:

    metadata: Dict[str, Any] = {
        "translation_attempts":
            _pipeline_attempts(
                result
            ),

        "translation_warnings":
            _pipeline_warnings(
                result
            ),

        "translation_target_language":
            target_language,

        "translation_target_language_code":
            target_language_code,

        "translation_pipeline_status":
            str(
                getattr(
                    result,
                    "status",
                    "",
                )
                or ""
            ),

        "translation_pipeline_reason":
            _pipeline_reason(
                result
            ),

        "translation_requires_review":
            bool(
                getattr(
                    result,
                    "requires_review",
                    False,
                )
            ),

        "translation_blocked":
            bool(
                getattr(
                    result,
                    "blocked",
                    False,
                )
            ),
    }

    metadata.update(
        _detection_metadata(
            result
        )
    )

    metadata.update(
        _quality_metadata(
            result
        )
    )

    pipeline_metadata = (
        _pipeline_metadata(
            result
        )
    )

    if pipeline_metadata:

        metadata[
            "translation_pipeline_metadata"
        ] = pipeline_metadata

    return metadata


def _build_manual_translation_policy():
    """
    Manual 🌐 Translation must remain available even before
    automatic Workspace/Destination language policy is wired
    into onboarding/settings.

    The Legacy default policy preserves existing publication
    behavior. run_manual_translation_pipeline() supplies the
    explicit manual override and target language.
    """

    return build_legacy_default_policy()


# =========================================================
# START TRANSLATION
# =========================================================

def start_translation(
    *,
    chat_id: int,
    user_id: int,
    original_text: str,
    source_language: str = "auto",
    source_kind: str = "message",
    source_key: str = "",
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> TranslationControllerResult:

    text = str(
        original_text
        or ""
    )

    if not text.strip():

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            reason="empty_translation_source",
        )

    try:

        state = create_translation_state(
            chat_id=chat_id,
            user_id=user_id,
            original_text=text,
            source_language=source_language,
            source_kind=source_kind,
            source_key=source_key,
            metadata=metadata,
        )

    except Exception as exc:

        logger.exception(
            "❌ Could not create translation state | "
            "chat_id=%s | user_id=%s",
            chat_id,
            user_id,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            reason=str(
                exc
            ),
        )

    logger.info(
        "🌐 Translation workflow started | "
        "review_id=%s | chat_id=%s | "
        "user_id=%s | source_kind=%s",
        state.review_id,
        chat_id,
        user_id,
        source_kind,
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_LANGUAGE_MENU,
        text=(
            build_language_selection_text()
        ),
        reply_markup=_keyboard_markup(
            build_language_keyboard()
        ),
        review_id=state.review_id,
        state=state,
    )


# =========================================================
# LANGUAGE MENU
# =========================================================

def show_translation_language_menu(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    return TranslationControllerResult(
        success=True,
        action=RESULT_LANGUAGE_MENU,
        text=(
            build_language_selection_text()
        ),
        reply_markup=_keyboard_markup(
            build_language_keyboard()
        ),
        review_id=review_id,
        state=state,
    )


# =========================================================
# MORE LANGUAGES
# =========================================================

def show_more_translation_languages(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
    page: int = 0,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    return TranslationControllerResult(
        success=True,
        action=RESULT_MORE_LANGUAGES,
        text=build_more_languages_text(
            page
        ),
        reply_markup=_keyboard_markup(
            build_more_languages_keyboard(
                page
            )
        ),
        review_id=review_id,
        state=state,
    )


# =========================================================
# CUSTOM LANGUAGE
# =========================================================

def request_custom_translation_language(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    updated = (
        mark_waiting_custom_language(
            review_id
        )
    )

    if updated is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason=(
                "could_not_mark_custom_language_wait"
            ),
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_CUSTOM_LANGUAGE_INPUT,
        text=(
            build_custom_language_prompt()
        ),
        review_id=review_id,
        state=updated,
    )


# =========================================================
# EXECUTE TRANSLATION THROUGH SHARED PIPELINE
# =========================================================

def _execute_translation(
    *,
    state: TranslationState,
    target_language: str,
    target_language_code: str = "",
    restart_preview: bool = False,
    retry_failed: bool = False,
) -> TranslationControllerResult:
    """
    Execute manual translation through the Shared Translation
    Pipeline.

    IMPORTANT:

    The old Controller called translate_text() directly.

    The Controller now delegates to:

        run_manual_translation_pipeline()

    Therefore every manual translation receives:

        - automatic source-language detection
        - provider fallback for ambiguous language
        - TranslationPolicy decision
        - Translation Service validation
        - semantic / linguistic quality validation
        - bounded retry from ORIGINAL source
        - fail-closed behavior

    This function still does NOT publish anything.
    """

    language_state = (
        set_translation_language(
            state.review_id,
            restart_preview=restart_preview,
            **({"retry_failed": True} if retry_failed else {}),
            target_language=(
                target_language
            ),
            target_language_code=(
                target_language_code
            ),
        )
    )

    if language_state is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            reason=(
                "could_not_set_translation_language"
            ),
        )

    logger.info(
        "🌐 Translation pipeline started | "
        "review_id=%s | stored_source=%s | "
        "target=%s | code=%s",
        language_state.review_id,
        language_state.source_language,
        target_language,
        target_language_code,
    )

    try:

        policy = (
            _build_manual_translation_policy()
        )

        pipeline_result = (
            run_manual_translation_pipeline(
                text=(
                    language_state.original_text
                ),
                policy=policy,
                target_language=(
                    target_language
                ),
                content_kind=(
                    language_state.source_kind
                    or "text"
                ),
                semantic_quality=True,
                quality_retries=1,
            )
        )

    except Exception as exc:

        logger.exception(
            "❌ Translation pipeline raised error | "
            "review_id=%s | target=%s",
            language_state.review_id,
            target_language,
        )

        failed_state = (
            mark_translation_failed(
                language_state.review_id,
                reason=(
                    "translation_pipeline_error"
                ),
            )
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                "translation_pipeline_error"
            ),
            review_id=(
                language_state.review_id
            ),
            target_language=(
                target_language
            ),
            state=failed_state,
            reason=str(
                exc
            ),
            metadata={
                "pipeline_exception":
                    type(
                        exc
                    ).__name__,
            },
        )

    pipeline_success = bool(
        getattr(
            pipeline_result,
            "success",
            False,
        )
    )

    pipeline_status = str(
        getattr(
            pipeline_result,
            "status",
            "",
        )
        or ""
    ).strip()

    translated_text = (
        _pipeline_output_text(
            pipeline_result
        )
    )

    reason = (
        _pipeline_reason(
            pipeline_result
        )
    )

    attempts = (
        _pipeline_attempts(
            pipeline_result
        )
    )

    warnings = (
        _pipeline_warnings(
            pipeline_result
        )
    )

    translation_result = (
        _pipeline_translation_result(
            pipeline_result
        )
    )

    pipeline_state_metadata = (
        _build_pipeline_state_metadata(
            pipeline_result,
            target_language=(
                target_language
            ),
            target_language_code=(
                target_language_code
            ),
        )
    )

    # =====================================================
    # PIPELINE FAILURE / BLOCK
    # =====================================================

    if (
        not pipeline_success
        or pipeline_status
        in {
            PIPELINE_BLOCKED,
            PIPELINE_FAILED,
        }
        or not translated_text
    ):

        failed_state = (
            mark_translation_failed(
                language_state.review_id,
                reason=reason,
                metadata={
                    **pipeline_state_metadata,
                    "translation_retry_available": bool(
                        (pipeline_state_metadata.get("translation_pipeline_metadata") or {})
                        .get("provider_failure", {}).get("deferred")
                    ),
                },
            )
        )

        logger.warning(
            "⚠️ Translation pipeline failed | "
            "review_id=%s | status=%s | "
            "reason=%s | attempts=%s | warnings=%s",
            language_state.review_id,
            pipeline_status,
            reason,
            attempts,
            warnings,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                reason
            ),
            review_id=(
                language_state.review_id
            ),
            target_language=(
                target_language
            ),
            state=failed_state,
            translation_result=(
                translation_result
            ),
            reason=reason,
            metadata=(
                pipeline_state_metadata
            ),
        )

    # =====================================================
    # MANUAL TRANSLATION MUST NOT PASSTHROUGH
    # =====================================================
    #
    # A manual 🌐 request explicitly asks for translation.
    # If the shared pipeline unexpectedly returns passthrough,
    # we do not silently preview the original as translated.
    # =====================================================

    if pipeline_status == PIPELINE_PASSTHROUGH:

        failed_state = (
            mark_translation_failed(
                language_state.review_id,
                reason=(
                    "manual_translation_unexpected_passthrough"
                ),
            )
        )

        logger.error(
            "❌ Manual translation unexpectedly passthrough | "
            "review_id=%s | target=%s",
            language_state.review_id,
            target_language,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                "manual_translation_unexpected_passthrough"
            ),
            review_id=(
                language_state.review_id
            ),
            target_language=(
                target_language
            ),
            state=failed_state,
            translation_result=(
                translation_result
            ),
            reason=(
                "manual_translation_unexpected_passthrough"
            ),
            metadata=(
                pipeline_state_metadata
            ),
        )

    # =====================================================
    # ACCEPT ONLY TRANSLATED / REVIEW-REQUIRED
    # =====================================================

    if pipeline_status not in {
        PIPELINE_TRANSLATED,
        PIPELINE_REVIEW_REQUIRED,
    }:

        failed_state = (
            mark_translation_failed(
                language_state.review_id,
                reason=(
                    "unexpected_translation_pipeline_status"
                ),
            )
        )

        logger.error(
            "❌ Unexpected translation pipeline status | "
            "review_id=%s | status=%s",
            language_state.review_id,
            pipeline_status,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                "unexpected_translation_pipeline_status"
            ),
            review_id=(
                language_state.review_id
            ),
            target_language=(
                target_language
            ),
            state=failed_state,
            translation_result=(
                translation_result
            ),
            reason=(
                "unexpected_translation_pipeline_status"
            ),
            metadata=(
                pipeline_state_metadata
            ),
        )

    # =====================================================
    # MANUAL FLOW ALWAYS REQUIRES PREVIEW
    # =====================================================

    preview_state = (
        set_translation_preview(
            language_state.review_id,
            translated_text=(
                translated_text
            ),
            metadata=(
                pipeline_state_metadata
            ),
        )
    )

    if preview_state is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=(
                language_state.review_id
            ),
            translation_result=(
                translation_result
            ),
            reason=(
                "could_not_store_translation_preview"
            ),
            metadata=(
                pipeline_state_metadata
            ),
        )

    logger.info(
        "✅ Translation pipeline preview ready | "
        "review_id=%s | source=%s | "
        "target=%s | status=%s | "
        "attempts=%s | output_length=%s",
        preview_state.review_id,
        getattr(
            pipeline_result,
            "source_language",
            "auto",
        ),
        target_language,
        pipeline_status,
        attempts,
        len(
            translated_text
        ),
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_PREVIEW,
        text=build_translation_preview_text(
            target_language
        ),
        reply_markup=_keyboard_markup(
            build_translation_preview_keyboard(preview_state.review_id)
        ),
        review_id=(
            preview_state.review_id
        ),
        translated_text=(
            preview_state.translated_text
        ),
        target_language=(
            target_language
        ),
        state=preview_state,
        translation_result=(
            translation_result
        ),
        reason=(
            "translation_preview_ready"
        ),
        metadata=(
            pipeline_state_metadata
        ),
    )


# =========================================================
# REGISTERED LANGUAGE
# =========================================================

def select_translation_language(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
    language_code: str,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    language: Optional[
        TranslationLanguage
    ] = get_language(
        language_code
    )

    if language is None:

        logger.warning(
            "⚠️ Unknown translation language | "
            "review_id=%s | code=%s",
            review_id,
            language_code,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=review_id,
            state=state,
            reason=(
                "unknown_translation_language"
            ),
        )

    return _execute_translation(
        state=state,
        target_language=(
            language.english_name
        ),
        target_language_code=(
            language.code
        ),
    )


# =========================================================
# CUSTOM LANGUAGE SUBMISSION
# =========================================================

def submit_custom_translation_language(
    *,
    chat_id: int,
    user_id: int,
    target_language: str,
) -> TranslationControllerResult:

    state = (
        get_active_translation_state(
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    if (
        state.status
        != STATE_WAITING_CUSTOM_LANGUAGE
    ):

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=state.review_id,
            state=state,
            reason=(
                "not_waiting_for_custom_language"
            ),
        )

    language_name = str(
        target_language
        or ""
    ).strip()

    if not language_name:

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=state.review_id,
            state=state,
            reason=(
                "empty_custom_language"
            ),
        )

    if len(
        language_name
    ) > 80:

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=state.review_id,
            state=state,
            reason=(
                "custom_language_too_long"
            ),
        )

    return _execute_translation(
        state=state,
        target_language=(
            language_name
        ),
        target_language_code="custom",
    )


# =========================================================
# EDIT TRANSLATION
# =========================================================

def retry_translation(*, review_id: str, chat_id: int, user_id: int) -> TranslationControllerResult:
    state = get_translation_state(review_id)
    security = _state_security_check(state, chat_id=chat_id, user_id=user_id)
    if security:
        return security
    if not translation_retry_available(state):
        return TranslationControllerResult(
            success=False, action=RESULT_INVALID_STATE, review_id=review_id,
            reason="translation_retry_not_allowed",
        )
    return _execute_translation(
        state=state, target_language=state.target_language,
        target_language_code=state.target_language_code, retry_failed=True,
    )


def retranslate_translation(*, review_id: str, chat_id: int, user_id: int,
                            replace_edit: bool = False) -> TranslationControllerResult:
    state = get_translation_state(review_id)
    security = _state_security_check(state, chat_id=chat_id, user_id=user_id)
    if security:
        return security
    if state.status != STATE_PREVIEW or (state.edited_text and not replace_edit):
        return TranslationControllerResult(
            success=False, action=RESULT_INVALID_STATE, review_id=review_id,
            reason="translation_restart_not_allowed", state=state,
        )
    return _execute_translation(
        state=state, target_language=state.target_language,
        target_language_code=state.target_language_code, restart_preview=True,
    )


def request_translation_edit(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    if state.status != STATE_PREVIEW:

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=review_id,
            state=state,
            reason=(
                "translation_not_in_preview"
            ),
        )

    updated = (
        mark_waiting_translation_edit(
            review_id
        )
    )

    if updated is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason=(
                "could_not_enter_translation_edit"
            ),
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_EDIT_INPUT,
        text=(
            "✏️ متن ترجمه‌شده را اصلاح کنید.\n\n"
            "نسخه کامل اصلاح‌شده را در پیام بعدی "
            "ارسال کنید."
        ),
        review_id=review_id,
        translated_text=(
            state.edited_text or state.translated_text
        ),
        target_language=(
            state.target_language
        ),
        state=updated,
    )


# =========================================================
# SUBMIT MANUAL EDIT
# =========================================================

def submit_translation_edit(
    *,
    chat_id: int,
    user_id: int,
    translated_text: str,
) -> TranslationControllerResult:

    state = (
        get_active_translation_state(
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    if (
        state.status
        != STATE_WAITING_EDIT
    ):

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=state.review_id,
            state=state,
            reason=(
                "not_waiting_for_translation_edit"
            ),
        )

    text = str(
        translated_text
        or ""
    ).strip()

    if not text:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            state=state,
            reason=(
                "empty_translation_edit"
            ),
        )

    updated = (
        apply_translation_edit(
            state.review_id,
            translated_text=text,
        )
    )

    if updated is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            reason=(
                "could_not_apply_translation_edit"
            ),
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_PREVIEW,
        text=build_translation_preview_text(
            updated.target_language
        ),
        reply_markup=_keyboard_markup(
            build_translation_preview_keyboard(updated.review_id)
        ),
        review_id=updated.review_id,
        translated_text=(
            updated.edited_text or updated.translated_text
        ),
        target_language=(
            updated.target_language
        ),
        state=updated,
        reason=(
            "translation_edit_applied"
        ),
    )


# =========================================================
# CONFIRM TRANSLATION
# =========================================================

def confirm_translation(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    confirmed = (
        confirm_translation_state(
            review_id
        )
    )

    if confirmed is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=review_id,
            state=state,
            reason=(
                "translation_cannot_be_confirmed"
            ),
        )

    logger.info(
        "✅ Translation confirmed | "
        "review_id=%s | target=%s | "
        "source_kind=%s",
        confirmed.review_id,
        confirmed.target_language,
        confirmed.source_kind,
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_CONFIRMED,
        review_id=confirmed.review_id,
        translated_text=(
            confirmed.edited_text or confirmed.translated_text
        ),
        target_language=(
            confirmed.target_language
        ),
        state=confirmed,
        reason="translation_confirmed",
        metadata={
            "source_kind":
                confirmed.source_kind,

            "source_key":
                confirmed.source_key,

            "original_text":
                confirmed.original_text,

            **dict(
                confirmed.metadata
                or {}
            ),
        },
    )


# =========================================================
# CANCEL
# =========================================================

def cancel_translation(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    cancelled = (
        cancel_translation_state(
            review_id
        )
    )

    if cancelled is None:

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason=(
                "translation_cancel_failed"
            ),
        )

    logger.info(
        "❌ Translation workflow cancelled | "
        "review_id=%s",
        review_id,
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_CANCELLED,
        text="❌ ترجمه لغو شد.",
        review_id=review_id,
        state=cancelled,
        reason=(
            "translation_cancelled"
        ),
    )


# =========================================================
# ORIGINAL TEXT
# =========================================================

def get_translation_original(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:

    state = get_translation_state(
        review_id
    )

    security_result = (
        _state_security_check(
            state,
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if security_result:
        return security_result

    return TranslationControllerResult(
        success=True,
        action=RESULT_ORIGINAL,
        text=state.original_text,
        review_id=review_id,
        translated_text=(
            state.translated_text
        ),
        target_language=(
            state.target_language
        ),
        state=state,
    )


# =========================================================
# ACTIVE TEXT INPUT ROUTER
# =========================================================

def handle_translation_text_input(
    *,
    chat_id: int,
    user_id: int,
    text: str,
) -> Optional[
    TranslationControllerResult
]:
    """
    Translation Pending Guard.

    Only consumes the next text message when Translation
    explicitly expects text input:

    - custom target language
    - manual translation edit

    Otherwise returns None so the existing webhook continues
    through its normal Editorial / External Review /
    Publication flow.
    """

    state = (
        get_active_translation_state(
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if state is None:
        return None

    if (
        state.status
        == STATE_WAITING_CUSTOM_LANGUAGE
    ):

        return (
            submit_custom_translation_language(
                chat_id=chat_id,
                user_id=user_id,
                target_language=text,
            )
        )

    if (
        state.status
        == STATE_WAITING_EDIT
    ):

        return submit_translation_edit(
            chat_id=chat_id,
            user_id=user_id,
            translated_text=text,
        )

    return None


# =========================================================
# CLEANUP AFTER PUBLICATION
# =========================================================

def complete_translation_workflow(
    review_id: str,
) -> bool:
    """
    Called only AFTER the existing Shared Publication Engine
    accepts/completes the confirmed translated publication.

    This function never publishes content itself.
    """

    removed = remove_translation_state(
        review_id
    )

    if removed is None:
        return False

    logger.info(
        "🧹 Translation workflow completed | "
        "review_id=%s",
        review_id,
    )

    return True
