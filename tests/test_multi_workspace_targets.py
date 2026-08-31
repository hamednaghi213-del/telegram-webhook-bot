import sys
from types import ModuleType

from core.target_resolver import resolve_publication_targets


def _install_database(monkeypatch, *, selected, destinations, legacy=None):
    database = ModuleType("core.database")
    database.get_tenant = lambda _chat_id: legacy
    database.get_user_by_telegram_id = lambda _chat_id: {"id": 9}
    database.get_active_workspace_preference = lambda _user_id: {
        "legacy_selected": bool(legacy),
    }
    database.list_selected_workspace_ids = lambda _user_id: list(selected)
    database.list_user_workspace_memberships = lambda _user_id: [
        {"id": workspace_id, "name": f"گروه {workspace_id}"}
        for workspace_id in sorted(destinations)
    ]
    database.get_workspace_setup_state = lambda _workspace_id: {"step": "completed"}
    database.get_workspace_member = lambda _workspace_id, _user_id: {
        "role": "owner",
        "status": "active",
    }
    database.list_verified_active_destinations = (
        lambda workspace_id: list(destinations.get(workspace_id, []))
    )
    monkeypatch.setitem(sys.modules, "core.database", database)


def _destinations(workspace_id, count):
    return [
        {
            "id": workspace_id * 100 + index,
            "platform": "telegram",
            "external_id": f"@group_{workspace_id}_{index}",
            "status": "active",
            "verified": True,
        }
        for index in range(1, count + 1)
    ]


def test_selected_workspace_fans_out_to_all_ten_verified_active_destinations(monkeypatch):
    destinations = {1: _destinations(1, 10)}
    _install_database(monkeypatch, selected={1}, destinations=destinations)

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    assert len(targets) == 10
    assert {target.workspace_id for target in targets} == {1}


def test_unselected_workspace_contributes_no_targets(monkeypatch):
    destinations = {1: _destinations(1, 10)}
    _install_database(monkeypatch, selected=set(), destinations=destinations)

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    assert targets == []


def test_two_selected_workspaces_publish_union(monkeypatch):
    destinations = {1: _destinations(1, 10), 2: _destinations(2, 10)}
    _install_database(monkeypatch, selected={1, 2}, destinations=destinations)

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    assert len(targets) == 20
    assert {target.workspace_id for target in targets} == {1, 2}


def test_duplicate_physical_destination_across_workspaces_is_canonicalized(monkeypatch):
    destinations = {
        1: [{"id": 11, "platform": "telegram", "external_id": "@same"}],
        2: [{"id": 22, "platform": "telegram", "external_id": "same"}],
    }
    _install_database(monkeypatch, selected={1, 2}, destinations=destinations)

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    assert len(targets) == 1
    assert targets[0].kind == "workspace"


def test_legacy_and_workspace_duplicate_prefers_workspace_target(monkeypatch):
    destinations = {
        1: [{"id": 11, "platform": "telegram", "external_id": "@same"}],
    }
    _install_database(
        monkeypatch,
        selected={1},
        destinations=destinations,
        legacy={"telegram_channel": "same", "bale_channel": ""},
    )

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    telegram_targets = [target for target in targets if target.platform == "telegram"]
    assert len(telegram_targets) == 1
    assert telegram_targets[0].kind == "workspace"
