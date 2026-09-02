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
