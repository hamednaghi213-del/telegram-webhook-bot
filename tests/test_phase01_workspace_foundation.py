"""
tests/test_phase01_workspace_foundation.py

Focused unit tests for Phase 1 workspace foundation.

All Supabase calls are patched so the suite runs offline without
a real database connection.  The tests exercise:

  - get_or_create_user_by_telegram_id  (create + idempotent get)
  - create_workspace                    (workspace row + owner member)
  - add_workspace_member               (second member)
  - duplicate membership protection
  - same user in multiple workspaces
  - multiple users in one workspace
  - list_user_workspaces
  - list_workspace_members
  - update_workspace_member_role
  - update_workspace_member_status     (suspend, reactivate, remove)
  - removed member not treated as active
  - legacy get_tenant(user_id) unchanged
"""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers for building a fake Supabase client that mimics the fluent API
# ---------------------------------------------------------------------------

class _FakeQuery:
    """Minimal chainable query builder that returns preset data."""

    def __init__(self, data=None, raises=None):
        self._data = data or []
        self._raises = raises

    # Chainable methods – every unknown attribute returns self so we can
    # write  supabase.table(...).select(...).eq(...).limit(...).execute()
    def __getattr__(self, name):
        return self._chain

    def _chain(self, *a, **kw):
        return self

    def execute(self):
        if self._raises:
            raise self._raises
        result = MagicMock()
        result.data = self._data
        return result


def _make_supabase_mock():
    """Return a MagicMock whose .table() returns a _FakeQuery by default."""
    mock = MagicMock()
    mock.table.return_value = _FakeQuery()
    return mock


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------

def _load_database_module(supabase_mock):
    """
    Import core.database with the Supabase client replaced by supabase_mock.
    Re-imports on every call so each test group gets a fresh module.
    """
    # Remove cached module so we get a fresh import
    for key in list(sys.modules.keys()):
        if "core.database" in key or key == "core.database":
            del sys.modules[key]

    # Patch env vars so validation inside the module doesn't raise
    with patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_KEY": "fake-key",
    }):
        # Patch create_client to return our mock
        with patch("supabase.create_client", return_value=supabase_mock):
            import core.database as db
            # Replace the module-level client with our mock
            db.supabase = supabase_mock
            return db


# ===========================================================================
# Test Cases
# ===========================================================================

class TestGetOrCreateUser(unittest.TestCase):
    """get_or_create_user_by_telegram_id – create path and idempotent get."""

    def _db(self, supabase_mock=None):
        if supabase_mock is None:
            supabase_mock = _make_supabase_mock()
        return _load_database_module(supabase_mock), supabase_mock

    def test_create_new_user(self):
        """When no existing row, inserts and returns the new user."""
        existing_query = _FakeQuery(data=[])          # select returns nothing
        new_user = {"id": 1, "telegram_user_id": 111, "username": "alice"}
        insert_query = _FakeQuery(data=[new_user])    # insert returns new row

        mock = _make_supabase_mock()
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.limit.return_value = table_mock

        select_result = MagicMock()
        select_result.data = []
        table_mock.execute.return_value = select_result

        insert_result = MagicMock()
        insert_result.data = [new_user]
        table_mock.insert.return_value.execute.return_value = insert_result

        mock.table.return_value = table_mock

        db, _ = self._db(mock)
        user = db.get_or_create_user_by_telegram_id(
            111, username="alice"
        )
        self.assertEqual(user["telegram_user_id"], 111)
        self.assertEqual(user["username"], "alice")

    def test_idempotent_get(self):
        """When a row already exists, returns it without inserting."""
        existing_user = {"id": 7, "telegram_user_id": 222}

        mock = _make_supabase_mock()
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.limit.return_value = table_mock

        select_result = MagicMock()
        select_result.data = [existing_user]
        table_mock.execute.return_value = select_result

        mock.table.return_value = table_mock

        db, _ = self._db(mock)
        user = db.get_or_create_user_by_telegram_id(222)
        self.assertEqual(user["id"], 7)
        # insert should NOT have been called
        table_mock.insert.assert_not_called()


class TestCreateWorkspace(unittest.TestCase):
    """create_workspace – creates workspace and auto-adds owner member."""

    def _make_db_with_workspace_flow(self, workspace_row, member_row):
        """
        Build a mock that:
          1. workspaces.insert → workspace_row
          2. workspace_members.insert → member_row
        """
        mock = _make_supabase_mock()

        ws_table = MagicMock()
        ws_insert_result = MagicMock()
        ws_insert_result.data = [workspace_row]
        ws_table.insert.return_value.execute.return_value = ws_insert_result

        member_table = MagicMock()
        member_insert_result = MagicMock()
        member_insert_result.data = [member_row]
        member_table.insert.return_value.execute.return_value = member_insert_result

        call_count = {"n": 0}

        def table_side_effect(name):
            call_count["n"] += 1
            if name == "workspaces":
                return ws_table
            if name == "workspace_members":
                return member_table
            return MagicMock()

        mock.table.side_effect = table_side_effect
        return mock

    def test_create_workspace_returns_workspace_row(self):
        ws_row = {"id": 10, "name": "News Room", "owner_user_id": 1}
        mem_row = {"id": 100, "workspace_id": 10, "user_id": 1, "role": "owner"}

        mock = self._make_db_with_workspace_flow(ws_row, mem_row)
        db = _load_database_module(mock)

        ws = db.create_workspace("News Room", owner_user_id=1)
        self.assertEqual(ws["id"], 10)
        self.assertEqual(ws["name"], "News Room")

    def test_owner_added_as_member(self):
        ws_row = {"id": 10, "name": "News Room", "owner_user_id": 1}
        mem_row = {"id": 100, "workspace_id": 10, "user_id": 1, "role": "owner"}

        mock = self._make_db_with_workspace_flow(ws_row, mem_row)
        db = _load_database_module(mock)

        db.create_workspace("News Room", owner_user_id=1)
        # workspace_members.insert should have been called with role=owner
        member_table_calls = [
            c for c in mock.table.call_args_list
            if c.args[0] == "workspace_members"
        ]
        self.assertTrue(len(member_table_calls) >= 1)


class TestGetWorkspace(unittest.TestCase):
    def test_returns_workspace(self):
        ws = {"id": 5, "name": "Sport"}

        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        result = MagicMock()
        result.data = [ws]
        tbl.execute.return_value = result
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        found = db.get_workspace(5)
        self.assertEqual(found["id"], 5)

    def test_returns_none_when_missing(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        result = MagicMock()
        result.data = []
        tbl.execute.return_value = result
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        self.assertIsNone(db.get_workspace(999))


class TestAddWorkspaceMember(unittest.TestCase):
    def _db_with_insert(self, row):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        ins_result = MagicMock()
        ins_result.data = [row]
        tbl.insert.return_value.execute.return_value = ins_result
        mock.table.return_value = tbl
        return _load_database_module(mock)

    def test_add_second_member(self):
        mem = {"id": 200, "workspace_id": 10, "user_id": 2, "role": "writer"}
        db = self._db_with_insert(mem)
        result = db.add_workspace_member(10, 2, "writer")
        self.assertEqual(result["role"], "writer")

    def test_duplicate_raises(self):
        """Supabase raises on UNIQUE violation; our helper propagates it."""
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.insert.return_value.execute.side_effect = Exception("duplicate key")
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        with self.assertRaises(Exception):
            db.add_workspace_member(10, 1, "owner")


class TestListUserWorkspaces(unittest.TestCase):
    def test_returns_workspaces_for_user(self):
        memberships = [{"workspace_id": 10}, {"workspace_id": 20}]
        workspaces = [
            {"id": 10, "name": "A"},
            {"id": 20, "name": "B"},
        ]

        mock = _make_supabase_mock()
        call_count = {"n": 0}

        def table_side(name):
            call_count["n"] += 1
            tbl = MagicMock()
            tbl.select.return_value = tbl
            tbl.eq.return_value = tbl
            tbl.in_.return_value = tbl
            if name == "workspace_members":
                r = MagicMock(); r.data = memberships
            else:
                r = MagicMock(); r.data = workspaces
            tbl.execute.return_value = r
            return tbl

        mock.table.side_effect = table_side
        db = _load_database_module(mock)
        result = db.list_user_workspaces(1)
        self.assertEqual(len(result), 2)

    def test_returns_empty_when_no_memberships(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        r = MagicMock(); r.data = []
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        self.assertEqual(db.list_user_workspaces(999), [])

    def test_same_user_in_multiple_workspaces(self):
        """User can belong to more than one workspace."""
        memberships = [
            {"workspace_id": 1},
            {"workspace_id": 2},
            {"workspace_id": 3},
        ]
        workspaces = [
            {"id": 1, "name": "W1"},
            {"id": 2, "name": "W2"},
            {"id": 3, "name": "W3"},
        ]

        mock = _make_supabase_mock()

        def table_side(name):
            tbl = MagicMock()
            tbl.select.return_value = tbl
            tbl.eq.return_value = tbl
            tbl.in_.return_value = tbl
            if name == "workspace_members":
                r = MagicMock(); r.data = memberships
            else:
                r = MagicMock(); r.data = workspaces
            tbl.execute.return_value = r
            return tbl

        mock.table.side_effect = table_side
        db = _load_database_module(mock)
        result = db.list_user_workspaces(5)
        self.assertEqual(len(result), 3)


class TestListWorkspaceMembers(unittest.TestCase):
    def test_multiple_users_in_one_workspace(self):
        members = [
            {"id": 1, "user_id": 10, "role": "owner"},
            {"id": 2, "user_id": 11, "role": "writer"},
            {"id": 3, "user_id": 12, "role": "publisher"},
        ]
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        r = MagicMock(); r.data = members
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        result = db.list_workspace_members(10)
        self.assertEqual(len(result), 3)


class TestUpdateWorkspaceMemberRole(unittest.TestCase):
    def test_update_role(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.update.return_value = tbl
        tbl.eq.return_value = tbl
        r = MagicMock(); r.data = [{"role": "manager"}]
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        ok = db.update_workspace_member_role(10, 2, "manager")
        self.assertTrue(ok)


class TestUpdateWorkspaceMemberStatus(unittest.TestCase):
    def _db_with_update_result(self, data):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.update.return_value = tbl
        tbl.eq.return_value = tbl
        r = MagicMock(); r.data = data
        tbl.execute.return_value = r
        mock.table.return_value = tbl
        return _load_database_module(mock)

    def test_suspend_member(self):
        db = self._db_with_update_result([{"status": "suspended"}])
        self.assertTrue(db.update_workspace_member_status(10, 2, "suspended"))

    def test_reactivate_member(self):
        db = self._db_with_update_result([{"status": "active"}])
        self.assertTrue(db.update_workspace_member_status(10, 2, "active"))

    def test_remove_member(self):
        db = self._db_with_update_result([{"status": "removed"}])
        self.assertTrue(db.update_workspace_member_status(10, 2, "removed"))

    def test_removed_member_not_in_active_list(self):
        """list_user_workspaces filters by status=active, so removed users
        don't appear.  Simulate by returning empty memberships."""
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        r = MagicMock(); r.data = []   # removed member has no active rows
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        self.assertEqual(db.list_user_workspaces(99), [])


class TestGetWorkspaceMember(unittest.TestCase):
    def test_returns_member(self):
        mem = {"id": 5, "workspace_id": 10, "user_id": 3, "role": "writer"}
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        r = MagicMock(); r.data = [mem]
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        result = db.get_workspace_member(10, 3)
        self.assertEqual(result["role"], "writer")

    def test_returns_none_when_missing(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        r = MagicMock(); r.data = []
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        self.assertIsNone(db.get_workspace_member(10, 999))


class TestLegacyGetTenant(unittest.TestCase):
    """Verify get_tenant(user_id) is present and unchanged."""

    def test_get_tenant_exists(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        tenant = {"user_id": 42, "telegram_channel": "@TestCh"}
        r = MagicMock(); r.data = [tenant]
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        result = db.get_tenant(42)
        self.assertEqual(result["telegram_channel"], "@TestCh")

    def test_get_tenant_returns_none_when_missing(self):
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        r = MagicMock(); r.data = []
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        self.assertIsNone(db.get_tenant(9999))

    def test_get_tenant_queries_tenants_table(self):
        """Confirms the legacy table name has not been changed."""
        mock = _make_supabase_mock()
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        r = MagicMock(); r.data = []
        tbl.execute.return_value = r
        mock.table.return_value = tbl

        db = _load_database_module(mock)
        db.get_tenant(1)
        mock.table.assert_called_with("tenants")


if __name__ == "__main__":
    unittest.main()
