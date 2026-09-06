"""Telegram adapter for external-content review callbacks."""

from __future__ import annotations

import logging

from typing import (
    Any,
    Callable,
    Dict,
    Optional,
)

from core.external_review_callback import (
    ExternalReviewCallbackError,
    handle_external_review_callback,
)
from core.external_review_controller import (
    DEFAULT_EXTERNAL_REVIEW_CONTROLLER,
    ExternalReviewController,
)


logger = logging.getLogger(__name__)


# =========================================================
# PUBLIC HANDLER
# =========================================================


def handle_external_review_telegram_callback(
    *,
    callback_query: Dict[str, Any],
    answer_callback_query: Callable[
        [str, str],
        Any,
    ],
    send_message: Callable[..., Any],
    controller: Optional[
        ExternalReviewController
    ] = None,
    api_url: str = "",
    execute_decision: Optional[
        Callable[..., Any]
    ] = None,
    queue_editorial_review: Optional[
        Callable[..., Any]
    ] = None,
    req_id: str = "",
) -> bool:
    """
    Handle Telegram UI delivery for an external-review callback.

    Returns:
        False:
            callback does not belong to external review.

        True:
            callback belongs to external review and was handled.

    Lifecycle rule:

        create pending
            ↓
        optionally update media selection
            ↓
        choose final content mode
            ↓
        execute decision
            ↓
        publication succeeds
            ↓
        consume pending state

    Media selection is NON-TERMINAL.

    These actions only update review state:

        media
        nomedia

    They MUST NOT:
      - publish
      - summarize
      - run Editorial
      - consume pending state

    Final actions such as standard / short / headline / lead /
    editorial inherit the persistent media selection.

    A failed execution must NOT consume the pending review.
    """

    if not isinstance(
        callback_query,
        dict,
    ):
        return False

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
        or ""
    ).strip()

    if not callback_data.startswith(
        "extrev:"
    ):
        return False

    callback_id = str(
        callback_query.get(
            "id",
            "",
        )
        or ""
    )

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
        answer_callback_query(
            callback_id,
            "کاربر قابل تشخیص نیست.",
        )

        return True

    resolved_controller = (
        controller
        if controller is not None
        else DEFAULT_EXTERNAL_REVIEW_CONTROLLER
    )

    try:
        result = (
            handle_external_review_callback(
                callback_data=callback_data,
                chat_id=int(
                    user_id
                ),
                controller=resolved_controller,
            )
        )

    except ExternalReviewCallbackError as exc:
        logger.warning(
            "[%s] Invalid external review callback | %s",
            req_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            "دستور بررسی نامعتبر است.",
        )

        return True

    except Exception as exc:
        logger.exception(
            "[%s] External review callback failed | %s",
            req_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )

        return True

    if not result.handled:
        return False

    # =====================================================
    # CANCEL
    # =====================================================

    if result.cancelled is not None:
        answer_callback_query(
            callback_id,
            "لغو شد.",
        )

        send_message(
            int(
                user_id
            ),
            "❌ بررسی این مطلب لغو شد.",
        )

        return True

    # =====================================================
    # NON-TERMINAL MEDIA STATE UPDATE
    # =====================================================

    if result.state_updated:
        pending = (
            result.pending
        )

        answer_callback_query(
            callback_id,
            result.message
            or "انتخاب تصویر ثبت شد.",
        )

        if pending is None:
            return True

        if (
            pending.media_selection_explicit
            and not pending.selected_media_indexes
        ):
            send_message(
                int(
                    user_id
                ),
                (
                    "🚫 حالت بدون تصویر انتخاب شد.\n\n"
                    "حالا یکی از حالت‌های انتشار "
                    "مثل استاندارد، کوتاه یا تحریریه "
                    "را انتخاب کنید."
                ),
            )

            return True

        if pending.selected_media_indexes:
            selected_numbers = ", ".join(
                str(index + 1)
                for index
                in pending.selected_media_indexes
            )

            send_message(
                int(
                    user_id
                ),
                (
                    "🖼 تصاویر انتخاب‌شده: "
                    f"{selected_numbers}\n\n"
                    "می‌توانید تصاویر دیگری را هم "
                    "اضافه یا حذف کنید، سپس حالت "
                    "انتشار را انتخاب کنید."
                ),
            )

            return True

        answer_callback_query(
            callback_id,
            "انتخاب رسانه ثبت شد.",
        )

        return True

    # =====================================================
    # FINAL DECISION REQUIRED
    # =====================================================

    if result.decision is None:
        answer_callback_query(
            callback_id,
            "درخواست ثبت نشد.",
        )

        return True

    decision = (
        result.decision
    )

    review = (
        decision.review
    )

    # =====================================================
    # OPTIONAL EXECUTION BOUNDARY
    # =====================================================

    if execute_decision is not None:

        try:
            execution = (
                execute_decision(
                    decision=decision,
                    api_url=api_url,
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review "
                    "execution failed | %s"
                ),
                req_id,
                exc,
            )

            # IMPORTANT:
            # Pending state remains intact.
            # This preserves both:
            #   - selected content mode
            #   - persistent media selection
            #
            # The user can retry after transformation or
            # publication failure.
            answer_callback_query(
                callback_id,
                "انتشار مطلب با خطا روبرو شد.",
            )

            return True

        if getattr(
            execution,
            "published",
            False,
        ):
            # =================================================
            # CONSUME ONLY AFTER SUCCESSFUL PUBLICATION
            # =================================================

            try:
                resolved_controller.consume_after_success(
                    review_id=decision.review_id,
                    chat_id=decision.chat_id,
                )

            except Exception as exc:
                # Publication has already succeeded.
                # Cleanup failure must not be reported as
                # publication failure.
                logger.exception(
                    (
                        "[%s] External review published but "
                        "pending-state cleanup failed | "
                        "review_id=%s chat_id=%s | %s"
                    ),
                    req_id,
                    decision.review_id,
                    decision.chat_id,
                    exc,
                )

                answer_callback_query(
                    callback_id,
                    (
                        "منتشر شد، اما پاک‌سازی "
                        "وضعیت بررسی کامل نشد."
                    ),
                )

                send_message(
                    int(
                        user_id
                    ),
                    (
                        "✅ مطلب با موفقیت منتشر شد.\n\n"
                        "⚠️ وضعیت بررسی به‌طور کامل "
                        "پاک نشد؛ از ارسال دوباره "
                        "همین انتخاب خودداری کنید."
                    ),
                )

                return True

            answer_callback_query(
                callback_id,
                "منتشر شد.",
            )

            send_message(
                int(
                    user_id
                ),
                "✅ مطلب با موفقیت منتشر شد.",
            )

            return True

    # =====================================================
    # SMART SUMMARY SIGNAL
    # =====================================================

    if (
        decision.requires_smart_summary
    ):
        answer_callback_query(
            callback_id,
            "انتخاب ثبت شد.",
        )

        send_message(
            int(
                user_id
            ),
            (
                "✅ حالت کوتاه انتخاب شد.\n\n"
                "مطلب برای پردازش در مسیر مشترک "
                "خلاصه‌سازی آماده است."
            ),
        )

        return True

    # =====================================================
    # SHARED EDITORIAL FLOW
    # =====================================================

    if (
        decision.requires_editorial_rewrite
    ):
        answer_callback_query(
            callback_id,
            "انتخاب ثبت شد.",
        )

        if queue_editorial_review is None:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ مسیر تحریریه در حال حاضر "
                    "در دسترس نیست."
                ),
            )

            return True

        review_parts = []

        if review.title:
            review_parts.append(
                str(
                    review.title
                ).strip()
            )

        if review.lead:
            review_parts.append(
                str(
                    review.lead
                ).strip()
            )

        if review.body:
            review_parts.append(
                str(
                    review.body
                ).strip()
            )

        editorial_text = "\n\n".join(
            part
            for part in review_parts
            if part
        ).strip()

        if not editorial_text:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ متنی برای بازنویسی "
                    "تحریریه وجود ندارد."
                ),
            )

            return True

        try:
            queued = (
                queue_editorial_review(
                    chat_id=int(
                        user_id
                    ),
                    text=editorial_text,
                    entities=[],
                    forced_content_type=(
                        "news_analysis"
                    ),
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External editorial "
                    "queue failed | %s"
                ),
                req_id,
                exc,
            )

            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ ایجاد بررسی تحریریه "
                    "با خطا روبرو شد."
                ),
            )

            return True

        if not queued:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ بررسی تحریریه "
                    "ایجاد نشد."
                ),
            )

        return True

    # =====================================================
    # REVIEW PREVIEW
    # =====================================================

    answer_callback_query(
        callback_id,
        "انتخاب ثبت شد.",
    )

    preview_parts = []

    if review.title:
        preview_parts.append(
            review.title
        )

    if review.lead:
        preview_parts.append(
            review.lead
        )

    if review.body:
        preview_parts.append(
            review.body
        )

    preview_text = "\n\n".join(
        preview_parts
    ).strip()

    if not preview_text:
        preview_text = (
            "انتخاب شما ثبت شد."
        )

    send_message(
        int(
            user_id
        ),
        (
            "✅ انتخاب شما ثبت شد.\n\n"
            f"{preview_text}"
        ),
    )

    return True
