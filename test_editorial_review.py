from core.editorial_review import (
    ACTION_NEEDS_APPROVAL,
    ACTION_PUBLISH_DIRECT,
    ACTION_PUBLISH_ORIGINAL,
    ACTION_UNCERTAIN,
    CONTENT_TYPE_NEWS_ANALYSIS,
    CONTENT_TYPE_NORMAL_NEWS,
    CONTENT_TYPE_OPINION_NOTE,
    CONTENT_TYPE_SENSITIVE,
    CONTENT_TYPE_UNCERTAIN,
    analyze_editorial_content,
    parse_editorial_classification,
)


# =========================================================
# FAKE AI PROVIDERS
#
# این تست‌ها عمداً Gemini واقعی را صدا نمی‌زنند.
# هدف فقط تست منطق editorial_review است.
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


def fake_summarizer(
    text,
    instruction,
    target_length
):
    # برای تست Validator باید خروجی:
    #
    # 1. از target_length بیشتر نباشد
    # 2. بیش از حد مجاز کوتاه نشود
    # 3. اطلاعات جدید تولید نکند
    #
    # بنابراین بخشی از خود متن اصلی را
    # در مرز کلمه برمی‌گردانیم.

    if len(text) <= target_length:
        return text

    candidate = text[:target_length]

    position = candidate.rfind(" ")

    if position > 0:
        candidate = candidate[:position]

    return candidate.strip()


# =========================================================
# PARSER TESTS
# =========================================================


def test_parse_normal_news():

    result = parse_editorial_classification(
        "NORMAL_NEWS"
    )

    assert (
        result
        == CONTENT_TYPE_NORMAL_NEWS
    )


def test_parse_news_analysis():

    result = parse_editorial_classification(
        "NEWS_ANALYSIS"
    )

    assert (
        result
        == CONTENT_TYPE_NEWS_ANALYSIS
    )


def test_parse_opinion_note():

    result = parse_editorial_classification(
        "OPINION_NOTE"
    )

    assert (
        result
        == CONTENT_TYPE_OPINION_NOTE
    )


def test_parse_sensitive_content():

    result = parse_editorial_classification(
        "SENSITIVE_CONTENT"
    )

    assert (
        result
        == CONTENT_TYPE_SENSITIVE
    )


def test_parse_uncertain():

    result = parse_editorial_classification(
        "UNCERTAIN"
    )

    assert (
        result
        == CONTENT_TYPE_UNCERTAIN
    )


def test_parse_unknown_value_is_uncertain():

    result = parse_editorial_classification(
        "SOMETHING_UNKNOWN"
    )

    assert (
        result
        == CONTENT_TYPE_UNCERTAIN
    )


# =========================================================
# NORMAL NEWS
# =========================================================


def test_normal_news_does_not_require_approval():

    text = (
        "وزارت خارجه اعلام کرد مذاکرات "
        "امروز در پایتخت برگزار شد."
    )

    result = analyze_editorial_content(
        original_text=text,
        classifier=fake_classifier_normal,
        summarizer=fake_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NORMAL_NEWS
    )

    assert (
        result.action
        == ACTION_PUBLISH_DIRECT
    )

    assert (
        result.needs_approval
        is False
    )

    assert (
        result.original_text
        == text
    )

    assert (
        result.suggested_text
        == text
    )

    assert (
        result.summary_success
        is True
    )


# =========================================================
# SENSITIVE CONTENT
# =========================================================


def test_sensitive_content_is_not_auto_summarized():

    text = (
        "در بند نخست توافق اعلام شده است "
        "که اجرای تعهدات از تاریخ مشخص "
        "و مطابق شروط رسمی آغاز خواهد شد."
    )

    result = analyze_editorial_content(
        original_text=text,
        classifier=fake_classifier_sensitive,
        summarizer=fake_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_SENSITIVE
    )

    assert (
        result.action
        == ACTION_PUBLISH_ORIGINAL
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.suggested_text
        == text
    )

    assert (
        result.summary_success
        is False
    )


# =========================================================
# UNCERTAIN CONTENT
# =========================================================


def test_uncertain_content_requires_approval():

    text = (
        "این متن ساختار مشخصی ندارد "
        "و نوع رسانه‌ای آن با اطمینان "
        "قابل تشخیص نیست."
    )

    result = analyze_editorial_content(
        original_text=text,
        classifier=fake_classifier_uncertain,
        summarizer=fake_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_UNCERTAIN
    )

    assert (
        result.action
        == ACTION_UNCERTAIN
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.suggested_text
        == text
    )


# =========================================================
# OPINION NOTE
# =========================================================


def test_opinion_note_requires_approval():

    text = (
        "کشورها دیگر دوست ندارند. "
        "جهان امروز بر پایه منفعت موضوعی "
        "و روابط چندلایه حرکت می‌کند. "
    ) * 40

    result = analyze_editorial_content(
        original_text=text,
        target_length=950,
        classifier=fake_classifier_opinion,
        summarizer=fake_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_OPINION_NOTE
    )

    assert (
        result.action
        == ACTION_NEEDS_APPROVAL
    )

    assert (
        result.needs_approval
        is True
    )

    assert (
        result.original_text
        == text.strip()
    )


# =========================================================
# NEWS ANALYSIS
# =========================================================


def test_news_analysis_requires_approval():

    text = (
        "تحولات اخیر نشان می‌دهد رقابت "
        "بازیگران منطقه‌ای وارد مرحله تازه‌ای "
        "شده است و پیامدهای آن می‌تواند بر "
        "معادلات سیاسی اثر بگذارد. "
    ) * 30

    result = analyze_editorial_content(
        original_text=text,
        target_length=950,
        classifier=fake_classifier_analysis,
        summarizer=fake_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    )

    assert (
        result.action
        == ACTION_NEEDS_APPROVAL
    )

    assert (
        result.needs_approval
        is True
    )


# =========================================================
# SHORT OPINION NOTE
#
# حتی اگر متن از target کوتاه‌تر باشد،
# چون یادداشت است باید approval داشته باشد.
# =========================================================


def test_short_opinion_still_requires_approval():

    text = (
        "سیاست خارجی در جهان جدید "
        "بیش از گذشته بر منفعت موضوعی "
        "استوار شده است."
    )

    result = analyze_editorial_content(
        original_text=text,
        target_length=950,
        classifier=fake_classifier_opinion,
        summarizer=fake_summarizer
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
        result.action
        == ACTION_NEEDS_APPROVAL
    )

    assert (
        result.suggested_text
        == text
    )


# =========================================================
# EMPTY TEXT
# =========================================================


def test_empty_text_is_safe():

    result = analyze_editorial_content(
        original_text="",
        classifier=fake_classifier_normal,
        summarizer=fake_summarizer
    )

    assert (
        result.needs_approval
        is False
    )

    assert (
        result.action
        == ACTION_PUBLISH_DIRECT
    )

    assert (
        result.original_text
        == ""
    )

    assert (
        result.suggested_text
        == ""
    )


# =========================================================
# ORIGINAL TEXT PRESERVATION
# =========================================================


def test_original_text_is_preserved():

    text = (
        "پایان کشور دوست\n\n"
        "کشورها دیگر دوست ندارند. "
        "این گزاره توصیف جهان امروز است. "
    ) * 20

    result = analyze_editorial_content(
        original_text=text,
        target_length=950,
        classifier=fake_classifier_opinion,
        summarizer=fake_summarizer
    )

    assert (
        result.original_text
        == text.strip()
    )

    assert (
        result.needs_approval
        is True
    )
