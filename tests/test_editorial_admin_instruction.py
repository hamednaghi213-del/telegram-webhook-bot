import os

import pytest

from core.editorial_pending import (
    clear_pending_reviews,
    create_pending_review,
    get_pending_review,
    get_waiting_admin_instruction_review,
    record_admin_instruction_applied,
    set_admin_instruction_waiting,
    update_pending_summary,
)

from core.editorial_review import (
    CONTENT_TYPE_OPINION_NOTE,
    apply_admin_instruction_to_editorial_summary,
)


# =========================================================
# FIXTURES
# =========================================================

@pytest.fixture(autouse=True)
def clear_store_before_and_after():

    clear_pending_reviews()

    yield

    clear_pending_reviews()


# =========================================================
# TEST DATA
# =========================================================

ORIGINAL_BODY = (
    "ایران در شرایطی مذاکرات را ادامه می‌دهد که "
    "اعتماد میان طرفین کاهش یافته است. "
    "با این حال تهران حفظ چارچوب مذاکره را "
    "راهی برای کنترل هزینه‌های سیاسی و جلوگیری "
    "از ورود به یک بحران غیرقابل کنترل می‌داند. "
    "در این ارزیابی، ادامه گفت‌وگو لزوماً به معنای "
    "اعتماد به نتیجه مذاکرات نیست بلکه ابزاری برای "
    "مدیریت صحنه و انتقال هزینه شکست احتمالی به طرف مقابل است."
)

CURRENT_SUMMARY = (
    "ایران با وجود کاهش اعتماد، ادامه مذاکرات را "
    "ابزاری برای کنترل صحنه و جلوگیری از تشدید بحران می‌داند."
)


# =========================================================
# TEST 01
# CREATE REVIEW DEFAULT ADMIN STATE
# =========================================================

def test_pending_review_admin_instruction_default_state():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "editorial_body":
                ORIGINAL_BODY,
            "summary_success":
                True
        }
    )

    assert review is not None

    assert (
        review.metadata.get(
            "awaiting_admin_instruction"
        )
        is False
    )

    assert (
        review.metadata.get(
            "admin_instruction_count"
        )
        == 0
    )


# =========================================================
# TEST 02
# ACTIVATE ADMIN WAITING MODE
# =========================================================

def test_set_admin_instruction_waiting():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "editorial_body":
                ORIGINAL_BODY,
            "summary_success":
                True
        }
    )

    updated = (
        set_admin_instruction_waiting(
            review_id=review.review_id,
            user_id=1001
        )
    )

    assert updated is not None

    assert (
        updated.metadata.get(
            "awaiting_admin_instruction"
        )
        is True
    )

    assert (
        updated.metadata.get(
            "admin_instruction_requested_at"
        )
        is not None
    )


# =========================================================
# TEST 03
# FIND WAITING REVIEW
# =========================================================

def test_get_waiting_admin_instruction_review():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "editorial_body":
                ORIGINAL_BODY,
            "summary_success":
                True
        }
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=1001
    )

    waiting = (
        get_waiting_admin_instruction_review(
            user_id=1001
        )
    )

    assert waiting is not None

    assert (
        waiting.review_id
        == review.review_id
    )


# =========================================================
# TEST 04
# ONLY ONE WAITING REVIEW PER USER
# =========================================================

def test_only_one_waiting_admin_review_per_user():

    first = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "summary_success":
                True
        }
    )

    second = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "summary_success":
                True
        }
    )

    set_admin_instruction_waiting(
        review_id=first.review_id,
        user_id=1001
    )

    set_admin_instruction_waiting(
        review_id=second.review_id,
        user_id=1001
    )

    first_after = get_pending_review(
        review_id=first.review_id,
        user_id=1001
    )

    second_after = get_pending_review(
        review_id=second.review_id,
        user_id=1001
    )

    assert (
        first_after.metadata.get(
            "awaiting_admin_instruction"
        )
        is False
    )

    assert (
        second_after.metadata.get(
            "awaiting_admin_instruction"
        )
        is True
    )


# =========================================================
# TEST 05
# WRONG USER CANNOT ACTIVATE WAITING
# =========================================================

def test_wrong_user_cannot_activate_admin_waiting():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY
    )

    result = (
        set_admin_instruction_waiting(
            review_id=review.review_id,
            user_id=9999
        )
    )

    assert result is None


# =========================================================
# TEST 06
# RECORD APPLIED ADMIN INSTRUCTION
# =========================================================

def test_record_admin_instruction_applied():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=1001
    )

    updated = (
        record_admin_instruction_applied(
            review_id=review.review_id,
            user_id=1001,
            instruction=(
                "تأکید بیشتری روی کنترل صحنه داشته باشد."
            )
        )
    )

    assert updated is not None

    assert (
        updated.metadata.get(
            "awaiting_admin_instruction"
        )
        is False
    )

    assert (
        updated.metadata.get(
            "admin_instruction_count"
        )
        == 1
    )

    assert (
        updated.metadata.get(
            "last_admin_instruction"
        )
        ==
        "تأکید بیشتری روی کنترل صحنه داشته باشد."
    )

    assert (
        updated.metadata.get(
            "last_admin_instruction_applied_at"
        )
        is not None
    )


# =========================================================
# TEST 07
# ADMIN EDIT SUCCESS
# =========================================================

def test_apply_admin_instruction_success():

    def fake_summarizer(
        original_text,
        instruction,
        target_length
    ):

        assert (
            ORIGINAL_BODY
            in original_text
        )

        assert (
            "دستور ادمین"
            in instruction
        )

        assert (
            "کنترل صحنه"
            in instruction
        )

        return (
            "ایران با وجود کاهش اعتماد، مذاکرات را "
            "ابزاری برای کنترل صحنه و جلوگیری از "
            "تشدید بحران می‌داند."
        )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                "تأکید بیشتری روی کنترل صحنه داشته باشد."
            ),
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=fake_summarizer
        )
    )

    assert (
        result.summary_success
        is True
    )

    assert (
        result.reason
        == "admin_instruction_ready"
    )

    assert (
        result.suggested_text
        != ""
    )

    assert (
        result.metadata.get(
            "admin_instruction_applied"
        )
        is True
    )


# =========================================================
# TEST 08
# ADMIN EDIT EMPTY INSTRUCTION
# =========================================================

def test_apply_admin_instruction_empty_instruction():

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction="",
            content_type=CONTENT_TYPE_OPINION_NOTE
        )
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == "admin_instruction_empty"
    )

    assert (
        result.suggested_text
        == CURRENT_SUMMARY
    )


# =========================================================
# TEST 09
# ADMIN EDIT TOO LONG
# =========================================================

def test_apply_admin_instruction_too_long():

    very_long_instruction = (
        "الف"
        * 1600
    )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                very_long_instruction
            ),
            content_type=CONTENT_TYPE_OPINION_NOTE
        )
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == "admin_instruction_too_long"
    )

    assert (
        result.suggested_text
        == CURRENT_SUMMARY
    )


# =========================================================
# TEST 10
# PROVIDER FAILURE KEEPS OLD SUMMARY
# =========================================================

def test_admin_instruction_provider_failure_keeps_previous_summary():

    def failing_summarizer(
        original_text,
        instruction,
        target_length
    ):

        raise RuntimeError(
            "provider failed"
        )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                "متن را کوتاه‌تر کن."
            ),
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=failing_summarizer
        )
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.suggested_text
        == CURRENT_SUMMARY
    )

    assert (
        result.reason
        == "admin_instruction_failed"
    )


# =========================================================
# TEST 11
# UPDATE SUMMARY AFTER ADMIN EDIT
# =========================================================

def test_admin_instruction_updated_summary_can_be_saved():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
        metadata={
            "summary_success":
                True
        }
    )

    new_summary = (
        "ایران مذاکرات را ابزاری برای "
        "کنترل صحنه و مهار هزینه بحران می‌داند."
    )

    updated = (
        update_pending_summary(
            review_id=review.review_id,
            user_id=1001,
            new_summary=new_summary,
            regeneration_count=(
                review.regeneration_count
            ),
            metadata={
                "summary_success":
                    True
            }
        )
    )

    assert updated is not None

    assert (
        updated.current_summary
        == new_summary
    )

    assert (
        updated.metadata.get(
            "summary_success"
        )
        is True
    )


# =========================================================
# TEST 12
# ADMIN INSTRUCTION MUST NOT MODIFY ORIGINAL
# =========================================================

def test_admin_instruction_preserves_original_text():

    review = create_pending_review(
        user_id=1001,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY
    )

    original_before = (
        review.original_text
    )

    update_pending_summary(
        review_id=review.review_id,
        user_id=1001,
        new_summary=(
            "نسخه جدید خلاصه"
        ),
        regeneration_count=0
    )

    updated = get_pending_review(
        review_id=review.review_id,
        user_id=1001
    )

    assert updated is not None

    assert (
        updated.original_text
        == original_before
    )
