import pytest

from flask import Flask

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
# TEST APP
# =========================================================

app = Flask(
    __name__
)


# =========================================================
# TEST DATA
# =========================================================

USER_ID = 123456789

REVIEW_ID_PLACEHOLDER = "review"

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
    "ایران با وجود کاهش اعتماد، ادامه مذاکرات را ابزاری "
    "برای کنترل صحنه و جلوگیری از تشدید بحران می‌داند."
)

UPDATED_SUMMARY = (
    "ایران در شرایط کاهش اعتماد، مذاکره را نه نشانه اعتماد "
    "به نتیجه بلکه ابزاری برای مدیریت صحنه، کنترل هزینه‌های "
    "سیاسی و جلوگیری از ورود به بحران غیرقابل کنترل می‌داند."
)

ADMIN_INSTRUCTION = (
    "روی نقش مذاکرات در کنترل صحنه و مدیریت هزینه‌های "
    "سیاسی تأکید بیشتری داشته باشد."
)


# =========================================================
# AUTO CLEANUP
# =========================================================

@pytest.fixture(
    autouse=True
)
def cleanup_pending_store():

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
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        regeneration_count=0,
        metadata={
            "kind": "text",

            "summary_success": True,

            "editorial_title":
                "مذاکره برای مدیریت بحران",

            "editorial_author":
                "نویسنده آزمایشی",

            "editorial_body":
                ORIGINAL_BODY,

            "main_text":
                ORIGINAL_BODY,

            "blockquote_blocks":
                [],

            "expandable_blocks":
                [],

            "other_entities":
                [],
        }
    )


# =========================================================
# FAKE SUCCESSFUL AI RESULT
# =========================================================

def build_successful_admin_result():

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
                ADMIN_INSTRUCTION,

            "admin_instruction_applied":
                True,

            "validation": {
                "valid": True,
                "errors": [],
                "warnings": [],
            },

            "certainty_retry_called":
                False,
        }
    )


# =========================================================
# FAKE FAILED AI RESULT
# =========================================================

def build_failed_admin_result():

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
            "admin_instruction":
                ADMIN_INSTRUCTION,

            "generation_reason":
                "validation_failed",

            "validation": {
                "valid": False,
                "errors": [
                    "certainty_markers_lost"
                ],
                "warnings": [],
            },
        }
    )


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
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        })

        return True

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        fake_send_message
    )

    # =====================================================
    # TENANT
    # =====================================================

    import core.database

    monkeypatch.setattr(
        core.database,
        "get_tenant",
        lambda user_id: {
            "telegram_channel":
                "@Donya24News"
        }
    )


# =========================================================
# TEST 01
# CALLBACK MUST ACTIVATE WAITING MODE
# =========================================================

def test_admin_instruction_callback_activates_waiting(
    monkeypatch
):

    review = (
        create_test_review()
    )

    sent_messages = []

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda *args, **kwargs: True
    )

    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda chat_id,
        text,
        parse_mode=None,
        reply_markup=None:
            sent_messages.append(
                {
                    "chat_id":
                        chat_id,

                    "text":
                        text,

                    "reply_markup":
                        reply_markup,
                }
            )
            or True
    )

    callback_query = {
        "id": "callback-1",

        "data": (
            f"ed:instruction:"
            f"{review.review_id}"
        ),

        "from": {
            "id": USER_ID
        },
    }

    handled = (
        webhook_handler
        .handle_editorial_callback(
            callback_query=callback_query,
            req_id="test01"
        )
    )

    assert (
        handled
        is True
    )

    stored = (
        get_pending_review(
            review.review_id,
            user_id=USER_ID
        )
    )

    assert (
        stored
        is not None
    )

    assert (
        stored.status
        == STATUS_PENDING
    )

    assert (
        is_waiting_for_admin_instruction(
            stored
        )
        is True
    )

    assert (
        stored.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is True
    )

    waiting_review = (
        get_waiting_admin_instruction_review(
            USER_ID
        )
    )

    assert (
        waiting_review
        is not None
    )

    assert (
        waiting_review.review_id
        == review.review_id
    )

    assert any(
        "منتظر"
        in item["text"]
        or "دستور ادمین"
        in item["text"]
        for item
        in sent_messages
    )


# =========================================================
# TEST 02
# NEXT TEXT MUST BE CONSUMED AS ADMIN INSTRUCTION
#
# مهم‌ترین تست E2E این مرحله.
#
# پیام ادمین:
#
# - نباید News جدید شود
# - نباید مستقیم منتشر شود
# - نباید Review جدید ایجاد کند
# - باید روی Review منتظر اعمال شود
# =========================================================

def test_next_text_is_consumed_as_admin_instruction(
    monkeypatch
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
    # IF NORMAL NEWS PIPELINE IS CALLED => TEST MUST FAIL
    # =====================================================

    def forbidden_queue(
        *args,
        **kwargs
    ):

        pytest.fail(
            "Admin instruction must not enter "
            "normal editorial queue"
        )

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        forbidden_queue
    )

    def forbidden_normal_publish(
        *args,
        **kwargs
    ):

        pytest.fail(
            "Admin instruction must not be "
            "published as normal text"
        )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        forbidden_normal_publish
    )

    # =====================================================
    # FAKE AI
    # =====================================================

    import core.editorial_review

    captured = {}

    def fake_apply_admin_instruction(
        original_text,
        previous_summary,
        admin_instruction,
        content_type,
        target_length=950,
        summarizer=None
    ):

        captured[
            "original_text"
        ] = original_text

        captured[
            "previous_summary"
        ] = previous_summary

        captured[
            "admin_instruction"
        ] = admin_instruction

        captured[
            "content_type"
        ] = content_type

        return (
            build_successful_admin_result()
        )

    monkeypatch.setattr(
        core.editorial_review,
        (
            "apply_admin_instruction_to_"
            "editorial_summary"
        ),
        fake_apply_admin_instruction
    )

    # =====================================================
    # WEBHOOK REQUEST
    # =====================================================

    payload = {
        "update_id": 900001,

        "message": {
            "message_id": 500,

            "chat": {
                "id": USER_ID,
                "type": "private",
            },

            "from": {
                "id": USER_ID,
                "is_bot": False,
            },

            "text":
                ADMIN_INSTRUCTION,
        }
    }

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    # =====================================================
    # HTTP
    # =====================================================

    assert (
        status
        == 200
    )

    assert (
        body.get(
            "ok"
        )
        is True
    )

    # =====================================================
    # ORIGINAL BODY MUST BE AI SOURCE
    # =====================================================

    assert (
        captured[
            "original_text"
        ]
        == ORIGINAL_BODY
    )

    # =====================================================
    # PREVIOUS SUMMARY MUST BE AVAILABLE
    # =====================================================

    assert (
        captured[
            "previous_summary"
        ]
        == CURRENT_SUMMARY
    )

    # =====================================================
    # EXACT ADMIN INSTRUCTION
    # =====================================================

    assert (
        captured[
            "admin_instruction"
        ]
        == ADMIN_INSTRUCTION
    )

    assert (
        captured[
            "content_type"
        ]
        == CONTENT_TYPE_OPINION_NOTE
    )

    # =====================================================
    # REVIEW MUST BE UPDATED
    # =====================================================

    updated = (
        get_pending_review(
            review.review_id,
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

    # =====================================================
    # WAITING MUST BE CLEARED AFTER SUCCESS
    # =====================================================

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is False
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is False
    )

    # =====================================================
    # INSTRUCTION HISTORY
    # =====================================================

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_LAST_TEXT_KEY
        )
        == ADMIN_INSTRUCTION
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY
        )
        == 1
    )

    # =====================================================
    # NEW PREVIEW MUST BE SENT
    # =====================================================

    assert any(
        UPDATED_SUMMARY
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


# =========================================================
# TEST 03
# ADMIN INSTRUCTION MUST NEVER BE PUBLISHED TO CHANNEL
# =========================================================

def test_admin_instruction_text_is_never_published_directly(
    monkeypatch
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
    # CHANNEL PUBLISH MUST NEVER HAPPEN
    # =====================================================

    channel_calls = []

    def fake_send_to_channel(
        text,
        parse_mode=None
    ):

        channel_calls.append({
            "text": text,
            "parse_mode": parse_mode,
        })

        return True

    monkeypatch.setattr(
        webhook_handler,
        "send_to_channel",
        fake_send_to_channel
    )

    # =====================================================
    # NORMAL TEXT PIPELINE MUST NOT RUN
    # =====================================================

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda *args, **kwargs:
            pytest.fail(
                "Instruction must not create "
                "another editorial review"
            )
    )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        lambda *args, **kwargs:
            pytest.fail(
                "Instruction must not use "
                "normal publish path"
            )
    )

    # =====================================================
    # FAKE SUCCESSFUL AI
    # =====================================================

    import core.editorial_review

    monkeypatch.setattr(
        core.editorial_review,
        (
            "apply_admin_instruction_to_"
            "editorial_summary"
        ),
        lambda *args, **kwargs:
            build_successful_admin_result()
    )

    payload = {
        "update_id": 900002,

        "message": {
            "message_id": 501,

            "chat": {
                "id": USER_ID,
                "type": "private",
            },

            "from": {
                "id": USER_ID,
                "is_bot": False,
            },

            "text":
                ADMIN_INSTRUCTION,
        }
    }

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        body.get(
            "ok"
        )
        is True
    )

    # =====================================================
    # ABSOLUTELY NO CHANNEL PUBLICATION
    # =====================================================

    assert (
        channel_calls
        == []
    )

    updated = (
        get_pending_review(
            review.review_id,
            USER_ID
        )
    )

    assert (
        updated.current_summary
        == UPDATED_SUMMARY
    )


# =========================================================
# TEST 04
# FAILED VALIDATION MUST KEEP PREVIOUS SUMMARY
#
# سیاست:
#
# اگر AI یا Validator نسخه جدید را رد کرد:
#
# - Current Summary قبلی باقی می‌ماند
# - Review همچنان Pending است
# - چیزی منتشر نمی‌شود
# - Waiting Mode نیز باقی می‌ماند تا ادمین
#   بتواند دستور اصلاح‌شده دیگری بفرستد.
# =========================================================

def test_failed_admin_instruction_keeps_previous_summary(
    monkeypatch
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

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda *args, **kwargs:
            pytest.fail(
                "Failed instruction must still "
                "not enter normal news pipeline"
            )
    )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        lambda *args, **kwargs:
            pytest.fail(
                "Failed admin instruction must "
                "not be published"
            )
    )

    # =====================================================
    # FAKE VALIDATION FAILURE
    # =====================================================

    import core.editorial_review

    monkeypatch.setattr(
        core.editorial_review,
        (
            "apply_admin_instruction_to_"
            "editorial_summary"
        ),
        lambda *args, **kwargs:
            build_failed_admin_result()
    )

    payload = {
        "update_id": 900003,

        "message": {
            "message_id": 502,

            "chat": {
                "id": USER_ID,
                "type": "private",
            },

            "from": {
                "id": USER_ID,
                "is_bot": False,
            },

            "text":
                ADMIN_INSTRUCTION,
        }
    }

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        body.get(
            "ok"
        )
        is True
    )

    stored = (
        get_pending_review(
            review.review_id,
            USER_ID
        )
    )

    # =====================================================
    # OLD SUMMARY MUST SURVIVE
    # =====================================================

    assert (
        stored.current_summary
        == CURRENT_SUMMARY
    )

    # =====================================================
    # REVIEW MUST REMAIN ACTIVE
    # =====================================================

    assert (
        stored.status
        == STATUS_PENDING
    )

    # =====================================================
    # WAITING MUST REMAIN ACTIVE
    #
    # ادمین بتواند بدون زدن دوباره دکمه
    # دستور اصلاح‌شده بفرستد.
    # =====================================================

    assert (
        is_waiting_for_admin_instruction(
            stored
        )
        is True
    )

    # =====================================================
    # FAILED INSTRUCTION MUST NOT COUNT AS APPLIED
    # =====================================================

    assert (
        stored.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY,
            0
        )
        == 0
    )

    # =====================================================
    # USER MUST RECEIVE FAILURE MESSAGE
    # =====================================================

    assert any(
        (
            "تأیید"
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
            "اصلاح"
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


# =========================================================
# TEST 05
# NORMAL TEXT WITHOUT WAITING REVIEW
# MUST KEEP OLD PIPELINE
# =========================================================

def test_normal_text_without_waiting_review_keeps_old_path(
    monkeypatch
):

    sent_messages = []

    install_common_webhook_mocks(
        monkeypatch,
        sent_messages
    )

    queue_calls = []

    process_calls = []

    def fake_queue(
        chat_id,
        text,
        entities,
        forward_source=None
    ):

        queue_calls.append({
            "chat_id": chat_id,
            "text": text,
        })

        return False

    def fake_process(
        chat_id,
        text,
        entities,
        forward_source=None
    ):

        process_calls.append({
            "chat_id": chat_id,
            "text": text,
        })

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

    normal_text = (
        "این یک خبر عادی برای تست مسیر قبلی است."
    )

    payload = {
        "update_id": 900004,

        "message": {
            "message_id": 503,

            "chat": {
                "id": USER_ID,
                "type": "private",
            },

            "from": {
                "id": USER_ID,
                "is_bot": False,
            },

            "text":
                normal_text,
        }
    }

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        body, status = (
            webhook_handler
            .handle_webhook()
        )

    assert (
        status
        == 200
    )

    assert (
        body.get(
            "ok"
        )
        is True
    )

    # =====================================================
    # OLD PIPELINE MUST STILL WORK
    # =====================================================

    assert (
        len(
            queue_calls
        )
        == 1
    )

    assert (
        queue_calls[0][
            "text"
        ]
        == normal_text
    )

    assert (
        len(
            process_calls
        )
        == 1
    )

    assert (
        process_calls[0][
            "text"
        ]
        == normal_text
    )


# =========================================================
# TEST 06
# ADMIN INSTRUCTION SUCCESS MUST NOT FINALIZE REVIEW
#
# بعد از اصلاح:
#
# ادمین هنوز باید بتواند:
#
# ✅ انتشار خلاصه
# ✏️ اصلاح دوباره
# 📄 انتشار اصل
# 🔄 بازنویسی
# ❌ لغو
#
# را انتخاب کند.
# =========================================================

def test_successful_admin_edit_keeps_review_pending(
    monkeypatch
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

    monkeypatch.setattr(
        webhook_handler,
        "try_queue_editorial_text_review",
        lambda *args, **kwargs:
            pytest.fail(
                "Admin instruction entered "
                "normal queue"
            )
    )

    monkeypatch.setattr(
        webhook_handler,
        "process_text_message",
        lambda *args, **kwargs:
            pytest.fail(
                "Admin instruction entered "
                "normal publish path"
            )
    )

    import core.editorial_review

    monkeypatch.setattr(
        core.editorial_review,
        (
            "apply_admin_instruction_to_"
            "editorial_summary"
        ),
        lambda *args, **kwargs:
            build_successful_admin_result()
    )

    payload = {
        "update_id": 900005,

        "message": {
            "message_id": 504,

            "chat": {
                "id": USER_ID,
                "type": "private",
            },

            "from": {
                "id": USER_ID,
                "is_bot": False,
            },

            "text":
                ADMIN_INSTRUCTION,
        }
    }

    with app.test_request_context(
        "/webhook",
        method="POST",
        json=payload
    ):

        _, status = (
            webhook_handler
            .handle_webhook()
        )

    assert (
        status
        == 200
    )

    stored = (
        get_pending_review(
            review.review_id,
            USER_ID
        )
    )

    assert (
        stored.status
        == STATUS_PENDING
    )

    assert (
        stored.current_summary
        == UPDATED_SUMMARY
    )

    assert (
        is_waiting_for_admin_instruction(
            stored
        )
        is False
    )

    # =====================================================
    # PREVIEW MUST HAVE INLINE KEYBOARD
    # =====================================================

    preview_messages = [
        item
        for item
        in sent_messages
        if item.get(
            "reply_markup"
        )
    ]

    assert (
        preview_messages
    )

    keyboard = (
        preview_messages[-1][
            "reply_markup"
        ]
    )

    callback_values = []

    for row in (
        keyboard.get(
            "inline_keyboard",
            []
        )
        or []
    ):

        for button in row:

            callback_data = (
                button.get(
                    "callback_data"
                )
            )

            if callback_data:

                callback_values.append(
                    callback_data
                )

    assert (
        f"ed:summary:{review.review_id}"
        in callback_values
    )

    assert (
        f"ed:instruction:{review.review_id}"
        in callback_values
    )

    assert (
        f"ed:original:{review.review_id}"
        in callback_values
    )

    assert (
        f"ed:cancel:{review.review_id}"
        in callback_values
    )
