import pytest

from core.caption_manager import analyze_content
from core.telegram_caption_entities import utf16_length


MAIN = "❇️ متن فارسی خبر"
EXPANDABLE = "نقل‌قول فارسی که باید به‌صورت بازشونده باقی بماند."
RTL_BRANDING = "#رسانه_فارسی\n@SharedNews"
LTR_BRANDING = "#Shared_News\n@SharedNews"


def _entity_types(plan):
    return [entity["type"] for entity in plan.telegram["media_caption_entities"]]


def _parts(plan):
    telegram = plan.telegram
    return 1 + len(telegram["followup_messages"])


@pytest.mark.parametrize("prefix", [MAIN, "😀 " + MAIN])
def test_expandable_rtl_branding_uses_telegram_autodetection_without_text_change(prefix):
    before = analyze_content(
        main_text=prefix,
        expandable_blocks=[{"text": EXPANDABLE, "offset": 100}],
        branding=RTL_BRANDING,
    )
    caption = before.telegram["media_caption"]

    assert caption == f"{prefix}\n\n{EXPANDABLE}\n\n{RTL_BRANDING}"
    assert utf16_length(caption) == utf16_length(
        f"{prefix}\n\n{EXPANDABLE}\n\n{RTL_BRANDING}"
    )
    assert _entity_types(before) == ["expandable_blockquote"]
    assert caption.endswith("#رسانه_فارسی\n@SharedNews")
    assert "\u200e" not in caption and "\u200f" not in caption
    assert "\u2066" not in caption and "\u2067" not in caption and "\u2069" not in caption
    assert _parts(before) == 1


def test_expandable_ltr_branding_keeps_explicit_clickable_entities():
    plan = analyze_content(
        main_text=MAIN,
        expandable_blocks=[{"text": EXPANDABLE, "offset": 100}],
        branding=LTR_BRANDING,
    )

    assert _entity_types(plan) == [
        "expandable_blockquote",
        "hashtag",
        "mention",
    ]


def test_normal_blockquote_is_unchanged():
    plan = analyze_content(
        main_text=MAIN,
        blockquote_blocks=[{"text": EXPANDABLE, "offset": 100}],
        branding=RTL_BRANDING,
    )

    assert _entity_types(plan) == ["blockquote", "hashtag", "mention"]


def test_no_blockquote_path_is_unchanged_and_single_part():
    plan = analyze_content(main_text=MAIN, branding=RTL_BRANDING)

    assert plan.telegram["media_caption"] == f"{MAIN}\n\n{RTL_BRANDING}"
    assert plan.telegram["media_caption_entities"] == []
    assert _parts(plan) == 1


def test_boundary_fix_does_not_change_capacity_or_delivery_part_count():
    plan = analyze_content(
        main_text=MAIN,
        expandable_blocks=[{"text": EXPANDABLE, "offset": 100}],
        branding=RTL_BRANDING,
    )
    caption = plan.telegram["media_caption"]

    assert len(caption) == len(f"{MAIN}\n\n{EXPANDABLE}\n\n{RTL_BRANDING}")
    assert utf16_length(caption) == utf16_length(
        f"{MAIN}\n\n{EXPANDABLE}\n\n{RTL_BRANDING}"
    )
    assert plan.telegram["followup_messages"] == []
