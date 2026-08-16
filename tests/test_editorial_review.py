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
    MAX_REGENERATION_COUNT,
    analyze_editorial_content,
    can_regenerate_editorial_summary,
    parse_editorial_classification,
    regenerate_editorial_summary,
)


# =========================================================
# TEST HELPERS
# =========================================================


def trim_at_word_boundary(
    text,
    target_length
):
    if len(text) <= target_length:
        return text.strip()

    candidate = text[:target_length]

    position = candidate.rfind(" ")

    if position > 0:
        candidate = candidate[:position]

    return candidate.strip()


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
    return trim_at_word_boundary(
        text,
        target_length
    )


def fake_regenerator_success(
    text,
    instruction,
    target_length
):
    # خروجی از خود متن اصلی ساخته می‌شود.
    # در نتیجه Validator با اطلاعات ساختگی مواجه نمی‌شود
    # و نسبت کاهش نیز واقعی باقی می‌ماند.

    return trim_at_word_boundary(
        text,
        target_length
    )


def fake_regenerator_same(
    text,
    instruction,
    target_length
):
    # خروجی دقیقاً براساس Target واقعی تولید می‌شود.
    # تست SAME SUMMARY نیز باید previous_summary را
    # با همین Target بسازد.

    return trim_at_word_boundary(
        text,
        target_length
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
            "SOMETHING_UNKNOWN"
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
# ADAPTIVE TARGET
#
# متن تحلیل 3918 کاراکتری با سیاست کاهش 75 درصد
# حداقل به حدود 980 کاراکتر نیاز دارد.
#
# بنابراین Target در صورت لزوم باید از 950
# بالاتر برود تا Validator وارد وضعیت غیرممکن نشود.
# =========================================================


def test_news_analysis_adaptive_target_avoids_impossible_reduction():

    text = (
        "تحولات سیاسی نشان می‌دهد ایران در شرایطی "
        "مسیر مذاکرات را حفظ می‌کند که سطح اعتماد "
        "میان طرفین کاهش یافته است. با این حال، "
        "ادامه گفت‌وگو در ارزیابی تهران می‌تواند "
        "ابزاری برای مدیریت هزینه‌های سیاسی، کنترل "
        "صحنه و جلوگیری از ورود به بحران گسترده‌تر "
        "باشد. همچنین به نظر می‌رسد طولانی شدن "
        "فرایند مذاکرات می‌تواند بر محاسبات داخلی "
        "و خارجی بازیگران اثر بگذارد. "
    ) * 14

    observed_targets = []

    def adaptive_summarizer(
        original_text,
        instruction,
        target_length
    ):

        observed_targets.append(
            target_length
        )

        return trim_at_word_boundary(
            original_text,
            target_length
        )

    result = analyze_editorial_content(
        original_text=text,
        target_length=950,
        classifier=fake_classifier_analysis,
        summarizer=adaptive_summarizer
    )

    assert (
        result.content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    )

    assert (
        result.needs_approval
        is True
    )

    assert observed_targets

    # Classification از classifier جداگانه انجام شده،
    # بنابراین این لیست فقط Target خلاصه‌سازی را دارد.
    assert (
        observed_targets[-1]
        >= 950
    )


# =========================================================
# SHORT OPINION NOTE
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


# =========================================================
# OPINION NOTE REGENERATION
# =========================================================


def test_opinion_note_regeneration_success():

    original_text = (
        "کشورها دیگر دوست ندارند و سیاست خارجی "
        "در جهان جدید بیش از گذشته بر منفعت موضوعی "
        "و روابط چندلایه استوار شده است. "
    ) * 12

    previous_summary = (
        "خلاصه قبلی درباره تغییر ماهیت روابط کشورها بود."
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
        len(
            result.suggested_text
        )
        <= 950
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


# =========================================================
# NEWS ANALYSIS REGENERATION
# =========================================================


def test_news_analysis_regeneration_success():

    original_text = (
        "تحولات منطقه‌ای نشان می‌دهد رقابت میان "
        "بازیگران اصلی وارد مرحله تازه‌ای شده و "
        "پیامدهای سیاسی و امنیتی آن قابل توجه است. "
    ) * 9

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
#
# نکته مهم:
#
# در نسخه فعلی Adaptive Target،
# Regeneration برای این متن Effective Target = 950 دارد.
#
# بنابراین previous_summary هم باید دقیقاً با 950
# ساخته شود تا Fake Regenerator همان خروجی را برگرداند
# و SAME SUMMARY واقعاً تست شود.
# =========================================================


def test_regeneration_same_as_previous_is_rejected():

    original_text = (
        "جهان امروز شبکه‌ای از روابط موضوعی است و "
        "کشورها در هر حوزه بر اساس منافع متفاوت "
        "تصمیم می‌گیرند. "
    ) * 12

    previous_summary = (
        trim_at_word_boundary(
            original_text,
            950
        )
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
        == "regeneration_not_allowed_for_content_type"
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
        == "regeneration_not_allowed_for_content_type"
    )


# =========================================================
# CAN REGENERATE HELPER
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
# ORIGINAL TEXT PRESERVED DURING REGENERATION
# =========================================================


def test_regeneration_preserves_original_text():

    original_text = (
        "متن اصلی باید در تمام مراحل بازتولید "
        "بدون تغییر نگهداری شود. "
    ) * 12

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
