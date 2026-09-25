"""Database-level coverage for canonical Add Channel registration."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = []
        self.action = "select"
        self.payload = None
        self.maximum = None

    def select(self, _columns):
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def neq(self, key, value):
        self.filters.append(("neq", key, value))
        return self

    def is_(self, key, value):
        self.filters.append(("is", key, value))
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.action, self.payload = "upsert", payload
        assert on_conflict in {
            "workspace_id,destination_id",
            "media_identity_id,user_id",
        }
        return self

    def execute(self):
        rows = self.client.rows[self.table]
        matching = [
            row for row in rows
            if all(
                (
                    row.get(key) == value
                    if op == "eq"
                    else row.get(key) != value
                    if op == "neq"
                    else row.get(key) is None
                )
                for op, key, value in self.filters
            )
        ]

        if self.action == "select":
            selected = matching
            if self.maximum is not None:
                selected = selected[:self.maximum]
            return types.SimpleNamespace(
                data=[dict(row) for row in selected]
            )

        if self.action == "insert":
            payload = dict(self.payload)

            if self.table == "publication_destinations":
                if self.client.racing_row is not None:
                    rows.append(self.client.racing_row)
                    self.client.racing_row = None
                    raise RuntimeError(
                        "duplicate key value violates unique constraint"
                    )

                for row in rows:
                    if (
                        row["platform"],
                        row.get("normalized_external_id"),
                    ) == (
                        payload["platform"],
                        payload.get("normalized_external_id"),
                    ) and row["status"] != "removed":
                        raise RuntimeError(
                            "duplicate key value violates unique constraint"
                        )

            payload.setdefault("id", len(rows) + 1)
            rows.append(payload)
            return types.SimpleNamespace(data=[dict(payload)])

        if self.action == "update":
            for row in matching:
                row.update(self.payload)
            return types.SimpleNamespace(
                data=[dict(row) for row in matching]
            )

        if self.action == "upsert":
            payload = dict(self.payload)

            if self.table == "media_identity_members":
                existing = next(
                    (
                        row
                        for row in rows
                        if row["media_identity_id"]
                        == payload["media_identity_id"]
                        and row["user_id"] == payload["user_id"]
                    ),
                    None,
                )
                if existing:
                    existing.update(payload)
                else:
                    rows.append(payload)
                return types.SimpleNamespace(data=[dict(payload)])

            if any(
                row["destination_id"] == payload["destination_id"]
                and row["workspace_id"] != payload["workspace_id"]
                and row["status"] == "active"
                for row in rows
            ):
                raise RuntimeError(
                    "destination already has an active workspace"
                )

            existing = next(
                (
                    row
                    for row in rows
                    if row["destination_id"] == payload["destination_id"]
                    and row["workspace_id"] == payload["workspace_id"]
                ),
                None,
            )
            if existing:
                existing.update(payload)
            else:
                rows.append(payload)

            return types.SimpleNamespace(data=[dict(payload)])

        raise AssertionError(self.action)


class Client:
    def __init__(self):
        self.rows = {
            "publication_destinations": [],
            "workspace_destinations": [],
            "media_identities": [],
            "media_identity_members": [],
        }
        self.racing_row = None

    def table(self, name):
        return Query(self, name)


@pytest.fixture
def database(monkeypatch):
    client = Client()

    fake_supabase = types.ModuleType("supabase")
    fake_supabase.create_client = lambda *_args: client
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)

    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    path = Path(__file__).resolve().parents[1] / "core" / "database.py"
    spec = importlib.util.spec_from_file_location(
        "add_channel_database_under_test",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        module,
        "get_workspace",
        lambda wid: {"id": wid, "owner_user_id": wid},
    )
    monkeypatch.setattr(module, "service_supabase", client)

    return module, client


def test_global_canonical_creation_idempotence_and_platform_separation(database):
    module, client = database

    telegram, outcome = module.register_setup_destination_canonical(
        1, "telegram", "@MyChannel", "Telegram"
    )
    repeated, repeated_outcome = module.register_setup_destination_canonical(
        1, "telegram", "@mychannel", "Telegram"
    )
    bale, bale_outcome = module.register_setup_destination_canonical(
        1, "bale", "@MyChannel", "Bale"
    )

    assert (outcome, repeated_outcome, bale_outcome) == (
        "associated", "same_workspace", "associated"
    )
    assert telegram["normalized_external_id"] == "mychannel"
    assert bale["normalized_external_id"] == "mychannel"
    assert repeated["id"] == telegram["id"] != bale["id"]
    assert len(client.rows["publication_destinations"]) == 2

    assert telegram["media_identity_id"] is not None
    assert bale["media_identity_id"] == telegram["media_identity_id"]
    assert len(client.rows["media_identities"]) == 1
    assert client.rows["media_identities"][0]["identity_key"] == "workspace:1"

    assert len(client.rows["media_identity_members"]) == 1
    owner = client.rows["media_identity_members"][0]
    assert owner["media_identity_id"] == telegram["media_identity_id"]
    assert owner["user_id"] == 1
    assert owner["role"] == "owner"
    assert owner["status"] == "active"


def test_unassociated_destination_keeps_media_identity_and_other_owner_rejected(
    database,
):
    module, client = database

    client.rows["publication_destinations"].append({
        "id": 7,
        "workspace_id": 1,
        "platform": "telegram",
        "external_id": "@Existing",
        "normalized_external_id": "existing",
        "media_identity_id": 45,
        "status": "inactive",
    })

    destination, outcome = module.register_setup_destination_canonical(
        2, "telegram", "@EXISTING", "Other name"
    )
    assert outcome == "associated"
    assert destination["id"] == 7
    assert destination["media_identity_id"] == 45

    _, rejected = module.register_setup_destination_canonical(
        3, "telegram", "@existing", "Other name"
    )
    assert rejected == "owned_elsewhere"
    assert client.rows["workspace_destinations"] == [{
        "workspace_id": 2,
        "destination_id": 7,
        "status": "active",
        "updated_at": client.rows["workspace_destinations"][0]["updated_at"],
    }]



def test_same_workspace_reregistration_repairs_wrong_media_identity(database):
    module, client = database

    client.rows["publication_destinations"].append({
        "id": 24,
        "workspace_id": 28,
        "platform": "bale",
        "external_id": "@khatehmarzi",
        "normalized_external_id": "khatehmarzi",
        "media_identity_id": 7,
        "status": "inactive",
    })
    client.rows["workspace_destinations"].append({
        "workspace_id": 28,
        "destination_id": 24,
        "status": "active",
    })

    repaired, outcome = module.register_setup_destination_canonical(
        28,
        "bale",
        "@KHATEHMARZI",
        "@khatehmarzi",
    )

    assert outcome == "same_workspace"
    assert repaired["id"] == 24

    canonical = next(
        row
        for row in client.rows["media_identities"]
        if row["identity_key"] == "workspace:28"
    )

    assert repaired["media_identity_id"] == canonical["id"]
    assert (
        client.rows["publication_destinations"][0]["media_identity_id"]
        == canonical["id"]
    )
    assert canonical["id"] != 7

    assert client.rows["workspace_destinations"] == [{
        "workspace_id": 28,
        "destination_id": 24,
        "status": "active",
    }]



def test_legacy_null_identity_and_competing_insert_do_not_duplicate(database):
    module, client = database

    client.rows["publication_destinations"].append({
        "id": 8,
        "workspace_id": 1,
        "platform": "bale",
        "external_id": "@Old",
        "normalized_external_id": None,
        "media_identity_id": 55,
        "status": "inactive",
    })

    reused, outcome = module.register_setup_destination_canonical(
        1, "bale", "@OLD", "Old"
    )
    assert outcome == "associated" and reused["id"] == 8
    assert (
        client.rows["publication_destinations"][0]["normalized_external_id"]
        == "old"
    )

    client.racing_row = {
        "id": 9,
        "workspace_id": 2,
        "platform": "telegram",
        "external_id": "@Race",
        "normalized_external_id": "race",
        "media_identity_id": None,
        "status": "inactive",
    }

    raced, race_outcome = module.register_setup_destination_canonical(
        2, "telegram", "@RACE", "Race"
    )

    assert raced["id"] == 9
    assert race_outcome == "associated"
    assert raced["media_identity_id"] is not None
    assert len(client.rows["publication_destinations"]) == 2
