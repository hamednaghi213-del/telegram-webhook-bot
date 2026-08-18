"""
tests/test_phase01_workspace_foundation.py

Phase 0/1 focused test suite.

All workspace functions are exercised against a FakeSupabase in-memory
store so no live database connection is required.  The legacy
get_tenant() path is verified to remain functionally unchanged.
"""

from __future__ import annotations

import sys
import types
import uuid
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# FakeSupabase — in-memory Supabase query-builder shim
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    """Chainable query builder that operates on a list of dicts."""

    def __init__(self, rows: list, store: "_FakeTable"):
        self._rows = list(rows)          # working copy
        self._store = store              # reference to mutate on execute
        self._op: str = "select"
        self._filters: list = []
        self._limit_val: Optional[int] = None
        self._update_payload: Optional[dict] = None
        self._insert_payload: Optional[dict] = None
        self._in_field: Optional[str] = None
        self._in_values: Optional[list] = None

    # --- filter helpers ---

    def select(self, *args):
        self._op = "select"
        return self

    def eq(self, field, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self._in_field = field
        self._in_values = list(values)
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    # --- mutation helpers ---

    def insert(self, payload):
        self._op = "insert"
        self._insert_payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._update_payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._insert_payload = payload
        self._on_conflict = on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    # --- execution ---

    def _apply_filters(self, rows):
        result = rows
        for (op, field, value) in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(field) == value]
        if self._in_field is not None:
            result = [
                r for r in result
                if r.get(self._in_field) in self._in_values
            ]
        if self._limit_val is not None:
            result = result[: self._limit_val]
        return result

    def execute(self):
        rows = self._store.rows

        if self._op == "select":
            matched = self._apply_filters(rows)
            return _Response(deepcopy(matched))

        if self._op == "insert":
            row = deepcopy(self._insert_payload)
            if "id" not in row or row["id"] is None:
                row["id"] = str(uuid.uuid4())
            # enforce unique composite constraint if defined
            unique_fields = self._store._unique_fields
            if unique_fields:
                for existing in self._store.rows:
                    if all(existing.get(f) == row.get(f) for f in unique_fields):
                        raise Exception(
                            f"duplicate key violates unique constraint on "
                            f"{unique_fields}"
                        )
            rows.append(row)
            return _Response([deepcopy(row)])

        if self._op == "update":
            matched = self._apply_filters(rows)
            for row in matched:
                row.update(self._update_payload)
            return _Response(deepcopy(matched))

        if self._op == "upsert":
            conflict = getattr(self, "_on_conflict", None)
            row = deepcopy(self._insert_payload)
            if "id" not in row or row["id"] is None:
                row["id"] = str(uuid.uuid4())
            if conflict:
                existing = [
                    r for r in rows
                    if r.get(conflict) == row.get(conflict)
                ]
                if existing:
                    existing[0].update(row)
                    return _Response([deepcopy(existing[0])])
            rows.append(row)
            return _Response([deepcopy(row)])

        if self._op == "delete":
            matched = self._apply_filters(rows)
            for row in matched:
                rows.remove(row)
            return _Response(deepcopy(matched))

        return _Response([])


class _FakeTable:
    def __init__(self, unique_fields: tuple = ()):
        self.rows: List[Dict[str, Any]] = []
        self._unique_fields = unique_fields  # tuple of field names for composite unique

    def select(self, *args):
        return _Query(self.rows, self).select(*args)

    def insert(self, payload):
        return _Query(self.rows, self).insert(payload)

    def update(self, payload):
        return _Query(self.rows, self).update(payload)

    def upsert(self, payload, on_conflict=None):
        return _Query(self.rows, self).upsert(payload, on_conflict=on_conflict)

    def delete(self):
        return _Query(self.rows, self).delete()

    def eq(self, field, value):
        return _Query(self.rows, self).eq(field, value)


class FakeSupabase:
    """In-memory Supabase replacement for unit tests."""

    def __init__(self):
        self._tables: Dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        if name not in self._tables:
            unique_fields: tuple = ()
            if name == "ws_workspace_members":
                unique_fields = ("workspace_id", "user_id")
            elif name == "ws_users":
                unique_fields = ("telegram_id",)
            self._tables[name] = _FakeTable(unique_fields=unique_fields)
        return self._tables[name]

    def reset(self):
        self._tables.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_fake_sb = FakeSupabase()


@pytest.fixture(autouse=True)
def _reset_store():
    """Wipe all in-memory tables before each test."""
    _fake_sb.reset()
    yield


@pytest.fixture
def db():
    """
    Return the core.database module with supabase replaced by FakeSupabase.
    Always loads the real module from disk, bypassing any module-level fakes
    installed by other integration tests.
    """
    import importlib
    import os

    os.environ.setdefault("SUPABASE_URL", "http://fake")
    os.environ.setdefault("SUPABASE_KEY", "fake-key")

    # Temporarily clear the cached entry so importlib loads from disk.
    cached = sys.modules.pop("core.database", None)
    try:
        with patch("supabase.create_client", return_value=_fake_sb):
            real_db = importlib.import_module("core.database")
        real_db.supabase = _fake_sb
        yield real_db
    finally:
        # Restore whatever was in sys.modules before (may be a fake module
        # installed by another test or the real module we just loaded).
        if cached is not None:
            sys.modules["core.database"] = cached
        else:
            sys.modules.pop("core.database", None)


# ---------------------------------------------------------------------------
# Helper: build a user row the way the fake DB would
# ---------------------------------------------------------------------------

def _make_user(db, telegram_id, **kwargs):
    return db.get_or_create_user_by_telegram_id(telegram_id, **kwargs)


def _make_workspace(db, name, owner_user_id):
    return db.create_workspace(name=name, owner_user_id=owner_user_id)


# ===========================================================================
# TEST CASES
# ===========================================================================

# 1. Create user from Telegram user_id
def test_create_user_from_telegram_id(db):
    user = _make_user(db, 111111)
    assert user["telegram_id"] == 111111
    assert "id" in user
    assert user["id"] is not None


# 2. get_or_create user is idempotent
def test_get_or_create_user_idempotent(db):
    u1 = _make_user(db, 222222, first_name="Alice")
    u2 = _make_user(db, 222222, first_name="Alice Updated")
    assert u1["id"] == u2["id"]
    # Only one row should exist
    rows = _fake_sb.table("ws_users").select("*").execute().data
    assert len(rows) == 1


# 3. Create workspace
def test_create_workspace(db):
    owner = _make_user(db, 300000)
    ws = _make_workspace(db, "News Room", owner["id"])
    assert ws["name"] == "News Room"
    assert ws["owner_user_id"] == owner["id"]
    assert ws["status"] == "active"


# 4. Owner membership auto-created on workspace creation
def test_owner_membership_created_on_workspace_creation(db):
    owner = _make_user(db, 400000)
    ws = _make_workspace(db, "Alpha", owner["id"])
    member = db.get_workspace_member(ws["id"], owner["id"])
    assert member is not None
    assert member["role"] == "owner"
    assert member["status"] == "active"


# 5. Add second member
def test_add_second_member(db):
    owner = _make_user(db, 500000)
    writer = _make_user(db, 500001)
    ws = _make_workspace(db, "Beta", owner["id"])
    db.add_workspace_member(ws["id"], writer["id"], role="writer")
    member = db.get_workspace_member(ws["id"], writer["id"])
    assert member is not None
    assert member["role"] == "writer"


# 6. Duplicate membership protection
def test_duplicate_membership_raises(db):
    owner = _make_user(db, 600000)
    ws = _make_workspace(db, "Gamma", owner["id"])
    # Owner is already a member; inserting again must fail (unique constraint)
    with pytest.raises(Exception):
        db.add_workspace_member(ws["id"], owner["id"], role="writer")


# 7. Same user in multiple workspaces
def test_same_user_in_multiple_workspaces(db):
    owner = _make_user(db, 700000)
    ws1 = _make_workspace(db, "WS-1", owner["id"])
    ws2 = _make_workspace(db, "WS-2", owner["id"])
    workspaces = db.list_user_workspaces(owner["id"])
    ws_ids = {w["id"] for w in workspaces}
    assert ws1["id"] in ws_ids
    assert ws2["id"] in ws_ids


# 8. Multiple users in one workspace
def test_multiple_users_in_one_workspace(db):
    owner = _make_user(db, 800000)
    u1 = _make_user(db, 800001)
    u2 = _make_user(db, 800002)
    ws = _make_workspace(db, "Delta", owner["id"])
    db.add_workspace_member(ws["id"], u1["id"], role="manager")
    db.add_workspace_member(ws["id"], u2["id"], role="publisher")
    members = db.list_workspace_members(ws["id"])
    user_ids = {m["user_id"] for m in members}
    assert owner["id"] in user_ids
    assert u1["id"] in user_ids
    assert u2["id"] in user_ids


# 9. List user workspaces
def test_list_user_workspaces(db):
    owner = _make_user(db, 900000)
    _make_workspace(db, "WS-A", owner["id"])
    _make_workspace(db, "WS-B", owner["id"])
    workspaces = db.list_user_workspaces(owner["id"])
    assert len(workspaces) >= 2


# 10. List workspace members
def test_list_workspace_members(db):
    owner = _make_user(db, 1000000)
    extra = _make_user(db, 1000001)
    ws = _make_workspace(db, "Epsilon", owner["id"])
    db.add_workspace_member(ws["id"], extra["id"], role="writer")
    members = db.list_workspace_members(ws["id"])
    assert len(members) == 2


# 11. Update role
def test_update_member_role(db):
    owner = _make_user(db, 1100000)
    writer = _make_user(db, 1100001)
    ws = _make_workspace(db, "Zeta", owner["id"])
    db.add_workspace_member(ws["id"], writer["id"], role="writer")
    updated = db.update_workspace_member_role(ws["id"], writer["id"], "manager")
    assert updated["role"] == "manager"


# 12. Suspend member
def test_suspend_member(db):
    owner = _make_user(db, 1200000)
    u = _make_user(db, 1200001)
    ws = _make_workspace(db, "Eta", owner["id"])
    db.add_workspace_member(ws["id"], u["id"], role="writer")
    db.update_workspace_member_status(ws["id"], u["id"], "suspended")
    member = db.get_workspace_member(ws["id"], u["id"])
    assert member["status"] == "suspended"


# 13. Reactivate member
def test_reactivate_member(db):
    owner = _make_user(db, 1300000)
    u = _make_user(db, 1300001)
    ws = _make_workspace(db, "Theta", owner["id"])
    db.add_workspace_member(ws["id"], u["id"], role="writer")
    db.update_workspace_member_status(ws["id"], u["id"], "suspended")
    db.update_workspace_member_status(ws["id"], u["id"], "active")
    member = db.get_workspace_member(ws["id"], u["id"])
    assert member["status"] == "active"


# 14. Removed member not active
def test_removed_member_not_active(db):
    owner = _make_user(db, 1400000)
    u = _make_user(db, 1400001)
    ws = _make_workspace(db, "Iota", owner["id"])
    db.add_workspace_member(ws["id"], u["id"], role="writer")
    db.update_workspace_member_status(ws["id"], u["id"], "removed")
    # list_user_workspaces only returns active memberships
    user_workspaces = db.list_user_workspaces(u["id"])
    ws_ids = {w["id"] for w in user_workspaces}
    assert ws["id"] not in ws_ids


# 15. Legacy get_tenant(user_id) unchanged
def test_legacy_get_tenant_unchanged(db):
    """
    Verify that get_tenant still queries the 'tenants' table by user_id
    and returns the row if found, exactly as before Phase 1 changes.
    """
    # Seed a fake tenant row
    tenant_row = {
        "id": str(uuid.uuid4()),
        "user_id": 9999,
        "bot_token": "tok",
        "telegram_channel": "@TestChan",
        "bale_channel": "",
        "bale_token": "",
        "hashtag": "#hash",
        "channel_tag": "@tag",
    }
    _fake_sb.table("tenants").insert(tenant_row).execute()

    result = db.get_tenant(9999)
    assert result is not None
    assert result["telegram_channel"] == "@TestChan"
    assert result["user_id"] == 9999

    # Non-existent user returns None
    assert db.get_tenant(0) is None


# ---------------------------------------------------------------------------
# Validation guard: invalid role/status values
# ---------------------------------------------------------------------------

def test_invalid_role_rejected(db):
    owner = _make_user(db, 9000000)
    ws = _make_workspace(db, "Kappa", owner["id"])
    u = _make_user(db, 9000001)
    with pytest.raises(ValueError, match="Invalid role"):
        db.add_workspace_member(ws["id"], u["id"], role="superadmin")


def test_invalid_status_rejected(db):
    owner = _make_user(db, 9100000)
    u = _make_user(db, 9100001)
    ws = _make_workspace(db, "Lambda", owner["id"])
    db.add_workspace_member(ws["id"], u["id"], role="writer")
    with pytest.raises(ValueError, match="Invalid status"):
        db.update_workspace_member_status(ws["id"], u["id"], "banned")


def test_get_workspace_returns_none_for_unknown(db):
    result = db.get_workspace(str(uuid.uuid4()))
    assert result is None


def test_get_workspace_member_returns_none_for_unknown(db):
    owner = _make_user(db, 9200000)
    ws = _make_workspace(db, "Mu", owner["id"])
    result = db.get_workspace_member(ws["id"], str(uuid.uuid4()))
    assert result is None
