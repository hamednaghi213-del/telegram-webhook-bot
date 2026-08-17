import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class FakeQuery:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self._eq_filters = []
        self._in_filters = []
        self._limit = None
        self._op = "select"
        self._payload = None

    def select(self, _columns):
        self._op = "select"
        return self

    def eq(self, column, value):
        self._eq_filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, set(values)))
        return self

    def limit(self, value):
        self._limit = value
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _apply_filters(self, rows):
        filtered = rows
        for column, value in self._eq_filters:
            filtered = [r for r in filtered if r.get(column) == value]
        for column, values in self._in_filters:
            filtered = [r for r in filtered if r.get(column) in values]
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return filtered

    def execute(self):
        table = self.store.setdefault(self.table_name, [])
        if self._op == "select":
            return SimpleNamespace(
                data=[dict(row) for row in self._apply_filters(table)]
            )

        if self._op == "insert":
            payload = dict(self._payload)
            if "id" not in payload:
                payload["id"] = f"{self.table_name}_{len(table) + 1}"
            table.append(payload)
            return SimpleNamespace(data=[dict(payload)])

        if self._op == "update":
            updated = []
            for row in table:
                row_matches = all(
                    row.get(column) == value
                    for column, value in self._eq_filters
                )
                if not row_matches:
                    continue
                for column, values in self._in_filters:
                    if row.get(column) not in values:
                        row_matches = False
                        break
                if row_matches:
                    row.update(dict(self._payload))
                    updated.append(dict(row))
            return SimpleNamespace(data=updated)

        if self._op == "delete":
            remaining = []
            deleted = []
            for row in table:
                row_matches = all(
                    row.get(column) == value
                    for column, value in self._eq_filters
                )
                if row_matches:
                    deleted.append(dict(row))
                else:
                    remaining.append(row)
            self.store[self.table_name] = remaining
            return SimpleNamespace(data=deleted)

        raise RuntimeError(f"Unsupported operation: {self._op}")


class FakeSupabase:
    def __init__(self):
        self.store = {
            "tenants": [],
            "users": [],
            "workspaces": [],
            "workspace_members": [],
        }

    def table(self, table_name):
        return FakeQuery(self.store, table_name)


@pytest.fixture
def db_module(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "a.b.c")

    fake_supabase = FakeSupabase()
    fake_supabase_module = types.ModuleType("supabase")
    fake_supabase_module.create_client = lambda _url, _key: fake_supabase
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase_module)

    if "core.database" in sys.modules:
        del sys.modules["core.database"]
    import core.database as db

    return importlib.reload(db)


def test_create_user_from_telegram_id(db_module):
    user = db_module.get_or_create_user_by_telegram_id(1001)
    assert user["telegram_user_id"] == 1001
    assert user["status"] == "active"


def test_get_or_create_user_idempotent(db_module):
    first = db_module.get_or_create_user_by_telegram_id(1002)
    second = db_module.get_or_create_user_by_telegram_id(1002)
    assert first["id"] == second["id"]


def test_workspace_owner_and_membership_lifecycle(db_module):
    owner = db_module.get_or_create_user_by_telegram_id(2001)
    second_user = db_module.get_or_create_user_by_telegram_id(2002)

    workspace = db_module.create_workspace("News Desk", owner["id"])
    fetched_workspace = db_module.get_workspace(workspace["id"])
    assert fetched_workspace["owner_user_id"] == owner["id"]

    owner_member = db_module.get_workspace_member(workspace["id"], owner["id"])
    assert owner_member["role"] == "owner"
    assert owner_member["status"] == "active"

    second_member = db_module.add_workspace_member(
        workspace["id"],
        second_user["id"],
        role="writer",
    )
    assert second_member["role"] == "writer"
    assert second_member["status"] == "active"

    duplicate = db_module.add_workspace_member(
        workspace["id"],
        second_user["id"],
        role="writer",
    )
    assert duplicate["id"] == second_member["id"]

    updated_role = db_module.update_workspace_member_role(
        workspace["id"],
        second_user["id"],
        "publisher",
    )
    assert updated_role["role"] == "publisher"

    suspended = db_module.update_workspace_member_status(
        workspace["id"],
        second_user["id"],
        "suspended",
    )
    assert suspended["status"] == "suspended"

    active_members = db_module.list_workspace_members(workspace["id"])
    active_member_ids = {member["user_id"] for member in active_members}
    assert second_user["id"] not in active_member_ids

    reactivated = db_module.update_workspace_member_status(
        workspace["id"],
        second_user["id"],
        "active",
    )
    assert reactivated["status"] == "active"

    removed = db_module.update_workspace_member_status(
        workspace["id"],
        second_user["id"],
        "removed",
    )
    assert removed["status"] == "removed"

    active_members_after_remove = db_module.list_workspace_members(workspace["id"])
    active_ids_after_remove = {member["user_id"] for member in active_members_after_remove}
    assert second_user["id"] not in active_ids_after_remove


def test_user_workspace_relationships(db_module):
    user_a = db_module.get_or_create_user_by_telegram_id(3001)
    user_b = db_module.get_or_create_user_by_telegram_id(3002)
    user_c = db_module.get_or_create_user_by_telegram_id(3003)

    workspace_1 = db_module.create_workspace("Desk A", user_a["id"])
    workspace_2 = db_module.create_workspace("Desk B", user_b["id"])

    db_module.add_workspace_member(workspace_1["id"], user_b["id"], role="manager")
    db_module.add_workspace_member(workspace_1["id"], user_c["id"], role="writer")
    db_module.add_workspace_member(workspace_2["id"], user_a["id"], role="publisher")

    user_a_workspaces = db_module.list_user_workspaces(user_a["id"])
    user_a_workspace_ids = {workspace["id"] for workspace in user_a_workspaces}
    assert workspace_1["id"] in user_a_workspace_ids
    assert workspace_2["id"] in user_a_workspace_ids

    workspace_1_members = db_module.list_workspace_members(workspace_1["id"])
    workspace_1_member_ids = {member["user_id"] for member in workspace_1_members}
    assert user_a["id"] in workspace_1_member_ids
    assert user_b["id"] in workspace_1_member_ids
    assert user_c["id"] in workspace_1_member_ids


def test_get_tenant_legacy_behavior_unchanged(db_module):
    db_module.supabase.store["tenants"].append({
        "id": "tenant_1",
        "user_id": 9999,
        "telegram_channel": "@legacy-channel",
        "bale_channel": "@legacy-bale",
        "bot_token": "legacy-bot-token",
        "bale_token": "legacy-bale-token",
        "hashtag": "#legacy",
        "channel_tag": "@legacy",
    })
    tenant = db_module.get_tenant(9999)
    assert tenant is not None
    assert tenant["telegram_channel"] == "@legacy-channel"
    assert tenant["bale_channel"] == "@legacy-bale"
