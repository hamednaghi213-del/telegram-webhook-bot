import pytest
import unicodedata

from core.caption_manager import (
    analyze_content,
    append_branding,
)
from core.telegram_caption_entities import validate_caption_entities


def _utf16_entity_text(text, entity):
    encoded = text.encode("utf-16-le")
    start = entity["offset"] * 2
    end = start + entity["length"] * 2
    return encoded[start:end].decode("utf-16-le")


def _paragraph_directions(text):
    strong = {"L", "R", "AL"}
    return [
        next((unicodedata.bidirectional(char) for char in line if unicodedata.bidirectional(char) in strong), None)
        for line in text.splitlines()
    ]


def test_persian_expandable_media_branding_matches_normal_bidi_boundary():
    main_text = "تیتر فارسی\n\nمتن اصلی فارسی"
    expandable = "تحلیل تکمیلی فارسی درباره خبر"
    hashtag = "#دنیا_۲۴_نیوز"
    mention = "@Donya24News"
    branding = f"{hashtag}\n{mention}"

    plan = analyze_content(
        main_text=main_text,
        expandable_blocks=[{"text": expandable, "offset": 100}],
        branding=branding,
    )
    caption = plan.telegram["media_caption"]
    entities = plan.telegram["media_caption_entities"]
    hashtag_entity = next(item for item in entities if item["type"] == "hashtag")
    mention_entity = next(item for item in entities if item["type"] == "mention")

    assert validate_caption_entities(caption, entities)
    assert _utf16_entity_text(caption, hashtag_entity) == hashtag
    assert _utf16_entity_text(caption, mention_entity) == mention
    assert caption.endswith(f"{expandable}\n\n{branding}")
    assert "\n\n\n" not in caption[caption.index(expandable) + len(expandable):]

    normal_text = append_branding(main_text, branding)
    assert caption.rsplit(expandable, 1)[1] == normal_text.rsplit(main_text, 1)[1]
    assert _paragraph_directions(caption[-len(branding):]) == _paragraph_directions(
        normal_text[-len(branding):]
    ) == ["AL", "L"]


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

    # =====================================================
    # VERIFY CAPTION STRUCTURE
    # =====================================================

    assert caption, "Caption must not be empty"
    assert main_text in caption, "Main text must be in caption"
    assert "ادامه خبر" in caption, "Expandable content must be in caption"
    assert "#دنیا_۲۴_نیوز" in caption, "Hashtag must be in caption"
    assert "@Donya24News" in caption, "Mention must be in caption"

    # =====================================================
    # VERIFY ENTITY TYPES
    # =====================================================

    entity_types = [
        e["type"] for e in entities
    ]

    assert "expandable_blockquote" in entity_types, (
        "Expandable blockquote entity must exist"
    )
    assert "hashtag" in entity_types, (
        "Hashtag entity must exist (explicit, not auto-detected)"
    )
    assert "mention" in entity_types, (
        "Mention entity must exist (explicit, not auto-detected)"
    )

    # =====================================================
    # VERIFY ENTITY COUNT
    # =====================================================

    assert len(entities) == 3, (
        f"Expected 3 entities (expandable, hashtag, mention), "
        f"got {len(entities)}"
    )

    # =====================================================
    # FIND EACH ENTITY
    # =====================================================

    expandable_entity = next(
        (e for e in entities if e["type"] == "expandable_blockquote"),
        None
    )
    hashtag_entity = next(
        (e for e in entities if e["type"] == "hashtag"),
        None
    )
    mention_entity = next(
        (e for e in entities if e["type"] == "mention"),
        None
    )

    assert expandable_entity, "Expandable entity not found"
    assert hashtag_entity, "Hashtag entity not found"
    assert mention_entity, "Mention entity not found"

    # =====================================================
    # VERIFY ENTITY ORDERING
    # =====================================================

    expandable_offset = expandable_entity["offset"]
    hashtag_offset = hashtag_entity["offset"]
    mention_offset = mention_entity["offset"]

    assert (
        expandable_offset < hashtag_offset < mention_offset
    ), (
        f"Entity offsets must be ordered: "
        f"expandable({expandable_offset}) < "
        f"hashtag({hashtag_offset}) < "
        f"mention({mention_offset})"
    )

    # =====================================================
    # VERIFY HASHTAG ENTITY
    # =====================================================

    hashtag_text = "#دنیا_۲۴_نیوز"
    hashtag_pos_in_caption = caption.rfind(hashtag_text)

    assert hashtag_pos_in_caption >= 0, (
        f"Hashtag '{hashtag_text}' not found in caption"
    )

    assert hashtag_entity["length"] > 0, (
        "Hashtag entity length must be positive"
    )

    # =====================================================
    # VERIFY MENTION ENTITY
    # =====================================================

    mention_text = "@Donya24News"
    mention_pos_in_caption = caption.rfind(mention_text)

    assert mention_pos_in_caption >= 0, (
        f"Mention '{mention_text}' not found in caption"
    )

    assert mention_entity["length"] > 0, (
        "Mention entity length must be positive"
    )

    # =====================================================
    # VERIFY ENTITY BOUNDARIES DON'T OVERLAP
    # =====================================================

    expandable_end = (
        expandable_entity["offset"]
        + expandable_entity["length"]
    )

    hashtag_start = hashtag_entity["offset"]
    hashtag_end = hashtag_start + hashtag_entity["length"]

    mention_start = mention_entity["offset"]

    assert (
        expandable_end <= hashtag_start
    ), (
        "Expandable and hashtag must not overlap"
    )

    assert (
        hashtag_end <= mention_start
    ), (
        "Hashtag and mention must not overlap"
    )

    # =====================================================
    # VERIFY BRANDING AT END OF CAPTION
    # =====================================================

    assert caption.endswith(mention_text), (
        "Caption must end with mention"
    )

    # Find where branding starts
    branding_start_pos = caption.rfind(hashtag_text)
    branding_section = caption[branding_start_pos:]

    assert hashtag_text in branding_section, (
        "Hashtag must be in branding section"
    )
    assert mention_text in branding_section, (
        "Mention must be in branding section"
    )

    # =====================================================
    # VERIFY CAPTION LENGTH
    # =====================================================

    assert len(caption) <= 1024, (
        f"Caption length {len(caption)} exceeds Telegram limit 1024"
    )

    # =====================================================
    # VERIFY PARSE MODE
    # =====================================================

    parse_mode = telegram_plan.get("media_parse_mode")
    assert parse_mode is None, (
        "Plain text caption (entities only) should have parse_mode=None, "
        f"got {parse_mode}"
    )

    print()
    print("=" * 70)
    print("✅ TEST PASSED: Explicit Branding Entities")
    print("=" * 70)
    print()
    print(f"Caption length: {len(caption)}")
    print(f"Entities count: {len(entities)}")
    print()
    print("Entity breakdown:")
    for entity in entities:
        entity_type = entity["type"]
        offset = entity["offset"]
        length = entity["length"]
        print(
            f"  • {entity_type:25} | "
            f"offset={offset:4} | length={length:3}"
        )
    print()
    print(f"Branding position:")
    print(f"  Hashtag starts at: {hashtag_offset}")
    print(f"  Mention starts at: {mention_offset}")
    print()
    print("=" * 70)


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
    entities = plan.telegram["media_caption_entities"]

    # Hashtag must be explicit entity
    hashtag_entity = next(
        (e for e in entities if e["type"] == "hashtag"),
        None
    )

    assert hashtag_entity, "Hashtag entity must exist"

    # Hashtag text must be in caption
    hashtag_text = "#دنیا_۲۴_نیوز"
    assert hashtag_text in caption, (
        "Hashtag must be in caption"
    )

    # Hashtag offset must point to correct position
    hashtag_offset = hashtag_entity["offset"]
    hashtag_length = hashtag_entity["length"]

    # Extract text at entity offset/length
    caption_utf16 = caption.encode("utf-16-le")
    start_byte = hashtag_offset * 2
    end_byte = start_byte + (hashtag_length * 2)

    extracted_text = (
        caption_utf16[start_byte:end_byte]
        .decode("utf-16-le")
    )

    assert extracted_text == hashtag_text, (
        f"Entity offset/length should point to hashtag. "
        f"Expected '{hashtag_text}', got '{extracted_text}'"
    )

    print()
    print("✅ Hashtag positioned correctly (RTL-safe)")
    print(f"   Text: {hashtag_text}")
    print(f"   Offset: {hashtag_offset}")
    print(f"   Length: {hashtag_length}")
    print()


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
    entities = plan.telegram["media_caption_entities"]

    # Mention must be explicit entity
    mention_entity = next(
        (e for e in entities if e["type"] == "mention"),
        None
    )

    assert mention_entity, "Mention entity must exist"

    # Mention text must be in caption
    mention_text = "@Donya24News"
    assert mention_text in caption, (
        "Mention must be in caption"
    )

    # Mention offset must point to correct position
    mention_offset = mention_entity["offset"]
    mention_length = mention_entity["length"]

    # Extract text at entity offset/length
    caption_utf16 = caption.encode("utf-16-le")
    start_byte = mention_offset * 2
    end_byte = start_byte + (mention_length * 2)

    extracted_text = (
        caption_utf16[start_byte:end_byte]
        .decode("utf-16-le")
    )

    assert extracted_text == mention_text, (
        f"Entity offset/length should point to mention. "
        f"Expected '{mention_text}', got '{extracted_text}'"
    )

    print()
    print("✅ Mention positioned correctly (LTR)")
    print(f"   Text: {mention_text}")
    print(f"   Offset: {mention_offset}")
    print(f"   Length: {mention_length}")
    print()


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
    entities = plan.telegram["media_caption_entities"]

    # Count hashtag entities
    hashtag_entities = [
        e for e in entities if e["type"] == "hashtag"
    ]

    assert len(hashtag_entities) == 1, (
        f"Expected 1 hashtag entity, got {len(hashtag_entities)}"
    )

    # Count mention entities
    mention_entities = [
        e for e in entities if e["type"] == "mention"
    ]

    assert len(mention_entities) == 1, (
        f"Expected 1 mention entity, got {len(mention_entities)}"
    )

    print()
    print("✅ No duplication of branding entities")
    print(f"   Hashtag entities: {len(hashtag_entities)}")
    print(f"   Mention entities: {len(mention_entities)}")
    print()
