import importlib
import sys
import types
from copy import deepcopy

import pytest


class FakeResult:

    def __init__(self, data):
        self.data = data


class FakeQuery:

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = []
        self.limit_value = None
        self.select_columns = None
        self.on_conflict = None

    def select(self, columns):
        self.operation = "select"
        self.select_columns = columns
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self.operation = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.client.query_log.append({
            "table": self.table_name,
            "operation": self.operation,
            "filters": list(self.filters),
            "limit": self.limit_value,
            "select": self.select_columns,
            "on_conflict": self.on_conflict,
        })

        if self.operation == "select":
            rows = self.client._filter_rows(
                self.table_name,
                self.filters
            )
            if self.limit_value is not None:
                rows = rows[:self.limit_value]
            return FakeResult([deepcopy(row) for row in rows])

        if self.operation == "insert":
            payloads = self.payload
            if isinstance(payloads, dict):
                payloads = [payloads]

            inserted = [
                self.client._insert_row(
                    self.table_name,
                    payload
                )
                for payload in payloads
            ]
            return FakeResult(inserted)

        if self.operation == "update":
            updated = self.client._update_rows(
                self.table_name,
                self.filters,
                self.payload
            )
            return FakeResult(updated)

        if self.operation == "delete":
            deleted = self.client._delete_rows(
                self.table_name,
                self.filters
            )
            return FakeResult(deleted)

        if self.operation == "upsert":
            updated = self.client._upsert_rows(
                self.table_name,
                self.payload,
                self.on_conflict
            )
            return FakeResult(updated)

        raise AssertionError(
            f"Unsupported operation: {self.operation}"
        )


class FakeSupabaseClient:

    def __init__(self):
        self.tables = {
            "tenants": [],
            "users": [],
            "workspaces": [],
            "workspace_members": [],
        }
        self.next_ids = {
            "users": 1,
            "workspaces": 1,
            "workspace_members": 1,
        }
        self.query_log = []

    def table(self, table_name):
        return FakeQuery(self, table_name)

    def _filter_rows(self, table_name, filters):
        rows = self.tables.get(table_name, [])
        for column, value in filters:
            rows = [
                row for row in rows
                if row.get(column) == value
            ]
        return rows

    def _insert_row(self, table_name, payload):
        row = deepcopy(payload)

        if table_name == "users":
            for existing in self.tables[table_name]:
                if existing["telegram_user_id"] == row["telegram_user_id"]:
                    raise ValueError("duplicate telegram user")

        if table_name == "workspaces":
            owner_user_id = row.get("owner_user_id")
            if owner_user_id is not None and not any(
                existing["id"] == owner_user_id
                for existing in self.tables["users"]
            ):
                raise ValueError("owner user does not exist")

        if table_name == "workspace_members":
            if not any(
                existing["id"] == row["workspace_id"]
                for existing in self.tables["workspaces"]
            ):
                raise ValueError("workspace does not exist")
            if not any(
                existing["id"] == row["user_id"]
                for existing in self.tables["users"]
            ):
                raise ValueError("user does not exist")
            for existing in self.tables[table_name]:
                if (
                    existing["workspace_id"] == row["workspace_id"]
                    and existing["user_id"] == row["user_id"]
                ):
                    raise ValueError("duplicate membership")

        if table_name in self.next_ids and "id" not in row:
            row["id"] = self.next_ids[table_name]
            self.next_ids[table_name] += 1

        self.tables.setdefault(table_name, []).append(row)
        return deepcopy(row)

    def _update_rows(self, table_name, filters, payload):
        updated = []
        for row in self.tables.get(table_name, []):
            if all(row.get(column) == value for column, value in filters):
                row.update(deepcopy(payload))
                updated.append(deepcopy(row))
        return updated

    def _delete_rows(self, table_name, filters):
        deleted = []
        remaining = []
        for row in self.tables.get(table_name, []):
            if all(row.get(column) == value for column, value in filters):
                deleted.append(deepcopy(row))
            else:
                remaining.append(row)
        self.tables[table_name] = remaining
        return deleted

    def _upsert_rows(self, table_name, payload, on_conflict):
        payloads = payload
        if isinstance(payloads, dict):
            payloads = [payloads]

        rows = []
        for item in payloads:
            match = None
            for existing in self.tables.get(table_name, []):
                if existing.get(on_conflict) == item.get(on_conflict):
                    match = existing
                    break

            if match is None:
                rows.append(self._insert_row(table_name, item))
                continue

            match.update(deepcopy(item))
            rows.append(deepcopy(match))

        return rows


@pytest.fixture
def database_module(monkeypatch):
    fake_client = FakeSupabaseClient()
    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda url, key: fake_client

    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)

    sys.modules.pop("core.database", None)
    core_package = sys.modules.get("core")
    if core_package is not None and hasattr(core_package, "database"):
        delattr(core_package, "database")

    database = importlib.import_module("core.database")
    database = importlib.reload(database)
    return database, fake_client


def test_get_or_create_user_by_telegram_id_is_idempotent(database_module):
    database, fake_client = database_module

    created_user = database.get_or_create_user_by_telegram_id(1001)
    fetched_user = database.get_or_create_user_by_telegram_id(1001)

    assert created_user["telegram_user_id"] == 1001
    assert created_user["status"] == "active"
    assert fetched_user == created_user
    assert len(fake_client.tables["users"]) == 1


def test_create_workspace_owner_and_memberships(database_module):
    database, _ = database_module

    owner = database.get_or_create_user_by_telegram_id(2001)
    member = database.get_or_create_user_by_telegram_id(2002)

    workspace = database.create_workspace(
        name="News Desk",
        owner_user_id=owner["id"]
    )
    duplicate_owner = database.add_workspace_member(
        workspace_id=workspace["id"],
        user_id=owner["id"],
        role="owner",
        status="active"
    )
    second_member = database.add_workspace_member(
        workspace_id=workspace["id"],
        user_id=member["id"],
        role="writer"
    )

    owner_membership = database.get_workspace_member(
        workspace["id"],
        owner["id"]
    )
    members = database.list_workspace_members(workspace["id"])
    workspaces = database.list_user_workspaces(owner["id"])

    assert workspace["name"] == "News Desk"
    assert workspace["owner_user_id"] == owner["id"]
    assert owner_membership["role"] == "owner"
    assert owner_membership["status"] == "active"
    assert duplicate_owner["id"] == owner_membership["id"]
    assert second_member["role"] == "writer"
    assert [row["user_id"] for row in members] == [
        owner["id"],
        member["id"],
    ]
    assert workspaces[0]["id"] == workspace["id"]
    assert workspaces[0]["membership_role"] == "owner"


def test_workspace_member_role_and_status_lifecycle(database_module):
    database, _ = database_module

    owner = database.get_or_create_user_by_telegram_id(3001)
    member = database.get_or_create_user_by_telegram_id(3002)
    workspace = database.create_workspace(
        name="Editorial",
        owner_user_id=owner["id"]
    )
    database.add_workspace_member(
        workspace_id=workspace["id"],
        user_id=member["id"],
        role="writer"
    )

    promoted = database.update_workspace_member_role(
        workspace["id"],
        member["id"],
        "publisher"
    )
    suspended = database.update_workspace_member_status(
        workspace["id"],
        member["id"],
        "suspended"
    )
    reactivated = database.update_workspace_member_status(
        workspace["id"],
        member["id"],
        "active"
    )
    removed = database.update_workspace_member_status(
        workspace["id"],
        member["id"],
        "removed"
    )

    active_members = database.list_workspace_members(workspace["id"])
    all_members = database.list_workspace_members(
        workspace["id"],
        include_inactive=True
    )
    active_workspaces = database.list_user_workspaces(member["id"])
    all_workspaces = database.list_user_workspaces(
        member["id"],
        include_inactive=True
    )

    assert promoted["role"] == "publisher"
    assert suspended["status"] == "suspended"
    assert reactivated["status"] == "active"
    assert removed["status"] == "removed"
    assert [row["user_id"] for row in active_members] == [owner["id"]]
    assert len(all_members) == 2
    assert active_workspaces == []
    assert all_workspaces[0]["membership_status"] == "removed"


def test_memberships_support_multiple_users_and_workspaces(database_module):
    database, _ = database_module

    user_one = database.get_or_create_user_by_telegram_id(4001)
    user_two = database.get_or_create_user_by_telegram_id(4002)
    user_three = database.get_or_create_user_by_telegram_id(4003)

    workspace_one = database.create_workspace(
        name="Desk One",
        owner_user_id=user_one["id"]
    )
    workspace_two = database.create_workspace(
        name="Desk Two",
        owner_user_id=user_one["id"]
    )

    database.add_workspace_member(
        workspace_id=workspace_one["id"],
        user_id=user_two["id"],
        role="manager"
    )
    database.add_workspace_member(
        workspace_id=workspace_one["id"],
        user_id=user_three["id"],
        role="publisher"
    )
    database.add_workspace_member(
        workspace_id=workspace_two["id"],
        user_id=user_two["id"],
        role="writer"
    )

    user_two_workspaces = database.list_user_workspaces(user_two["id"])
    workspace_one_members = database.list_workspace_members(workspace_one["id"])

    assert [workspace["name"] for workspace in user_two_workspaces] == [
        "Desk One",
        "Desk Two",
    ]
    assert [row["user_id"] for row in workspace_one_members] == [
        user_one["id"],
        user_two["id"],
        user_three["id"],
    ]


def test_invalid_role_and_status_are_rejected(database_module):
    database, _ = database_module

    owner = database.get_or_create_user_by_telegram_id(5001)
    member = database.get_or_create_user_by_telegram_id(5002)
    workspace = database.create_workspace(
        name="Validation",
        owner_user_id=owner["id"]
    )

    with pytest.raises(ValueError, match="workspace member role"):
        database.add_workspace_member(
            workspace_id=workspace["id"],
            user_id=member["id"],
            role="admin"
        )

    with pytest.raises(ValueError, match="workspace member status"):
        database.add_workspace_member(
            workspace_id=workspace["id"],
            user_id=member["id"],
            status="pending"
        )

    database.add_workspace_member(
        workspace_id=workspace["id"],
        user_id=member["id"],
        role="writer"
    )

    with pytest.raises(ValueError, match="workspace member role"):
        database.update_workspace_member_role(
            workspace["id"],
            member["id"],
            "admin"
        )

    with pytest.raises(ValueError, match="workspace member status"):
        database.update_workspace_member_status(
            workspace["id"],
            member["id"],
            "pending"
        )


def test_get_tenant_behavior_is_unchanged(database_module):
    database, fake_client = database_module

    fake_client.tables["tenants"].append({
        "user_id": 9001,
        "telegram_channel": "@legacy-channel",
        "bale_channel": "@legacy-bale",
        "bot_token": "legacy-bot-token",
        "bale_token": "legacy-bale-token",
        "hashtag": "#legacy",
        "channel_tag": "@legacy",
    })

    tenant = database.get_tenant(9001)

    assert tenant == {
        "user_id": 9001,
        "telegram_channel": "@legacy-channel",
        "bale_channel": "@legacy-bale",
        "bot_token": "legacy-bot-token",
        "bale_token": "legacy-bale-token",
        "hashtag": "#legacy",
        "channel_tag": "@legacy",
    }
    assert fake_client.query_log[-1] == {
        "table": "tenants",
        "operation": "select",
        "filters": [("user_id", 9001)],
        "limit": 1,
        "select": "*",
        "on_conflict": None,
    }
