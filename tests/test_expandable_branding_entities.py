import unicodedata

from core.caption_manager import analyze_content, append_branding
from core.telegram_caption_entities import utf16_length, validate_caption_entities


def _utf16_entity_text(text, entity):
    encoded = text.encode("utf-16-le")
    start = entity["offset"] * 2
    end = start + entity["length"] * 2
    return encoded[start:end].decode("utf-16-le")


def _paragraph_directions(text):
    strong = {"L", "R", "AL"}
    return [
        next((unicodedata.bidirectional(char) for char in line
              if unicodedata.bidirectional(char) in strong), None)
        for line in text.splitlines()
    ]


def _persian_expandable_plan():
    return analyze_content(
        main_text="❇️ تیتر فارسی\n\n🔹 متن اصلی فارسی",
        expandable_blocks=[
            {"text": "تحلیل تکمیلی فارسی درباره خبر", "offset": 100}
        ],
        branding="#دنیا_۲۴_نیوز\n@Donya24News",
    )


def test_persian_expandable_media_branding_uses_safe_bidi_boundary():
    plan = _persian_expandable_plan()
    caption = plan.telegram["media_caption"]
    entities = plan.telegram["media_caption_entities"]
    expandable = "تحلیل تکمیلی فارسی درباره خبر"
    branding = "#دنیا_۲۴_نیوز\n@Donya24News"

    assert validate_caption_entities(caption, entities)
    assert [entity["type"] for entity in entities] == ["expandable_blockquote"]
    assert _utf16_entity_text(caption, entities[0]) == expandable
    assert caption.endswith(f"{expandable}\n\n{branding}")
    assert caption.count("#دنیا_۲۴_نیوز") == 1
    assert caption.count("@Donya24News") == 1
    assert utf16_length(caption) == utf16_length(
        "❇️ تیتر فارسی\n\n🔹 متن اصلی فارسی\n\n"
        f"{expandable}\n\n{branding}"
    )


def test_expandable_branding_matches_normal_visible_paragraph_boundary():
    plan = _persian_expandable_plan()
    caption = plan.telegram["media_caption"]
    main_text = "❇️ تیتر فارسی\n\n🔹 متن اصلی فارسی"
    expandable = "تحلیل تکمیلی فارسی درباره خبر"
    branding = "#دنیا_۲۴_نیوز\n@Donya24News"
    normal_text = append_branding(main_text, branding)

    assert caption.rsplit(expandable, 1)[1] == normal_text.rsplit(main_text, 1)[1]
    assert _paragraph_directions(caption[-len(branding):]) == ["AL", "L"]
    assert "\n\n\n" not in caption[caption.index(expandable) + len(expandable):]


def test_expandable_entity_stops_before_branding_separator():
    plan = _persian_expandable_plan()
    caption = plan.telegram["media_caption"]
    entity = plan.telegram["media_caption_entities"][0]
    end = entity["offset"] + entity["length"]
    encoded = caption.encode("utf-16-le")

    assert encoded[end * 2:].decode("utf-16-le").startswith(
        "\n\n#دنیا_۲۴_نیوز\n@Donya24News"
    )


def test_ltr_expandable_branding_retains_explicit_clickable_entities():
    hashtag = "#World_News"
    mention = "@Donya24News"
    plan = analyze_content(
        main_text="❇️ خبر",
        expandable_blocks=[{"text": "توضیح", "offset": 10}],
        branding=f"{hashtag}\n{mention}",
    )
    caption = plan.telegram["media_caption"]
    entities = plan.telegram["media_caption_entities"]

    assert [entity["type"] for entity in entities] == [
        "expandable_blockquote", "hashtag", "mention"
    ]
    assert _utf16_entity_text(caption, entities[1]) == hashtag
    assert _utf16_entity_text(caption, entities[2]) == mention
