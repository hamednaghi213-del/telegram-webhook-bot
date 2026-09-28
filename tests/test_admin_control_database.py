import importlib
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def _load_database():
    existing = sys.modules.get("core.database")
    if existing is not None:
        return existing

    original_supabase = sys.modules.get("supabase")
    fake_supabase = type(sys)("supabase")
    fake_supabase.create_client = lambda _url, _key: object()
    sys.modules["supabase"] = fake_supabase

    try:
        return importlib.import_module("core.database")
    finally:
        if original_supabase is not None:
            sys.modules["supabase"] = original_supabase
        else:
            sys.modules.pop("supabase", None)


db = _load_database()


class FakeQuery:
    def __init__(self, data=None):
        self.data = data or []
        self.payload = None
        self.filters = []
        self.on_conflict = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, value):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeSupabase:
    def __init__(self):
        self.tables = {}
        self.last_table = None

    def table(self, name):
        self.last_table = name
        return self.tables.setdefault(name, FakeQuery())


def test_get_admin_destination_control(monkeypatch):
    fake = FakeSupabase()
    fake.tables["admin_destination_controls"] = FakeQuery(
        [{"destination_id": 10, "admin_state": "paused"}]
    )
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.get_admin_destination_control(10)

    assert result["destination_id"] == 10
    assert result["admin_state"] == "paused"


def test_upsert_admin_destination_control(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([{"destination_id": 10, "admin_state": "blocked"}])
    fake.tables["admin_destination_controls"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.upsert_admin_destination_control(
        10,
        "blocked",
        reason="manual block",
        changed_by_platform="telegram",
        changed_by_external_user_id=123,
    )

    assert result["admin_state"] == "blocked"
    assert query.payload["destination_id"] == 10
    assert query.payload["admin_state"] == "blocked"
    assert query.payload["reason"] == "manual block"
    assert query.on_conflict == "destination_id"


def test_list_admin_destination_controls(monkeypatch):
    fake = FakeSupabase()
    fake.tables["admin_destination_controls"] = FakeQuery(
        [
            {"destination_id": 10, "admin_state": "active"},
            {"destination_id": 11, "admin_state": "paused"},
        ]
    )
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.list_admin_destination_controls()

    assert len(result) == 2
    assert result[1]["admin_state"] == "paused"


def test_create_admin_access_request(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([{"id": 77, "status": "pending"}])
    fake.tables["admin_access_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.create_admin_access_request(
        requester_user_id=5,
        workspace_id=8,
        platform="telegram",
        external_id="@ExampleChannel",
        normalized_external_id="examplechannel",
        display_name="Example Channel",
    )

    assert result["id"] == 77
    assert query.payload["request_type"] == "add_destination"
    assert query.payload["workspace_id"] == 8
    assert query.payload["status"] == "pending"


def test_list_pending_admin_access_requests(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([{"id": 77, "status": "pending"}])
    fake.tables["admin_access_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.list_pending_admin_access_requests()

    assert result == [{"id": 77, "status": "pending"}]
    assert ("status", "pending") in query.filters


def test_review_admin_access_request(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([{"id": 77, "status": "approved"}])
    fake.tables["admin_access_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.review_admin_access_request(
        77,
        "approved",
        review_reason="approved by admin",
        reviewed_by_platform="bale",
        reviewed_by_external_user_id=456,
    )

    assert result["status"] == "approved"
    assert query.payload["reviewed_by_platform"] == "bale"
    assert query.payload["reviewed_by_external_user_id"] == 456
    assert query.payload["reviewed_at"]
    assert query.payload["updated_at"]


def test_record_admin_audit_log(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([{"id": 101, "action": "pause_destination"}])
    fake.tables["admin_audit_log"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.record_admin_audit_log(
        "pause_destination",
        "telegram",
        actor_external_user_id=123,
        target_type="destination",
        target_id=10,
        details={"reason": "temporary pause"},
    )

    assert result["action"] == "pause_destination"
    assert query.payload["actor_platform"] == "telegram"
    assert query.payload["target_type"] == "destination"
    assert query.payload["target_id"] == 10
    assert query.payload["details"]["reason"] == "temporary pause"

class FakeRegistrationQuery(FakeQuery):
    def execute(self):
        if self.payload is None:
            return SimpleNamespace(data=[])

        return SimpleNamespace(
            data=[{
                "id": 201,
                "user_id": self.payload["user_id"],
                "requested_platform": self.payload["requested_platform"],
                "requested_external_user_id": self.payload[
                    "requested_external_user_id"
                ],
                "status": self.payload["status"],
            }]
        )


def test_get_admin_registration_request_for_user(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([
        {
            "id": 201,
            "user_id": 5,
            "requested_platform": "telegram",
            "requested_external_user_id": 123,
            "status": "pending",
        }
    ])
    fake.tables["admin_registration_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.get_admin_registration_request_for_user(5)

    assert result["id"] == 201
    assert result["user_id"] == 5
    assert ("user_id", 5) in query.filters


def test_create_admin_registration_request(monkeypatch):
    fake = FakeSupabase()
    query = FakeRegistrationQuery()
    fake.tables["admin_registration_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.create_admin_registration_request(
        user_id=5,
        requested_platform="telegram",
        requested_external_user_id=123,
    )

    assert result["id"] == 201
    assert result["status"] == "pending"
    assert query.payload["user_id"] == 5
    assert query.payload["requested_platform"] == "telegram"
    assert query.payload["requested_external_user_id"] == 123


def test_create_admin_registration_request_reuses_existing(monkeypatch):
    fake = FakeSupabase()
    existing = {
        "id": 201,
        "user_id": 5,
        "requested_platform": "telegram",
        "requested_external_user_id": 123,
        "status": "pending",
    }
    query = FakeQuery([existing])
    fake.tables["admin_registration_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.create_admin_registration_request(
        user_id=5,
        requested_platform="telegram",
        requested_external_user_id=123,
    )

    assert result == existing
    assert query.payload is None


def test_list_pending_admin_registration_requests(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([
        {
            "id": 201,
            "user_id": 5,
            "status": "pending",
        }
    ])
    fake.tables["admin_registration_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.list_pending_admin_registration_requests()

    assert result == [
        {
            "id": 201,
            "user_id": 5,
            "status": "pending",
        }
    ]
    assert ("status", "pending") in query.filters


def test_review_admin_registration_request(monkeypatch):
    fake = FakeSupabase()
    query = FakeQuery([
        {
            "id": 201,
            "status": "approved",
        }
    ])
    fake.tables["admin_registration_requests"] = query
    monkeypatch.setattr(db, "service_supabase", fake)

    result = db.review_admin_registration_request(
        201,
        "approved",
        review_reason="approved by admin",
        reviewed_by_platform="telegram",
        reviewed_by_external_user_id=123,
    )

    assert result["status"] == "approved"
    assert query.payload["status"] == "approved"
    assert query.payload["review_reason"] == "approved by admin"
    assert query.payload["reviewed_by_platform"] == "telegram"
    assert query.payload["reviewed_by_external_user_id"] == 123
    assert query.payload["reviewed_at"]
    assert query.payload["updated_at"]