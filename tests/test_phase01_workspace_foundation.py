"""
tests/test_phase01_workspace_foundation.py

Unit tests for the Phase 0/1 Workspace Foundation helpers.

All Supabase I/O is mocked via unittest.mock so these tests run
without any real database connection.
"""

import sys
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(data):
    """Return a PostgRESTAPIResponse-like mock with .data set."""
    resp = MagicMock()
    resp.data = data
    return resp


def _make_chainable_client():
    """
    Return a MagicMock whose table/select/insert/… calls all return self,
    so call chains like client.table("x").select("*").eq("id", 1).execute()
    resolve to client.execute().
    """
    client = MagicMock()
    for attr in ("table", "select", "insert", "update", "upsert", "delete",
                 "eq", "neq", "limit"):
        getattr(client, attr).return_value = client
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Fresh chainable Supabase mock for each test."""
    return _make_chainable_client()


@pytest.fixture()
def db(client):
    """
    Load core.database with env vars set and supabase.client patched in-place.
    Returns the module object.
    """
    env = {"SUPABASE_URL": "https://mock.supabase.co", "SUPABASE_KEY": "mock-key"}
    for mod in list(sys.modules):
        if mod == "core.database" or mod == "core":
            del sys.modules[mod]
    with patch.dict("os.environ", env):
        with patch("supabase.create_client", return_value=client):
            import core.database as _db
    # Replace the live supabase client inside the loaded module
    _db.supabase = client
    return _db


# ===========================================================================
# get_or_create_user_by_telegram_id
# ===========================================================================

class TestGetOrCreateUserByTelegramId:

    def test_returns_existing_user(self, db, client):
        existing = {"id": 1, "telegram_id": 111, "first_name": "Ali"}
        client.execute.return_value = _make_response([existing])

        result = db.get_or_create_user_by_telegram_id(111, first_name="Ali")

        assert result == existing

    def test_creates_user_when_not_found(self, db, client):
        new_user = {"id": 2, "telegram_id": 222, "first_name": "Reza"}
        client.execute.side_effect = [
            _make_response([]),       # select → not found
            _make_response([new_user]),  # insert → created
        ]

        result = db.get_or_create_user_by_telegram_id(
            222, first_name="Reza", username="reza_t"
        )

        assert result == new_user

    def test_returns_user_without_optional_fields(self, db, client):
        user = {"id": 3, "telegram_id": 333}
        client.execute.return_value = _make_response([user])

        result = db.get_or_create_user_by_telegram_id(333)
        assert result["telegram_id"] == 333

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("DB error")
        with pytest.raises(Exception, match="DB error"):
            db.get_or_create_user_by_telegram_id(999)


# ===========================================================================
# create_workspace
# ===========================================================================

class TestCreateWorkspace:

    def test_creates_workspace_and_adds_owner_member(self, db, client):
        workspace_row = {"id": 10, "name": "News Room", "slug": "news-room", "owner_id": 1}
        member_row    = {"id": 1, "workspace_id": 10, "user_id": 1, "role": "owner"}
        client.execute.side_effect = [
            _make_response([workspace_row]),
            _make_response([member_row]),
        ]

        result = db.create_workspace(name="News Room", slug="news-room", owner_id=1)

        assert result == workspace_row

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("insert failed")
        with pytest.raises(Exception, match="insert failed"):
            db.create_workspace("X", "x", 1)


# ===========================================================================
# get_workspace
# ===========================================================================

class TestGetWorkspace:

    def test_returns_workspace(self, db, client):
        ws = {"id": 5, "name": "Sports", "slug": "sports", "owner_id": 2}
        client.execute.return_value = _make_response([ws])

        result = db.get_workspace(5)
        assert result == ws

    def test_returns_none_when_not_found(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.get_workspace(999) is None

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = RuntimeError("timeout")
        with pytest.raises(RuntimeError):
            db.get_workspace(1)


# ===========================================================================
# list_user_workspaces
# ===========================================================================

class TestListUserWorkspaces:

    def test_returns_active_memberships(self, db, client):
        rows = [
            {"id": 1, "workspace_id": 10, "user_id": 1, "status": "active"},
            {"id": 2, "workspace_id": 20, "user_id": 1, "status": "active"},
        ]
        client.execute.return_value = _make_response(rows)

        result = db.list_user_workspaces(1)
        assert len(result) == 2

    def test_returns_empty_list_when_none(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.list_user_workspaces(42) == []

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("oops")
        with pytest.raises(Exception):
            db.list_user_workspaces(1)


# ===========================================================================
# add_workspace_member
# ===========================================================================

class TestAddWorkspaceMember:

    def test_adds_member_with_defaults(self, db, client):
        member = {"id": 7, "workspace_id": 10, "user_id": 3, "role": "writer", "status": "active"}
        client.execute.return_value = _make_response([member])

        result = db.add_workspace_member(10, 3)
        assert result == member

    def test_adds_member_with_explicit_role_and_status(self, db, client):
        member = {"id": 8, "workspace_id": 10, "user_id": 4, "role": "publisher", "status": "active"}
        client.execute.return_value = _make_response([member])

        result = db.add_workspace_member(10, 4, role="publisher", status="active")
        assert result["role"] == "publisher"

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("unique violation")
        with pytest.raises(Exception):
            db.add_workspace_member(10, 3)


# ===========================================================================
# get_workspace_member
# ===========================================================================

class TestGetWorkspaceMember:

    def test_returns_member(self, db, client):
        member = {"id": 1, "workspace_id": 10, "user_id": 1, "role": "owner"}
        client.execute.return_value = _make_response([member])

        result = db.get_workspace_member(10, 1)
        assert result == member

    def test_returns_none_when_not_found(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.get_workspace_member(10, 99) is None

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("db down")
        with pytest.raises(Exception):
            db.get_workspace_member(1, 1)


# ===========================================================================
# list_workspace_members
# ===========================================================================

class TestListWorkspaceMembers:

    def test_returns_all_members(self, db, client):
        members = [
            {"id": 1, "workspace_id": 10, "user_id": 1, "role": "owner"},
            {"id": 2, "workspace_id": 10, "user_id": 2, "role": "writer"},
        ]
        client.execute.return_value = _make_response(members)

        result = db.list_workspace_members(10)
        assert len(result) == 2

    def test_returns_empty_list(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.list_workspace_members(10) == []

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("query failed")
        with pytest.raises(Exception):
            db.list_workspace_members(10)


# ===========================================================================
# update_workspace_member_role
# ===========================================================================

class TestUpdateWorkspaceMemberRole:

    @pytest.mark.parametrize("role", ["owner", "manager", "publisher", "writer"])
    def test_updates_to_valid_roles(self, db, client, role):
        client.execute.return_value = _make_response([{"id": 1, "role": role}])
        assert db.update_workspace_member_role(10, 1, role) is True

    def test_returns_false_when_no_row_updated(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.update_workspace_member_role(10, 99, "writer") is False

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("constraint error")
        with pytest.raises(Exception):
            db.update_workspace_member_role(10, 1, "invalid")


# ===========================================================================
# update_workspace_member_status
# ===========================================================================

class TestUpdateWorkspaceMemberStatus:

    @pytest.mark.parametrize("status", ["active", "suspended", "removed"])
    def test_updates_to_valid_statuses(self, db, client, status):
        client.execute.return_value = _make_response([{"id": 1, "status": status}])
        assert db.update_workspace_member_status(10, 1, status) is True

    def test_returns_false_when_no_row_updated(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.update_workspace_member_status(10, 99, "removed") is False

    def test_propagates_exception(self, db, client):
        client.execute.side_effect = Exception("timeout")
        with pytest.raises(Exception):
            db.update_workspace_member_status(10, 1, "active")


# ===========================================================================
# Backward-compatibility: get_tenant must still work
# ===========================================================================

class TestGetTenantBackwardCompatibility:

    def test_get_tenant_still_works(self, db, client):
        tenant = {"user_id": 42, "telegram_channel": "@test", "bot_token": "tok"}
        client.execute.return_value = _make_response([tenant])

        result = db.get_tenant(42)
        assert result == tenant

    def test_get_tenant_returns_none_when_missing(self, db, client):
        client.execute.return_value = _make_response([])
        assert db.get_tenant(9999) is None
