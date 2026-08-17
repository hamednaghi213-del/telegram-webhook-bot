import pytest
from unittest.mock import patch

import core.webhook_handler as webhook_handler


# =========================================================
# EDITORIAL TAG DETECTION
# =========================================================

def test_detect_opinion_tag_without_space():

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            "#یادداشت\n"
            "عنوان یادداشت\n\n"
            "متن اصلی یادداشت"
        )
    )

    assert (
        content_type
        == "opinion_note"
    )

    assert (
        text
        == (
            "عنوان یادداشت\n\n"
            "متن اصلی یادداشت"
        )
    )

    assert removed > 0

    assert "#یادداشت" not in text


def test_detect_opinion_tag_with_space():

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            "# یادداشت\n"
            "عنوان یادداشت\n\n"
            "متن اصلی یادداشت"
        )
    )

    assert (
        content_type
        == "opinion_note"
    )

    assert (
        text
        == (
            "عنوان یادداشت\n\n"
            "متن اصلی یادداشت"
        )
    )

    assert removed > 0

    assert "# یادداشت" not in text


def test_detect_analysis_tag_without_space():

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            "#تحلیل\n"
            "عنوان تحلیل\n\n"
            "متن اصلی تحلیل"
        )
    )

    assert (
        content_type
        == "news_analysis"
    )

    assert (
        text
        == (
            "عنوان تحلیل\n\n"
            "متن اصلی تحلیل"
        )
    )

    assert removed > 0

    assert "#تحلیل" not in text


def test_detect_analysis_tag_with_space():

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            "# تحلیل\n"
            "عنوان تحلیل\n\n"
            "متن اصلی تحلیل"
        )
    )

    assert (
        content_type
        == "news_analysis"
    )

    assert (
        text
        == (
            "عنوان تحلیل\n\n"
            "متن اصلی تحلیل"
        )
    )

    assert removed > 0

    assert "# تحلیل" not in text


# =========================================================
# DEFAULT = NEWS
# =========================================================

def test_no_editorial_tag_is_normal_news():

    original = (
        "حامد نقی لو\n\n"
        "این یک پیام خبری عادی است و "
        "نباید به دلیل وجود نام در ابتدای "
        "پیام به عنوان یادداشت تشخیص داده شود."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_analytical_language_without_tag_is_still_normal_news():

    original = (
        "تحولات اخیر می‌تواند بر روند مذاکرات "
        "اثر بگذارد و پیامدهای سیاسی مهمی "
        "برای بازیگران منطقه داشته باشد."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_author_name_does_not_trigger_editorial_mode():

    original = (
        "علی رضایی\n\n"
        "تهران و واشینگتن در روزهای آینده "
        "مذاکرات خود را ادامه خواهند داد."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_word_yaddasht_inside_body_does_not_trigger():

    original = (
        "این یک خبر عادی است.\n\n"
        "یک رسانه در یادداشتی نوشته است که "
        "تحولات اخیر اهمیت زیادی دارد."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_word_analysis_inside_body_does_not_trigger():

    original = (
        "خبر جدید منتشر شد.\n\n"
        "در ادامه این گزارش یک تحلیل کوتاه "
        "نیز درباره پیامدهای اتفاق آمده است."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


# =========================================================
# TAG MUST BE FIRST NON-EMPTY LINE
# =========================================================

def test_tag_after_normal_text_is_not_editorial():

    original = (
        "این یک خبر عادی است.\n\n"
        "#یادداشت\n"
        "ادامه متن"
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_empty_lines_before_tag_are_allowed():

    original = (
        "\n\n"
        "#یادداشت\n"
        "عنوان\n\n"
        "متن"
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert (
        content_type
        == "opinion_note"
    )

    assert text == "عنوان\n\nمتن"

    assert removed > 0


# =========================================================
# UNKNOWN HASHTAGS
# =========================================================

def test_normal_hashtag_is_not_editorial():

    original = (
        "#فوری\n"
        "خبر جدید منتشر شد."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


def test_donya24_hashtag_is_not_editorial():

    original = (
        "#دنیا_۲۴_نیوز\n"
        "خبر جدید منتشر شد."
    )

    content_type, text, removed = (
        webhook_handler.detect_editorial_admin_tag(
            original
        )
    )

    assert content_type is None

    assert text == original

    assert removed == 0


# =========================================================
# ENTITY OFFSET SHIFT
# =========================================================

def test_entities_shift_after_editorial_tag():

    entities = [
        {
            "type": "bold",
            "offset": 10,
            "length": 5
        }
    ]

    result = (
        webhook_handler.shift_entities_after_prefix_removal(
            entities,
            8
        )
    )

    assert len(result) == 1

    assert (
        result[0]["offset"]
        == 2
    )

    assert (
        result[0]["length"]
        == 5
    )


def test_entity_inside_removed_tag_is_removed():

    entities = [
        {
            "type": "bold",
            "offset": 0,
            "length": 5
        }
    ]

    result = (
        webhook_handler.shift_entities_after_prefix_removal(
            entities,
            8
        )
    )

    assert result == []


def test_entity_overlapping_removed_prefix_is_removed():

    entities = [
        {
            "type": "bold",
            "offset": 5,
            "length": 10
        }
    ]

    result = (
        webhook_handler.shift_entities_after_prefix_removal(
            entities,
            8
        )
    )

    assert result == []


def test_entities_unchanged_when_no_prefix_removed():

    entities = [
        {
            "type": "bold",
            "offset": 2,
            "length": 10
        }
    ]

    result = (
        webhook_handler.shift_entities_after_prefix_removal(
            entities,
            0
        )
    )

    assert result == entities


# =========================================================
# EXPLICIT EDITORIAL CLASSIFICATION
# =========================================================

def test_explicit_opinion_forces_opinion_classifier():

    def fake_analyzer(
        original_text,
        target_length=950,
        classifier=None,
        summarizer=None
    ):

        assert classifier is not None

        result = classifier(
            original_text,
            "",
            64
        )

        assert (
            result
            == "OPINION_NOTE"
        )

        class FakeResult:

            content_type = (
                "opinion_note"
            )

            needs_approval = True

            suggested_text = (
                "نسخه پیشنهادی"
            )

            summary_success = True

            reason = (
                "editorial_summary_ready"
            )

            metadata = {
                "regeneration_count": 0
            }

        return FakeResult()

    class FakeStructure:

        title = "عنوان"
        author = "نویسنده"
        body = "متن یادداشت"

        author_source = "header"
        author_confidence = "high"

    class FakePending:

        review_id = "test-review"

        content_type = (
            "opinion_note"
        )

        current_summary = (
            "نسخه پیشنهادی"
        )

        regeneration_count = 0

    with patch(
        "core.editorial_review.analyze_editorial_content",
        side_effect=fake_analyzer
    ), patch(
        "core.editorial_structure.extract_editorial_structure",
        return_value=FakeStructure()
    ), patch(
        "core.editorial_pending.create_pending_review",
        return_value=FakePending()
    ), patch.object(
        webhook_handler,
        "prepare_text_content",
        return_value={
            "main_text": "متن یادداشت",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }
    ), patch.object(
        webhook_handler,
        "build_editorial_source_text",
        return_value="متن یادداشت"
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True
    ):

        result = (
            webhook_handler
            .try_queue_editorial_text_review(
                chat_id=1001,
                text="متن یادداشت
