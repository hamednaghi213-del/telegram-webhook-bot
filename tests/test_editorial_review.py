from core.editorial_review import (
    CONTENT_TYPE_NORMAL_NEWS,
    CONTENT_TYPE_NEWS_ANALYSIS,
    CONTENT_TYPE_OPINION_NOTE,
    CONTENT_TYPE_SENSITIVE,
    CONTENT_TYPE_UNCERTAIN,
    MAX_REGENERATION_COUNT,
    can_regenerate_editorial_summary,
    parse_editorial_classification,
    review_editorial_content,
    regenerate_editorial_summary,
)


# =========================================================
# TEST HELPERS
# =========================================================


def fake_classifier_normal(
    text,
    instruction,
    target_length
):
    return "NORMAL_NEWS"


def fake_classifier_analysis(
    text,
    instruction,
    target_length
):
    return "NEWS_ANALYSIS"


def fake_classifier_opinion(
    text,
    instruction,
    target_length
):
    return "OPINION_NOTE"


def fake_classifier_sensitive(
    text,
    instruction,
    target_length
):
    return "SENSITIVE_CONTENT"


def fake_classifier_uncertain(
    text,
    instruction,
    target_length
):
    return "UNCERTAIN"


def fake_regenerator_success(
    text,
    instruction,
    target_length
):
    candidate = (
        "نسخه جدید خلاصه تحلیلی است که "
        "تز اصلی، استدلال کلیدی و نتیجه متن "
        "را بدون افزودن اطلاعات تازه حفظ می‌کند."
    )

    if len(candidate) <= target_length:
        return candidate

    return candidate[:target_length]


def fake_regenerator_same(
    text,
    instruction,
    target_length
):
    return (
        "خلاصه قبلی بدون هیچ تغییر"
    )


def fake_regenerator_error(
    text,
    instruction,
    target_length
):
    raise RuntimeError(
        "provider failed"
    )


# =========================================================
# CLASSIFICATION PARSER
# =========================================================


def test_parse_normal_news():

    result = (
        parse_editorial_classification(
            "NORMAL_NEWS"
        )
    )

    assert (
        result
        == CONTENT_TYPE_NORMAL_NEWS
    )


def test_parse_news_analysis():

    result = (
        parse_editorial_classification(
            "NEWS_ANALYSIS"
        )
    )

    assert (
        result
        == CONTENT_TYPE_NEWS_ANALYSIS
    )


def test_parse_opinion_note():

    result = (
        parse_editorial_classification(
            "OPINION_NOTE"
        )
    )

    assert (
        result
        == CONTENT_TYPE_OPINION_NOTE
    )


def test_parse_sensitive_content():

    result = (
        parse_editorial_classification(
            "SENSITIVE_CONTENT"
        )
    )

    assert (
        result
        == CONTENT_TYPE_SENSITIVE
    )


def test_parse_uncertain():

    result = (
        parse_editorial_classification(
            "UNCERTAIN"
        )
    )

    assert (
        result
        == CONTENT_TYPE_UNCERTAIN
    )


def test_parse_unknown_value_is_uncertain():

    result = (
        parse_editorial_classification(
            "UNKNOWN_VALUE"
        )
    )

    assert (
        result
        == CONTENT_TYPE_UNCERTAIN
    )


# =========================================================
# NORMAL NEWS
# =========================================================


def test_normal_news_does_not_require_approval():

    original_text = (
        "این یک خبر عادی درباره تحولات "
        "سیاسی و منطقه‌ای است."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_normal
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NORMAL_NEWS
    )

    assert (
        result.needs_approval
        is False
    )

    assert (
        result.original_text
        == original_text
    )


# =========================================================
# SENSITIVE CONTENT
# =========================================================


def test_sensitive_content_is_not_auto_summarized():

    original_text = (
        "این متن شامل مفاد رسمی توافق، "
        "شروط و تعهدات طرفین است."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_sensitive
    )

    assert (
        result.content_type
        == CONTENT_TYPE_SENSITIVE
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.original_text
        == original_text
    )


# =========================================================
# UNCERTAIN CONTENT
# =========================================================


def test_uncertain_content_requires_approval():

    original_text = (
        "ماهیت این متن به صورت قطعی "
        "قابل تشخیص نیست."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_uncertain
    )

    assert (
        result.content_type
        == CONTENT_TYPE_UNCERTAIN
    )

    assert (
        result.needs_approval
        is True
    )


# =========================================================
# OPINION NOTE
# =========================================================


def test_opinion_note_requires_approval():

    original_text = (
        "این یادداشت به بررسی روندهای "
        "سیاست خارجی و تغییر رفتار "
        "بازیگران بین‌المللی می‌پردازد."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_opinion
    )

    assert (
        result.content_type
        == CONTENT_TYPE_OPINION_NOTE
    )

    assert (
        result.needs_approval
        is True
    )


# =========================================================
# NEWS ANALYSIS
# =========================================================


def test_news_analysis_requires_approval():

    original_text = (
        "این تحلیل پیامدهای سیاسی و "
        "امنیتی یک تحول منطقه‌ای را "
        "بررسی می‌کند."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_analysis
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    )

    assert (
        result.needs_approval
        is True
    )


# =========================================================
# SHORT OPINION
# =========================================================


def test_short_opinion_still_requires_approval():

    original_text = (
        "این یک یادداشت کوتاه تحلیلی است."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_opinion
    )

    assert (
        result.content_type
        == CONTENT_TYPE_OPINION_NOTE
    )

    assert (
        result.needs_approval
        is True
    )


# =========================================================
# EMPTY TEXT
# =========================================================


def test_empty_text_is_safe():

    result = review_editorial_content(
        original_text="",
        classifier=fake_classifier_normal
    )

    assert (
        result.original_text
        == ""
    )

    assert (
        result.needs_approval
        is False
    )


# =========================================================
# ORIGINAL TEXT PRESERVATION
# =========================================================


def test_original_text_is_preserved():

    original_text = (
        "متن اصلی باید بدون تغییر "
        "در سیستم نگهداری شود."
    )

    result = review_editorial_content(
        original_text=original_text,
        classifier=fake_classifier_opinion
    )

    assert (
        result.original_text
        == original_text
    )


# =========================================================
# REGENERATION
# =========================================================


def test_opinion_note_regeneration_success():

    original_text = (
        "کشورها دیگر دوست ندارند و سیاست خارجی "
        "در جهان جدید بیش از گذشته بر منفعت موضوعی "
        "و روابط چندلایه استوار شده است. "
    ) * 30

    previous_summary = (
        "خلاصه قبلی درباره تغییر ماهیت "
        "روابط کشورها بود."
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_success
    )

    assert (
        result.content_type
        == CONTENT_TYPE_OPINION_NOTE
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.summary_success
        is True
    )

    assert (
        result.reason
        == "editorial_regeneration_ready"
    )

    assert (
        result.suggested_text
        != previous_summary
    )

    assert (
        result.metadata[
            "regeneration_count"
        ]
        == 1
    )

    assert (
        result.metadata[
            "can_regenerate"
        ]
        is True
    )


def test_news_analysis_regeneration_success():

    original_text = (
        "تحولات منطقه‌ای نشان می‌دهد رقابت میان "
        "بازیگران اصلی وارد مرحله تازه‌ای شده و "
        "پیامدهای سیاسی و امنیتی آن قابل توجه است. "
    ) * 25

    previous_summary = (
        "خلاصه قبلی تحلیل تحولات منطقه‌ای."
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_NEWS_ANALYSIS,
        target_length=950,
        regeneration_count=1,
        summarizer=fake_regenerator_success
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.summary_success
        is True
    )

    assert (
        result.reason
        == "editorial_regeneration_ready"
    )

    assert (
        result.metadata[
            "regeneration_count"
        ]
        == 2
    )


# =========================================================
# REGENERATION LIMIT
# =========================================================


def test_regeneration_limit_reached():

    original_text = (
        "این یک متن تحلیلی بلند برای آزمون "
        "سقف بازتولید خلاصه است. "
    ) * 30

    previous_summary = (
        "خلاصه موجود"
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        target_length=950,
        regeneration_count=(
            MAX_REGENERATION_COUNT
        ),
        summarizer=fake_regenerator_success
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == "regeneration_limit_reached"
    )

    assert (
        result.suggested_text
        == previous_summary
    )

    assert (
        result.metadata[
            "can_regenerate"
        ]
        is False
    )


# =========================================================
# SAME SUMMARY PROTECTION
# =========================================================


def test_regeneration_same_as_previous_is_rejected():

    original_text = (
        "این متن برای بررسی جلوگیری از بازگشت "
        "همان خلاصه قبلی استفاده می‌شود. "
    ) * 30

    previous_summary = (
        "خلاصه قبلی بدون هیچ تغییر"
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_same
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == "regeneration_same_as_previous"
    )

    assert (
        result.suggested_text
        == previous_summary
    )

    assert (
        result.metadata[
            "regeneration_count"
        ]
        == 1
    )


# =========================================================
# PROVIDER FAILURE
# =========================================================


def test_regeneration_provider_failure_keeps_previous_summary():

    original_text = (
        "این متن برای آزمون خطای سرویس "
        "خلاصه‌سازی ساخته شده است. "
    ) * 30

    previous_summary = (
        "خلاصه قبلی باید حفظ شود."
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_error
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == "regeneration_failed"
    )

    assert (
        result.suggested_text
        == previous_summary
    )

    assert (
        result.metadata[
            "regeneration_count"
        ]
        == 1
    )


# =========================================================
# BLOCK SENSITIVE CONTENT
# =========================================================


def test_sensitive_content_cannot_regenerate():

    original_text = (
        "این متن شامل مفاد رسمی و شروط "
        "یک توافق حساس است."
    )

    previous_summary = (
        "خلاصه قبلی"
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_SENSITIVE,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_success
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == (
            "regeneration_not_allowed_for_content_type"
        )
    )

    assert (
        result.suggested_text
        == previous_summary
    )


# =========================================================
# BLOCK NORMAL NEWS
# =========================================================


def test_normal_news_cannot_regenerate():

    original_text = (
        "این یک خبر عادی است."
    )

    previous_summary = (
        "خلاصه قبلی"
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_NORMAL_NEWS,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_success
    )

    assert (
        result.summary_success
        is False
    )

    assert (
        result.reason
        == (
            "regeneration_not_allowed_for_content_type"
        )
    )

    assert (
        result.suggested_text
        == previous_summary
    )


# =========================================================
# CAN REGENERATE
# =========================================================


def test_can_regenerate_before_limit():

    assert (
        can_regenerate_editorial_summary(
            0
        )
        is True
    )

    assert (
        can_regenerate_editorial_summary(
            1
        )
        is True
    )

    assert (
        can_regenerate_editorial_summary(
            2
        )
        is True
    )


def test_cannot_regenerate_at_limit():

    assert (
        can_regenerate_editorial_summary(
            MAX_REGENERATION_COUNT
        )
        is False
    )


# =========================================================
# ORIGINAL TEXT DURING REGENERATION
# =========================================================


def test_regeneration_preserves_original_text():

    original_text = (
        "متن اصلی باید در تمام مراحل بازتولید "
        "بدون تغییر نگهداری شود. "
    ) * 30

    previous_summary = (
        "نسخه قبلی"
    )

    result = regenerate_editorial_summary(
        original_text=original_text,
        previous_summary=previous_summary,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        target_length=950,
        regeneration_count=0,
        summarizer=fake_regenerator_success
    )

    assert (
        result.original_text
        == original_text.strip()
    )
