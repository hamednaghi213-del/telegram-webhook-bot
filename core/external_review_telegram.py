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
    req_id: str = "",
) -> bool:
    """
    Handle Telegram UI delivery for an external-review callback.

    Returns:
        False:
            callback does not belong to external review.

        True:
            callback belongs to external review and was consumed.

    This adapter intentionally does not publish content.
    Publication remains a separate integration boundary.
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

    try:
        result = (
            handle_external_review_callback(
                callback_data=callback_data,
                chat_id=int(
                    user_id
                ),
                controller=controller,
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
            "این پیش‌نمایش منقضی شده یا دیگر در دسترس نیست.",
        )

        return True

    if not result.handled:
        return False

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

    if result.decision is None:
        answer_callback_query(
            callback_id,
            "درخواست ثبت نشد.",
        )

        return True

    answer_callback_query(
        callback_id,
        "انتخاب ثبت شد.",
    )

    decision = (
        result.decision
    )

    review = (
        decision.review
    )

    if (
        decision.requires_smart_summary
    ):
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

    if (
        decision.requires_editorial_rewrite
    ):
        send_message(
            int(
                user_id
            ),
            (
                "✅ بازنویسی تحریریه انتخاب شد.\n\n"
                "مطلب برای پردازش در مسیر مشترک "
                "تحریریه آماده است."
            ),
        )

        return True

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
