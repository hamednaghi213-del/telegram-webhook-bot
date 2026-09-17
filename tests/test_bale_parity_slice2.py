"""Focused tests for Bale Full Bot Parity — slice 2.

Covers: Bale callbacks routed into the SHARED workspace/setup
callback logic, Bale transport acknowledgement, workspace
create/switch/stateful-input flows from Bale, destination
management from Bale (both Bale and Telegram destinations),
keyboard/callback payload preservation, identity isolation and
Telegram non-regression.
"""

import importlib
import os
import sys
import threading

import pytest


# ---------------------------------------------------------
# Bootstrap core.database before core.* imports.
# ---------------------------------------------------------

os.environ.setdefault(
    "SUPABASE_URL", "https://example.test"
)
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault(
    "SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key"
)

_fake_supabase = sys.modules.get("supabase")

if _fake_supabase is None or not getattr(
    _fake_supabase, "_is_persistence_fake", False
):
    _fake_supabase = type(sys)("supabase")
    _fake_supabase._is_persistence_fake = True
    _fake_supabase.create_client = (
        lambda _url, _key: object()
    )
    sys.modules["supabase"] = _fake_supabase


def _ensure_real(module_name, sentinel):
    """Guarantee a REAL core module in sys.modules.

    Polluter files install fake ModuleTypes that never get restored;
    sentinel attributes (only present on the real modules) decide
    whether a re-import is needed. Slice 1 may already have imported
    the real modules in this process -- reuse them so module
    references stay consistent across both test files.
    """
    existing = sys.modules.get(module_name)

    if existing is not None and hasattr(
        existing, sentinel
    ):
        return existing

    sys.modules.pop(module_name, None)

    core_package = sys.modules.get("core")

    if core_package is not None:
        core_package.__dict__.pop(
            module_name.rsplit(".", 1)[-1],
            None,
        )

    return importlib.import_module(module_name)


_ensure_real(
    "core.database", "get_user_by_bale_id"
)
_ensure_real(
    "core.command_handler",
    "get_or_create_identity_for_chat",
)

import core.database  # noqa: E402

sys.modules["supabase"] = _fake_supabase

import core.bale_adapter  # noqa: E402
import core.command_handler  # noqa: E402
import core.messaging  # noqa: E402
import core.webhook_handler  # noqa: E402
import core.workspace_publisher  # noqa: E402

from core.messaging import (  # noqa: E402
    bound_context,
    current_context,
    reset_default_context,
)


_REAL_DATABASE = core.database
_COMMAND_HANDLER = core.command_handler
_BALE_ADAPTER = core.bale_adapter
_WEBHOOK_HANDLER = core.webhook_handler
_WORKSPACE_PUBLISHER = core.workspace_publisher


@pytest.fixture(autouse=True)
def _isolate_adapter_state():
    reset_default_context()
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"
    yield
    reset_default_context()
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"


def _patch_db(monkeypatch, name, value):
    """Patch the real module AND whatever 'core.database' object is
    live in sys.modules (polluter files swap in fakes that never get
    restored; shared code imports the module dynamically)."""
    monkeypatch.setattr(
        _REAL_DATABASE,
        name,
        value,
        raising=False,
    )

    live = sys.modules.get("core.database")

    if live is not None and live is not _REAL_DATABASE:
        monkeypatch.setattr(
            live,
            name,
            value,
            raising=False,
        )


def _patch_ch(monkeypatch, name, value):
    """Patch command_handler attributes on the real module and on
    any live (possibly fake) sys.modules object."""
    monkeypatch.setattr(
        _COMMAND_HANDLER,
        name,
        value,
        raising=False,
    )

    live = sys.modules.get("core.command_handler")

    if live is not None and live is not _COMMAND_HANDLER:
        monkeypatch.setattr(
            live,
            name,
            value,
            raising=False,
        )


def _patch_wp(monkeypatch, name, value):
    monkeypatch.setattr(
        _WORKSPACE_PUBLISHER,
        name,
        value,
        raising=False,
    )


# =========================================================
# FAKE SHARED DATABASE (workspace/identity accessors)
# =========================================================


class _FakeDB:
    """In-memory double for the workspace/identity accessors used
    by the shared flows under test."""

    def __init__(self):
        self.users = []
        self.next_id = 100
        self.selected = None
        self.workspaces = {
            7: {
                "id": 7,
                "name": "رسانه مشترک",
                "owner_user_id": 1,
                "status": "active",
            }
        }
        self.destinations = {
            11: {
                "id": 11,
                "workspace_id": 7,
                "external_id": "@tgchannel",
                "name": "@tgchannel",
                "platform": "telegram",
                "status": "active",
            }
        }
        self.pending_actions = {}

    # -- identity ------------------------------------------------

    def _new_user(self, **fields):
        self.next_id += 1
        row = {"id": self.next_id, "status": "active"}
        row.update(fields)
        self.users.append(row)
        return dict(row)

    def get_user_by_telegram_id(self, telegram_user_id):
        for row in self.users:
            if (
                row.get("telegram_user_id")
                == telegram_user_id
            ):
                return dict(row)

        return None

    def get_or_create_user_by_telegram_id(
        self,
        telegram_user_id,
        status="active",
    ):
        found = self.get_user_by_telegram_id(
            telegram_user_id
        )

        if found:
            return found

        return self._new_user(
            telegram_user_id=telegram_user_id
        )

    def get_user_by_bale_id(self, bale_user_id):
        for row in self.users:
            if row.get("bale_user_id") == bale_user_id:
                return dict(row)

        return None

    def get_or_create_user_by_bale_id(
        self,
        bale_user_id,
        status="active",
        *,
        telegram_user_id=None,
    ):
        found = self.get_user_by_bale_id(bale_user_id)

        if found:
            return found

        return self._new_user(
            bale_user_id=bale_user_id,
            telegram_user_id=telegram_user_id,
        )

    def get_user_by_id(self, user_id):
        for row in self.users:
            if row["id"] == user_id:
                return dict(row)

        return None

    def get_tenant(self, chat_id):
        return None

    # -- pending actions -----------------------------------------

    def set_user_pending_workspace_action(
        self,
        user_id,
        action,
        workspace_id=None,
    ):
        self.pending_actions[user_id] = {
            "action": action,
            "workspace_id": workspace_id,
        }

    def clear_user_pending_workspace_action(
        self,
        user_id,
    ):
        self.pending_actions.pop(user_id, None)

    # -- workspaces ----------------------------------------------

    def list_owned_workspaces(
        self,
        user_id,
        include_inactive=True,
    ):
        return [
            dict(ws)
            for ws in self.workspaces.values()
            if ws.get("owner_user_id") == user_id
        ]

    def list_user_workspaces(
        self,
        user_id,
        include_inactive=False,
    ):
        if user_id == 1:
            return [
                dict(self.workspaces[7])
            ]

        return []

    def list_user_workspace_memberships(
        self,
        user_id,
    ):
        return self.list_user_workspaces(user_id)

    def get_workspace(self, workspace_id):
        ws = self.workspaces.get(workspace_id)

        return dict(ws) if ws else None

    def get_workspace_member(
        self,
        workspace_id,
        user_id,
    ):
        if user_id == 1 and workspace_id == 7:
            return {
                "role": "owner",
                "status": "active",
            }

        return None

    def get_active_workspace_preference(
        self,
        user_id,
    ):
        return {
            "context_type": "workspace",
            "legacy_selected": False,
            "active_workspace_id": 7,
        }

    def list_selected_workspace_ids(self, user_id):
        return [7]

    def select_workspace(self, user_id, workspace_id):
        self.selected = workspace_id

    def get_workspace_setup_state(self, workspace_id):
        return {"step": "completed"}

    def list_workspace_destinations(
        self,
        workspace_id,
    ):
        return [
            dict(dest)
            for dest in self.destinations.values()
            if dest["workspace_id"] == workspace_id
        ]

    def get_publication_destination(
        self,
        destination_id,
    ):
        dest = self.destinations.get(destination_id)

        return dict(dest) if dest else None


@pytest.fixture()
def fake_db():
    return _FakeDB()


@pytest.fixture()
def db_env(fake_db, monkeypatch):
    """Expose the fake database to shared code via the real module
    AND via command_handler's module-global aliases."""
    db_names = (
        "get_user_by_telegram_id",
        "get_or_create_user_by_telegram_id",
        "get_user_by_bale_id",
        "get_or_create_user_by_bale_id",
        "get_user_by_id",
        "get_tenant",
        "set_user_pending_workspace_action",
        "clear_user_pending_workspace_action",
        "list_owned_workspaces",
        "list_user_workspaces",
        "list_user_workspace_memberships",
        "get_workspace",
        "get_workspace_member",
        "get_active_workspace_preference",
        "list_selected_workspace_ids",
        "select_workspace",
        "get_workspace_setup_state",
        "list_workspace_destinations",
        "get_publication_destination",
    )

    for name in db_names:
        _patch_db(
            monkeypatch,
            name,
            getattr(fake_db, name),
        )

    for name in (
        "get_user_by_telegram_id",
        "get_or_create_user_by_telegram_id",
        "get_user_by_bale_id",
        "get_or_create_user_by_bale_id",
        "get_tenant",
        "list_owned_workspaces",
        "list_user_workspaces",
        "list_user_workspace_memberships",
        "get_workspace",
        "get_workspace_member",
        "get_active_workspace_preference",
        "list_selected_workspace_ids",
        "get_workspace_setup_state",
    ):
        _patch_ch(
            monkeypatch,
            name,
            getattr(fake_db, name),
        )

    return fake_db


class _BaleHTTPRecorder:
    """Records calls the REAL Bale context makes to the Bale Bot API
    (the adapter translation layer) and answers them with success."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json))

        class _Resp:
            status_code = 200

            def json(self):
                return {"ok": True}

        return _Resp()

    def urls(self, method):
        return [
            url
            for url, _payload in self.calls
            if f"/{method}" in url
        ]


@pytest.fixture()
def bale_http(monkeypatch):
    """Intercept the Bale Bot API at the adapter translation layer."""
    recorder = _BaleHTTPRecorder()
    monkeypatch.setenv(
        "BALE_BOT_TOKEN", "test-bale-token"
    )
    monkeypatch.setattr(
        core.messaging.requests,
        "post",
        recorder,
    )
    return recorder


def _bale_command(text, chat_id=555000):
    return {
        "message": {
            "chat": {"id": chat_id},
            "text": text,
            "entities": [
                {
                    "type": "bot_command",
                    "offset": 0,
                    "length": len(
                        text.split()[0]
                    ),
                }
            ],
        }
    }


# =========================================================
# CALLBACKS — shared routing + Bale acknowledgement
# =========================================================


def test_bale_workspace_callback_routes_to_shared_handler(
    monkeypatch,
):
    """A Bale ``ws:`` callback reaches the existing workspace
    callback dispatcher (no duplicated business logic)."""
    calls = []

    _patch_wp(
        monkeypatch,
        "handle_workspace_callback",
        lambda cq, req_id, api_url: calls.append(
            (cq, req_id, api_url)
        )
        or True,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-1",
                    "data": "ws:manage:7",
                    "from": {"id": 555000},
                    "message": {
                        "chat": {"id": 555000},
                        "message_id": 10,
                    },
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert len(calls) == 1

    cq, req_id, api_url = calls[0]

    # Shared payload semantics preserved end-to-end.
    assert cq["data"] == "ws:manage:7"
    assert cq["from"]["id"] == 555000
    assert cq["message"]["chat"]["id"] == 555000

    # Origin restored after processing.
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


def test_bale_setup_callback_routes_to_shared_handler(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        _WEBHOOK_HANDLER,
        "handle_setup_callback",
        lambda cq, req_id: calls.append((cq, req_id))
        or True,
        raising=False,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-2",
                    "data": "setup:start",
                    "from": {"id": 555000},
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert calls[0][0]["data"] == "setup:start"


def test_bale_callback_acknowledgement_uses_bale_transport(
    db_env,
    bale_http,
    monkeypatch,
):
    """setup:done from Bale: acknowledgement and the completion
    reply travel over the BALE Bot API, never Telegram HTTP."""
    monkeypatch.setattr(
        _COMMAND_HANDLER,
        "API_URL",
        "",
        raising=False,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-done",
                    "data": "setup:done",
                    "from": {"id": 555000},
                }
            }
        )
    )

    assert status == 200

    # Ack went to the Bale Bot API with the shared callback id.
    assert (
        len(bale_http.urls("answerCallbackQuery"))
        == 1
    )
    assert "cb-done" in str(bale_http.calls)

    # The completion message was sent over Bale to the user chat.
    completion = [
        payload
        for url, payload in bale_http.calls
        if "/sendMessage" in url
        and (payload or {}).get("chat_id")
        == 555000
        and "راه‌اندازی کامل شد"
        in (payload or {}).get("text", "")
    ]
    assert completion

    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


def test_unknown_callback_acknowledged_without_business_logic(
    bale_http,
    monkeypatch,
):
    setup_calls = []
    ws_calls = []

    monkeypatch.setattr(
        _WEBHOOK_HANDLER,
        "handle_setup_callback",
        lambda cq, req_id: setup_calls.append(cq),
        raising=False,
    )
    monkeypatch.setattr(
        _WORKSPACE_PUBLISHER,
        "handle_workspace_callback",
        lambda cq, req_id, api_url: ws_calls.append(
            cq
        ),
        raising=False,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-x",
                    "data": "future:unknown",
                    "from": {"id": 1},
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is False
    assert setup_calls == []
    assert ws_calls == []

    # The client was still acknowledged over Bale (no hang).
    assert bale_http.urls("answerCallbackQuery")


def test_callback_context_cannot_leak_into_other_requests(
    monkeypatch,
):
    """Origin/messaging binding is request-scoped: a failing shared
    handler and a concurrent Telegram-bound thread both stay clean."""

    def boom(cq, req_id):
        raise RuntimeError("shared handler failed")

    _patch_wp(
        monkeypatch,
        "handle_workspace_callback",
        boom,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-boom",
                    "data": "ws:legacy",
                    "from": {"id": 1},
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is False
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )
    assert current_context().name == "telegram"

    # Concurrent-thread isolation: the binding is thread-local.
    seen = {}

    def probe():
        seen["origin"] = (
            _COMMAND_HANDLER.CURRENT_ORIGIN
        )
        seen["context"] = current_context().name

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join()

    assert seen["origin"] == "telegram"
    assert seen["context"] == "telegram"


# =========================================================
# WORKSPACE FLOWS FROM BALE
# =========================================================


def test_bale_workspace_creation_flow(
    db_env,
    bale_http,
    monkeypatch,
):
    calls = {}

    def fake_create_workspace(chat_id):
        calls["create"] = chat_id

        _COMMAND_HANDLER.get_or_create_identity_for_chat(
            chat_id
        )
        _COMMAND_HANDLER.send_message(
            chat_id,
            "📁 نام گروه رسانه‌ای را وارد کنید",
        )
        return True

    _patch_ch(
        monkeypatch,
        "handle_create_workspace",
        fake_create_workspace,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command("/register")
        )
    )

    assert response["handled"] is True
    assert calls["create"] == 555000

    # The Bale user got a bale-first identity with its own id.
    bale_user = db_env.get_user_by_bale_id(555000)
    assert bale_user is not None
    assert bale_user["telegram_user_id"] is None

    # The prompt travelled over the Bale Bot API.
    assert any(
        "/sendMessage" in url
        and "نام گروه"
        in (payload or {}).get("text", "")
        for url, payload in bale_http.calls
    )


def test_bale_stateful_input_enters_shared_path(
    db_env,
    bale_http,
    monkeypatch,
):
    """Bare text from Bale enters the SAME stateful-input path;
    the pending action is keyed by the internal users.id."""
    calls = {}

    def fake_stateful_input(text, chat_id):
        calls["input"] = (text, chat_id)

        user = (
            _COMMAND_HANDLER._identity_for_chat(
                chat_id
            )
        )
        db_env.set_user_pending_workspace_action(
            user["id"],
            "create_workspace_name",
            None,
        )
        return True

    _patch_ch(
        monkeypatch,
        "handle_workspace_stateful_input",
        fake_stateful_input,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "message": {
                    "chat": {"id": 555000},
                    "text": "رسانه تازه من",
                }
            }
        )
    )

    assert response["handled"] is True
    assert response["reason"] == "stateful_input"
    assert calls["input"] == (
        "رسانه تازه من",
        555000,
    )

    bale_user = db_env.get_user_by_bale_id(555000)
    assert (
        db_env.pending_actions[bale_user["id"]][
            "action"
        ]
        == "create_workspace_name"
    )


def test_bale_switch_workspace(db_env, monkeypatch):
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_switchworkspace",
        lambda args, chat_id: calls.setdefault(
            "switch", (args, chat_id)
        )
        or True,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command("/switchworkspace 7")
        )
    )

    assert response["handled"] is True
    assert calls["switch"] == ("7", 555000)


def test_associated_bale_identity_shares_workspace(
    db_env,
):
    """An explicitly linked Bale identity resolves to the SAME
    internal user (id=1) and therefore the same Workspace records."""
    # Internal user 1 owns workspace 7 and is linked to Bale 555000.
    db_env.users.append(
        {
            "id": 1,
            "telegram_user_id": 999,
            "bale_user_id": 555000,
            "status": "active",
        }
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    user = _COMMAND_HANDLER._identity_for_chat(
        555000
    )

    assert user["id"] == 1

    user_ws, workspace = (
        _COMMAND_HANDLER._get_workspace_for_user(
            555000
        )
    )

    assert user_ws["id"] == 1
    assert workspace["id"] == 7

    # The same internal user resolves on Telegram too.
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    tg_user = _COMMAND_HANDLER._identity_for_chat(
        999
    )

    assert tg_user["id"] == 1


def test_same_numeric_ids_never_cross_identities(
    db_env,
):
    """A Telegram user and a Bale user with the SAME numeric id are
    two different internal accounts."""
    db_env.get_or_create_user_by_telegram_id(
        888888,
        status="active",
    )
    db_env.get_or_create_user_by_bale_id(
        888888,
        status="active",
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    tg_user = _COMMAND_HANDLER._identity_for_chat(
        888888
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    bale_user = _COMMAND_HANDLER._identity_for_chat(
        888888
    )

    assert tg_user["id"] != bale_user["id"]
    assert (
        tg_user["telegram_user_id"] == 888888
    )
    assert (
        bale_user["bale_user_id"] == 888888
    )
    assert (
        bale_user["telegram_user_id"] is None
    )


def test_legacy_tenant_guard_blocks_bale_origin(
    db_env,
    monkeypatch,
):
    """Slice-1 regression guard: legacy tenants are Telegram-only."""

    def fake_tenant(chat_id):
        return {"telegram_channel": "@legacy"}

    monkeypatch.setattr(
        _COMMAND_HANDLER,
        "get_tenant",
        fake_tenant,
        raising=False,
    )
    monkeypatch.setattr(
        _REAL_DATABASE,
        "get_tenant",
        fake_tenant,
        raising=False,
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    assert (
        _COMMAND_HANDLER._legacy_tenant(4242)
        is None
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    assert _COMMAND_HANDLER._legacy_tenant(
        4242
    ) == {"telegram_channel": "@legacy"}


# =========================================================
# SETUP / ONBOARDING FROM BALE
# =========================================================


def test_bale_setup_command_progresses_shared_state(
    db_env,
    monkeypatch,
):
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_setup",
        lambda chat_id: calls.setdefault(
            "setup", chat_id
        )
        or True,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command("/setup")
        )
    )

    assert response["handled"] is True
    assert calls["setup"] == 555000


def test_setup_callback_full_flow_from_bale(
    db_env,
    bale_http,
    monkeypatch,
):
    """setup:create_workspace from Bale runs the real shared setup
    callback handler; ack + prompts go over Bale transport."""
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_create_workspace",
        lambda chat_id: calls.setdefault(
            "create", chat_id
        )
        or True,
    )

    # Exactly what the Bale adapter does before dispatching a
    # callback: bind the Bale origin + outbound context.
    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    with bound_context(
        core.messaging.BaleMessagingContext()
    ):
        handled = (
            _WEBHOOK_HANDLER.handle_setup_callback(
                {
                    "id": "cb-create",
                    "data": "setup:create_workspace",
                    "from": {"id": 555000},
                },
                "bale-test",
            )
        )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    assert handled is True
    assert calls["create"] == 555000

    # Acknowledged over the Bale Bot API.
    assert (
        len(bale_http.urls("answerCallbackQuery"))
        == 1
    )


# =========================================================
# DESTINATION / CHANNEL MANAGEMENT FROM BALE
# =========================================================


def test_bale_destinations_listing(db_env, monkeypatch):
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_destinations",
        lambda chat_id: calls.setdefault(
            "dest", chat_id
        )
        or True,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command("/destinations")
        )
    )

    assert response["handled"] is True
    assert calls["dest"] == 555000


def test_bale_user_manages_bale_destination(
    db_env,
    monkeypatch,
):
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_addbale",
        lambda args, chat_id: calls.setdefault(
            "addbale", (args, chat_id)
        )
        or True,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command("/addbale @balechannel")
        )
    )

    assert response["handled"] is True
    assert calls["addbale"] == (
        "@balechannel",
        555000,
    )


def test_bale_user_manages_telegram_destination(
    db_env,
    monkeypatch,
):
    """Cross-platform management: a Bale chatter may add a Telegram
    destination — the shared layer chooses the operation."""
    calls = {}

    _patch_ch(
        monkeypatch,
        "handle_addchannel",
        lambda args, chat_id: calls.setdefault(
            "addchannel", (args, chat_id)
        )
        or True,
    )

    response, _status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command(
                "/addchannel @tgchannel"
            )
        )
    )

    assert response["handled"] is True
    assert calls["addchannel"] == (
        "@tgchannel",
        555000,
    )


def test_telegram_verification_untouched_by_bale_origin(
    db_env,
    monkeypatch,
):
    """Telegram destination verification keeps using the Telegram
    verifier even when the user is chatting through Bale."""
    import core.telegram_verifier

    verifier_calls = {}

    def fake_verify(token, channel):
        verifier_calls["token"] = token
        verifier_calls["channel"] = channel
        return True, "ok"

    monkeypatch.setattr(
        core.telegram_verifier,
        "verify_channel_admin",
        fake_verify,
    )
    monkeypatch.setattr(
        _COMMAND_HANDLER,
        "API_URL",
        "https://api.telegram.org/botTEST",
        raising=False,
    )

    # The shared verifier imports these from core.database
    # dynamically -- patch at the database layer (real + live).
    _patch_db(
        monkeypatch,
        "upsert_destination_verification",
        lambda dest_id, **kw: None,
    )
    _patch_db(
        monkeypatch,
        "update_publication_destination_status",
        lambda dest_id, status: None,
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    dest = {
        "id": 11,
        "external_id": "@tgchannel",
    }

    _COMMAND_HANDLER._verify_and_activate_channel(
        7,
        dest,
        555000,
    )

    # The TELEGRAM verifier ran with the Telegram bot token even
    # though the user is chatting through Bale.
    assert (
        verifier_calls["channel"]
        == "@tgchannel"
    )
    assert "TEST" in str(
        verifier_calls["token"]
    )


# =========================================================
# KEYBOARDS / CALLBACK PAYLOAD PRESERVATION
# =========================================================


def test_bale_keyboard_translation_in_adapter_layer(
    bale_http,
):
    """Under the Bale origin the shared keyboard sender translates
    to the Bale Bot API in the messaging adapter — payload and
    callback_data are preserved verbatim."""
    keyboard = [
        [
            {
                "text": "🏷 گروه ۷",
                "callback_data": "ws:manage:7",
            }
        ]
    ]

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    with bound_context(
        core.messaging.BaleMessagingContext()
    ):
        ok = (
            _COMMAND_HANDLER.send_message_with_keyboard(
                555000,
                "🏢 گروه‌های رسانه‌ای شما",
                keyboard,
            )
        )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    assert ok is True

    keyboard_sends = [
        payload
        for url, payload in bale_http.calls
        if "/sendMessage" in url
    ]

    assert len(keyboard_sends) == 1
    assert (
        keyboard_sends[0]["chat_id"] == 555000
    )
    assert (
        keyboard_sends[0]["reply_markup"][
            "inline_keyboard"
        ]
        == keyboard
    )


def test_telegram_workspace_callback_keeps_telegram_transport(
    monkeypatch,
):
    """Non-regression: a Telegram callback on the default context
    still acknowledges through the historical Telegram sender."""
    posted = []

    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr(
        _WORKSPACE_PUBLISHER.requests,
        "post",
        lambda url, json=None, timeout=None: (
            posted.append(url) or _FakeResponse()
        ),
    )

    _WORKSPACE_PUBLISHER._ws_answer_callback(
        "https://api.telegram.org/botTEST",
        "tg-cb-1",
        "انتخاب شد",
    )

    assert posted == [
        "https://api.telegram.org/botTEST/answerCallbackQuery"
    ]


def test_workspace_callback_dispatch_prefers_context(
    monkeypatch,
):
    """The dispatch wrapper routes to the shared handler with the
    Bale transport suppressed (api_url None) under Bale origin."""
    calls = {}

    _patch_wp(
        monkeypatch,
        "_handle_workspace_callback",
        lambda cq, req_id, api_url: calls.setdefault(
            "cb", (cq["data"], api_url)
        ),
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    with bound_context(
        core.messaging.BaleMessagingContext()
    ):
        _WORKSPACE_PUBLISHER.handle_workspace_callback(
            {"data": "ws:manage:7"},
            "req-1",
            "https://api.telegram.org/botSHOULD-NOT-USE",
        )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    assert calls["cb"] == ("ws:manage:7", None)
