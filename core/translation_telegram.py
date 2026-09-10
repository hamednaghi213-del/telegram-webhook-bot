from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from core.translation_controller import (
    RESULT_CANCELLED,
    RESULT_CONFIRMED,
    RESULT_CUSTOM_LANGUAGE_INPUT,
    RESULT_EDIT_INPUT,
    RESULT_FAILED,
    RESULT_INVALID_LANGUAGE,
    RESULT_INVALID_STATE,
    RESULT_LANGUAGE_MENU,
    RESULT_MORE_LANGUAGES,
    RESULT_NOT_FOUND,
    RESULT_ORIGINAL,
    RESULT_PREVIEW,
    TranslationControllerResult,
    cancel_translation,
    confirm_translation,
    get_translation_original,
    request_custom_translation_language,
    request_translation_edit,
    select_translation_language,
    show_more_translation_languages,
    show_translation_language_menu,
)

from core.translation_state import (
    get_active_translation_state,
)

from core.translation_ui import (
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_CONFIRM,
    ACTION_CUSTOM,
    ACTION_EDIT,
    ACTION_LANGUAGE,
    ACTION_MORE,
    ACTION_OPEN,
    ACTION_ORIGINAL,
    is_translation_callback,
    parse_translation_callback,
)


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION TELEGRAM ADAPTER
# =========================================================
#
# NEW FILE
#
# Telegram-specific adapter for the shared Translation flow.
#
# Responsibilities:
#
# - recognize tr:* callbacks
# - resolve user/chat identity
# - resolve active TranslationState
# - route callbacks to TranslationController
# - render controller results in Telegram
#
# It DOES NOT:
#
# - translate content itself
# - call Gemini directly
# - create publication logic
# - duplicate PublicationPlan
# - change Legacy / Workspace routing
#
# Confirmed content is returned to the caller.
# Publication remains the responsibility of the Shared Engine.
#
# =========================================================


SendMessage = Callable[..., Any]
AnswerCallback = Callable[..., Any]


# =========================================================
# CALLBACK HELPERS
# =========================================================

def _callback_id(
    callback_query: Dict[str, Any],
) -> str:
    return str(
        callback_query.get(
            "id",
            "",
        )
        or ""
    )


def _callback_data(
    callback_query: Dict[str, Any],
) -> str:
    return str(
        callback_query.get(
            "data",
            "",
        )
        or ""
    )


def _callback_user_id(
    callback_query: Dict[str, Any],
) -> Optional[int]:

    value = (
        callback_query.get(
            "from",
            {},
        )
        or {}
    ).get(
        "id"
    )

    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _callback_chat_id(
    callback_query: Dict[str, Any],
) -> Optional[int]:

    message = (
        callback_query.get(
            "message",
            {},
        )
        or {}
    )

    chat = (
        message.get(
            "chat",
            {},
        )
        or {}
    )

    value = chat.get(
        "id"
    )

    if value is None:
        return _callback_user_id(
            callback_query
        )

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


# =========================================================
# ACTIVE REVIEW
# =========================================================

def _active_review_id(
    *,
    chat_id: int,
    user_id: int,
) -> str:

    state = (
        get_active_translation_state(
            chat_id=chat_id,
            user_id=user_id,
        )
    )

    if state is None:
        return ""

    return str(
        state.review_id
        or ""
    )


# =========================================================
# TELEGRAM RESULT RENDERER
# =========================================================

def render_translation_result(
    *,
    result: TranslationControllerResult,
    chat_id: int,
    send_message: SendMessage,
) -> None:

    # -----------------------------------------
    # PREVIEW
    # -----------------------------------------

    if result.action == RESULT_PREVIEW:

        preview_text = str(
            result.translated_text
            or ""
        ).strip()

        header = str(
            result.text
            or ""
        ).strip()

        if header and preview_text:
            output = (
                f"{header}\n\n"
                f"{preview_text}"
            )

        else:
            output = (
                preview_text
                or header
                or "ترجمه آماده است."
            )

        send_message(
            chat_id,
            output,
            reply_markup=(
                result.reply_markup
            ),
        )

        return

    # -----------------------------------------
    # ORIGINAL
    # -----------------------------------------

    if result.action == RESULT_ORIGINAL:

        send_message(
            chat_id,
            result.text
            or "متن اصلی در دسترس نیست.",
        )

        return

    # -----------------------------------------
    # CONFIRMED
    # -----------------------------------------

    if result.action == RESULT_CONFIRMED:

        send_message(
            chat_id,
            (
                "✅ ترجمه تأیید شد.\n\n"
                "نسخه ترجمه‌شده برای مرحله انتشار "
                "آماده است."
            ),
        )

        return

    # -----------------------------------------
    # CANCELLED
    # -----------------------------------------

    if result.action == RESULT_CANCELLED:

        send_message(
            chat_id,
            result.text
            or "❌ ترجمه لغو شد.",
        )

        return

    # -----------------------------------------
    # FAILURES
    # -----------------------------------------

    if result.action in {
        RESULT_FAILED,
        RESULT_NOT_FOUND,
        RESULT_INVALID_LANGUAGE,
        RESULT_INVALID_STATE,
    }:

        send_message(
            chat_id,
            result.text
            or (
                "❌ انجام این مرحله ترجمه ممکن نشد. "
                "لطفاً دوباره تلاش کنید."
            ),
        )

        return

    # -----------------------------------------
    # NORMAL CONTROLLER MESSAGE
    # -----------------------------------------

    if result.text:

        send_message(
            chat_id,
            result.text,
            reply_markup=(
                result.reply_markup
            ),
        )


# =========================================================
# TRANSLATION CALLBACK ROUTER
# =========================================================

def handle_translation_telegram_callback(
    *,
    callback_query: Dict[str, Any],
    answer_callback_query: AnswerCallback,
    send_message: SendMessage,
    req_id: str = "",
) -> Optional[
    TranslationControllerResult
]:

    callback_data = _callback_data(
        callback_query
    )

    if not is_translation_callback(
        callback_data
    ):
        return None

    callback_id = _callback_id(
        callback_query
    )

    user_id = _callback_user_id(
        callback_query
    )

    chat_id = _callback_chat_id(
        callback_query
    )

    if (
        user_id is None
        or chat_id is None
    ):

        answer_callback_query(
            callback_id,
            "کاربر قابل تشخیص نیست.",
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            reason="telegram_identity_missing",
        )

    parsed = parse_translation_callback(
        callback_data
    )

    if not parsed.valid:

        answer_callback_query(
            callback_id,
            "دستور ترجمه نامعتبر است.",
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_FAILED,
            reason="invalid_translation_callback",
        )

    review_id = _active_review_id(
        chat_id=chat_id,
        user_id=user_id,
    )

    # tr:open is only valid after the caller has created
    # TranslationState from the actual source content.
    #
    # This prevents the Telegram adapter from guessing which
    # message/review should be translated.

    if parsed.action == ACTION_OPEN:

        if not review_id:

            answer_callback_query(
                callback_id,
                "محتوایی برای ترجمه انتخاب نشده است.",
            )

            return TranslationControllerResult(
                success=False,
                action=RESULT_NOT_FOUND,
                reason="translation_source_not_initialized",
            )

        answer_callback_query(
            callback_id,
            "انتخاب زبان",
        )

        result = (
            show_translation_language_menu(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    if not review_id:

        answer_callback_query(
            callback_id,
            "این درخواست ترجمه منقضی شده است.",
        )

        return TranslationControllerResult(
            success=False,
            action=RESULT_NOT_FOUND,
            reason="translation_state_not_found",
        )

    # -----------------------------------------
    # LANGUAGE
    # -----------------------------------------

    if parsed.action == ACTION_LANGUAGE:

        language_code = str(
            parsed.value
            or ""
        ).strip()

        if not language_code:

            answer_callback_query(
                callback_id,
                "زبان نامعتبر است.",
            )

            return TranslationControllerResult(
                success=False,
                action=RESULT_INVALID_LANGUAGE,
                review_id=review_id,
                reason="missing_language_code",
            )

        answer_callback_query(
            callback_id,
            "در حال ترجمه...",
        )

        result = (
            select_translation_language(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
                language_code=language_code,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # MORE LANGUAGES
    # -----------------------------------------

    if parsed.action == ACTION_MORE:

        try:
            page = int(
                parsed.value
                or parsed.page
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            page = 0

        answer_callback_query(
            callback_id,
            "زبان‌های بیشتر",
        )

        result = (
            show_more_translation_languages(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
                page=page,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # BACK
    # -----------------------------------------

    if parsed.action == ACTION_BACK:

        answer_callback_query(
            callback_id,
            "بازگشت",
        )

        result = (
            show_translation_language_menu(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # CUSTOM LANGUAGE
    # -----------------------------------------

    if parsed.action == ACTION_CUSTOM:

        answer_callback_query(
            callback_id,
            "زبان دلخواه",
        )

        result = (
            request_custom_translation_language(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # EDIT
    # -----------------------------------------

    if parsed.action == ACTION_EDIT:

        answer_callback_query(
            callback_id,
            "اصلاح ترجمه",
        )

        result = (
            request_translation_edit(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # ORIGINAL
    # -----------------------------------------

    if parsed.action == ACTION_ORIGINAL:

        answer_callback_query(
            callback_id,
            "متن اصلی",
        )

        result = (
            get_translation_original(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # CANCEL
    # -----------------------------------------

    if parsed.action == ACTION_CANCEL:

        answer_callback_query(
            callback_id,
            "ترجمه لغو شد.",
        )

        result = (
            cancel_translation(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # -----------------------------------------
    # CONFIRM
    # -----------------------------------------

    if parsed.action == ACTION_CONFIRM:

        answer_callback_query(
            callback_id,
            "ترجمه تأیید شد.",
        )

        result = (
            confirm_translation(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        # IMPORTANT:
        #
        # We intentionally DO NOT publish here.
        #
        # The caller receives RESULT_CONFIRMED and will hand
        # the translated content to the existing Shared
        # Publication Engine in the integration stage.

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    answer_callback_query(
        callback_id,
        "دستور ترجمه شناخته نشد.",
    )

    logger.warning(
        "[%s] ⚠️ Unknown translation callback | "
        "data=%s | user=%s",
        req_id,
        callback_data,
        user_id,
    )

    return TranslationControllerResult(
        success=False,
        action=RESULT_FAILED,
        review_id=review_id,
        reason="unknown_translation_callback",
    )
