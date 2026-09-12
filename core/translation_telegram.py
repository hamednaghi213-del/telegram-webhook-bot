from __future__ import annotations

import logging

from typing import (
    Any,
    Callable,
    Dict,
    Optional,
)


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
    retranslate_translation,
    select_translation_language,
    show_more_translation_languages,
    show_translation_language_menu,
)

from core.translation_publication import (
    publish_confirmed_translation,
    translation_publication_message,
    translation_ui_message,
    build_translation_publication_payload,
)

from core.translation_state import (
    get_active_translation_state,
    get_translation_state,
    ACTIVE_STATES,
)

from core.translation_ui import (
    build_edited_translation_preview_text,
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_CONFIRM,
    ACTION_CUSTOM,
    ACTION_EDIT,
    ACTION_LANGUAGE,
    ACTION_MORE,
    ACTION_OPEN,
    ACTION_ORIGINAL,
    ACTION_RETRANSLATE,
    ACTION_RETRANSLATE_CONFIRM,
    build_translation_callback,
    is_translation_callback,
    parse_translation_callback,
)


logger = logging.getLogger(__name__)


# =========================================================
# TELEGRAM TRANSLATION CALLBACK ADAPTER
# =========================================================
#
# Responsibilities:
#
# Telegram callback
#       ↓
# Translation Controller
#       ↓
# Translation Review
#       ↓
# Confirm
#       ↓
# Translation Publication Bridge
#       ↓
# Existing Shared Publication Engine
#
# IMPORTANT:
#
# - No direct Telegram channel publication.
# - No direct Bale publication.
# - No duplicate Publication Engine.
# - Final publication is delegated to:
#
#       publish_confirmed_translation()
#
# which itself reuses the existing:
#
#       publish_prepared_text()
#
# =========================================================


SendMessage = Callable[..., Any]

AnswerCallback = Callable[..., Any]

PublishPreparedText = Callable[..., Any]


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
    ).strip()


def _callback_data(
    callback_query: Dict[str, Any],
) -> str:

    return str(
        callback_query.get(
            "data",
            "",
        )
        or ""
    ).strip()


def _callback_user_id(
    callback_query: Dict[str, Any],
) -> Optional[int]:

    from_user = (
        callback_query.get(
            "from",
            {},
        )
        or {}
    )

    user_id = (
        from_user.get(
            "id"
        )
    )

    if user_id is None:
        return None

    try:

        return int(
            user_id
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

    chat_id = (
        chat.get(
            "id"
        )
    )

    if chat_id is None:

        # In private bot conversations Telegram user_id and
        # chat_id are normally identical. Keep this fallback
        # for callbacks whose message envelope is unavailable.
        return _callback_user_id(
            callback_query
        )

    try:

        return int(
            chat_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


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
        getattr(
            state,
            "review_id",
            "",
        )
        or ""
    ).strip()


# =========================================================
# RESULT FACTORY
# =========================================================

def _controller_result(
    *,
    success: bool,
    action: str,
    text: str = "",
    review_id: str = "",
    reason: str = "",
) -> TranslationControllerResult:

    return TranslationControllerResult(
        success=success,
        action=action,
        text=text,
        review_id=review_id,
        reason=reason,
    )


# =========================================================
# RESULT RENDERER
# =========================================================

def render_translation_result(
    *,
    result: TranslationControllerResult,
    chat_id: int,
    send_message: SendMessage,
    review_id: str = "",
) -> None:
    """
    Convert TranslationControllerResult to Telegram user
    messages.

    Publication itself is NOT performed here.
    """

    if result is None:
        return

    review_id = getattr(result, "review_id", "") or review_id
    original_send_message = send_message

    def send_message(chat_id, text, **kwargs):
        return original_send_message(
            chat_id, translation_ui_message(text, review_id),
            **dict(kwargs, link_preview_options={"is_disabled": True})
        )

    action = str(
        getattr(
            result,
            "action",
            "",
        )
        or ""
    )

    text = str(
        getattr(
            result,
            "text",
            "",
        )
        or ""
    ).strip()

    reply_markup = getattr(
        result,
        "reply_markup",
        None,
    )

    # Bind Cancel on language menus too; old generic callbacks never resolve
    # to a different active review. Copy markup rather than mutate its owner.
    if reply_markup and review_id:
        reply_markup = dict(reply_markup)
        reply_markup["inline_keyboard"] = [
            [dict(button, callback_data=build_translation_callback(ACTION_CANCEL, review_id))
             if button.get("callback_data") == "tr:cancel" else dict(button)
             for button in row]
            for row in reply_markup.get("inline_keyboard", [])
        ]

    translated_text = str(
        getattr(
            result,
            "translated_text",
            "",
        )
        or ""
    ).strip()

    # =====================================================
    # TRANSLATION PREVIEW
    # =====================================================

    if action == RESULT_PREVIEW:

        parts = []

        state = getattr(result, "state", None)
        if state is None:
            state = get_translation_state(review_id)
        try:
            if state is None:
                raise ValueError("preview_state_missing")
            translated_text = build_translation_publication_payload(state)["main_text"]
            if not translated_text.strip():
                raise ValueError("preview_content_empty")
        except Exception:
            logger.exception("Translation preview preparation failed | review_id=%s", review_id)
            send_message(chat_id, "❌ آماده‌سازی پیش‌نمایش ممکن نشد؛ دوباره تلاش کنید.")
            return

        metadata = getattr(state, "metadata", {}) or {}
        policy = (metadata.get("translation_pipeline_metadata") or {}).get("editorial_policy") or {}
        if policy.get("status") == "review_required":
            parts.append("⚠️ این ترجمه به دلیل اصطلاحات حساس تحریریه نیاز به بازبینی دارد؛ پیش از تأیید، واژه‌ها و بافت جمله را بررسی کنید.")

        if getattr(state, "edited_text", ""):
            text = build_edited_translation_preview_text()
        if text:
            parts.append(
                text
            )

        if translated_text:
            if getattr(state, "edited_text", ""):
                parts.append("──────────\n" + translated_text + "\n──────────")
            else:
                parts.append(translated_text)

        preview = "\n\n".join(
            part
            for part in parts
            if part
        ).strip()

        if not preview:
            preview = (
                "🌐 ترجمه آماده بررسی است."
            )

        send_message(
            chat_id,
            preview,
            reply_markup=reply_markup,
        )

        return

    # =====================================================
    # ORIGINAL TEXT
    # =====================================================

    if action == RESULT_ORIGINAL:

        if text:

            send_message(
                chat_id,
                text,
                reply_markup=reply_markup,
            )

        return

    # =====================================================
    # CONFIRM
    # =====================================================

    if action == RESULT_CONFIRMED:

        # Final publication acknowledgement is sent by the
        # publication bridge section after actual Shared
        # Engine execution.
        return

    # =====================================================
    # CANCEL
    # =====================================================

    if action == RESULT_CANCELLED:

        send_message(
            chat_id,
            text
            or "❌ ترجمه لغو شد.",
            reply_markup=reply_markup,
        )

        return

    # =====================================================
    # ERRORS
    # =====================================================

    if action in {
        RESULT_FAILED,
        RESULT_NOT_FOUND,
        RESULT_INVALID_LANGUAGE,
        RESULT_INVALID_STATE,
    }:

        send_message(
            chat_id,
            text
            or "❌ پردازش ترجمه با خطا روبرو شد.",
            reply_markup=reply_markup,
        )

        return

    # =====================================================
    # NORMAL CONTROLLER MESSAGE
    # =====================================================

    if text:

        send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
        )


# =========================================================
# CALLBACK HANDLER
# =========================================================

def handle_translation_telegram_callback(
    *,
    callback_query: Dict[str, Any],
    answer_callback_query: AnswerCallback,
    send_message: SendMessage,
    publish_prepared_text: PublishPreparedText,
    req_id: str = "",
) -> Optional[
    TranslationControllerResult
]:
    """
    Handle Telegram callbacks beginning with:

        tr:

    Returns:
        None
            callback does not belong to Translation

        TranslationControllerResult
            callback was handled

    IMPORTANT:

    `publish_prepared_text` is injected by webhook_handler so
    Translation never owns a separate publication engine.
    """

    original_send_message = send_message

    def send_message(chat_id, text, **kwargs):
        return original_send_message(
            chat_id, text, **dict(kwargs, link_preview_options={"is_disabled": True})
        )

    callback_data = (
        _callback_data(
            callback_query
        )
    )

    if not is_translation_callback(
        callback_data
    ):

        return None

    callback_id = (
        _callback_id(
            callback_query
        )
    )

    user_id = (
        _callback_user_id(
            callback_query
        )
    )

    chat_id = (
        _callback_chat_id(
            callback_query
        )
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    if (
        user_id is None
        or chat_id is None
    ):

        answer_callback_query(
            callback_id,
            "کاربر قابل تشخیص نیست."
        )

        return _controller_result(
            success=False,
            action=RESULT_FAILED,
            text=(
                "❌ امکان تشخیص کاربر برای ترجمه وجود ندارد."
            ),
            reason=(
                "translation_user_not_found"
            ),
        )

    # =====================================================
    # CALLBACK PARSE
    # =====================================================

    parsed = (
        parse_translation_callback(
            callback_data
        )
    )

    if not parsed.valid:

        answer_callback_query(
            callback_id,
            "دستور ترجمه نامعتبر است."
        )

        result = (
            _controller_result(
                success=False,
                action=RESULT_FAILED,
                text=(
                    "❌ دستور ترجمه معتبر نیست."
                ),
                reason=(
                    "invalid_translation_callback"
                ),
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # ACTIVE REVIEW
    # =====================================================

    review_actions = {
        ACTION_CONFIRM, ACTION_EDIT, ACTION_ORIGINAL, ACTION_CANCEL,
        ACTION_RETRANSLATE, ACTION_RETRANSLATE_CONFIRM,
        "keepedit",
    }
    if parsed.action in review_actions:
        review_id = parsed.value
        exact_state = get_translation_state(review_id) if review_id else None
        allowed = ACTIVE_STATES if parsed.action == ACTION_CANCEL else {"preview"}
        if (not review_id or callback_data != f"tr:{parsed.action}:{review_id}"
                or exact_state is None or exact_state.review_id != review_id or exact_state.chat_id != chat_id
                or exact_state.user_id != user_id or exact_state.status not in allowed):
            message = translation_ui_message(
                "❌ این درخواست دیگر قابل انجام نیست؛ از پیش‌نمایش معتبر همان ترجمه استفاده کنید.",
                review_id,
            )
            answer_callback_query(callback_id, "این درخواست بسته، قدیمی یا نامعتبر است.")
            send_message(chat_id, message)
            return _controller_result(success=False, action=RESULT_INVALID_STATE,
                                      review_id=review_id, reason="stale_translation_action")
    else:
        review_id = _active_review_id(chat_id=chat_id, user_id=user_id)

    # tr:open does NOT itself create a translation state.
    #
    # The source path — Editorial, External Review, normal
    # content, etc. — must first bind the actual source
    # content to a TranslationState.
    if not review_id:

        answer_callback_query(
            callback_id,
            "درخواست ترجمه پیدا نشد."
        )

        result = (
            _controller_result(
                success=False,
                action=RESULT_NOT_FOUND,
                text=(
                    "❌ درخواست ترجمه پیدا نشد یا منقضی شده است."
                ),
                reason=(
                    "translation_state_not_found"
                ),
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    logger.info(
        "[%s] 🌐 TRANSLATION-CALLBACK | "
        "action=%s | review_id=%s | "
        "user=%s | chat=%s",
        req_id,
        parsed.action,
        review_id,
        user_id,
        chat_id,
    )

    # =====================================================
    # OPEN
    # =====================================================

    if parsed.action == ACTION_OPEN:

        result = (
            show_translation_language_menu(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "زبان ترجمه را انتخاب کنید."
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # LANGUAGE
    # =====================================================

    if parsed.action == ACTION_LANGUAGE:

        answer_callback_query(
            callback_id,
            "در حال ترجمه..."
        )

        result = (
            select_translation_language(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
                language_code=(
                    parsed.value
                ),
            )
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # MORE LANGUAGES
    # =====================================================

    if parsed.action == ACTION_MORE:

        result = (
            show_more_translation_languages(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
                page=parsed.page,
            )
        )

        answer_callback_query(
            callback_id,
            "زبان‌های بیشتر"
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # BACK
    # =====================================================

    if parsed.action == ACTION_BACK:

        result = (
            show_translation_language_menu(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "بازگشت"
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # CUSTOM LANGUAGE
    # =====================================================

    if parsed.action == ACTION_CUSTOM:

        result = (
            request_custom_translation_language(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "نام زبان را ارسال کنید."
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # EDIT
    # =====================================================

    if parsed.action == "keepedit":
        answer_callback_query(callback_id, "اصلاح دستی حفظ شد.")
        send_message(chat_id, translation_ui_message("✅ اصلاح دستی حفظ شد؛ می‌توانید از پیش‌نمایش همان ترجمه ادامه دهید.", review_id))
        return _controller_result(success=True, action=RESULT_EDIT_INPUT, review_id=review_id)

    if parsed.action in {ACTION_RETRANSLATE, ACTION_RETRANSLATE_CONFIRM}:
        if exact_state.edited_text and parsed.action != ACTION_RETRANSLATE_CONFIRM:
            answer_callback_query(callback_id, "جایگزینی اصلاح دستی نیاز به تأیید دارد.")
            send_message(
                chat_id,
                translation_ui_message("⚠️ ترجمه مجدد از متن اصلی، اصلاح دستی شما را پس از موفقیت جایگزین می‌کند. ادامه می‌دهید؟", review_id),
                reply_markup={"inline_keyboard": [[
                    {"text": "🔄 تأیید ترجمه مجدد", "callback_data": build_translation_callback(ACTION_RETRANSLATE_CONFIRM, review_id)},
                    {"text": "حفظ اصلاح دستی", "callback_data": build_translation_callback("keepedit", review_id)},
                ]]},
            )
            return _controller_result(success=True, action=RESULT_EDIT_INPUT, review_id=review_id)
        answer_callback_query(callback_id, "ترجمه مجدد از متن اصلی آغاز شد.")
        try:
            send_message(chat_id, translation_ui_message("⏳ ترجمه مجدد از متن اصلی در حال آماده‌سازی است.", review_id))
        except Exception:
            logger.exception("Retranslation progress message failed | review_id=%s", review_id)
        result = retranslate_translation(
            review_id=review_id, chat_id=chat_id, user_id=user_id,
            replace_edit=parsed.action == ACTION_RETRANSLATE_CONFIRM,
        )
        render_translation_result(result=result, chat_id=chat_id, send_message=send_message, review_id=review_id)
        return result

    if parsed.action == ACTION_EDIT:

        result = (
            request_translation_edit(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "متن اصلاح‌شده را ارسال کنید."
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # ORIGINAL
    # =====================================================

    if parsed.action == ACTION_ORIGINAL:

        result = (
            get_translation_original(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "متن اصلی"
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # CANCEL
    # =====================================================

    if parsed.action == ACTION_CANCEL:

        result = (
            cancel_translation(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        answer_callback_query(
            callback_id,
            "ترجمه لغو شد."
        )

        render_translation_result(
            result=result,
            chat_id=chat_id,
            send_message=send_message,
        )

        return result

    # =====================================================
    # CONFIRM + SHARED PUBLICATION
    # =====================================================

    if parsed.action == ACTION_CONFIRM:

        result = (
            confirm_translation(
                review_id=review_id,
                chat_id=chat_id,
                user_id=user_id,
            )
        )

        if not result.success:

            answer_callback_query(
                callback_id,
                "تأیید ترجمه انجام نشد."
            )

            render_translation_result(
                result=result,
                chat_id=chat_id,
                send_message=send_message,
            )

            return result

        confirmed_state = (
            result.state
            or get_translation_state(
                review_id
            )
        )

        if confirmed_state is None:

            answer_callback_query(
                callback_id,
                (
                    "ترجمه تأیید شد اما وضعیت آن "
                    "پیدا نشد."
                )
            )

            send_message(
                chat_id,
                translation_ui_message(
                    "❌ امکان آماده‌سازی ترجمه "
                    "برای انتشار وجود نداشت.",
                    review_id,
                )
            )

            return result

        answer_callback_query(
            callback_id,
            "در حال انتشار نسخه ترجمه‌شده..."
        )

        try:
            send_message(
                chat_id,
                translation_ui_message(
                    "⏳ ترجمه تأیید شد و در حال انتشار است.", review_id
                ),
            )
        except Exception:
            logger.exception("Translation progress message failed | review_id=%s", review_id)

        try:

            publication = (
                publish_confirmed_translation(
                    state=confirmed_state,
                    publish_prepared_text=(
                        publish_prepared_text
                    ),
                )
            )

        except Exception as exc:

            logger.exception(
                "[%s] ❌ Translation publication failed | "
                "review_id=%s | %s",
                req_id,
                review_id,
                exc,
            )

            send_message(
                chat_id,
                translation_ui_message(
                    "❌ انتشار نسخه ترجمه‌شده "
                    "با خطا روبرو شد.",
                    review_id,
                )
            )

            return result

        send_message(
            chat_id,
            translation_publication_message(
                publication
            ),
        )

        logger.info(
            "[%s] 🌐 TRANSLATION-CONFIRM-PUBLICATION | "
            "review_id=%s | success=%s | published=%s",
            req_id,
            review_id,
            publication.success,
            publication.published,
        )

        return result

    # =====================================================
    # UNKNOWN ACTION
    # =====================================================

    answer_callback_query(
        callback_id,
        "دستور ترجمه شناخته نشد."
    )

    result = (
        _controller_result(
            success=False,
            action=RESULT_FAILED,
            text=(
                "❌ این عملیات ترجمه پشتیبانی نمی‌شود."
            ),
            review_id=review_id,
            reason=(
                "unsupported_translation_action"
            ),
        )
    )

    render_translation_result(
        result=result,
        chat_id=chat_id,
        send_message=send_message,
    )

    return result
