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
    workspaces, error = workspace_publisher.resolve_workspaces_for_user(
        100,
        lambda _telegram_id: {"id": 1},
        lambda _user_id: WORKSPACES,
        lambda _user_id: {"active_workspace_id": 20, "context_type": "workspace"},
        lambda _user_id: [],
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
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = lambda _user_id, workspace_id: selected.add(workspace_id)
    fake_database.deselect_workspace = lambda _user_id, workspace_id: selected.remove(workspace_id)
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    fake_database.get_tenant = lambda _chat_id: None
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setattr(workspace_publisher, "_ws_answer_callback", lambda *args: answers.append(args))
    monkeypatch.setattr(workspace_publisher, "_ws_edit_message_keyboard", lambda *args: edits.append(args))
    monkeypatch.setattr(workspace_publisher, "_ws_send_message", lambda *args: messages.append(args))

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
    fake_database.list_selected_workspace_ids = lambda _user_id: sorted(selected)
    fake_database.select_workspace = lambda _user_id, workspace_id: selected.add(workspace_id)
    fake_database.deselect_workspace = lambda _user_id, workspace_id: selected.remove(workspace_id)
    fake_database.list_user_workspace_memberships = lambda _user_id: WORKSPACES
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    monkeypatch.setattr(workspace_publisher, "_ws_answer_callback", lambda *args: answers.append(args))

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
        database, "get_active_workspace_preference", lambda _user_id: None
    )

    result = database.set_active_legacy_context(3)

    payload = fake_supabase.preferences.payloads[0][0]
    assert payload["created_at"] > 0
    assert payload["updated_at"] >= payload["created_at"]
    assert result["created_at"] == payload["created_at"]
