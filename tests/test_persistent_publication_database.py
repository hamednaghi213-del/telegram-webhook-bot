import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def select(self, value):
        self.calls.append(("select", value))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def upsert(self, payload, on_conflict=None):
        self.calls.append(
            ("upsert", payload, on_conflict)
        )
        return self

    def execute(self):
        self.calls.append(("execute",))
        return SimpleNamespace(data=self.rows)


class FakeServiceSupabase:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.tables = []
        self.query = None

    def table(self, name):
        self.tables.append(name)
        self.query = FakeQuery(self.rows)
        return self.query


@pytest.fixture
def db(monkeypatch):
    fake_client = FakeServiceSupabase()

    fake_supabase_module = types.ModuleType(
        "supabase"
    )
    fake_supabase_module.create_client = (
        lambda _url, _key: fake_client
    )

    monkeypatch.setitem(
        sys.modules,
        "supabase",
        fake_supabase_module,
    )

    monkeypatch.setenv(
        "SUPABASE_URL",
        "https://example.test",
    )
    monkeypatch.setenv(
        "SUPABASE_KEY",
        "test-anon-key",
    )
    monkeypatch.setenv(
        "SUPABASE_SERVICE_ROLE_KEY",
        "test-service-role-key",
    )

    sys.modules.pop("core.database", None)

    core_package = sys.modules.get("core")
    if core_package is not None:
        core_package.__dict__.pop(
            "database",
            None,
        )

    return importlib.import_module(
        "core.database"
    )


def test_get_persistent_publication_source(
    db,
    monkeypatch,
):
    row = {
        "id": 10,
        "source_key": "telegram:1:100",
    }

    fake = FakeServiceSupabase([row])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.get_persistent_publication_source(
            "telegram:1:100"
        )
    )

    assert result == row
    assert fake.tables == [
        "publication_sources"
    ]

    assert (
        "eq",
        "source_key",
        "telegram:1:100",
    ) in fake.query.calls


def test_ensure_persistent_publication_source(
    db,
    monkeypatch,
):
    row = {
        "id": 11,
        "source_key": "telegram:1:101",
    }

    fake = FakeServiceSupabase([row])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.ensure_persistent_publication_source(
            source_key="telegram:1:101",
            actor_user_id=7,
            source_kind="message",
            delivery_generation=1,
        )
    )

    assert result == row

    upsert_call = next(
        call
        for call in fake.query.calls
        if call[0] == "upsert"
    )

    _, payload, on_conflict = upsert_call

    assert payload == {
        "source_key": "telegram:1:101",
        "actor_user_id": 7,
        "source_kind": "message",
        "delivery_generation": 1,
    }

    assert on_conflict == "source_key"


def test_get_persistent_publication_delivery(
    db,
    monkeypatch,
):
    row = {
        "id": 20,
        "source_id": 11,
        "canonical_identity": (
            "telegram:external:farda_no"
        ),
    }

    fake = FakeServiceSupabase([row])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.get_persistent_publication_delivery(
            source_id=11,
            canonical_identity=(
                "telegram:external:farda_no"
            ),
            delivery_generation=1,
        )
    )

    assert result == row
    assert fake.tables == [
        "publication_deliveries"
    ]

    assert (
        "eq",
        "source_id",
        11,
    ) in fake.query.calls

    assert (
        "eq",
        "canonical_identity",
        "telegram:external:farda_no",
    ) in fake.query.calls


def test_ensure_persistent_publication_delivery(
    db,
    monkeypatch,
):
    row = {
        "id": 21,
        "source_id": 11,
        "canonical_identity": (
            "bale:external:farda_no"
        ),
    }

    fake = FakeServiceSupabase([row])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.ensure_persistent_publication_delivery(
            source_id=11,
            canonical_identity=(
                "bale:external:farda_no"
            ),
            platform="bale",
            destination_chat_id="@farda_no",
            workspace_id=4,
            destination_id=8,
            delivery_generation=1,
        )
    )

    assert result == row

    upsert_call = next(
        call
        for call in fake.query.calls
        if call[0] == "upsert"
    )

    _, payload, on_conflict = upsert_call

    assert payload == {
        "source_id": 11,
        "canonical_identity": (
            "bale:external:farda_no"
        ),
        "platform": "bale",
        "destination_chat_id": (
            "@farda_no"
        ),
        "workspace_id": 4,
        "destination_id": 8,
        "delivery_generation": 1,
    }

    assert on_conflict == (
        "source_id,"
        "canonical_identity,"
        "delivery_generation"
    )


def test_persistent_publication_requires_service_role(
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        db,
        "service_supabase",
        None,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Persistent publication state "
            "is not configured"
        ),
    ):
        db.get_persistent_publication_source(
            "telegram:1:999"
        )

def test_claim_persistent_publication_delivery(
    db,
    monkeypatch,
):
    row = {
        "claimed": True,
        "source_id": 11,
        "delivery_id": 21,
        "status": "sending",
        "attempt_count": 1,
        "lease_expires_at": (
            "2026-09-02T10:00:00+00:00"
        ),
    }

    class FakeRpc:
        def __init__(self):
            self.name = None
            self.params = None

        def rpc(self, name, params):
            self.name = name
            self.params = params
            return self

        def execute(self):
            return SimpleNamespace(
                data=[row]
            )

    fake = FakeRpc()

    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.claim_persistent_publication_delivery(
            source_key="telegram:1:101",
            canonical_identity=(
                "telegram:external:farda_no"
            ),
            platform="telegram",
            destination_chat_id="@farda_no",
            workspace_id=4,
            destination_id=8,
            delivery_generation=1,
            lease_owner="worker-test",
            lease_seconds=120,
        )
    )

    assert result == row

    assert fake.name == (
        "claim_publication_delivery"
    )

    assert fake.params == {
        "p_source_key": "telegram:1:101",
        "p_canonical_identity": (
            "telegram:external:farda_no"
        ),
        "p_platform": "telegram",
        "p_destination_chat_id": (
            "@farda_no"
        ),
        "p_workspace_id": 4,
        "p_destination_id": 8,
        "p_delivery_generation": 1,
        "p_lease_owner": "worker-test",
        "p_lease_seconds": 120,
    }

def test_record_persistent_publication_part_success(
    db,
    monkeypatch,
):
    class FakeQuery:
        def __init__(self):
            self.table_name = None
            self.payload = None
            self.on_conflict = None

        def table(self, name):
            self.table_name = name
            return self

        def upsert(
            self,
            payload,
            on_conflict=None,
        ):
            self.payload = payload
            self.on_conflict = on_conflict
            return self

        def execute(self):
            return SimpleNamespace(
                data=[self.payload]
            )

    fake = FakeQuery()

    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.record_persistent_publication_part_success(
            delivery_id=21,
            part_key="primary",
            message_id=501,
            message_ids=(501, 502, 503),
            destination_chat_id="@farda_no",
        )
    )

    assert fake.table_name == (
        "publication_delivery_parts"
    )

    assert fake.on_conflict == (
        "delivery_id,part_key"
    )

    assert result["delivery_id"] == 21
    assert result["part_key"] == "primary"
    assert result["status"] == "succeeded"
    assert result["message_id"] == 501

    assert result["message_ids"] == [
        501,
        502,
        503,
    ]

    assert result["destination_chat_id"] == (
        "@farda_no"
    )

    assert result["last_error"] is None
    assert result["lease_owner"] is None
    assert result["lease_expires_at"] is None

def test_get_persistent_publication_part(
    db,
    monkeypatch,
):
    row = {
        "id": 31,
        "delivery_id": 21,
        "part_key": "primary",
        "status": "succeeded",
        "message_id": 501,
        "message_ids": [501, 502],
        "destination_chat_id": "@farda_no",
    }

    class FakeQuery:
        def __init__(self):
            self.filters = {}

        def table(self, name):
            assert name == (
                "publication_delivery_parts"
            )
            return self

        def select(self, _columns):
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def limit(self, value):
            assert value == 1
            return self

        def execute(self):
            return SimpleNamespace(
                data=[row]
            )

    fake = FakeQuery()

    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = db.get_persistent_publication_part(
        delivery_id=21,
        part_key="primary",
    )

    assert result == row

    assert fake.filters == {
        "delivery_id": 21,
        "part_key": "primary",
    }

def test_mark_persistent_publication_delivery_succeeded(
    db,
    monkeypatch,
):
    class FakeQuery:
        def __init__(self):
            self.table_name = None
            self.payload = None
            self.filters = {}

        def table(self, name):
            self.table_name = name
            return self

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": self.filters["id"],
                        **self.payload,
                    }
                ]
            )

    fake = FakeQuery()

    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = (
        db.mark_persistent_publication_delivery_succeeded(
            delivery_id=21,
        )
    )

    assert fake.table_name == (
        "publication_deliveries"
    )

    assert fake.filters == {
        "id": 21,
    }

    assert fake.payload == {
        "status": "succeeded",
        "last_error": None,
        "lease_owner": None,
        "lease_expires_at": None,
    }

    assert result["id"] == 21
    assert result["status"] == "succeeded"
    assert result["last_error"] is None
    assert result["lease_owner"] is None
    assert result["lease_expires_at"] is None
