import os

from types import SimpleNamespace

import pytest

from flask import Flask

import core.webhook_handler as webhook_handler

from core.editorial_pending import (
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_PUBLISHED_ORIGINAL,
    STATUS_PUBLISHED_SUMMARY,
    clear_pending_reviews,
    create_pending_review,
    get_pending_review,
)


# =========================================================
# FLASK TEST APP
# =========================================================

app = Flask(__name__)


# =========================================================
# TEST SETUP
# =========================================================

@pytest.fixture(autouse=True)
def reset_editorial_state(
    monkeypatch
):

    clear_pending_reviews()

    monkeypatch.delenv(
        "ENABLE_EDITORIAL_REVIEW",
        raising=False
    )

    webhook_handler.initialize(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        channel_id="@test_channel",
        secret_token="test-secret"
    )

    yield

    clear_pending_reviews()

    monkeypatch.delenv(
        "ENABLE_EDITORIAL_REVIEW",
        raising=False
    )


# =========================================================
# HELPERS
# =========================================================

def make_opinion_result(
    original_text: str,
    summary_text: str = (
        "این نسخه خلاصه پیشنهادی "
        "برای انتشار است."
    )
):

    return SimpleNamespace(
        content_type="opinion_note",
        action="needs_approval",
        needs_approval=True,
        original_text=original_text,
        suggested_text=summary_text,
        summary_success=True,
        target_length=950,
        original_length=len(
            original_text
        ),
        suggested_length=len(
            summary_text
        ),
        reason="editorial_summary_ready",
        metadata={
            "regeneration_count": 0,
            "can_regenerate": True
        }
    )


def make_normal_result(
    original_text: str
):

    return SimpleNamespace(
        content_type="normal_news",
        action="publish_direct",
        needs_approval=False,
        original_text=original_text,
        suggested_text=original_text,
        summary_success=True,
        target_length=950,
        original_length=len(
            original_text
        ),
        suggested_length=len(
            original_text
        ),
        reason="normal_news_direct",
        metadata={
            "regeneration_count": 0,
            "can_regenerate": False
        }
    )


def callback_payload(
    action: str,
    review_id: str,
    user_id: int = 100
):

    return {
        "id": (
            f"callback-{action}"
        ),
        "from": {
            "id": user_id
        },
        "data": (
            f"ed:{action}:{review_id}"
        )
    }


# =========================================================
# FEATURE FLAG
# =========================================================

def test_editorial_review_disabled_by_default():

    assert (
        webhook_handler
        .editorial_review_enabled()
        is False
    )


def test_editorial_review_can_be_enabled(
    monkeypatch
):

    monkeypatch.setenv(
        "ENABLE_EDITORIAL_REVIEW",
        "true"
    )

    assert (
        webhook_handler
        .editorial_review_enabled()
        is True
    )


# =========================================================
# KEYBOARD
# =========================================================

def test_editorial_keyboard_contains_actions():

    keyboard = (
        webhook_handler
        .build_editorial_keyboard(
            review_id="abc123",
            has_summary=True,
            can_regenerate=True
        )
    )

    rows = (
        keyboard[
            "inline_keyboard"
        ]
    )

    callback_values = [
        button[
            "callback_data"
        ]
        for row in rows
        for button in row
    ]

    assert (
        "ed:summary:abc123"
        in callback_values
    )

    assert (
        "ed:original:abc123"
        in callback_values
    )

    assert (
        "ed:regen:abc123"
        in callback_values
    )

    assert (
        "ed:cancel:abc123"
        in callback_values
    )


def test_regeneration_button_can_be_removed():

    keyboard = (
        webhook_handler
        .build_editorial_keyboard(
            review_id="abc123",
            has_summary=True,
            can_regenerate=False
        )
    )

    callback_values = [
        button[
            "callback_data"
        ]
        for row
        in keyboard[
            "inline_keyboard"
        ]
        for button
        in row
    ]

    assert (
        "ed:regen:abc123"
        not in callback_values
    )


# =========================================================
# QUEUE OPINION NOTE
# =========================================================

def test_opinion_note_is_queued_for_review(
    monkeypatch
):

    monkeypatch.setenv(
        "ENABLE_EDITORIAL_REVIEW",
        "true"
    )

    original_text = (
        "این یک یادداشت تحلیلی "
        "برای بررسی سیاست خارجی است."
    )

    monkeypatch.setattr(
        webhook_handler,
        "prepare_text_content",
        lambda **kwargs: {
            "main_text": original_text,
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    )

    import core.editorial_review as editorial_review

    monkeypatch.setattr(
        editorial_review,
        "analyze_editorial_content",
        lambda original_text: (
            make_opinion_result(
                original_text
            )
        )
    )

    sent_messages = []

    def fake_send_message(
        chat_id,
        text,
        parse_mode=None,
        reply_markup=None
    ):

        sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "reply_markup":
                reply_markup
        })

        return True

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        fake_send_message
    )

    queued = (
        webhook_handler
        .try_queue_editorial_text_review(
            chat_id=100,
            text=original_text,
            entities=[],
            forward_source=None
        )
    )

    assert queued is True

    assert (
        len(
            sent_messages
        )
        == 1
    )

    assert (
        "پیش‌نمایش تحریریه"
        in sent_messages[0][
            "text"
        ]
    )

    assert (
        sent_messages[0][
            "reply_markup"
        ]
        is not None
    )


# =========================================================
# NORMAL NEWS IS NOT QUEUED
# =========================================================

def test_normal_news_is_not_queued(
    monkeypatch
):

    monkeypatch.setenv(
        "ENABLE_EDITORIAL_REVIEW",
        "true"
    )

    original_text = (
        "وزارت خارجه اعلام کرد "
        "نشست امروز برگزار شد."
    )

    monkeypatch.setattr(
        webhook_handler,
        "prepare_text_content",
        lambda **kwargs: {
            "main_text": original_text,
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    )

    import core.editorial_review as editorial_review

    monkeypatch.setattr(
        editorial_review,
        "analyze_editorial_content",
        lambda original_text: (
            make_normal_result(
                original_text
            )
        )
    )

    queued = (
        webhook_handler
        .try_queue_editorial_text_review(
            chat_id=100,
            text=original_text,
            entities=[],
            forward_source=None
        )
    )

    assert queued is False


# =========================================================
# WEBHOOK MUST HOLD REVIEW CONTENT
# =========================================================

def test_webhook_does_not_publish_text_when_queued(
    monkeypatch
):

    monkeypatch.setenv(
        "ENABLE_EDITORIAL_REVIEW",
        "true"
    )

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda **kwargs: True
    )

    publication_calls = []

    def fake_process_text_message(
        **kwargs
    ):

        publication_calls.append(
            kwargs
        )

        return True

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        fake_process_text_message
    )

    import core.database as database

    monkeypatch.setattr(
        database,
        "get_tenant",
        lambda user_id: {
            "telegram_channel":
                "@test_channel"
        }
    )

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {
                "id": 100
            },
            "text": (
                "این یک یادداشت "
                "تحلیلی آزمایشی است."
            )
        }
    }

    with app.test_request_context(
        "/",
        method="POST",
        json=payload,
        headers={
            "X-Telegram-Bot-Api-Secret-Token":
                "test-secret"
        }
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    assert status == 200

    assert (
        body.get(
            "editorial_review"
        )
        is True
    )

    assert publication_calls == []


# =========================================================
# NORMAL NEWS CONTINUES STABLE PATH
# =========================================================

def test_webhook_normal_news_uses_existing_path(
    monkeypatch
):

    monkeypatch.setenv(
        "ENABLE_EDITORIAL_REVIEW",
        "true"
    )

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda **kwargs: False
    )

    publication_calls = []

    def fake_process_text_message(
        **kwargs
    ):

        publication_calls.append(
            kwargs
        )

        return True

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        fake_process_text_message
    )

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda *args, **kwargs: True
    )

    import core.database as database

    monkeypatch.setattr(
        database,
        "get_tenant",
        lambda user_id: {
            "telegram_channel":
                "@test_channel"
        }
    )

    payload = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {
                "id": 100
            },
            "text": (
                "این یک خبر عادی است."
            )
        }
    }

    with app.test_request_context(
        "/",
        method="POST",
        json=payload,
        headers={
            "X-Telegram-Bot-Api-Secret-Token":
                "test-secret"
        }
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    assert status == 200

    assert body["ok"] is True

    assert (
        len(
            publication_calls
        )
        == 1
    )


# =========================================================
# PUBLISH SUMMARY CALLBACK
# =========================================================

def test_publish_summary_callback(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه تایید شده",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "kind": "text"
        }
    )

    published = []

    def fake_publish_prepared_text(
        **kwargs
    ):

        published.append(
            kwargs
        )

        return True

    monkeypatch.setattr(
        webhook_handler,
        "publish_prepared_text",
        fake_publish_prepared_text
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda *args, **kwargs: True
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "summary",
                review.review_id
            ),
            "test001"
        )
    )

    assert handled is True

    assert (
        len(
            published
        )
        == 1
    )

    assert (
        published[0][
            "main_text"
        ]
        == "خلاصه تایید شده"
    )

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_PUBLISHED_SUMMARY
    )


# =========================================================
# PUBLISH ORIGINAL CALLBACK
# =========================================================

def test_publish_original_callback(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text=(
            "متن اصلی کامل"
        ),
        current_summary=(
            "خلاصه پیشنهادی"
        ),
        metadata={
            "summary_success": True,
            "main_text":
                "متن اصلی فرمت شده",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    )

    published = []

    def fake_publish_prepared_text(
        **kwargs
    ):

        published.append(
            kwargs
        )

        return True

    monkeypatch.setattr(
        webhook_handler,
        "publish_prepared_text",
        fake_publish_prepared_text
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda *args, **kwargs: True
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "original",
                review.review_id
            ),
            "test002"
        )
    )

    assert handled is True

    assert (
        len(
            published
        )
        == 1
    )

    assert (
        published[0][
            "main_text"
        ]
        == "متن اصلی فرمت شده"
    )

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_PUBLISHED_ORIGINAL
    )


# =========================================================
# CANCEL CALLBACK
# =========================================================

def test_cancel_callback_never_publishes(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه"
    )

    publication_calls = []

    monkeypatch.setattr(
        webhook_handler,
        "publish_prepared_text",
        lambda **kwargs: (
            publication_calls.append(
                kwargs
            )
            or True
        )
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda *args, **kwargs: True
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "cancel",
                review.review_id
            ),
            "test003"
        )
    )

    assert handled is True

    assert publication_calls == []

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_CANCELLED
    )


# =========================================================
# REGENERATE CALLBACK
# =========================================================

def test_regenerate_callback_updates_pending(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text=(
            "متن اصلی بلند برای "
            "خلاصه نویسی مجدد"
        ),
        current_summary="خلاصه اول",
        regeneration_count=0,
        metadata={
            "summary_success": True
        }
    )

    import core.editorial_review as editorial_review

    regeneration_result = (
        SimpleNamespace(
            content_type="opinion_note",
            action="needs_approval",
            needs_approval=True,
            original_text=(
                review.original_text
            ),
            suggested_text=(
                "خلاصه دوم و جدید"
            ),
            summary_success=True,
            target_length=950,
            original_length=len(
                review.original_text
            ),
            suggested_length=len(
                "خلاصه دوم و جدید"
            ),
            reason=(
                "editorial_regeneration_ready"
            ),
            metadata={
                "regeneration_count": 1,
                "can_regenerate": True
            }
        )
    )

    monkeypatch.setattr(
        editorial_review,
        "regenerate_editorial_summary",
        lambda **kwargs: (
            regeneration_result
        )
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    sent_messages = []

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda *args, **kwargs: (
            sent_messages.append(
                {
                    "args": args,
                    "kwargs": kwargs
                }
            )
            or True
        )
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "regen",
                review.review_id
            ),
            "test004"
        )
    )

    assert handled is True

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_PENDING
    )

    assert (
        loaded.current_summary
        == "خلاصه دوم و جدید"
    )

    assert (
        loaded.regeneration_count
        == 1
    )

    assert (
        loaded.metadata[
            "summary_success"
        ]
        is True
    )

    assert (
        len(
            sent_messages
        )
        >= 1
    )


# =========================================================
# WRONG USER CANNOT CONTROL REVIEW
# =========================================================

def test_wrong_user_cannot_publish_review(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        metadata={
            "summary_success": True
        }
    )

    publication_calls = []

    monkeypatch.setattr(
        webhook_handler,
        "publish_prepared_text",
        lambda **kwargs: (
            publication_calls.append(
                kwargs
            )
            or True
        )
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "summary",
                review.review_id,
                user_id=999
            ),
            "test005"
        )
    )

    assert handled is True

    assert publication_calls == []

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_PENDING
    )


# =========================================================
# FINALIZED REVIEW CANNOT PUBLISH TWICE
# =========================================================

def test_finalized_review_cannot_publish_twice(
    monkeypatch
):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        metadata={
            "summary_success": True
        }
    )

    import core.editorial_pending as editorial_pending

    editorial_pending.mark_summary_published(
        review.review_id,
        user_id=100
    )

    publication_calls = []

    monkeypatch.setattr(
        webhook_handler,
        "publish_prepared_text",
        lambda **kwargs: (
            publication_calls.append(
                kwargs
            )
            or True
        )
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_payload(
                "original",
                review.review_id
            ),
            "test006"
        )
    )

    assert handled is True

    assert publication_calls == []

    loaded = get_pending_review(
        review.review_id,
        user_id=100
    )

    assert (
        loaded.status
        == STATUS_PUBLISHED_SUMMARY
    )


# =========================================================
# INVALID CALLBACK
# =========================================================

def test_non_editorial_callback_is_ignored():

    callback = {
        "id": "x",
        "from": {
            "id": 100
        },
        "data": "something_else"
    }

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback,
            "test007"
        )
    )

    assert handled is False
