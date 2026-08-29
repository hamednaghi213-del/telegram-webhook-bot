"""Phase 5 active-workspace selection tests."""

import importlib
import sys
import types

import pytest

from core import workspace_publisher


class _PreferenceResult:
    def __init__(self, data):
        self.data = data


class _PreferenceTable:
    def __init__(self):
        self.payloads = []

    def upsert(self, payload, on_conflict=None):
        self.payloads.append((dict(payload), on_conflict))
        return self

    def execute(self):
        return _PreferenceResult([self.payloads[-1][0]])


class _PreferenceSupabase:
    def __init__(self):
        self.preferences = _PreferenceTable()

    def table(self, name):
        assert name == "user_workspace_preferences"
        return self.preferences


@pytest.fixture
def preference_database(monkeypatch):
    fake_client = _PreferenceSupabase()
    fake_supabase_module = types.ModuleType("supabase")
    fake_supabase_module.create_client = lambda _url, _key: fake_client
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase_module)

    sys.modules.pop("core.database", None)
    core_package = sys.modules.get("core")
    if core_package is not None and hasattr(core_package, "database"):
        delattr(core_package, "database")
    database = importlib.import_module("core.database")
    yield database, fake_client

    sys.modules.pop("core.database", None)
    if core_package is not None and hasattr(core_package, "database"):
        delattr(core_package, "database")


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

    assert keyboard[0][0]["callback_data"] == "ws:toggle:10"
    assert keyboard[0][0]["text"].startswith("▫️")
    assert keyboard[1][0]["text"].startswith("✅")


def test_workspace_keyboard_marks_multiple_selected_workspaces():
    keyboard = workspace_publisher.build_workspace_keyboard(
        WORKSPACES, 10, selected_workspace_ids=[10, 20]
    )

    assert all(row[0]["text"].startswith("✅") for row in keyboard)
    assert [row[0]["callback_data"] for row in keyboard] == [
        "ws:toggle:10",
        "ws:toggle:20",
    ]


def test_multiple_workspaces_resolve_all_selected_memberships():
    workspaces, error = workspace_publisher.resolve_workspaces_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: WORKSPACES,
        lambda _user_id: {"active_workspace_id": 10, "context_type": "workspace"},
        lambda _user_id: [10, 20],
    )

    assert [workspace["id"] for workspace in workspaces] == [10, 20]
    assert error is None


def test_multiple_workspaces_fall_back_to_legacy_active_preference():
    """
    Backward compatibility:
    when no explicit publication-selection provider is available,
    the legacy active-workspace preference may still be used as fallback.

    This is intentionally different from an explicit selection provider
    returning [], which means the user has no workspace checked for publication.
    """
    workspaces, error = workspace_publisher.resolve_workspaces_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: WORKSPACES,
        lambda _user_id: {
            "active_workspace_id": 20,
            "context_type": "workspace",
        },
    )

    assert [workspace["id"] for workspace in workspaces] == [20]
    assert error is None


def test_workspace_toggle_adds_workspace_and_answers_callback(monkeypatch):
    selected = {10}
    answers = []
    edits = []
    messages = []
    fake_database = types.ModuleType("core.database")
    fake_database.get_user_by_telegram_id = lambda _chat_id: {"id": 1}
    fake_database.get_destination_branding = lambda _dest_id: None
    fake_database.get_workspace_branding = lambda _workspace_id: None
    fake_database.set_active_legacy_context = lambda _user_id: None
    fake_database.set_active_workspace = lambda _user_id, _workspace_id: None
    fake_database.set_legacy_workspace_selected = lambda _user_id, _selected: None
    fake_database.get_active_workspace_preference = lambda _user_id: {
        "context_type": "workspace",
        "active_workspace_id": 10,
        "legacy_selected": False,
    }
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = (
        lambda _user_id, workspace_id: selected.add(workspace_id)
    )
    fake_database.deselect_workspace = (
        lambda _user_id, workspace_id: selected.remove(workspace_id)
    )
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    fake_database.get_workspace_setup_state = (
        lambda _workspace_id: {"step": "completed"}
    )
    fake_database.get_tenant = lambda _chat_id: None
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda *args: answers.append(args),
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_edit_message_keyboard",
        lambda *args: edits.append(args),
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message",
        lambda *args: messages.append(args),
    )

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:toggle:20", "from": {"id": 100}},
        "req",
        "https://api.test",
    )

    assert selected == {10, 20}
    assert answers and "اضافه شد" in answers[-1][-1]
    assert edits
    assert all(row[0]["text"].startswith("✅") for row in edits[-1][-1])
    assert messages


def test_workspace_toggle_does_not_remove_last_selection(monkeypatch):
    selected = {10}
    answers = []
    fake_database = types.ModuleType("core.database")
    fake_database.get_user_by_telegram_id = lambda _chat_id: {"id": 1}
    fake_database.get_destination_branding = lambda _dest_id: None
    fake_database.get_workspace_branding = lambda _workspace_id: None
    fake_database.set_active_legacy_context = lambda _user_id: None
    fake_database.set_active_workspace = lambda _user_id, _workspace_id: None
    fake_database.set_legacy_workspace_selected = lambda _user_id, _selected: None
    fake_database.get_active_workspace_preference = lambda _user_id: {
        "context_type": "workspace",
        "active_workspace_id": 10,
        "legacy_selected": False,
    }
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = (
        lambda _user_id, workspace_id: selected.add(workspace_id)
    )
    fake_database.deselect_workspace = (
        lambda _user_id, workspace_id: selected.remove(workspace_id)
    )
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    fake_database.get_workspace_setup_state = (
        lambda _workspace_id: {"step": "completed"}
    )
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda *args: answers.append(args),
    )

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:toggle:10", "from": {"id": 100}},
        "req",
        "https://api.test",
    )

    assert selected == {10}
    assert "حداقل یک رسانه" in answers[-1][-1]


def test_workspace_keyboard_can_include_legacy_media_context():
    keyboard = workspace_publisher.build_workspace_keyboard(
        WORKSPACES,
        None,
        include_legacy=True,
        legacy_active=True,
    )

    assert keyboard[0][0] == {
        "text": "✅ رسانه قدیمی",
        "callback_data": "ws:legacy",
    }
    assert keyboard[1][0]["text"].startswith("▫️")


def test_legacy_and_workspace_can_both_show_selected():
    keyboard = workspace_publisher.build_workspace_keyboard(
        WORKSPACES,
        None,
        selected_workspace_ids=[20],
        include_legacy=True,
        legacy_active=True,
    )

    assert keyboard[0][0]["text"].startswith("✅")
    assert keyboard[1][0]["text"].startswith("▫️")
    assert keyboard[2][0]["text"].startswith("✅")


def test_selected_workspace_in_legacy_context_is_activated_not_removed(monkeypatch):
    selected = {20}
    active = []
    answers = []
    fake_database = types.ModuleType("core.database")
    fake_database.get_user_by_telegram_id = lambda _chat_id: {"id": 1}
    fake_database.get_destination_branding = lambda _dest_id: None
    fake_database.get_workspace_branding = lambda _workspace_id: None
    fake_database.set_active_legacy_context = lambda _user_id: None
    fake_database.set_legacy_workspace_selected = lambda _user_id, _selected: None
    fake_database.set_active_workspace = (
        lambda user_id, workspace_id: active.append(workspace_id)
    )
    fake_database.get_active_workspace_preference = lambda _user_id: (
        {
            "context_type": "workspace",
            "active_workspace_id": active[-1],
            "legacy_selected": True,
        }
        if active
        else {
            "context_type": "legacy",
            "active_workspace_id": None,
            "legacy_selected": True,
        }
    )
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = (
        lambda _user_id, workspace_id: selected.add(workspace_id)
    )
    fake_database.deselect_workspace = (
        lambda _user_id, workspace_id: selected.remove(workspace_id)
    )
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    fake_database.get_workspace_setup_state = (
        lambda _workspace_id: {"step": "completed"}
    )
    fake_database.get_tenant = lambda _chat_id: {"telegram_channel": "@old"}
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda *args: answers.append(args),
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_edit_message_keyboard",
        lambda *args: None,
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message",
        lambda *args: None,
    )

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:toggle:20", "from": {"id": 100}},
        "req",
        "https://api.test",
    )

    assert selected == {20}
    assert active == [20]
    assert "تکمیل راه‌اندازی" in answers[-1][-1]


def test_active_incomplete_workspace_resumes_existing_setup(monkeypatch):
    selected = {20}
    resumed = []
    fake_database = types.ModuleType("core.database")
    fake_database.get_user_by_telegram_id = lambda _chat_id: {"id": 1}
    fake_database.get_destination_branding = lambda _dest_id: None
    fake_database.get_workspace_branding = lambda _workspace_id: None
    fake_database.set_active_legacy_context = lambda _user_id: None
    fake_database.set_legacy_workspace_selected = lambda _user_id, _selected: None
    fake_database.set_active_workspace = lambda _user_id, _workspace_id: None
    fake_database.get_active_workspace_preference = lambda _user_id: {
        "context_type": "workspace",
        "active_workspace_id": 20,
        "legacy_selected": True,
    }
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = (
        lambda _user_id, workspace_id: selected.add(workspace_id)
    )
    fake_database.deselect_workspace = (
        lambda _user_id, workspace_id: selected.remove(workspace_id)
    )
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    fake_database.get_workspace_setup_state = lambda _workspace_id: {
        "step": "in_progress",
        "current_step_key": "setup_branding_sample",
    }
    fake_database.get_tenant = lambda _chat_id: {"telegram_channel": "@old"}
    fake_command_handler = types.ModuleType("core.command_handler")
    fake_command_handler.handle_setup = lambda chat_id: resumed.append(chat_id)
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setitem(sys.modules, "core.command_handler", fake_command_handler)
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda *args: None,
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_edit_message_keyboard",
        lambda *args: None,
    )
    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message",
        lambda *args: None,
    )

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:toggle:20", "from": {"id": 100}},
        "req",
        "https://api.test",
    )

    assert selected == {20}
    assert resumed == [100]


def test_existing_preference_upserts_always_include_original_created_at(
    monkeypatch, preference_database
):
    database, fake_supabase = preference_database
    monkeypatch.setattr(
        database,
        "get_active_workspace_preference",
        lambda _user_id: {"user_id": 2, "created_at": 123.5},
    )
    monkeypatch.setattr(
        database,
        "get_workspace_member",
        lambda _workspace_id, _user_id: {"status": "active"},
    )
    monkeypatch.setattr(
        database,
        "get_workspace",
        lambda workspace_id: {"id": workspace_id, "status": "active"},
    )

    database.set_active_workspace(2, 10)
    database.set_active_legacy_context(2)

    workspace_payload = fake_supabase.preferences.payloads[0][0]
    legacy_payload = fake_supabase.preferences.payloads[1][0]
    assert workspace_payload["created_at"] == 123.5
    assert legacy_payload["created_at"] == 123.5
    assert workspace_payload["context_type"] == "workspace"
    assert workspace_payload["active_workspace_id"] == 10
    assert legacy_payload["context_type"] == "legacy"
    assert legacy_payload["active_workspace_id"] is None


def test_new_preference_upsert_supplies_created_at(
    monkeypatch, preference_database
):
    database, fake_supabase = preference_database
    monkeypatch.setattr(
        database,
        "get_active_workspace_preference",
        lambda _user_id: None,
    )

    result = database.set_active_legacy_context(3)

    payload = fake_supabase.preferences.payloads[0][0]
    assert payload["created_at"] > 0
    assert payload["updated_at"] >= payload["created_at"]
    assert result["created_at"] == payload["created_at"]

def test_workspace_keyboard_does_not_restore_unchecked_active_workspace():
    """
    Regression:
    An explicitly empty publication selection means no workspace is checked.
    Active workspace is management context only and must not appear selected.
    """
    keyboard = workspace_publisher.build_workspace_keyboard(
        WORKSPACES,
        20,
        selected_workspace_ids=[],
    )

    assert keyboard[0][0]["text"].startswith("▫️")
    assert keyboard[1][0]["text"].startswith("▫️")

def test_workspace_keyboard_shows_media_name_without_membership_role():
    """
    Regression:
    /workspaces must show the media display name as the main label.
    Membership roles such as owner/manager/publisher must not be appended
    to the visible media title.
    """
    workspaces = [
        {
            "id": 30,
            "name": "Internal Workspace Name",
            "membership_role": "owner",
            "display_label": "دنیا ۲۴ انگلیسی",
            "display_platforms": ["bale", "telegram"],
        }
    ]

    keyboard = workspace_publisher.build_workspace_keyboard(
        workspaces,
        30,
        selected_workspace_ids=[30],
    )

    text = keyboard[0][0]["text"]

    assert text.startswith("✅ دنیا ۲۴ انگلیسی")
    assert "bale/telegram" in text
    assert "(owner)" not in text
    assert "Internal Workspace Name" not in text
