import sys
import types

import pytest

from flask import Flask

import core
import core.webhook_handler as webhook_handler

from core.editorial_pending import (
    ADMIN_INSTRUCTION_COUNT_KEY,
    ADMIN_INSTRUCTION_LAST_TEXT_KEY,
    ADMIN_INSTRUCTION_WAITING_KEY,
    STATUS_PENDING,
    clear_pending_reviews,
    create_pending_review,
    get_pending_review,
    get_waiting_admin_instruction_review,
    is_waiting_for_admin_instruction,
    set_admin_instruction_waiting,
)

from core.editorial_review import (
    ACTION_NEEDS_APPROVAL,
    CONTENT_TYPE_OPINION_NOTE,
    EditorialReviewResult,
)


# =========================================================
# TEST CONSTANTS
# =========================================================

USER_ID = 123456789

REVIEW_TITLE = (
    "آزمون اصلاح تحریریه"
)

REVIEW_AUTHOR = (
    "نویسنده آزمایشی"
)

ORIGINAL_BODY = (
    "ایران در شرایطی مذاکرات را ادامه می‌دهد که اعتماد "
    "میان طرفین کاهش یافته است. با این حال تهران حفظ "
    "چارچوب مذاکره را راهی برای کنترل هزینه‌های سیاسی "
    "و جلوگیری از ورود به یک بحران غیرقابل کنترل می‌داند. "
    "در این ارزیابی، ادامه گفت‌وگو لزوماً به معنای اعتماد "
    "به نتیجه مذاکرات نیست بلکه ابزاری برای مدیریت صحنه "
    "و انتقال هزینه شکست احتمالی به طرف مقابل است."
)

CURRENT_SUMMARY = (
    "ایران با وجود کاهش اعتماد، ادامه مذاکرات را "
    "ابزاری برای مدیریت صحنه و جلوگیری از تشدید "
    "بحران می‌داند."
)

UPDATED_SUMMARY = (
    "ایران با وجود کاهش اعتماد، مذاکرات را ابزاری "
    "برای کنترل صحنه، مهار هزینه‌های سیاسی و جلوگیری "
    "از تشدید بحران می‌داند."
)

ADMIN_INSTRUCTION_TEXT = (
    "تأکید بیشتری روی کنترل صحنه داشته باشد."
)


# =========================================================
# TEST APP
# =========================================================

@pytest.fixture
def app():

    app = Flask(
        __name__
    )

    app.config[
        "TESTING"
    ] = True

    return app


# =========================================================
# RESET STORE
# =========================================================

@pytest.fixture(
    autouse=True
)
def reset_pending_reviews():

    clear_pending_reviews()

    yield

    clear_pending_reviews()


# =========================================================
# CREATE TEST REVIEW
# =========================================================

def create_test_review():

    return create_pending_review(
        user_id=USER_ID,
        content_type=(
            CONTENT_TYPE_OPINION_NOTE
        ),
        original_text=(
            ORIGINAL_BODY
        ),
        current_summary=(
            CURRENT_SUMMARY
        ),
        regeneration_count=0,
        metadata={
            "kind":
                "text",

            "summary_success":
                True,

            "editorial_title":
                REVIEW_TITLE,

            "editorial_author":
                REVIEW_AUTHOR,

            "editorial_body":
                ORIGINAL_BODY,

            "main_text":
                ORIGINAL_BODY,

            "blockquote_blocks":
                [],

            "expandable_blocks":
                [],

            "other_entities":
                []
        }
    )


# =========================================================
# FAKE DATABASE MODULE
#
# مهم:
#
# core.database واقعی نباید در این تست Import شود،
# چون در زمان Import به SUPABASE_URL نیاز دارد.
#
# بنابراین برای تست E2E یک Module جعلی داخل
# sys.modules قرار می‌دهیم.
# =========================================================

def install_fake_database(
    monkeypatch
):

    fake_database = (
        types.ModuleType(
            "core.database"
        )
    )

    def fake_get_tenant(
        user_id
    ):

        return {
            "telegram_channel":
                "@Donya24News"
        }

    fake_database.get_tenant = (
        fake_get_tenant
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database
    )

    monkeypatch.setattr(
        core,
        "database",
        fake_database,
        raising=False
    )

    return fake_database


# =========================================================
# COMMON WEBHOOK MOCKS
# =========================================================

def install_common_webhook_mocks(
    monkeypatch,
    sent_messages
):

    # =====================================================
    # SECURITY
    # =====================================================

    monkeypatch.setattr(
        webhook_handler,
        "validate_webhook_token",
        lambda: True
    )

    # =====================================================
    # USER MESSAGES
    # =====================================================

    def fake_send_message(
        chat_id,
        text,
        parse_mode=None,
        reply_markup=None
    ):

        sent_messages.append({
            "chat_id":
                chat_id,

            "text":
                text,

            "parse_mode":
                parse_mode,

            "reply_markup":
                reply_markup,
        })

        return True

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        fake_send_message
    )

    # =====================================================
    # DATABASE
    #
    # Supabase واقعی در Unit/E2E Test فراخوانی نمی‌شود.
    # =====================================================

    install_fake_database(
        monkeypatch
    )


# =========================================================
# CALLBACK REQUEST
# =========================================================

def build_callback_payload(
    review_id: str
):

    return {
        "update_id":
            1000,

        "callback_query": {
            "id":
                "callback-test-id",

            "from": {
                "id":
                    USER_ID
            },

            "data":
                f"ed:instruction:{review_id}"
        }
    }


# =========================================================
# TEXT REQUEST
# =========================================================

def build_text_payload(
    text: str
):

    return {
        "update_id":
            2000,

        "message": {
            "message_id":
                10,

            "chat": {
                "id":
                    USER_ID,

                "type":
                    "private"
            },

            "from": {
                "id":
                    USER_ID
            },

            "text":
                text
        }
    }


# =========================================================
# TEST 01
# CALLBACK ACTIVATES WAITING
# =========================================================

def test_admin_instruction_callback_activates_waiting(
    monkeypatch,
    app
):

    review = (
        create_test_review()
    )

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    payload = (
        build_callback_payload(
            review.review_id
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    updated = (
        get_pending_review(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is True
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is True
    )

    assert (
        any(
            "حالت اصلاح با دستور ادمین"
            in (
                item.get(
                    "text",
                    ""
                )
                or ""
            )
            for item
            in sent_messages
        )
    )


# =========================================================
# TEST 02
# NEXT TEXT MUST BE CONSUMED AS ADMIN INSTRUCTION
# =========================================================

def test_next_text_is_consumed_as_admin_instruction(
    monkeypatch,
    app
):

    review = (
        create_test_review()
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    # =====================================================
    # ADMIN EDIT RESULT
    # =====================================================

    def fake_apply_admin_instruction(
        original_text,
        previous_summary,
        admin_instruction,
        content_type,
        target_length=950,
        summarizer=None
    ):

        assert (
            original_text
            == ORIGINAL_BODY
        )

        assert (
            previous_summary
            == CURRENT_SUMMARY
        )

        assert (
            admin_instruction
            == ADMIN_INSTRUCTION_TEXT
        )

        assert (
            content_type
            == CONTENT_TYPE_OPINION_NOTE
        )

        return EditorialReviewResult(
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),

            action=(
                ACTION_NEEDS_APPROVAL
            ),

            needs_approval=True,

            original_text=(
                ORIGINAL_BODY
            ),

            suggested_text=(
                UPDATED_SUMMARY
            ),

            summary_success=True,

            target_length=950,

            original_length=len(
                ORIGINAL_BODY
            ),

            suggested_length=len(
                UPDATED_SUMMARY
            ),

            reason=(
                "admin_instruction_ready"
            ),

            metadata={
                "admin_instruction":
                    ADMIN_INSTRUCTION_TEXT,

                "admin_instruction_applied":
                    True
            }
        )

    import core.editorial_review as editorial_review_module

    monkeypatch.setattr(
        editorial_review_module,
        "apply_admin_instruction_to_editorial_summary",
        fake_apply_admin_instruction
    )

    # =====================================================
    # NEWS PATH MUST NOT RUN
    # =====================================================

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda *args, **kwargs: pytest.fail(
            "Admin instruction must not enter "
            "normal editorial queue"
        )
    )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        lambda *args, **kwargs: pytest.fail(
            "Admin instruction must not be "
            "published as normal text"
        )
    )

    payload = (
        build_text_payload(
            ADMIN_INSTRUCTION_TEXT
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    updated = (
        get_pending_review(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    assert (
        updated.current_summary
        == UPDATED_SUMMARY
    )

    assert (
        updated.status
        == STATUS_PENDING
    )

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is False
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_LAST_TEXT_KEY
        )
        == ADMIN_INSTRUCTION_TEXT
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY
        )
        == 1
    )


# =========================================================
# TEST 03
# ADMIN INSTRUCTION MUST NEVER BE PUBLISHED DIRECTLY
# =========================================================

def test_admin_instruction_text_is_never_published_directly(
    monkeypatch,
    app
):

    review = (
        create_test_review()
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    import core.editorial_review as editorial_review_module

    def fake_apply(
        **kwargs
    ):

        return EditorialReviewResult(
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),

            action=(
                ACTION_NEEDS_APPROVAL
            ),

            needs_approval=True,

            original_text=(
                ORIGINAL_BODY
            ),

            suggested_text=(
                UPDATED_SUMMARY
            ),

            summary_success=True,

            target_length=950,

            original_length=len(
                ORIGINAL_BODY
            ),

            suggested_length=len(
                UPDATED_SUMMARY
            ),

            reason=(
                "admin_instruction_ready"
            ),

            metadata={}
        )

    monkeypatch.setattr(
        editorial_review_module,
        "apply_admin_instruction_to_editorial_summary",
        fake_apply
    )

    direct_publish_called = {
        "value":
            False
    }

    def fake_process_text_message(
        *args,
        **kwargs
    ):

        direct_publish_called[
            "value"
        ] = True

        return True

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        fake_process_text_message
    )

    payload = (
        build_text_payload(
            ADMIN_INSTRUCTION_TEXT
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    assert (
        direct_publish_called[
            "value"
        ]
        is False
    )


# =========================================================
# TEST 04
# FAILED ADMIN EDIT KEEPS PREVIOUS SUMMARY
# =========================================================

def test_failed_admin_instruction_keeps_previous_summary(
    monkeypatch,
    app
):

    review = (
        create_test_review()
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    import core.editorial_review as editorial_review_module

    def fake_failed_apply(
        **kwargs
    ):

        return EditorialReviewResult(
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),

            action=(
                ACTION_NEEDS_APPROVAL
            ),

            needs_approval=True,

            original_text=(
                ORIGINAL_BODY
            ),

            suggested_text=(
                CURRENT_SUMMARY
            ),

            summary_success=False,

            target_length=950,

            original_length=len(
                ORIGINAL_BODY
            ),

            suggested_length=len(
                CURRENT_SUMMARY
            ),

            reason=(
                "admin_instruction_failed"
            ),

            metadata={
                "validation": {
                    "valid":
                        False,

                    "errors": [
                        "certainty_markers_lost"
                    ]
                }
            }
        )

    monkeypatch.setattr(
        editorial_review_module,
        "apply_admin_instruction_to_editorial_summary",
        fake_failed_apply
    )

    payload = (
        build_text_payload(
            ADMIN_INSTRUCTION_TEXT
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    updated = (
        get_pending_review(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    # نسخه قبلی باید محفوظ بماند.
    assert (
        updated.current_summary
        == CURRENT_SUMMARY
    )

    assert (
        updated.status
        == STATUS_PENDING
    )

    assert (
        any(
            (
                "نسخه قبلی"
                in (
                    item.get(
                        "text",
                        ""
                    )
                    or ""
                )
            )
            or
            (
                "مورد تأیید"
                in (
                    item.get(
                        "text",
                        ""
                    )
                    or ""
                )
            )
            for item
            in sent_messages
        )
    )


# =========================================================
# TEST 05
# NORMAL TEXT WITHOUT WAITING REVIEW KEEPS OLD PATH
# =========================================================

def test_normal_text_without_waiting_review_keeps_old_path(
    monkeypatch,
    app
):

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    queued_called = {
        "value":
            False
    }

    process_called = {
        "value":
            False
    }

    def fake_queue(
        *args,
        **kwargs
    ):

        queued_called[
            "value"
        ] = True

        return False

    def fake_process(
        *args,
        **kwargs
    ):

        process_called[
            "value"
        ] = True

        return True

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        fake_queue
    )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        fake_process
    )

    payload = (
        build_text_payload(
            "این یک خبر عادی برای انتشار است."
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    assert (
        queued_called[
            "value"
        ]
        is True
    )

    assert (
        process_called[
            "value"
        ]
        is True
    )


# =========================================================
# TEST 06
# SUCCESSFUL ADMIN EDIT KEEPS REVIEW PENDING
# =========================================================

def test_successful_admin_edit_keeps_review_pending(
    monkeypatch,
    app
):

    review = (
        create_test_review()
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    import core.editorial_review as editorial_review_module

    def fake_success(
        **kwargs
    ):

        return EditorialReviewResult(
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),

            action=(
                ACTION_NEEDS_APPROVAL
            ),

            needs_approval=True,

            original_text=(
                ORIGINAL_BODY
            ),

            suggested_text=(
                UPDATED_SUMMARY
            ),

            summary_success=True,

            target_length=950,

            original_length=len(
                ORIGINAL_BODY
            ),

            suggested_length=len(
                UPDATED_SUMMARY
            ),

            reason=(
                "admin_instruction_ready"
            ),

            metadata={
                "admin_instruction":
                    ADMIN_INSTRUCTION_TEXT
            }
        )

    monkeypatch.setattr(
        editorial_review_module,
        "apply_admin_instruction_to_editorial_summary",
        fake_success
    )

    payload = (
        build_text_payload(
            ADMIN_INSTRUCTION_TEXT
        )
    )

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        response, status = (
            webhook_handler.handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        response[
            "ok"
        ]
        is True
    )

    updated = (
        get_pending_review(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    assert (
        updated.status
        == STATUS_PENDING
    )

    assert (
        updated.current_summary
        == UPDATED_SUMMARY
    )

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is False
    )

    assert (
        any(
            (
                "پیش‌نمایش"
                in (
                    item.get(
                        "text",
                        ""
                    )
                    or ""
                )
            )
            or
            (
                UPDATED_SUMMARY
                in (
                    item.get(
                        "text",
                        ""
                    )
                    or ""
                )
            )
            for item
            in sent_messages
        )
    )


# =========================================================
# TEST 07
# WAITING REVIEW LOOKUP
# =========================================================

def test_waiting_review_lookup_after_activation():

    review = (
        create_test_review()
    )

    assert (
        get_waiting_admin_instruction_review(
            USER_ID
        )
        is None
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    waiting = (
        get_waiting_admin_instruction_review(
            USER_ID
        )
    )

    assert (
        waiting
        is not None
    )

    assert (
        waiting.review_id
        == review.review_id
    )


# =========================================================
# TEST 08
# ADMIN INSTRUCTION COUNTER STARTS AT ZERO
# =========================================================

def test_admin_instruction_counter_starts_zero():

    review = (
        create_test_review()
    )

    assert (
        review.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY,
            0
        )
        == 0
    )


# =========================================================
# TEST 09
# ORIGINAL BODY MUST STAY UNCHANGED
# =========================================================

def test_admin_edit_never_mutates_original_body():

    review = (
        create_test_review()
    )

    original_before = (
        review.original_text
    )

    body_before = (
        review.metadata.get(
            "editorial_body"
        )
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    updated = (
        get_pending_review(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    assert (
        updated.original_text
        == original_before
    )

    assert (
        updated.metadata.get(
            "editorial_body"
        )
        == body_before
    )


# =========================================================
# TEST 10
# WAITING FLAG DOES NOT FINALIZE REVIEW
# =========================================================

def test_instruction_waiting_does_not_finalize_review():

    review = (
        create_test_review()
    )

    updated = (
        set_admin_instruction_waiting(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        updated
        is not None
    )

    assert (
        updated.status
        == STATUS_PENDING
    )

    assert (
        updated.current_summary
        == CURRENT_SUMMARY
    )
