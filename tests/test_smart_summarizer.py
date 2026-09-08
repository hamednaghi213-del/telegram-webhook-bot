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


# =========================================================
# REQUIREMENT A: BOUNDED ADAPTIVE OVERSHOOT RETRIES
# (opt-in, max_overshoot_retries, validated against the
# caller's ORIGINAL target_length on every attempt)
# =========================================================


def _neutral_filler(length):
    sentence = (
        "این یک جمله خنثی و بدون عدد یا نام خاص است. "
    )
    text = (sentence * (length // len(sentence) + 2))
    return text[:length]


def test_default_behavior_allows_only_one_overshoot_retry():
    """
    Unset max_overshoot_retries must reproduce the original
    single-retry contract byte-for-byte: exactly one retry attempt
    (two total generation calls), even if the retry still overshoots.
    """

    original = _neutral_filler(3000)

    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        # Every attempt overshoots the caller's target (940).
        return _neutral_filler(1000)

    result = summarize_text_safely(
        original_text=original,
        target_length=940,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.9,
    )

    # 1 initial call + 1 retry == 2 total, never 3.
    assert len(calls) == 2
    assert result.success is False
    assert result.metadata["max_overshoot_retries"] == 1
    assert result.metadata["overshoot_attempts"] == 1


def test_underfill_retry_failure_falls_back_to_valid_first_result():
    original = _neutral_filler(1200)
    first = _neutral_filler(825)
    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        return first if len(calls) == 1 else _neutral_filler(1223)

    result = summarize_text_safely(
        original_text=original,
        target_length=940,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.9,
    )

    assert len(calls) == 2
    assert result.success is True
    assert result.validation_passed is True
    assert result.summary_text == first
    assert result.summary_length == 825
    assert result.metadata["retry_reason"] == "underfill"


def test_external_short_style_opt_in_allows_three_total_attempts():
    """
    Requirement A: opt-in max_overshoot_retries=2 permits up to 3
    total attempts (1 initial + 2 retries), matching the External
    Review SHORT wiring (EXTERNAL_SHORT_MAX_OVERSHOOT_RETRIES=2).
    Every attempt must still validate against the ORIGINAL
    target_length of 940.
    """

    original = _neutral_filler(3000)

    call_lengths = [1000, 980, 900]
    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        return _neutral_filler(
            call_lengths[len(calls) - 1]
        )

    result = summarize_text_safely(
        original_text=original,
        target_length=940,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.9,
        max_overshoot_retries=2,
    )

    # 1 initial + 2 retries == 3 total attempts.
    assert len(calls) == 3

    assert result.success is True
    assert result.validation_passed is True
    assert len(result.summary_text) == 900
    assert len(result.summary_text) <= 940

    assert result.metadata["max_overshoot_retries"] == 2
    assert result.metadata["overshoot_attempts"] == 2


def test_opt_in_overshoot_retries_still_fail_closed_when_exhausted():
    """
    Even with the larger opt-in retry budget, if every attempt keeps
    overshooting the ORIGINAL target, the function must fail closed
    (return the original text, success False) rather than accepting
    an over-length summary.
    """

    original = _neutral_filler(3000)

    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        # Always overshoots the caller's original 940 target.
        return _neutral_filler(1000)

    result = summarize_text_safely(
        original_text=original,
        target_length=940,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.9,
        max_overshoot_retries=2,
    )

    # 1 initial + 2 retries == 3 total attempts, all exhausted.
    assert len(calls) == 3

    assert result.success is False
    assert result.validation_passed is False
    assert result.summary_text == original
    assert result.metadata["max_overshoot_retries"] == 2
    assert result.metadata["overshoot_attempts"] == 2


def test_overshoot_retry_validates_every_attempt_against_original_target():
    """
    Requirement A: raising the retry budget must never relax what
    counts as a valid result -- every retry (not just the first) is
    validated with validate_summary against the caller's ORIGINAL
    target_length (940), never the internal (smaller) retry target.
    """

    original = _neutral_filler(3000)

    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        # First attempt overshoots; the single retry lands exactly
        # at the original target boundary (940), which must be
        # accepted even though it is larger than the internal retry
        # target requested of the provider.
        if len(calls) == 1:
            return _neutral_filler(1000)
        return _neutral_filler(940)

    result = summarize_text_safely(
        original_text=original,
        target_length=940,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.9,
    )

    assert len(calls) == 2
    # The internal retry target requested from the provider must be
    # smaller than 940 (adaptive), yet the 940-length result is
    # still accepted because it fits the ORIGINAL target.
    assert calls[1] < 940

    assert result.success is True
    assert len(result.summary_text) == 940


def test_retry_target_floor_allows_exact_1030_to_976_to_valid():
    original = _neutral_filler(32533)
    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        if len(calls) == 1:
            return _neutral_filler(1200)
        return _neutral_filler(1030)

    result = summarize_text_safely(
        original_text=original,
        target_length=1030,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.97,
        max_overshoot_retries=2,
    )

    assert calls == [1030, 976]
    assert result.success is True
    assert result.validation_passed is True
    assert len(result.summary_text) == 1030
    assert result.metadata["retry_target"] == 976


def test_retry_target_floor_still_fails_closed_when_1030_to_976_remains_invalid():
    original = _neutral_filler(32533)
    calls = []

    def fake_provider(original_text, instruction, target_length):
        calls.append(target_length)
        return _neutral_filler(1200 if len(calls) == 1 else 1100)

    result = summarize_text_safely(
        original_text=original,
        target_length=1030,
        summarizer=fake_provider,
        aggressive_max_reduction_ratio=0.97,
        max_overshoot_retries=2,
    )

    assert calls == [1030, 976]
    assert result.success is False
    assert result.validation_passed is False
    assert result.summary_text == original
