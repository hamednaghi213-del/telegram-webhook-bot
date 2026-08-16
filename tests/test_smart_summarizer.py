from core.smart_summarizer import (
    DEFAULT_MAX_REDUCTION_RATIO,
    SummaryResult,
    calculate_reduction_ratio,
    extract_numbers,
    extract_mentions,
    extract_hashtags,
    extract_urls,
    extract_certainty_markers,
    extract_protected_facts,
    detect_new_numbers,
    needs_summarization,
    validate_summary,
    build_summarization_instruction,
    summarize_text_safely,
)


# =========================================================
# TEST 01
# NEEDS SUMMARIZATION
# =========================================================

def test_needs_summarization():

    assert (
        needs_summarization(
            "متن کوتاه",
            100
        )
        is False
    )

    assert (
        needs_summarization(
            "ا" * 101,
            100
        )
        is True
    )

    assert (
        needs_summarization(
            "",
            100
        )
        is False
    )


# =========================================================
# TEST 02
# REDUCTION RATIO
# =========================================================

def test_calculate_reduction_ratio():

    original = (
        "ا"
        * 100
    )

    summary = (
        "ا"
        * 70
    )

    ratio = (
        calculate_reduction_ratio(
            original,
            summary
        )
    )

    assert (
        round(
            ratio,
            2
        )
        == 0.30
    )


# =========================================================
# TEST 03
# EXTRACT NUMBERS
# =========================================================

def test_extract_numbers():

    text = (
        "در سال ۲۰۲۶ میزان رشد 12.5 درصد "
        "و رقم نهایی ۳۰۰ اعلام شد."
    )

    numbers = (
        extract_numbers(
            text
        )
    )

    assert (
        "۲۰۲۶"
        in numbers
    )

    assert (
        "12.5"
        in numbers
    )

    assert (
        "۳۰۰"
        in numbers
    )


# =========================================================
# TEST 04
# EXTRACT MENTIONS
# =========================================================

def test_extract_mentions():

    text = (
        "منبع خبر @Donya24News "
        "و @Example_Channel است."
    )

    mentions = (
        extract_mentions(
            text
        )
    )

    assert (
        "@Donya24News"
        in mentions
    )

    assert (
        "@Example_Channel"
        in mentions
    )


# =========================================================
# TEST 05
# EXTRACT HASHTAGS
# =========================================================

def test_extract_hashtags():

    text = (
        "#دنیا_۲۴_نیوز "
        "#ایران "
        "متن خبر"
    )

    hashtags = (
        extract_hashtags(
            text
        )
    )

    assert (
        "#دنیا_۲۴_نیوز"
        in hashtags
    )

    assert (
        "#ایران"
        in hashtags
    )


# =========================================================
# TEST 06
# EXTRACT URLS
# =========================================================

def test_extract_urls():

    text = (
        "اطلاعات بیشتر در "
        "https://example.com/news "
        "منتشر شده است."
    )

    urls = (
        extract_urls(
            text
        )
    )

    assert (
        "https://example.com/news"
        in urls
    )


# =========================================================
# TEST 07
# CERTAINTY MARKERS
# =========================================================

def test_extract_certainty_markers():

    text = (
        "این رسانه مدعی شد احتمال دارد "
        "مذاکرات هفته آینده آغاز شود."
    )

    markers = (
        extract_certainty_markers(
            text
        )
    )

    assert (
        "مدعی شد"
        in markers
        or "مدعی"
        in markers
    )

    assert (
        "احتمال"
        in markers
    )


# =========================================================
# TEST 08
# PROTECTED FACTS
# =========================================================

def test_extract_protected_facts():

    text = (
        "رسانه @Example مدعی شد "
        "در سال ۲۰۲۶ تعداد ۳۰ نفر "
        "در این رویداد حضور داشتند."
    )

    facts = (
        extract_protected_facts(
            text
        )
    )

    assert (
        "۲۰۲۶"
        in facts[
            "numbers"
        ]
    )

    assert (
        "۳۰"
        in facts[
            "numbers"
        ]
    )

    assert (
        "@Example"
        in facts[
            "mentions"
        ]
    )

    assert (
        facts[
            "certainty_markers"
        ]
    )


# =========================================================
# TEST 09
# NEW NUMBER DETECTION
# =========================================================

def test_detect_new_numbers():

    original = (
        "این گزارش از کشته شدن "
        "۲۰ نفر خبر داد."
    )

    summary = (
        "این گزارش از کشته شدن "
        "۳۰ نفر خبر داد."
    )

    new_numbers = (
        detect_new_numbers(
            original,
            summary
        )
    )

    assert (
        "۳۰"
        in new_numbers
    )


# =========================================================
# TEST 10
# VALID SAFE SUMMARY
#
# کاهش باید زیر سقف 40 درصد باقی بماند.
# =========================================================

def test_validate_safe_summary():

    original = (
        "وزیر خارجه گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود. "
        "او افزود رایزنی‌ها همچنان ادامه دارد."
    )

    summary = (
        "وزیر خارجه گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود و "
        "رایزنی‌ها ادامه دارد."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is True
    )


# =========================================================
# TEST 11
# NEW NUMBER MUST FAIL
# =========================================================

def test_validate_rejects_new_number():

    original = (
        "مقام رسمی گفت "
        "۲۰ نفر در این نشست حضور داشتند."
    )

    summary = (
        "مقام رسمی گفت "
        "۳۰ نفر در این نشست حضور داشتند."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "new_numbers_detected"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 12
# CERTAINTY MUST NOT DISAPPEAR
# =========================================================

def test_validate_rejects_lost_certainty():

    original = (
        "وزیر گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود."
    )

    summary = (
        "مذاکرات هفته آینده آغاز می‌شود."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "certainty_markers_lost"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 13
# ATTRIBUTION MUST NOT DISAPPEAR
# =========================================================

def test_validate_rejects_lost_attribution_marker():

    original = (
        "رسانه ایکس مدعی شد "
        "۲۰ نفر کشته شده‌اند."
    )

    summary = (
        "۲۰ نفر کشته شده‌اند."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "certainty_markers_lost"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 14
# NEW MENTION MUST FAIL
# =========================================================

def test_validate_rejects_new_mention():

    original = (
        "این خبر توسط یک رسانه منتشر شد."
    )

    summary = (
        "این خبر توسط @FakeSource منتشر شد."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "new_mentions_detected"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 15
# NEW URL MUST FAIL
# =========================================================

def test_validate_rejects_new_url():

    original = (
        "این خبر در یک رسانه منتشر شد."
    )

    summary = (
        "این خبر در "
        "https://fake.example "
        "منتشر شد."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "new_urls_detected"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 16
# TOO AGGRESSIVE REDUCTION MUST FAIL
# =========================================================

def test_validate_rejects_aggressive_reduction():

    original = (
        "این یک متن خبری نسبتاً بلند "
        "برای بررسی میزان کاهش محتوا است. "
        * 10
    )

    summary = (
        "خبر کوتاه شد."
    )

    validation = (
        validate_summary(
            original_text=original,
            summary_text=summary,
            target_length=100,
            max_reduction_ratio=0.40
        )
    )

    assert (
        validation[
            "valid"
        ]
        is False
    )

    assert (
        "reduction_too_aggressive"
        in validation[
            "errors"
        ]
    )


# =========================================================
# TEST 17
# ALREADY FITS
# MODEL MUST NOT BE CALLED
# =========================================================

def test_already_fits_does_not_call_provider():

    called = {
        "value": False
    }

    def fake_provider(
        original_text,
        instruction,
        target_length
    ):

        called[
            "value"
        ] = True

        return (
            "این متن نباید ساخته شود."
        )

    original = (
        "متن کوتاه خبر"
    )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=100,
            summarizer=fake_provider
        )
    )

    assert (
        result.success
        is True
    )

    assert (
        result.summary_text
        == original
    )

    assert (
        result.reason
        == "already_fits"
    )

    assert (
        called[
            "value"
        ]
        is False
    )


# =========================================================
# TEST 18
# NO PROVIDER
#
# ORIGINAL MUST RETURN BYTE-FOR-BYTE / STRING-FOR-STRING
# =========================================================

def test_no_provider_returns_original():

    original = (
        "این یک متن خبری طولانی است. "
        * 10
    )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=200,
            summarizer=None
        )
    )

    assert (
        result.success
        is False
    )

    assert (
        result.summary_text
        == original
    )

    assert (
        result.original_text
        == original
    )

    assert (
        result.reason
        == "summarizer_not_configured"
    )


# =========================================================
# TEST 19
# REQUIRED REDUCTION TOO LARGE
# PROVIDER MUST NOT BE CALLED
# =========================================================

def test_provider_not_called_if_required_reduction_is_unsafe():

    called = {
        "value": False
    }

    def fake_provider(
        original_text,
        instruction,
        target_length
    ):

        called[
            "value"
        ] = True

        return (
            "خلاصه"
        )

    original = (
        "الف"
        * 1000
    )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=400,
            summarizer=fake_provider,
            max_reduction_ratio=0.40
        )
    )

    assert (
        result.success
        is False
    )

    assert (
        result.reason
        == "required_reduction_too_aggressive"
    )

    assert (
        result.summary_text
        == original
    )

    assert (
        called[
            "value"
        ]
        is False
    )


# =========================================================
# TEST 20
# SAFE PROVIDER RESULT ACCEPTED
#
# کاهش زیر 40 درصد باقی می‌ماند.
# =========================================================

def test_safe_provider_summary_is_accepted():

    original = (
        "وزیر خارجه گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود. "
        "او افزود رایزنی‌های دیپلماتیک "
        "در روزهای اخیر ادامه داشته است."
    )

    safe_summary = (
        "وزیر خارجه گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود و "
        "رایزنی‌های دیپلماتیک ادامه دارد."
    )

    def fake_provider(
        original_text,
        instruction,
        target_length
    ):

        return (
            safe_summary
        )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=100,
            summarizer=fake_provider
        )
    )

    assert (
        result.success
        is True
    )

    assert (
        result.validation_passed
        is True
    )

    assert (
        result.summary_text
        == safe_summary
    )

    assert (
        result.reason
        == "summary_accepted"
    )


# =========================================================
# TEST 21
# UNSAFE PROVIDER RESULT REJECTED
#
# Target باید از متن اصلی کوتاه‌تر باشد تا Provider
# واقعاً فراخوانی شود.
# =========================================================

def test_unsafe_provider_summary_is_rejected():

    original = (
        "وزیر گفت احتمال دارد "
        "مذاکرات هفته آینده آغاز شود."
    )

    unsafe_summary = (
        "مذاکرات هفته آینده آغاز می‌شود."
    )

    called = {
        "value": False
    }

    def fake_provider(
        original_text,
        instruction,
        target_length
    ):

        called[
            "value"
        ] = True

        return (
            unsafe_summary
        )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=40,
            summarizer=fake_provider
        )
    )

    assert (
        called[
            "value"
        ]
        is True
    )

    assert (
        result.success
        is False
    )

    assert (
        result.validation_passed
        is False
    )

    assert (
        result.summary_text
        == original
    )

    assert (
        result.reason
        == "validation_failed"
    )

    assert (
        "certainty_markers_lost"
        in result.metadata[
            "validation"
        ][
            "errors"
        ]
    )


# =========================================================
# TEST 22
# PROVIDER ERROR
# ORIGINAL MUST SURVIVE EXACTLY
# =========================================================

def test_provider_exception_returns_original():

    original = (
        "این یک متن خبری طولانی برای "
        "آزمایش خطای سرویس خلاصه‌ساز است. "
        * 5
    )

    def broken_provider(
        original_text,
        instruction,
        target_length
    ):

        raise RuntimeError(
            "provider unavailable"
        )

    result = (
        summarize_text_safely(
            original_text=original,
            target_length=200,
            summarizer=broken_provider
        )
    )

    assert (
        result.success
        is False
    )

    assert (
        result.summary_text
        == original
    )

    assert (
        result.original_text
        == original
    )

    assert (
        result.reason
        == "provider_error"
    )


# =========================================================
# TEST 23
# INSTRUCTION MUST CONTAIN ANTI-DISTORTION RULES
# =========================================================

def test_instruction_contains_anti_distortion_rules():

    instruction = (
        build_summarization_instruction(
            900
        )
    )

    assert (
        "افزودن اطلاعات جدید"
        in instruction
    )

    assert (
        "میزان قطعیت"
        in instruction
    )

    assert (
        "اعداد"
        in instruction
    )

    assert (
        "نام افراد"
        in instruction
    )

    assert (
        "دیدگاه یا برداشت شخصی"
        in instruction
    )

    assert (
        "900"
        in instruction
    )


# =========================================================
# TEST 24
# RESULT OBJECT
# =========================================================

def test_summary_result_object():

    result = SummaryResult(
        success=True,
        original_text="متن اصلی",
        summary_text="متن اصلی",
        target_length=100,
        original_length=8,
        summary_length=8,
        reduction_ratio=0.0,
        validation_passed=True,
        reason="already_fits",
        metadata={}
    )

    assert (
        result.success
        is True
    )

    assert (
        result.validation_passed
        is True
    )


# =========================================================
# TEST 25
# DEFAULT REDUCTION POLICY
# =========================================================

def test_default_reduction_policy_is_40_percent():

    assert (
        DEFAULT_MAX_REDUCTION_RATIO
        == 0.40
    )
