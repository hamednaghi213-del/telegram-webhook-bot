from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_review_controller import (
    ExternalReviewController,
)
from core.external_review_state import (
    ExternalReviewStateStore,
)
from core.external_review_telegram import (
    handle_external_review_telegram_callback,
)


# =========================================================
# HELPERS
# =========================================================


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/news",
        canonical_url="https://example.com/news",
        content_type="article",
        title="عنوان خبر",
        lead="لید خبر",
        body=(
            "پاراگراف اول\n\n"
            "پاراگراف دوم"
        ),
        source_name="Example",
        extraction_confidence=0.95,
    )


def _controller():
    return ExternalReviewController(
        state_store=(
            ExternalReviewStateStore(
                ttl_seconds=1800
            )
        )
    )


def _create_pending(
    controller,
    *,
    review_id="review-1",
    chat_id=12345,
):
    controller.create_pending(
        review_id=review_id,
        chat_id=chat_id,
        content=_content(),
    )


def _callback(
    data,
    *,
    user_id=12345,
    callback_id="cb-1",
):
    return {
        "id": callback_id,
        "data": data,
        "from": {
            "id": user_id,
        },
    }


# =========================================================
# FOREIGN CALLBACK
# =========================================================


def test_foreign_callback_is_not_claimed():
    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "setup:start"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=_controller(),
            req_id="req-1",
        )
    )

    assert handled is False
    assert answers == []
    assert messages == []


# =========================================================
# USER VALIDATION
# =========================================================


def test_missing_user_is_handled():
    answers = []

    callback = {
        "id": "cb-1",
        "data": (
            "extrev:standard:review-1"
        ),
        "from": {},
    }

    handled = (
        handle_external_review_telegram_callback(
            callback_query=callback,
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=_controller(),
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "کاربر قابل تشخیص نیست.",
        )
    ]


# =========================================================
# STANDARD
# =========================================================


def test_standard_callback_is_consumed():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
            req_id="req-1",
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert messages[0][0][0] == 12345

    assert (
        "عنوان خبر"
        in messages[0][0][1]
    )

    assert (
        "لید خبر"
        in messages[0][0][1]
    )

    assert (
        "پاراگراف اول"
        in messages[0][0][1]
    )


# =========================================================
# SHORT
# =========================================================


def test_short_callback_reports_shared_summary_path():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:short:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "مسیر مشترک خلاصه‌سازی"
        in messages[0][0][1]
    )


# =========================================================
# EDITORIAL
# =========================================================


def test_editorial_callback_reports_shared_editorial_path():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:editorial:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "مسیر تحریریه در حال حاضر"
        in messages[0][0][1]
    )

    assert (
        "در دسترس نیست"
        in messages[0][0][1]
    )


# =========================================================
# CANCEL
# =========================================================


def test_cancel_callback_is_acknowledged():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:cancel:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "لغو شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "لغو شد"
        in messages[0][0][1]
    )


# =========================================================
# INVALID CALLBACK
# =========================================================


def test_invalid_external_callback_is_handled_safely():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:unknown:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "دستور بررسی نامعتبر است.",
        )
    ]


# =========================================================
# EXPIRED / MISSING REVIEW
# =========================================================


def test_missing_review_is_handled_safely():
    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:not-found"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=_controller(),
            req_id="req-1",
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )
    ]


# =========================================================
# OWNERSHIP
# =========================================================


def test_user_cannot_consume_another_users_review():
    controller = _controller()

    _create_pending(
        controller,
        chat_id=111,
    )

    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1",
                    user_id=222,
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )
    ]

    pending = (
        controller.get_pending(
            review_id="review-1",
            chat_id=111,
        )
    )

    assert pending is not None


# =========================================================
# NO PUBLICATION
# =========================================================


def test_telegram_adapter_does_not_publish():
    controller = _controller()

    _create_pending(
        controller
    )

    calls = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1"
                )
            ),
            answer_callback_query=(
                lambda *args, **kwargs:
                None
            ),
            send_message=(
                lambda *args, **kwargs:
                calls.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert len(calls) == 1
