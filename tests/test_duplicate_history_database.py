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

    def order(self, column, desc=False):
        self.calls.append(("order", column, desc))
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

    fake_supabase_module = types.ModuleType("supabase")
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

    module = importlib.import_module(
        "core.database"
    )

    return module


def test_get_recent_duplicate_news_reads_only_requested_media(
    db,
    monkeypatch,
):
    rows = [
        {
            "id": 1,
            "media_identity_id": 7,
            "source_key": "source-1",
            "content_text": "خبر آزمایشی",
            "normalized_text": "خبر آزمایشی",
            "fingerprint": "abc",
            "published_at": "2026-09-02T00:00:00Z",
        }
    ]

    fake = FakeServiceSupabase(rows)
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = db.get_recent_duplicate_news(
        media_identity_id=7,
        limit=25,
    )

    assert result == rows
    assert fake.tables == [
        "duplicate_news_history"
    ]

    assert (
        "eq",
        "media_identity_id",
        7,
    ) in fake.query.calls

    assert (
        "order",
        "published_at",
        True,
    ) in fake.query.calls

    assert ("limit", 25) in fake.query.calls


def test_get_recent_duplicate_news_clamps_limit(
    db,
    monkeypatch,
):
    fake = FakeServiceSupabase([])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    db.get_recent_duplicate_news(
        media_identity_id=3,
        limit=9999,
    )

    assert ("limit", 200) in fake.query.calls


def test_record_duplicate_news_history_uses_logical_source_identity(
    db,
    monkeypatch,
):
    returned = {
        "id": 10,
        "media_identity_id": 4,
        "actor_user_id": 8,
        "source_key": "telegram:123:456",
        "content_text": "متن خبر",
        "normalized_text": "متن خبر",
        "fingerprint": "fingerprint-value",
    }

    fake = FakeServiceSupabase([returned])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = db.record_duplicate_news_history(
        media_identity_id=4,
        actor_user_id=8,
        source_key="telegram:123:456",
        content_text="متن خبر",
        normalized_text="متن خبر",
        fingerprint="fingerprint-value",
    )

    assert result == returned
    assert fake.tables == [
        "duplicate_news_history"
    ]

    upsert_calls = [
        call
        for call in fake.query.calls
        if call[0] == "upsert"
    ]

    assert len(upsert_calls) == 1

    _, payload, on_conflict = (
        upsert_calls[0]
    )

    assert payload == {
        "media_identity_id": 4,
        "actor_user_id": 8,
        "source_key": "telegram:123:456",
        "content_text": "متن خبر",
        "normalized_text": "متن خبر",
        "fingerprint": "fingerprint-value",
    }

    assert (
        on_conflict
        == "media_identity_id,source_key"
    )


def test_record_duplicate_news_history_accepts_missing_actor(
    db,
    monkeypatch,
):
    fake = FakeServiceSupabase(
        [
            {
                "id": 11,
                "media_identity_id": 5,
                "actor_user_id": None,
            }
        ]
    )

    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = db.record_duplicate_news_history(
        media_identity_id=5,
        actor_user_id=None,
        source_key="source-x",
        content_text="خبر",
        normalized_text="خبر",
        fingerprint="fp",
    )

    assert result is not None

    upsert_call = next(
        call
        for call in fake.query.calls
        if call[0] == "upsert"
    )

    payload = upsert_call[1]

    assert (
        payload["actor_user_id"]
        is None
    )


def test_record_duplicate_news_history_returns_none_without_row(
    db,
    monkeypatch,
):
    fake = FakeServiceSupabase([])
    monkeypatch.setattr(
        db,
        "service_supabase",
        fake,
    )

    result = db.record_duplicate_news_history(
        media_identity_id=6,
        actor_user_id=2,
        source_key="source-empty",
        content_text="خبر",
        normalized_text="خبر",
        fingerprint="fp",
    )

    assert result is None
