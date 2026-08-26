from core.workspace_publisher import build_workspace_keyboard


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

