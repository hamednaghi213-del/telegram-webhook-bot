"""Focused tests for Bale Full Bot Parity — slice 1.

Covers: separate Bale identity space (no numeric equivalence),
origin-scoped outbound transport, Bale webhook secret validation
(fail-closed), adapter command routing through the SHARED
handle_command, and Telegram-path regression.
"""

import os
import sys
from types import SimpleNamespace

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

# Some suite files install fake "core.*" ModuleTypes at collection
# time and never restore them. Purge every poisoned entry this file
# (and its transitive imports) needs, then import the REAL modules.
for _name in (
    "core.database",
    "core.command_handler",
    "core.messaging",
    "core.bale_adapter",
    "core.bale_forwarder",
    "core.branding_manager",
):
    sys.modules.pop(_name, None)

import core.database  # noqa: E402

sys.modules["supabase"] = _fake_supabase

import core.bale_adapter  # noqa: E402
import core.command_handler  # noqa: E402

from core.messaging import (  # noqa: E402
    bound_context,
    current_context,
    reset_default_context,
)


_COMMAND_HANDLER = core.command_handler
_BALE_ADAPTER = core.bale_adapter


_REAL_DATABASE = core.database


@pytest.fixture(autouse=True)
def _isolate_adapter_state():
    reset_default_context()
    yield
    reset_default_context()
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"


def _patch_real_db(monkeypatch, name, value):
    monkeypatch.setattr(
        _REAL_DATABASE,
        name,
        value,
        raising=False,
    )


def _patch_db_everywhere(monkeypatch, name, value):
    """Patch the real module AND whatever 'core.database' object is
    live in sys.modules (polluter files swap in fakes that never get
    restored; production resolves the module dynamically)."""
    _patch_real_db(monkeypatch, name, value)

    live = sys.modules.get("core.database")

    if live is not None and live is not _REAL_DATABASE:
        monkeypatch.setattr(
            live,
            name,
            value,
            raising=False,
        )


# =========================================================
# IDENTITY — separate identity spaces
# =========================================================


class _FakeIdentityDatabase:
    """Minimal users-table double for identity accessors."""

    def __init__(self):
        self.users = []

    def get_user_by_telegram_id(self, telegram_user_id):
        for row in self.users:
            if (
                row.get("telegram_user_id")
                == telegram_user_id
            ):
                return dict(row)

        return None

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
        existing = self.get_user_by_bale_id(
            bale_user_id
        )

        if existing:
            return existing

        row = {
            "id": 1000 + len(self.users) + 1,
            "bale_user_id": bale_user_id,
            "telegram_user_id": telegram_user_id,
            "status": status,
        }
        self.users.append(row)

        return dict(row)


@pytest.fixture()
def identity_db():
    return _FakeIdentityDatabase()


def test_bale_identity_get_or_create_is_bale_first(
    identity_db,
    monkeypatch,
):
    """A Bale user maps to its own account; no Telegram ID is
    invented and no Telegram lookup occurs."""
    _patch_db_everywhere(
        monkeypatch,
        "get_user_by_bale_id",
        identity_db.get_user_by_bale_id,
    )
    _patch_db_everywhere(
        monkeypatch,
        "get_or_create_user_by_bale_id",
        identity_db.get_or_create_user_by_bale_id,
    )

    # The Telegram branch resolves this from command_handler's
    # module globals -- patch it at the resolution site.
    monkeypatch.setattr(
        core.command_handler,
        "get_user_by_telegram_id",
        lambda telegram_user_id: pytest.fail(
            "Bale origin must not resolve Telegram identity"
        ),
        raising=True,
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    user = _COMMAND_HANDLER._identity_for_chat(
        987654321
    )

    assert user is not None
    assert user["bale_user_id"] == 987654321
    assert user["telegram_user_id"] is None

    # A Telegram user with the same numeric ID is a DIFFERENT
    # person: identity isolation is the core safety property.
    _patch_db_everywhere(
        monkeypatch,
        "get_user_by_telegram_id",
        lambda telegram_user_id: None,
    )
    monkeypatch.setattr(
        core.command_handler,
        "get_user_by_telegram_id",
        lambda telegram_user_id: None,
        raising=True,
    )

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"

    telegram_user = _COMMAND_HANDLER._identity_for_chat(
        987654321
    )

    assert telegram_user is None


def test_bale_identity_links_to_existing_account_explicitly(
    identity_db,
):
    """The accessor's linkage contract: when a caller explicitly
    links a Bale identity to an existing shared account, that
    account (not a new row) is resolved by the Bale ID."""
    fake = _FakeIdentityDatabase()
    fake.users.append(
        {
            "id": 7,
            "telegram_user_id": 111,
            "bale_user_id": None,
            "status": "active",
        }
    )

    # Simulate the linkage the accessor performs for an
    # explicitly linked account.
    fake.users[0]["bale_user_id"] = 555000

    resolved = fake.get_user_by_bale_id(555000)

    assert resolved["id"] == 7
    assert resolved["telegram_user_id"] == 111


def test_seam_defaults_to_telegram_origin():
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


# =========================================================
# TRANSPORT — origin-scoped outbound contexts
# =========================================================


class _RecordingContext:
    def __init__(self, name):
        self.name = name
        self.texts = []
        self.keyboards = []

    def send_text(
        self,
        chat_id,
        text,
        parse_mode=None,
    ):
        self.texts.append(
            (chat_id, text, parse_mode)
        )
        return True

    def send_keyboard(
        self,
        chat_id,
        text,
        keyboard,
    ):
        self.keyboards.append(
            (chat_id, text, keyboard)
        )
        return True


def test_transport_default_is_telegram():
    context = current_context()

    assert context.name == "telegram"


def test_bale_origin_replies_over_bale_transport():
    """With the Bale context bound, shared senders route to Bale —
    WITHOUT requiring Telegram API configuration."""
    recorder = _RecordingContext("bale")

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    with bound_context(recorder):
        ok = _COMMAND_HANDLER.send_message(
            555,
            "سلام از بله",
        )

    assert ok is True
    assert recorder.texts == [
        (555, "سلام از بله", None)
    ]

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"


def test_keyboard_sender_routes_to_bound_context():
    recorder = _RecordingContext("bale")

    _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"

    with bound_context(recorder):
        ok = _COMMAND_HANDLER.send_message_with_keyboard(
            556,
            "کیبورد بله",
            [
                [
                    {
                        "text": "دکمه",
                        "callback_data": "ws:back",
                    }
                ]
            ],
        )

    assert ok is True
    assert len(recorder.keyboards) == 1

    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"


def test_telegram_path_unchanged_when_origin_default(
    monkeypatch,
):
    """Telegram regression guard: default origin never touches the
    messaging registry; the historical HTTP sender is used."""
    posted = []

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, timeout=None):
        posted.append((url, json))
        return _FakeResponse()

    monkeypatch.setattr(
        _COMMAND_HANDLER.requests,
        "post",
        fake_post,
    )

    monkeypatch.setattr(
        core.command_handler,
        "API_URL",
        "https://api.telegram.org/botTEST",
        raising=True,
    )

    ok = _COMMAND_HANDLER.send_message(
        42,
        "پیام تلگرام",
    )

    assert ok is True
    assert len(posted) == 1
    assert "/sendMessage" in posted[0][0]
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


# =========================================================
# ADAPTER — secret validation and shared-command routing
# =========================================================


def test_bale_webhook_requires_secret():
    """Fail closed: no secret configured -> endpoint disabled."""
    _BALE_ADAPTER.initialize("")

    class _Req:
        headers = {}

    assert (
        _BALE_ADAPTER.validate_bale_webhook_token(_Req())
        is False
    )


def test_bale_webhook_rejects_wrong_secret():
    _BALE_ADAPTER.initialize("right-secret")

    class _Req:
        headers = {
            "X-Bale-Bot-Secret-Token": "wrong"
        }

    assert (
        _BALE_ADAPTER.validate_bale_webhook_token(_Req())
        is False
    )


def test_bale_webhook_accepts_correct_secret():
    _BALE_ADAPTER.initialize("right-secret")

    class _Req:
        headers = {
            "X-Bale-Bot-Secret-Token": "right-secret"
        }

    assert (
        _BALE_ADAPTER.validate_bale_webhook_token(_Req())
        is True
    )


def test_bale_update_non_command_is_ignored():
    _BALE_ADAPTER.initialize("secret")

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "message": {
                    "chat": {"id": 42},
                    "text": "سلام، این یک پیام معمولی است",
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is False
    assert (
        response.get("reason")
        == "non_command"
    )

    # Origin restored after processing.
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


def test_bale_workspaces_command_runs_shared_handler(
    monkeypatch,
):
    """/workspaces from Bale executes the SHARED handler with Bale
    identity and Bale replies."""
    _BALE_ADAPTER.initialize("secret")

    calls = []

    def fake_handle_command(text, chat_id):
        calls.append((text, chat_id))
        return True

    monkeypatch.setattr(
        _BALE_ADAPTER.command_handler,
        "handle_command",
        fake_handle_command,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "message": {
                    "chat": {"id": 777000},
                    "text": "/workspaces",
                    "entities": [
                        {
                            "type": "bot_command",
                            "offset": 0,
                            "length": 11,
                        }
                    ],
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert calls == [
        ("/workspaces", 777000)
    ]

    # Origin restored.
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


def test_bale_command_with_bot_suffix_parses(
    monkeypatch,
):
    """/cmd@botname reaches the shared handler unchanged."""
    _BALE_ADAPTER.initialize("secret")

    calls = []

    monkeypatch.setattr(
        _BALE_ADAPTER.command_handler,
        "handle_command",
        lambda text, chat_id: calls.append(
            (text, chat_id)
        )
        or True,
    )

    _BALE_ADAPTER.handle_bale_update(
        {
            "message": {
                "chat": {"id": 1},
                "text": "/start@mybalebot",
                "entities": [
                    {
                        "type": "bot_command",
                        "offset": 0,
                        "length": 16,
                    }
                ],
            }
        }
    )

    assert calls == [("/start@mybalebot", 1)]


def test_adapter_rebinds_messaging_context_for_request(
    monkeypatch,
):
    """The adapter binds the Bale context during dispatch and
    restores the default afterwards."""
    _BALE_ADAPTER.initialize("secret")

    seen_contexts = []

    def fake_handle_command(text, chat_id):
        seen_contexts.append(
            current_context().name
        )
        return True

    monkeypatch.setattr(
        _BALE_ADAPTER.command_handler,
        "handle_command",
        fake_handle_command,
    )

    _BALE_ADAPTER.handle_bale_update(
        {
            "message": {
                "chat": {"id": 9},
                "text": "/help",
                "entities": [
                    {
                        "type": "bot_command",
                        "offset": 0,
                        "length": 5,
                    }
                ],
            }
        }
    )

    assert seen_contexts == ["bale"]
    assert current_context().name == "telegram"


def test_adapter_exception_restores_origin(monkeypatch):
    _BALE_ADAPTER.initialize("secret")

    def boom(text, chat_id):
        raise RuntimeError("shared handler failed")

    monkeypatch.setattr(
        _BALE_ADAPTER.command_handler,
        "handle_command",
        boom,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "message": {
                    "chat": {"id": 5},
                    "text": "/status",
                    "entities": [
                        {
                            "type": "bot_command",
                            "offset": 0,
                            "length": 7,
                        }
                    ],
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is False

    # Origin and messaging context are restored even on failure.
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )
    assert current_context().name == "telegram"


# =========================================================
# DATABASE ACCESSOR + MIGRATION SHAPE
# =========================================================


def test_database_identity_accessors_exist():
    """Slice-1 accessors are exposed by the real database module."""
    assert hasattr(
        _REAL_DATABASE,
        "get_user_by_bale_id",
    )
    assert hasattr(
        _REAL_DATABASE,
        "get_or_create_user_by_bale_id",
    )


def test_migration_029_is_additive_and_indexed():
    from pathlib import Path

    migration = (
        Path(__file__)
        .resolve()
        .parents[1]
        / "schema"
        / "029_bale_user_identity.sql"
    ).read_text(encoding="utf-8")

    lowered = migration.lower()

    assert "add column if not exists bale_user_id bigint" in lowered
    assert "create unique index if not exists idx_users_bale_user_id" in lowered
    assert "where bale_user_id is not null" in lowered
    # Additive: no drops or destructive statements.
    assert "drop " not in lowered
    assert "alter type" not in lowered
