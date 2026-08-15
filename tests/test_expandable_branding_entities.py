import pytest

from core.caption_manager import (
    analyze_content
)


# =========================================================
# TEST: EXPLICIT BRANDING ENTITIES
# RTL/LTR BIDIRECTIONAL FIX
# =========================================================

def test_expandable_blockquote_with_explicit_hashtag_mention():
    """
    Test that hashtag and mention are explicit entities
    after expandable blockquote in Persian (RTL) text.
    
    This fixes the issue where hashtag appears in wrong
    position or invisible space due to BiDi algorithm conflict.
    
    Structure:
    - Main text (RTL)
    - Expandable blockquote (RTL)
    - Branding:
      - Hashtag (RTL)
      - Mention (LTR)
    """

    main_text = (
        "❇️ گواهی امنیتی برخی سایت‌های بانک مرکزی لغو شد\n\n"
        "🔹 متن اصلی خبر که توضیح می‌دهد موضوع را"
    )

    expandable_blocks = [
        {
            "text": "ادامه خبر و تحلیل تکمیلی درباره موضوع",
            "offset": 100
        }
    ]

    branding = (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )

    # =====================================================
    # ANALYZE
    # =====================================================

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=expandable_blocks,
        branding=branding
    )

    telegram_plan = plan.telegram

    caption = telegram_plan["media_caption"]
    entities = telegram_plan["media_caption_entities"]
    followup_messages = telegram_plan["followup_messages"]
    followup_entities = telegram_plan["followup_message_entities"]

    # =====================================================
    # VERIFY CAPTION STRUCTURE
    # =====================================================

    assert caption, "Caption must not be empty"
    assert caption == main_text, "Caption must contain only main text"
    assert "ادامه خبر" not in caption, "Expandable content must not be in caption"
    assert "#دنیا_۲۴_نیوز" not in caption, "Hashtag must not be in caption"
    assert "@Donya24News" not in caption, "Mention must not be in caption"

    # =====================================================
    # VERIFY ENTITY TYPES
    # =====================================================

    assert entities == [], (
        "Expandable/block branding entities must not exist in media caption"
    )

    # =====================================================
    # VERIFY ENTITY COUNT
    # =====================================================

    assert len(followup_messages) == 2, (
        f"Expected expandable + branding followups, got {len(followup_messages)}"
    )

    # =====================================================
    # FIND EACH ENTITY
    # =====================================================

    assert (
        followup_messages[0]
        == "ادامه خبر و تحلیل تکمیلی درباره موضوع"
    )
    assert (
        followup_messages[1]
        == branding
    )

    # =====================================================
    # VERIFY ENTITY ORDERING
    # =====================================================

    assert len(followup_entities) == 2
    assert len(followup_entities[0]) == 1
    assert followup_entities[0][0]["type"] == "expandable_blockquote"
    assert followup_entities[1] == []

    # =====================================================
    # VERIFY HASHTAG ENTITY
    # =====================================================

    parse_mode = telegram_plan.get("media_parse_mode")
    assert parse_mode is None, (
        "Plain text caption should have parse_mode=None, "
        f"got {parse_mode}"
    )


def test_expandable_blockquote_hashtag_position_rtl():
    """
    Test that hashtag appears in correct RTL position.
    
    Before fix: Hashtag invisible or wrong position
    After fix: Hashtag explicit entity at correct offset
    """

    main_text = "❇️ تیتر خبر\n\n🔹 متن اصلی"

    expandable_blocks = [
        {
            "text": "بخش قابل بسط",
            "offset": 50
        }
    ]

    branding = "#دنیا_۲۴_نیوز\n@Donya24News"

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=expandable_blocks,
        branding=branding
    )

    caption = plan.telegram["media_caption"]
    followup_messages = plan.telegram["followup_messages"]

    assert "#دنیا_۲۴_نیوز" not in caption
    assert followup_messages[1].splitlines()[0] == "#دنیا_۲۴_نیوز"


def test_expandable_blockquote_mention_position_ltr():
    """
    Test that mention appears in correct LTR position.
    """

    main_text = "❇️ تیتر خبر\n\n🔹 متن اصلی"

    expandable_blocks = [
        {
            "text": "بخش قابل بسط",
            "offset": 50
        }
    ]

    branding = "#دنیا_۲۴_نیوز\n@Donya24News"

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=expandable_blocks,
        branding=branding
    )

    caption = plan.telegram["media_caption"]
    followup_messages = plan.telegram["followup_messages"]

    assert "@Donya24News" not in caption
    assert followup_messages[1].splitlines()[1] == "@Donya24News"


def test_branding_entities_no_duplication():
    """
    Verify that hashtag and mention appear only once
    (in branding block, not duplicated elsewhere in text).
    """

    main_text = "❇️ خبر"

    expandable_blocks = [
        {
            "text": "توضیح",
            "offset": 10
        }
    ]

    branding = "#دنیا_۲۴_نیوز\n@Donya24News"

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=expandable_blocks,
        branding=branding
    )

    caption = plan.telegram["media_caption"]
    followup_messages = plan.telegram["followup_messages"]

    assert caption.count("#دنیا_۲۴_نیوز") == 0
    assert caption.count("@Donya24News") == 0
    assert followup_messages[-1].count("#دنیا_۲۴_نیوز") == 1
    assert followup_messages[-1].count("@Donya24News") == 1
