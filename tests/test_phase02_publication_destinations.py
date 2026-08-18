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
            "publication_destinations": [],
        }
        self.next_ids = {
            "users": 1,
            "workspaces": 1,
            "workspace_members": 1,
            "publication_destinations": 1,
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

    def _validate_publication_destination(self, row, current_id=None):
        if not any(
            existing["id"] == row["workspace_id"]
            for existing in self.tables["workspaces"]
        ):
            raise ValueError("workspace does not exist")

        if row.get("platform") not in {"telegram", "bale"}:
            raise ValueError("invalid platform")

        if row.get("destination_type") not in {"channel"}:
            raise ValueError("invalid destination_type")

        if row.get("status") not in {"active", "inactive", "removed"}:
            raise ValueError("invalid destination status")

        if row.get("is_default") and row.get("status") != "active":
            raise ValueError("default must be active")

        if row.get("status") != "removed":
            for existing in self.tables["publication_destinations"]:
                if existing["id"] == current_id:
                    continue
                if (
                    existing["workspace_id"] == row["workspace_id"]
                    and existing["platform"] == row["platform"]
                    and existing["external_id"] == row["external_id"]
                    and existing.get("status") != "removed"
                ):
                    raise ValueError("duplicate destination")

        if row.get("is_default") and row.get("status") == "active":
            for existing in self.tables["publication_destinations"]:
                if existing["id"] == current_id:
                    continue
                if (
                    existing["workspace_id"] == row["workspace_id"]
                    and existing.get("is_default")
                    and existing.get("status") == "active"
                ):
                    raise ValueError("duplicate active default")

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

        if table_name == "publication_destinations":
            self._validate_publication_destination(row)

        if table_name in self.next_ids and "id" not in row:
            row["id"] = self.next_ids[table_name]
            self.next_ids[table_name] += 1

        self.tables.setdefault(table_name, []).append(row)
        return deepcopy(row)

    def _update_rows(self, table_name, filters, payload):
        updated = []
        for row in self.tables.get(table_name, []):
            if all(row.get(column) == value for column, value in filters):
                updated_row = deepcopy(row)
                updated_row.update(deepcopy(payload))

                if table_name == "publication_destinations":
                    self._validate_publication_destination(
                        updated_row,
                        current_id=row.get("id")
                    )

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


def _create_workspace(database, telegram_user_id, name):
    owner = database.get_or_create_user_by_telegram_id(telegram_user_id)
    return database.create_workspace(name=name, owner_user_id=owner["id"])


def test_create_telegram_and_bale_destinations(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1001, "Desk")

    telegram_destination = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="TG Main",
        external_id="-10001"
    )
    bale_destination = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="bale",
        destination_type="channel",
        name="Bale Main",
        external_id="bale-01"
    )

    assert telegram_destination["platform"] == "telegram"
    assert bale_destination["platform"] == "bale"


def test_workspace_supports_multiple_and_100_plus_destinations(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1002, "Volume")

    for index in range(105):
        database.create_publication_destination(
            workspace_id=workspace["id"],
            platform="telegram",
            destination_type="channel",
            name=f"Destination {index}",
            external_id=f"ext-{index}"
        )

    destinations = database.list_workspace_destinations(workspace["id"])
    assert len(destinations) == 105


def test_duplicate_destination_is_idempotent_and_cross_workspace_allowed(database_module):
    database, _ = database_module
    workspace_one = _create_workspace(database, 1003, "One")
    workspace_two = _create_workspace(database, 1004, "Two")

    first = database.create_publication_destination(
        workspace_id=workspace_one["id"],
        platform="telegram",
        destination_type="channel",
        name="Desk One",
        external_id="same-external"
    )
    duplicate = database.create_publication_destination(
        workspace_id=workspace_one["id"],
        platform="telegram",
        destination_type="channel",
        name="Desk One Duplicate",
        external_id="same-external"
    )
    other_workspace = database.create_publication_destination(
        workspace_id=workspace_two["id"],
        platform="telegram",
        destination_type="channel",
        name="Desk Two",
        external_id="same-external"
    )

    assert duplicate["id"] == first["id"]
    assert other_workspace["id"] != first["id"]


def test_list_and_get_workspace_destinations(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1005, "List")

    destination = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="bale",
        destination_type="channel",
        name="Bale Desk",
        external_id="bale-list"
    )

    fetched = database.get_publication_destination(destination["id"])
    listed = database.list_workspace_destinations(workspace["id"])

    assert fetched["id"] == destination["id"]
    assert [row["id"] for row in listed] == [destination["id"]]


def test_update_destination_name_and_status_lifecycle(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1006, "Updates")

    destination = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="Original",
        external_id="updatable"
    )

    renamed = database.update_publication_destination(
        destination["id"],
        name="Renamed"
    )
    inactive = database.update_publication_destination_status(
        destination["id"],
        "inactive"
    )
    removed = database.update_publication_destination_status(
        destination["id"],
        "removed"
    )

    assert renamed["name"] == "Renamed"
    assert inactive["status"] == "inactive"
    assert removed["status"] == "removed"

    default_list = database.list_workspace_destinations(workspace["id"])
    all_list = database.list_workspace_destinations(
        workspace["id"],
        include_removed=True
    )

    assert default_list == []
    assert len(all_list) == 1
    assert all_list[0]["status"] == "removed"


def test_default_destination_set_change_and_get(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1007, "Defaults")
    other_workspace = _create_workspace(database, 1008, "Other")

    first = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="First",
        external_id="default-1"
    )
    second = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="Second",
        external_id="default-2"
    )
    foreign_destination = database.create_publication_destination(
        workspace_id=other_workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="Foreign",
        external_id="foreign-default"
    )

    database.set_default_publication_destination(workspace["id"], first["id"])
    first_default = database.get_default_publication_destination(workspace["id"])

    database.set_default_publication_destination(workspace["id"], second["id"])
    second_default = database.get_default_publication_destination(workspace["id"])

    first_after = database.get_publication_destination(first["id"])
    second_after = database.get_publication_destination(second["id"])

    assert first_default["id"] == first["id"]
    assert second_default["id"] == second["id"]
    assert first_after["is_default"] is False
    assert second_after["is_default"] is True

    with pytest.raises(ValueError, match="does not belong"):
        database.set_default_publication_destination(
            workspace["id"],
            foreign_destination["id"]
        )


def test_invalid_platform_status_and_orphan_workspace_are_rejected(database_module):
    database, _ = database_module
    workspace = _create_workspace(database, 1009, "Validation")

    with pytest.raises(ValueError, match="publication destination platform"):
        database.create_publication_destination(
            workspace_id=workspace["id"],
            platform="whatsapp",
            destination_type="channel",
            name="Invalid Platform",
            external_id="invalid-platform"
        )

    with pytest.raises(ValueError, match="publication destination status"):
        database.create_publication_destination(
            workspace_id=workspace["id"],
            platform="telegram",
            destination_type="channel",
            name="Invalid Status",
            external_id="invalid-status",
            status="paused"
        )

    destination = database.create_publication_destination(
        workspace_id=workspace["id"],
        platform="telegram",
        destination_type="channel",
        name="Valid",
        external_id="valid"
    )

    with pytest.raises(ValueError, match="publication destination status"):
        database.update_publication_destination_status(
            destination["id"],
            "paused"
        )

    with pytest.raises(ValueError, match="Workspace not found"):
        database.create_publication_destination(
            workspace_id=99999,
            platform="telegram",
            destination_type="channel",
            name="Orphan",
            external_id="orphan"
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
