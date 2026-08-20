"""Phase 5 active-workspace selection tests."""

from core import workspace_publisher


WORKSPACES = [
    {"id": 10, "name": "Alpha", "membership_role": "owner"},
    {"id": 20, "name": "Beta", "membership_role": "publisher"},
]


def test_single_workspace_resolves_without_preference():
    workspace, error = workspace_publisher.resolve_workspace_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: [WORKSPACES[0]],
    )

    assert workspace["id"] == 10
    assert error is None


def test_multiple_workspaces_resolve_persisted_selection():
    workspace, error = workspace_publisher.resolve_workspace_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: WORKSPACES,
        lambda _user_id: {"active_workspace_id": 20},
    )

    assert workspace["id"] == 20
    assert error is None


def test_stale_preference_requires_new_selection():
    workspace, error = workspace_publisher.resolve_workspace_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: WORKSPACES,
        lambda _user_id: {"active_workspace_id": 999},
    )

    assert workspace is None
    assert "چند رسانه" in error


def test_workspace_keyboard_marks_active_workspace():
    keyboard = workspace_publisher.build_workspace_keyboard(WORKSPACES, 20)

    assert keyboard[0][0]["callback_data"] == "ws:select:10"
    assert keyboard[0][0]["text"].startswith("▫️")
    assert keyboard[1][0]["text"].startswith("✅")
