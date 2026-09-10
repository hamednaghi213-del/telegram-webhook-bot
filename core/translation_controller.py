from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.translation_provider import (
    get_default_translation_provider,
    get_translation_provider_status,
)

from core.translation_service import (
    TranslationRequest,
    TranslationResult,
    translate_text_safely,
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
# NEW FILE
#
# این فایل چهار بخش Translation را به هم وصل می‌کند:
#
# translation_service.py
# translation_provider.py
# translation_ui.py
# translation_state.py
#
# Flow:
#
# User content
#      ↓
# start_translation()
#      ↓
# Language menu
#      ↓
# select_translation_language()
#      ↓
# Gemini Provider
#      ↓
# Safe Translation + Validation
#      ↓
# Translation Preview
#      ↓
# Confirm / Edit / Cancel
#
# این فایل هنوز:
#
# - مستقیم Telegram API را صدا نمی‌زند.
# - مستقیم Bale API را صدا نمی‌زند.
# - Publication Engine را صدا نمی‌زند.
# - Legacy / Workspace را تغییر نمی‌دهد.
#
# مرحله بعد، همین Controller از webhook/callback handler
# فراخوانی خواهد شد.
#
# =========================================================


# =========================================================
# RESULT TYPES
# =========================================================

RESULT_LANGUAGE_MENU = "language_menu"

RESULT_MORE_LANGUAGES = "more_languages"

RESULT_CUSTOM_LANGUAGE_INPUT = "custom_language_input"

RESULT_TRANSLATING = "translating"

RESULT_PREVIEW = "preview"

RESULT_EDIT_INPUT = "edit_input"

RESULT_CONFIRMED = "confirmed"

RESULT_CANCELLED = "cancelled"

RESULT_FAILED = "failed"

RESULT_NOT_FOUND = "not_found"

RESULT_FORBIDDEN = "forbidden"

RESULT_INVALID_LANGUAGE = "invalid_language"

RESULT_INVALID_STATE = "invalid_state"


# =========================================================
# CONTROLLER RESULT
# =========================================================

@dataclass(frozen=True)
class TranslationControllerResult:
    success: bool

    action: str

    text: str = ""

    reply_markup: Optional[Dict[str, Any]] = None

    review_id: str = ""

    translated_text: str = ""

    target_language: str = ""

    state: Optional[TranslationState] = None

    translation_result: Optional[TranslationResult] = None

    reason: str = ""

    metadata: Optional[Dict[str, Any]] = None


# =========================================================
# GENERIC HELPERS
# =========================================================

def _keyboard_markup(
    keyboard
) -> Dict[str, Any]:
    return keyboard_to_telegram_markup(
        keyboard
    )


def _state_security_check(
    state: Optional[TranslationState],
    *,
    chat_id: int,
    user_id: int,
) -> Optional[TranslationControllerResult]:
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
            reason="translation_state_forbidden",
        )

    return None


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
    metadata: Optional[Dict[str, Any]] = None,
) -> TranslationControllerResult:
    """
    شروع Session ترجمه.

    این تابع متن را ترجمه نمی‌کند.
    فقط State می‌سازد و منوی انتخاب زبان را برمی‌گرداند.
    """

    text = str(
        original_text or ""
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
            reason=str(exc),
        )

    logger.info(
        "🌐 Translation workflow started | "
        "review_id=%s | chat_id=%s | user_id=%s | "
        "source_kind=%s",
        state.review_id,
        chat_id,
        user_id,
        source_kind,
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_LANGUAGE_MENU,
        text=build_language_selection_text(),
        reply_markup=_keyboard_markup(
            build_language_keyboard()
        ),
        review_id=state.review_id,
        state=state,
    )


# =========================================================
# SHOW LANGUAGE MENU
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    return TranslationControllerResult(
        success=True,
        action=RESULT_LANGUAGE_MENU,
        text=build_language_selection_text(),
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
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
# CUSTOM LANGUAGE MODE
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    updated = mark_waiting_custom_language(
        review_id
    )

    if updated is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason="could_not_mark_custom_language_wait",
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_CUSTOM_LANGUAGE_INPUT,
        text=build_custom_language_prompt(),
        review_id=review_id,
        state=updated,
    )


# =========================================================
# TRANSLATION ENGINE EXECUTION
# =========================================================

def _execute_translation(
    *,
    state: TranslationState,
    target_language: str,
    target_language_code: str = "",
) -> TranslationControllerResult:
    provider = get_default_translation_provider()

    if provider is None:
        provider_status = (
            get_translation_provider_status()
        )

        failed_state = mark_translation_failed(
            state.review_id,
            reason=provider_status.reason,
        )

        logger.error(
            "❌ Translation provider unavailable | "
            "review_id=%s | provider=%s | model=%s | reason=%s",
            state.review_id,
            provider_status.provider,
            provider_status.model,
            provider_status.reason,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                provider_status.reason
            ),
            review_id=state.review_id,
            target_language=target_language,
            state=failed_state,
            reason=provider_status.reason,
        )

    language_state = set_translation_language(
        state.review_id,
        target_language=target_language,
        target_language_code=target_language_code,
    )

    if language_state is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            reason="could_not_set_translation_language",
        )

    request = TranslationRequest(
        text=language_state.original_text,
        source_language=(
            language_state.source_language
        ),
        target_language=target_language,
        metadata={
            **dict(
                language_state.metadata
            ),
            "review_id": (
                language_state.review_id
            ),
            "source_kind": (
                language_state.source_kind
            ),
            "source_key": (
                language_state.source_key
            ),
        },
    )

    logger.info(
        "🌐 Translation execution started | "
        "review_id=%s | source=%s | target=%s | code=%s",
        language_state.review_id,
        language_state.source_language,
        target_language,
        target_language_code,
    )

    result = translate_text_safely(
        request=request,
        provider=provider,
    )

    if (
        not result.success
        or not result.validation_passed
    ):
        failed_state = mark_translation_failed(
            language_state.review_id,
            reason=result.reason,
        )

        logger.warning(
            "⚠️ Translation workflow failed | "
            "review_id=%s | reason=%s | attempts=%s | "
            "validation_errors=%s",
            language_state.review_id,
            result.reason,
            result.attempts,
            list(
                result.validation.errors
            ),
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            text=build_translation_failed_text(
                result.reason
            ),
            review_id=language_state.review_id,
            target_language=target_language,
            state=failed_state,
            translation_result=result,
            reason=result.reason,
        )

    preview_state = set_translation_preview(
        language_state.review_id,
        translated_text=(
            result.translated_text
        ),
        metadata={
            "translation_attempts": (
                result.attempts
            ),
            "translation_validation_passed": (
                result.validation_passed
            ),
            "translation_validation_warnings": list(
                result.validation.warnings
            ),
            "translation_target_language": (
                target_language
            ),
            "translation_target_language_code": (
                target_language_code
            ),
        },
    )

    if preview_state is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=language_state.review_id,
            translation_result=result,
            reason="could_not_store_translation_preview",
        )

    logger.info(
        "✅ Translation preview ready | "
        "review_id=%s | target=%s | attempts=%s | "
        "output_length=%s",
        preview_state.review_id,
        target_language,
        result.attempts,
        len(
            result.translated_text
        ),
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_PREVIEW,
        text=build_translation_preview_text(
            target_language
        ),
        reply_markup=_keyboard_markup(
            build_translation_preview_keyboard()
        ),
        review_id=preview_state.review_id,
        translated_text=(
            preview_state.translated_text
        ),
        target_language=target_language,
        state=preview_state,
        translation_result=result,
        reason="translation_preview_ready",
    )


# =========================================================
# SELECT REGISTERED LANGUAGE
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
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
            "⚠️ Unknown translation language code | "
            "review_id=%s | code=%s",
            review_id,
            language_code,
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=review_id,
            reason="unknown_translation_language",
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
# SELECT CUSTOM LANGUAGE
# =========================================================

def submit_custom_translation_language(
    *,
    chat_id: int,
    user_id: int,
    target_language: str,
) -> TranslationControllerResult:
    state = get_active_translation_state(
        chat_id=chat_id,
        user_id=user_id,
    )

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
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
            reason="not_waiting_for_custom_language",
        )

    language_name = str(
        target_language or ""
    ).strip()

    if not language_name:
        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=state.review_id,
            state=state,
            reason="empty_custom_language",
        )

    # جلوگیری از ورودی‌های غیرمنطقی و متن‌های بسیار طولانی
    if len(language_name) > 80:
        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_LANGUAGE,
            review_id=state.review_id,
            state=state,
            reason="custom_language_too_long",
        )

    return _execute_translation(
        state=state,
        target_language=language_name,
        target_language_code="custom",
    )


# =========================================================
# EDIT TRANSLATION
# =========================================================

def request_translation_edit(
    *,
    review_id: str,
    chat_id: int,
    user_id: int,
) -> TranslationControllerResult:
    state = get_translation_state(
        review_id
    )

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    if state.status != STATE_PREVIEW:
        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=review_id,
            state=state,
            reason="translation_not_in_preview",
        )

    updated = mark_waiting_translation_edit(
        review_id
    )

    if updated is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason="could_not_enter_translation_edit",
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_EDIT_INPUT,
        text=(
            "✏️ متن ترجمه‌شده را اصلاح کنید.\n\n"
            "نسخه کامل اصلاح‌شده را در پیام بعدی ارسال کنید."
        ),
        review_id=review_id,
        translated_text=(
            state.translated_text
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
    state = get_active_translation_state(
        chat_id=chat_id,
        user_id=user_id,
    )

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    if state.status != STATE_WAITING_EDIT:
        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=state.review_id,
            state=state,
            reason="not_waiting_for_translation_edit",
        )

    text = str(
        translated_text or ""
    ).strip()

    if not text:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            state=state,
            reason="empty_translation_edit",
        )

    updated = apply_translation_edit(
        state.review_id,
        translated_text=text,
    )

    if updated is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=state.review_id,
            reason="could_not_apply_translation_edit",
        )

    return TranslationControllerResult(
        success=True,
        action=RESULT_PREVIEW,
        text=build_translation_preview_text(
            updated.target_language
        ),
        reply_markup=_keyboard_markup(
            build_translation_preview_keyboard()
        ),
        review_id=updated.review_id,
        translated_text=updated.translated_text,
        target_language=updated.target_language,
        state=updated,
        reason="translation_edit_applied",
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    confirmed = confirm_translation_state(
        review_id
    )

    if confirmed is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_INVALID_STATE,
            review_id=review_id,
            state=state,
            reason="translation_cannot_be_confirmed",
        )

    logger.info(
        "✅ Translation confirmed | "
        "review_id=%s | target=%s | source_kind=%s",
        confirmed.review_id,
        confirmed.target_language,
        confirmed.source_kind,
    )

    return TranslationControllerResult(
        success=True,
        action=RESULT_CONFIRMED,
        review_id=confirmed.review_id,
        translated_text=confirmed.translated_text,
        target_language=confirmed.target_language,
        state=confirmed,
        reason="translation_confirmed",
        metadata={
            "source_kind": (
                confirmed.source_kind
            ),
            "source_key": (
                confirmed.source_key
            ),
            "original_text": (
                confirmed.original_text
            ),
        },
    )


# =========================================================
# CANCEL TRANSLATION
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    cancelled = cancel_translation_state(
        review_id
    )

    if cancelled is None:
        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            review_id=review_id,
            reason="translation_cancel_failed",
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
        reason="translation_cancelled",
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

    security_result = _state_security_check(
        state,
        chat_id=chat_id,
        user_id=user_id,
    )

    if security_result:
        return security_result

    return TranslationControllerResult(
        success=True,
        action="original",
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
) -> Optional[TranslationControllerResult]:
    """
    Pending Guard مخصوص Translation.

    اگر کاربر در مرحله دریافت:
    - زبان دلخواه
    - یا متن اصلاح‌شده

    باشد، پیام بعدی باید ابتدا توسط Translation مصرف شود
    و نباید وارد مسیر Normal Publication شود.

    اگر Translation Pending وجود نداشته باشد:
    None برمی‌گرداند تا Webhook مسیر عادی خود را ادامه دهد.
    """

    state = get_active_translation_state(
        chat_id=chat_id,
        user_id=user_id,
    )

    if state is None:
        return None

    if (
        state.status
        == STATE_WAITING_CUSTOM_LANGUAGE
    ):
        return submit_custom_translation_language(
            chat_id=chat_id,
            user_id=user_id,
            target_language=text,
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
    review_id: str
) -> bool:
    """
    بعد از اینکه Shared Publication Engine انتشار تأییدشده
    را دریافت کرد، State موقت ترجمه حذف می‌شود.

    این تابع Publication را انجام نمی‌دهد.
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
