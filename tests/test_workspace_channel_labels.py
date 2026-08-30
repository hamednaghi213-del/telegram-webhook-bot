from core.workspace_publisher import build_workspace_keyboard, resolve_legacy_media_label


def test_workspace_keyboard_uses_real_channel_labels_and_internal_ids():
    keyboard = build_workspace_keyboard(
        [
            {"id": 12, "name": "رسانه من", "display_label": "@Donya24News_En", "membership_role": "owner"},
        ],
        12,
        selected_workspace_ids=[12],
        include_legacy=True,
        legacy_active=True,
        legacy_label="@Donya24News",
    )
    assert "@Donya24News" in keyboard[0][0]["text"]
    assert "@Donya24News_En" in keyboard[1][0]["text"]
    assert keyboard[1][0]["callback_data"] == "ws:toggle:12"


def test_workspace_keyboard_falls_back_to_workspace_name():
    keyboard = build_workspace_keyboard(
        [{"id": 5, "name": "نام واقعی", "membership_role": "manager"}],
        None,
    )
    assert "نام واقعی" in keyboard[0][0]["text"]


def test_legacy_label_ignores_registration_placeholder():
    assert resolve_legacy_media_label({
        "telegram_channel": "@channel",
        "channel_tag": "@Donya24News",
        "bale_channel": "@donya24_news",
    }) == "@Donya24News"


def test_legacy_label_hashtag_fallback_is_human_readable():
    assert resolve_legacy_media_label({
        "telegram_channel": "@channel",
        "hashtag": "#رسانه_نمونه",
    }) == "رسانه نمونه"

