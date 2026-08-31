import importlib
import sys
import types


class InMemoryDb:
    def __init__(self):
        self.users = []
        self.workspaces = []
        self.workspace_members = []
        self.tenants = {}
        self.calls = {
            "get_tenant": 0,
            "get_or_create_user_by_telegram_id": 0,
            "create_workspace": 0,
        }

    def get_tenant(self, user_id):
        self.calls["get_tenant"] += 1
        return self.tenants.get(user_id)

    def save_tenant(
        self,
        user_id,
        bot_token,
        telegram_channel,
        bale_channel="",
        bale_token="",
        hashtag=None,
        channel_tag=None,
    ):
        self.tenants[user_id] = {
            "user_id": user_id,
            "bot_token": bot_token,
            "telegram_channel": telegram_channel,
            "bale_channel": bale_channel,
            "bale_token": bale_token,
            "hashtag": hashtag,
            "channel_tag": channel_tag,
        }
        return True

    def update_bale_settings(self, user_id, bale_channel, bale_token):
        tenant = self.tenants.get(user_id)
        if not tenant:
            return False
        tenant["bale_channel"] = bale_channel
        tenant["bale_token"] = bale_token
        return True

    def get_user_by_telegram_id(self, telegram_user_id):
        for user in self.users:
            if user["telegram_user_id"] == telegram_user_id:
                return user
        return None

    def get_or_create_user_by_telegram_id(self, telegram_user_id, status="active"):
        self.calls["get_or_create_user_by_telegram_id"] += 1
        user = self.get_user_by_telegram_id(telegram_user_id)
        if user:
            return user
        user = {
            "id": len(self.users) + 1,
            "telegram_user_id": telegram_user_id,
            "status": status,
        }
        self.users.append(user)
        return user

    def get_user_by_id(self, user_id):
        return next((user for user in self.users if user["id"] == user_id), None)

    def set_user_pending_workspace_action(self, user_id, action, workspace_id=None):
        user = self.get_user_by_id(user_id)
        user["pending_workspace_action"] = action
        user["pending_workspace_id"] = workspace_id
        return user

    def clear_user_pending_workspace_action(self, user_id):
        return self.set_user_pending_workspace_action(user_id, None, None)

    def list_owned_workspaces(self, owner_user_id, include_inactive=False):
        rows = [
            row
            for row in self.workspaces
            if row["owner_user_id"] == owner_user_id
        ]
        if not include_inactive:
            rows = [
                row
                for row in rows
                if row.get("status") == "active"
            ]
        return sorted(rows, key=lambda row: row["id"])

    def create_workspace(self, name, owner_user_id, status="active"):
        self.calls["create_workspace"] += 1
        workspace = {
            "id": len(self.workspaces) + 1,
            "name": name,
            "owner_user_id": owner_user_id,
            "status": status,
        }
        self.workspaces.append(workspace)
        self.add_workspace_member(
            workspace["id"],
            owner_user_id,
            role="owner",
            status="active",
        )
        return workspace

    def get_workspace_member(self, workspace_id, user_id):
        for row in self.workspace_members:
            if (
                row["workspace_id"] == workspace_id
                and row["user_id"] == user_id
            ):
                return row
        return None

    def add_workspace_member(
        self,
        workspace_id,
        user_id,
        role="writer",
        status="active",
    ):
        existing = self.get_workspace_member(workspace_id, user_id)
        if existing:
            return existing
        row = {
            "id": len(self.workspace_members) + 1,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": role,
            "status": status,
        }
        self.workspace_members.append(row)
        return row

    def update_workspace_member_role(self, workspace_id, user_id, role):
        row = self.get_workspace_member(workspace_id, user_id)
        if not row:
            return None
        row["role"] = role
        return row

    def update_workspace_member_status(self, workspace_id, user_id, status):
        row = self.get_workspace_member(workspace_id, user_id)
        if not row:
            return None
        row["status"] = status
        return row


def _load_command_handler(monkeypatch):
    db = InMemoryDb()
    fake_database = types.ModuleType("core.database")
    fake_database.get_tenant = db.get_tenant
    fake_database.save_tenant = db.save_tenant
    fake_database.update_bale_settings = db.update_bale_settings
    fake_database.get_user_by_telegram_id = db.get_user_by_telegram_id
    fake_database.get_or_create_user_by_telegram_id = db.get_or_create_user_by_telegram_id
    fake_database.get_user_by_id = db.get_user_by_id
    fake_database.set_user_pending_workspace_action = db.set_user_pending_workspace_action
    fake_database.clear_user_pending_workspace_action = db.clear_user_pending_workspace_action
    fake_database.create_workspace = db.create_workspace
    fake_database.list_owned_workspaces = db.list_owned_workspaces
    fake_database.get_workspace_member = db.get_workspace_member
    fake_database.add_workspace_member = db.add_workspace_member
    fake_database.update_workspace_member_role = db.update_workspace_member_role
    fake_database.update_workspace_member_status = db.update_workspace_member_status
    monkeypatch.setitem(sys.modules, "core.database", fake_database)

    sys.modules.pop("core.command_handler", None)
    command_handler = importlib.import_module("core.command_handler")
    command_handler = importlib.reload(command_handler)

    sent_messages = []
    monkeypatch.setattr(
        command_handler,
        "send_message",
        lambda chat_id, text, parse_mode=None: sent_messages.append((chat_id, text)) or True,
    )
    monkeypatch.setattr(
        command_handler,
        "send_long_message",
        lambda chat_id, text, max_len=4096: sent_messages.append((chat_id, text)) or True,
    )
    monkeypatch.setattr(
        command_handler,
        "send_message_with_keyboard",
        lambda chat_id, text, keyboard: sent_messages.append((chat_id, text)) or True,
    )
    return command_handler, db, sent_messages


def test_start_new_user_waits_for_name_then_creates_owner_workspace(monkeypatch):
    command_handler, db, sent = _load_command_handler(monkeypatch)

    assert command_handler.handle_start(1001) is True

    assert len(db.users) == 1
    assert db.users[0]["telegram_user_id"] == 1001
    assert len(db.workspaces) == 0
    assert db.users[0]["pending_workspace_action"] == "create_workspace_name"
    assert command_handler.handle_workspace_stateful_input("سیاسی", 1001) is True
    assert len(db.workspaces) == 1
    assert db.workspaces[0]["name"] == "سیاسی"
    owner = db.get_workspace_member(db.workspaces[0]["id"], db.users[0]["id"])
    assert owner["role"] == "owner"
    assert owner["status"] == "active"
    assert "مقصد انتشار" in sent[-1][1]


def test_register_text_command_remains_available(monkeypatch):
    command_handler, db, sent = _load_command_handler(monkeypatch)

    assert command_handler.handle_command("/register", 1009) is True
    assert db.get_tenant(1009) is None
    user = db.get_user_by_telegram_id(1009)
    assert user is not None
    assert any("گروه رسانه‌ای" in message for _chat, message in sent)
    assert all("تنظیمات موقتی" not in message for _chat, message in sent)


def test_start_is_idempotent_and_does_not_duplicate_workspace(monkeypatch):
    command_handler, db, _ = _load_command_handler(monkeypatch)

    assert command_handler.handle_start(1002) is True
    assert command_handler.handle_start(1002) is True

    assert len(db.users) == 1
    assert len(db.workspaces) == 0
    assert command_handler.handle_workspace_stateful_input("اقتصادی", 1002) is True
    assert len(db.workspaces) == 1
    assert len(db.workspace_members) == 1
    assert db.calls["create_workspace"] == 1


def test_start_resumes_when_user_exists_but_workspace_missing(monkeypatch):
    command_handler, db, _ = _load_command_handler(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1003)
    assert user["telegram_user_id"] == 1003
    assert db.workspaces == []

    assert command_handler.handle_start(1003) is True

    assert len(db.users) == 1
    assert len(db.workspaces) == 0
    assert command_handler.handle_workspace_stateful_input("ورزشی", 1003) is True
    assert len(db.workspaces) == 1
    owner = db.get_workspace_member(db.workspaces[0]["id"], user["id"])
    assert owner["role"] == "owner"
    assert owner["status"] == "active"


def test_start_repairs_missing_owner_membership(monkeypatch):
    command_handler, db, _ = _load_command_handler(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1004)
    workspace = {
        "id": 1,
        "name": "رسانه من",
        "owner_user_id": user["id"],
        "status": "active",
    }
    db.workspaces.append(workspace)
    assert db.get_workspace_member(workspace["id"], user["id"]) is None

    assert command_handler.handle_start(1004) is True

    owner = db.get_workspace_member(workspace["id"], user["id"])
    assert owner["role"] == "owner"
    assert owner["status"] == "active"
    assert len(db.workspaces) == 1


def test_legacy_user_start_is_unchanged_and_not_onboarded(monkeypatch):
    command_handler, db, sent = _load_command_handler(monkeypatch)
    db.tenants[2001] = {"user_id": 2001, "telegram_channel": "@legacy"}

    assert command_handler.handle_start(2001) is True

    assert "برای شروع از /register استفاده کنید." in sent[-1][1]
    assert db.calls["get_or_create_user_by_telegram_id"] == 0
    assert db.calls["create_workspace"] == 0


def test_help_for_new_user_is_contextual(monkeypatch):
    command_handler, db, sent = _load_command_handler(monkeypatch)

    assert command_handler.handle_help(3001) is True
    assert "/start" in sent[-1][1]

    command_handler.handle_start(3001)
    assert command_handler.handle_help(3001) is True
    assert "راهنمای تکمیل تنظیمات" in sent[-1][1]
    assert "/adddestination" in sent[-1][1]


def test_help_button_action_and_existing_command_routing(monkeypatch):
    command_handler, _, sent = _load_command_handler(monkeypatch)

    assert command_handler.handle_command("راهنما", 3002) is True
    assert "راهنمای شروع" in sent[-1][1]

    monkeypatch.setattr(command_handler, "handle_status", lambda chat_id: True)
    assert command_handler.handle_command("/status", 3002) is True
