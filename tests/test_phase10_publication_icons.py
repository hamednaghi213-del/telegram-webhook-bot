from core.publication_icons import apply_icons, extract_icons, normalize_icons


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
