from core.editorial_pending import (
    ADMIN_INSTRUCTION_COUNT_KEY,
    ADMIN_INSTRUCTION_LAST_TEXT_KEY,
    ADMIN_INSTRUCTION_WAITING_KEY,
    STATUS_PENDING,
    clear_pending_reviews,
    create_pending_review,
    get_admin_instruction_count,
    get_waiting_admin_instruction_review,
    is_waiting_for_admin_instruction,
    record_admin_instruction_applied,
    set_admin_instruction_waiting,
    update_pending_summary,
)

from core.editorial_review import (
    CONTENT_TYPE_OPINION_NOTE,
    MAX_ADMIN_INSTRUCTION_LENGTH,
    apply_admin_instruction_to_editorial_summary,
)


# =========================================================
# TEST DATA
# =========================================================

USER_ID = 101647751

OTHER_USER_ID = 999999999


ORIGINAL_BODY = (
    "ایران در شرایطی مذاکرات را ادامه می‌دهد که اعتماد میان "
    "طرفین کاهش یافته است. با این حال تهران حفظ چارچوب مذاکره "
    "را راهی برای کنترل هزینه‌های سیاسی و جلوگیری از ورود به "
    "یک بحران غیرقابل کنترل می‌داند. در این ارزیابی، ادامه "
    "گفت‌وگو لزوماً به معنای اعتماد به نتیجه مذاکرات نیست بلکه "
    "ابزاری برای مدیریت صحنه و انتقال هزینه شکست احتمالی به "
    "طرف مقابل است."
)


CURRENT_SUMMARY = (
    "ایران با وجود کاهش اعتماد، ادامه مذاکرات را ابزاری "
    "برای کنترل صحنه و جلوگیری از تشدید بحران می‌داند."
)


# =========================================================
# TEST SETUP
# =========================================================

def setup_function():

    clear_pending_reviews()


def teardown_function():

    clear_pending_reviews()


# =========================================================
# TEST 01
# DEFAULT ADMIN INSTRUCTION STATE
# =========================================================

def test_pending_review_admin_instruction_default_state():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
    )

    assert (
        review.status
        == STATUS_PENDING
    )

    assert (
        review.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is False
    )

    assert (
        review.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY
        )
        == 0
    )

    assert (
        is_waiting_for_admin_instruction(
            review
        )
        is False
    )


# =========================================================
# TEST 02
# SET ADMIN INSTRUCTION WAITING
# =========================================================

def test_set_admin_instruction_waiting():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
    )

    updated = (
        set_admin_instruction_waiting(
            review_id=review.review_id,
            user_id=USER_ID
        )
    )

    assert updated is not None

    assert (
        updated.review_id
        == review.review_id
    )

    assert (
        updated.status
        == STATUS_PENDING
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is True
    )

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is True
    )


# =========================================================
# TEST 03
# GET WAITING REVIEW
# =========================================================

def test_get_waiting_admin_instruction_review():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
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

    assert waiting is not None

    assert (
        waiting.review_id
        == review.review_id
    )

    assert (
        waiting.user_id
        == USER_ID
    )

    assert (
        is_waiting_for_admin_instruction(
            waiting
        )
        is True
    )


# =========================================================
# TEST 04
# ONLY ONE WAITING REVIEW PER USER
# =========================================================

def test_only_one_waiting_admin_review_per_user():

    first_review = (
        create_pending_review(
            user_id=USER_ID,
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),
            original_text=ORIGINAL_BODY,
            current_summary=CURRENT_SUMMARY,
        )
    )

    second_review = (
        create_pending_review(
            user_id=USER_ID,
            content_type=(
                CONTENT_TYPE_OPINION_NOTE
            ),
            original_text=ORIGINAL_BODY,
            current_summary=CURRENT_SUMMARY,
        )
    )

    set_admin_instruction_waiting(
        review_id=first_review.review_id,
        user_id=USER_ID
    )

    assert (
        is_waiting_for_admin_instruction(
            first_review
        )
        is True
    )

    set_admin_instruction_waiting(
        review_id=second_review.review_id,
        user_id=USER_ID
    )

    assert (
        is_waiting_for_admin_instruction(
            first_review
        )
        is False
    )

    assert (
        is_waiting_for_admin_instruction(
            second_review
        )
        is True
    )

    waiting = (
        get_waiting_admin_instruction_review(
            USER_ID
        )
    )

    assert waiting is not None

    assert (
        waiting.review_id
        == second_review.review_id
    )


# =========================================================
# TEST 05
# WRONG USER CANNOT ACTIVATE WAITING
# =========================================================

def test_wrong_user_cannot_activate_admin_waiting():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
    )

    result = (
        set_admin_instruction_waiting(
            review_id=review.review_id,
            user_id=OTHER_USER_ID
        )
    )

    assert result is None

    assert (
        is_waiting_for_admin_instruction(
            review
        )
        is False
    )


# =========================================================
# TEST 06
# RECORD APPLIED ADMIN INSTRUCTION
# =========================================================

def test_record_admin_instruction_applied():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=USER_ID
    )

    instruction = (
        "تأکید بیشتری روی کنترل صحنه داشته باشد."
    )

    updated = (
        record_admin_instruction_applied(
            review_id=review.review_id,
            user_id=USER_ID,
            instruction=instruction
        )
    )

    assert updated is not None

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY
        )
        is False
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_LAST_TEXT_KEY
        )
        == instruction
    )

    assert (
        updated.metadata.get(
            ADMIN_INSTRUCTION_COUNT_KEY
        )
        == 1
    )

    assert (
        get_admin_instruction_count(
            updated
        )
        == 1
    )

    assert (
        is_waiting_for_admin_instruction(
            updated
        )
        is False
    )


# =========================================================
# TEST 07
# APPLY ADMIN INSTRUCTION SUCCESS
#
# نکته مهم:
#
# خروجی Fake AI نیز باید قواعد Validator را رعایت کند.
#
# متن اصلی دارای نشانه‌های قطعیت/انتساب مانند:
#
# در این ارزیابی
# لزوماً
# احتمالی
#
# است.
#
# بنابراین Fake Summary نیز آنها را حفظ می‌کند.
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

        assert (
            target_length
            > 0
        )

        return (
            "در این ارزیابی، ایران با وجود کاهش اعتماد، "
            "ادامه مذاکرات را لزوماً نشانه اعتماد به نتیجه "
            "نمی‌داند، بلکه آن را ابزاری برای کنترل صحنه، "
            "جلوگیری از ورود به بحران غیرقابل کنترل و انتقال "
            "هزینه شکست احتمالی به طرف مقابل می‌داند."
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
        result.original_text
        == ORIGINAL_BODY
    )

    assert (
        result.suggested_text
        != CURRENT_SUMMARY
    )

    assert (
        "کنترل صحنه"
        in result.suggested_text
    )

    assert (
        "در این ارزیابی"
        in result.suggested_text
    )

    assert (
        "لزوماً"
        in result.suggested_text
    )

    assert (
        "احتمالی"
        in result.suggested_text
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.metadata.get(
            "admin_instruction_applied"
        )
        is True
    )

    assert (
        result.metadata.get(
            "admin_instruction"
        )
        == (
            "تأکید بیشتری روی کنترل صحنه داشته باشد."
        )
    )


# =========================================================
# TEST 08
# EMPTY ADMIN INSTRUCTION
# =========================================================

def test_apply_admin_instruction_empty_instruction():

    provider_called = {
        "value": False
    }

    def fake_summarizer(
        original_text,
        instruction,
        target_length
    ):

        provider_called[
            "value"
        ] = True

        return CURRENT_SUMMARY

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction="",
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=fake_summarizer
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

    assert (
        provider_called[
            "value"
        ]
        is False
    )


# =========================================================
# TEST 09
# ADMIN INSTRUCTION TOO LONG
# =========================================================

def test_apply_admin_instruction_too_long():

    provider_called = {
        "value": False
    }

    def fake_summarizer(
        original_text,
        instruction,
        target_length
    ):

        provider_called[
            "value"
        ] = True

        return CURRENT_SUMMARY

    long_instruction = (
        "ا"
        * (
            MAX_ADMIN_INSTRUCTION_LENGTH
            + 1
        )
    )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                long_instruction
            ),
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=fake_summarizer
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

    assert (
        provider_called[
            "value"
        ]
        is False
    )


# =========================================================
# TEST 10
# PROVIDER FAILURE KEEPS PREVIOUS SUMMARY
# =========================================================

def test_admin_instruction_provider_failure_keeps_previous_summary():

    def failing_summarizer(
        original_text,
        instruction,
        target_length
    ):

        raise RuntimeError(
            "provider unavailable"
        )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                "روی کنترل صحنه تأکید بیشتری داشته باشد."
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
        result.reason
        == "admin_instruction_failed"
    )

    assert (
        result.suggested_text
        == CURRENT_SUMMARY
    )

    assert (
        result.original_text
        == ORIGINAL_BODY
    )

    assert (
        result.metadata.get(
            "generation_reason"
        )
        == "provider_error"
    )


# =========================================================
# TEST 11
# UPDATED SUMMARY CAN BE SAVED
# =========================================================

def test_admin_instruction_updated_summary_can_be_saved():

    review = create_pending_review(
        user_id=USER_ID,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        original_text=ORIGINAL_BODY,
        current_summary=CURRENT_SUMMARY,
    )

    new_summary = (
        "در این ارزیابی، ایران با وجود کاهش اعتماد، "
        "ادامه مذاکرات را لزوماً نشانه اعتماد نمی‌داند "
        "و آن را ابزاری برای مدیریت صحنه و انتقال هزینه "
        "شکست احتمالی به طرف مقابل می‌داند."
    )

    updated = (
        update_pending_summary(
            review_id=review.review_id,
            user_id=USER_ID,
            new_summary=new_summary,
            regeneration_count=(
                review.regeneration_count
            ),
            metadata={
                "summary_success": True,
                "admin_instruction_applied": True
            }
        )
    )

    assert updated is not None

    assert (
        updated.current_summary
        == new_summary
    )

    assert (
        updated.original_text
        == ORIGINAL_BODY
    )

    assert (
        updated.metadata.get(
            "summary_success"
        )
        is True
    )

    assert (
        updated.metadata.get(
            "admin_instruction_applied"
        )
        is True
    )


# =========================================================
# TEST 12
# ORIGINAL TEXT MUST ALWAYS BE PRESERVED
# =========================================================

def test_admin_instruction_preserves_original_text():

    def fake_summarizer(
        original_text,
        instruction,
        target_length
    ):

        return (
            "در این ارزیابی، ایران ادامه گفت‌وگو را "
            "لزوماً نشانه اعتماد نمی‌داند و آن را برای "
            "مدیریت صحنه و انتقال هزینه شکست احتمالی "
            "به طرف مقابل حفظ می‌کند."
        )

    result = (
        apply_admin_instruction_to_editorial_summary(
            original_text=ORIGINAL_BODY,
            previous_summary=CURRENT_SUMMARY,
            admin_instruction=(
                "نسخه را منسجم‌تر کن."
            ),
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=fake_summarizer
        )
    )

    assert (
        result.original_text
        == ORIGINAL_BODY
    )

    assert (
        ORIGINAL_BODY
        != result.suggested_text
    )

    assert (
        len(
            result.original_text
        )
        == len(
            ORIGINAL_BODY
        )
    )
