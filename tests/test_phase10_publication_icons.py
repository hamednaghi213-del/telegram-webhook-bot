from core.publication_icons import (
    apply_icons,
    extract_icons,
    format_with_icons,
    format_with_profile,
    normalize_icons,
    strip_icons,
)
from core.branding_sample import analyze_branding_sample, build_branding_preview


def _utf16(value):
    return len(value.encode("utf-16-le")) // 2


def test_extracts_any_unicode_icon_from_initial_branding_message():
    assert extract_icons("دنیا۲۴ #خبر @channel 🟢 🔵 📰") == ["🟢", "🔵", "📰"]


def test_user_can_increase_decrease_reorder_and_replace_icons():
    assert normalize_icons(["🔥", "⚡️", "🌍", "✅"]) == ["🔥", "⚡️", "🌍", "✅"]
    assert normalize_icons(["🟣"]) == ["🟣"]


def test_no_icon_mode_does_not_modify_content():
    assert apply_icons("متن خبر", [], enabled=False) == "متن خبر"


def test_icons_are_applied_in_user_selected_order():
    assert apply_icons("متن خبر", ["📰", "🔴"], enabled=True) == "📰 🔴\nمتن خبر"


def test_hashtags_and_channel_tags_are_not_icons():
    assert extract_icons("#خبر @channel") == []


def test_sample_formatter_replaces_foreign_icons_with_selected_style():
    source = "🚨 تیتر خبر\n\n1️⃣ بند اول\n\n🎬 بند دوم"
    assert format_with_icons(source, ["🟢", "🔵"]) == (
        "🟢 تیتر خبر\n\n🔵 1 بند اول\n\n🔵 بند دوم"
    )


def test_strip_icons_removes_custom_emoji_decoration_not_text():
    assert strip_icons("🎬 خبر مهم 🔥") == "خبر مهم"


def test_real_sample_excludes_bale_cta_icon_from_news_style():
    sample = (
        "🟩 تحویل دومین هواپیمای سوخت‌رسان\n\n"
        "🔷 بند اول خبر.\n\n"
        "🔷 بند دوم خبر.\n\n"
        "📌 بی‌نشانه را در بله دنبال کنید\n\n"
        "#بی_نشانه\n@beneshaneh"
    )
    analysis = analyze_branding_sample(sample)
    assert analysis["icons"] == ["🟩", "🔷", "📌"]
    assert analysis["structural_icons"] == ["🟩", "🔷"]
    assert analysis["cta_icons"] == ["📌"]
    assert "در بله دنبال کنید" not in analysis["content"]
    assert "📌" not in analysis["content"]
    preview = build_branding_preview(
        sample,
        analysis["icons"],
        {"hashtag": "#بی_نشانه", "channel_tag": "@beneshaneh"},
    )
    assert "📌" in preview
    assert preview.count("🔷") == 2


def test_real_text_sample_extracts_hidden_bale_link_and_bold_title():
    title = "جانشین اینفانتینو از آسیا می‌آید؟"
    cta = "📌 فردای‌نو را در بله دنبال کنید"
    sample = (
        f"🟩 {title}\n\n"
        "🔷 بند اول.\n\n🔷 بند دوم.\n\n🔷 بند سوم.\n\n"
        f"{cta}\n\n#فردای_نو\n@farda_nou"
    )
    title_start = sample.index(title)
    cta_start = sample.index(cta)
    entities = [
        {"type": "bold", "offset": _utf16(sample[:title_start]),
         "length": _utf16(title)},
        {"type": "text_link", "offset": _utf16(sample[:cta_start]),
         "length": _utf16(cta), "url": "https://ble.ir/farda_nou"},
    ]
    analysis = analyze_branding_sample(sample, entities)
    assert analysis["icons"] == ["🟩", "🔷", "📌"]
    assert analysis["bale_channel"] == "@farda_nou"
    assert analysis["bale_url"] == "https://ble.ir/farda_nou"
    assert analysis["bold_texts"] == [title]
    assert cta not in analysis["content"]


def test_complete_profile_preserves_cta_role_without_using_it_for_body():
    profile = {
        "title_icon": "🟩",
        "body_icons": ["🔷"],
        "cta_icons": ["📌"],
        "cta_lines": ["📌 رسانه را در بله دنبال کنید"],
    }
    rendered = format_with_profile("تیتر\n\nبند اول\n\nبند دوم", profile)
    assert rendered == (
        "🟩 تیتر\n\n🔷 بند اول\n\n🔷 بند دوم\n\n"
        "📌 رسانه را در بله دنبال کنید"
    )
