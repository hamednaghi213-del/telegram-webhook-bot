from copy import deepcopy
import importlib
import sys

import pytest

from core.workspace_destination_moves import list_move_candidates, move_destinations
from core.workspace_destinations import canonical_destination_identity, validate_destination_move
from core.workspace_publisher import (
    build_workspace_management_panel,
    build_destination_move_keyboard,
    selected_destination_ids_from_callback,
)


class FakeDatabase:
    def __init__(self, memberships, destinations):
        self.memberships = deepcopy(memberships)
        self.destinations = deepcopy(destinations)
        self.move_calls = []

    def list_user_workspace_memberships(self, user_id):
        return deepcopy(self.memberships.get(user_id, []))

    def list_publication_destinations_for_workspaces(self, workspace_ids):
        allowed = set(workspace_ids)
        return deepcopy([
            row for row in self.destinations
            if row["workspace_id"] in allowed and row.get("status") != "removed"
        ])

    def move_publication_destinations(self, destination_ids, target_workspace_id):
        self.move_calls.append((list(destination_ids), target_workspace_id))
        moved = []
        for row in self.destinations:
            if row["id"] in destination_ids:
                row["workspace_id"] = target_workspace_id
                row["is_default"] = False
                moved.append(deepcopy(row))
        return moved


def ws(workspace_id, role="owner", status="active", name=None):
    return {"id": workspace_id, "name": name or f"ws-{workspace_id}", "status": status, "member_role": role}


def dest(destination_id, workspace_id, platform="telegram", external_id="@channel", status="active", **extra):
    return {
        "id": destination_id,
        "workspace_id": workspace_id,
        "platform": platform,
        "external_id": external_id,
        "status": status,
        "is_default": extra.pop("is_default", False),
        **extra,
    }


def _load_real_database(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "a.b.c")
    sys.modules.pop("core.database", None)
    import core
    if hasattr(core, "database"):
        delattr(core, "database")
    return importlib.import_module("core.database")


@pytest.fixture
def database():
    return FakeDatabase(
        {7: [ws(1, "owner", name="مبدأ"), ws(2, "manager", name="سیاسی")]},
        [
            dest(10, 1, "telegram", "@siasat24", is_default=True, verification="kept", branding="kept"),
            dest(11, 1, "bale", "@siasat24"),
            dest(12, 2, "telegram", "@target"),
        ],
    )


def test_lists_only_other_manageable_workspace_destinations_in_one_bulk_query(database):
    target, candidates = list_move_candidates(database, 7, 2)
    assert target["name"] == "سیاسی"
    assert [row["id"] for row in candidates] == [10, 11]
    assert {row["source_workspace_name"] for row in candidates} == {"مبدأ"}


@pytest.mark.parametrize("role", ["viewer", "publisher", None])
def test_target_requires_owner_or_manager(role):
    database = FakeDatabase({7: [ws(1), ws(2, role)]}, [dest(1, 1)])
    with pytest.raises(ValueError, match="اجازه مدیریت"):
        list_move_candidates(database, 7, 2)


def test_inactive_target_is_rejected():
    database = FakeDatabase({7: [ws(1), ws(2, status="archived")]}, [dest(1, 1)])
    with pytest.raises(ValueError):
        move_destinations(database, 7, 2, [1])


def test_forged_destination_from_unmanaged_source_is_rejected():
    database = FakeDatabase({7: [ws(2)]}, [dest(99, 9)])
    with pytest.raises(ValueError):
        move_destinations(database, 7, 2, [99])
    assert database.move_calls == []


def test_move_preserves_id_metadata_and_moves_platforms_independently(database):
    moved = move_destinations(database, 7, 2, [10])
    assert [row["id"] for row in moved] == [10]
    assert moved[0]["workspace_id"] == 2
    assert moved[0]["verification"] == "kept"
    assert moved[0]["branding"] == "kept"
    assert database.destinations[1]["workspace_id"] == 1
    assert database.move_calls == [([10], 2)]


def test_multi_move_is_issued_as_one_batch(database):
    moved = move_destinations(database, 7, 2, [11, 10])
    assert [row["id"] for row in moved] == [10, 11]
    assert database.move_calls == [([10, 11], 2)]


@pytest.mark.parametrize(
    "target, moving",
    [
        (dest(2, 2, "telegram", "@Siasat24"), dest(1, 1, "telegram", "siasat24")),
        (dest(2, 2, "bale", "@Siasat24"), dest(1, 1, "bale", "@siasat24")),
    ],
)
def test_canonical_duplicate_blocks_whole_move(target, moving):
    allowed, reason, rows = validate_destination_move([target, moving], [1], 2)
    assert not allowed and "وجود دارد" in reason and rows == []


def test_same_handle_on_different_platform_is_not_a_duplicate():
    rows = [dest(2, 2, "telegram", "@same"), dest(1, 1, "bale", "@same")]
    assert validate_destination_move(rows, [1], 2)[0]


def test_duplicate_inside_selected_batch_is_rejected():
    rows = [dest(1, 1, "telegram", "@same"), dest(2, 3, "telegram", "same")]
    assert not validate_destination_move(rows, [1, 2], 4)[0]


@pytest.mark.parametrize("selected", [[], [404]])
def test_empty_or_stale_selection_is_rejected(database, selected):
    with pytest.raises(ValueError):
        move_destinations(database, 7, 2, selected)
    assert database.move_calls == []


def test_removed_destination_cannot_move():
    database = FakeDatabase({7: [ws(1), ws(2)]}, [dest(1, 1, status="removed")])
    with pytest.raises(ValueError):
        move_destinations(database, 7, 2, [1])


def test_destination_already_in_target_cannot_move():
    allowed, _, _ = validate_destination_move([dest(1, 2)], [1], 2)
    assert not allowed


def test_reverse_move_is_generic(database):
    first = move_destinations(database, 7, 2, [10])
    assert first[0]["workspace_id"] == 2
    second = move_destinations(database, 7, 1, [10])
    assert second[0]["workspace_id"] == 1


def test_keyboard_has_multi_select_confirm_and_back(database):
    _, candidates = list_move_candidates(database, 7, 2)
    keyboard = build_destination_move_keyboard(2, candidates, {10})
    assert keyboard[0][0]["text"].startswith("✅")
    assert keyboard[1][0]["text"].startswith("⬜")
    assert keyboard[-2][0]["callback_data"] == "ws:move:confirm:2"
    assert keyboard[-1][0]["callback_data"] == "ws:manage:2"
    assert all(len(button["callback_data"].encode()) <= 64 for row in keyboard for button in row)


def test_selected_ids_are_recovered_from_real_callback_markup(database):
    _, candidates = list_move_candidates(database, 7, 2)
    callback = {"message": {"reply_markup": {"inline_keyboard": build_destination_move_keyboard(2, candidates, {11})}}}
    assert selected_destination_ids_from_callback(callback) == {11}


def test_forged_malformed_markup_is_ignored():
    callback = {"message": {"reply_markup": {"inline_keyboard": [[{"callback_data": "ws:move:pick:2:not-int:1"}]]}}}
    assert selected_destination_ids_from_callback(callback) == set()


def test_canonical_identity_is_case_and_at_insensitive_but_platform_scoped():
    assert canonical_destination_identity(dest(1, 1, "Telegram", " @News ")) == ("telegram", "news")


def test_selection_and_history_are_not_touched_by_move_contract(database):
    database.selections = {7: [1, 2]}
    database.history = [{"workspace_id": 1, "telegram_destination_id": 10}]
    before_selection = deepcopy(database.selections)
    before_history = deepcopy(database.history)
    move_destinations(database, 7, 2, [10])
    assert database.selections == before_selection
    assert database.history == before_history


def test_management_panel_shows_destinations_directly_without_submenu():
    text, keyboard = build_workspace_management_panel(
        {"id": 2, "name": "سیاسی"},
        [dest(10, 2, "telegram", "@one"), dest(11, 2, "bale", "@two", status="inactive")],
    )
    assert "✅ @one — تلگرام" in text
    assert "⬜ @two — بله" in text
    assert "مدیریت کانال‌ها" not in text
    callbacks = [button["callback_data"] for row in keyboard for button in row]
    assert "ws:dest:toggle:10" in callbacks
    assert "ws:dest:toggle:11" in callbacks
    assert not any("@one" in callback or "تلگرام" in callback for callback in callbacks)


def test_management_panel_scales_without_fixed_destination_limit():
    rows = [dest(index, 2, external_id=f"@channel_{index}") for index in range(1, 101)]
    _text, keyboard = build_workspace_management_panel({"id": 2, "name": "بزرگ"}, rows)
    assert sum(1 for row in keyboard if row[0]["callback_data"].startswith("ws:dest:toggle:")) == 100


def test_destination_toggle_is_authorized_and_does_not_touch_workspace_selection(monkeypatch):
    database = _load_real_database(monkeypatch)
    from core import workspace_publisher

    row = dest(10, 2, "telegram", "@one")
    updates = []
    selection_calls = []
    edits = []
    monkeypatch.setattr(database, "get_user_by_telegram_id", lambda _chat: {"id": 7})
    monkeypatch.setattr(database, "get_publication_destination", lambda _id: deepcopy(row))
    monkeypatch.setattr(database, "get_workspace", lambda _id: {"id": 2, "name": "سیاسی", "status": "active"})
    monkeypatch.setattr(database, "get_workspace_member", lambda _wid, _uid: {"role": "manager", "status": "active"})
    monkeypatch.setattr(database, "update_publication_destination_status", lambda did, status: updates.append((did, status)))
    monkeypatch.setattr(database, "list_workspace_destinations", lambda _wid: [{**row, "status": "inactive"}])
    monkeypatch.setattr(database, "set_active_workspace", lambda *_args: selection_calls.append(_args))
    monkeypatch.setattr(workspace_publisher, "_ws_answer_callback", lambda *_args: None)
    monkeypatch.setattr(workspace_publisher, "_ws_edit_message_text", lambda *args: edits.append(args))

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:dest:toggle:10", "from": {"id": 100}, "message": {"chat": {"id": 100}, "message_id": 5}},
        "req",
        "https://api.test",
    )

    assert updates == [(10, "inactive")]
    assert selection_calls == []
    assert edits and "⬜ @one — تلگرام" in edits[0][2]


@pytest.mark.parametrize("role,status", [("viewer", "active"), ("manager", "inactive")])
def test_forged_destination_toggle_is_rejected(monkeypatch, role, status):
    database = _load_real_database(monkeypatch)
    from core import workspace_publisher

    updates = []
    answers = []
    monkeypatch.setattr(database, "get_user_by_telegram_id", lambda _chat: {"id": 7})
    monkeypatch.setattr(database, "get_publication_destination", lambda _id: dest(99, 9))
    monkeypatch.setattr(database, "get_workspace", lambda _id: {"id": 9, "status": "active"})
    monkeypatch.setattr(database, "get_workspace_member", lambda _wid, _uid: {"role": role, "status": status})
    monkeypatch.setattr(database, "update_publication_destination_status", lambda *args: updates.append(args))
    monkeypatch.setattr(workspace_publisher, "_ws_answer_callback", lambda *args: answers.append(args))

    workspace_publisher._handle_workspace_callback(
        {"id": "cb", "data": "ws:dest:toggle:99", "from": {"id": 100}},
        "req",
        "https://api.test",
    )

    assert updates == []
    assert answers and "قابل مدیریت نیست" in answers[-1][-1]
