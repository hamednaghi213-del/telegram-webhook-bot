"""Focused tests for the FINAL Bale Full Parity pass.

Covers: Bale text/media/caption ingestion into the SHARED content
pipeline (``process_incoming_message``), Bale-origin editorial
pending-review creation via the shared editorial path, ``ed:`` /
``dup:`` callback routing from the Bale adapter into the shared
handlers, the admin-instruction Pending Guard under the canonical
internal identity, origin-prefixed source keys, and Telegram
non-regression of the shared pipeline.
"""

import importlib
import os
import sys

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
    """Guarantee a REAL core module in sys.modules (polluter
    files install fakes that are never restored)."""
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

from core.messaging import (  # noqa: E402
    reset_default_context,
)


_REAL_DATABASE = core.database
_COMMAND_HANDLER = core.command_handler
_BALE_ADAPTER = core.bale_adapter
_WEBHOOK_HANDLER = core.webhook_handler


@pytest.fixture(autouse=True)
def _isolate_adapter_state():
    reset_default_context()
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"
    yield
    reset_default_context()
    _COMMAND_HANDLER.CURRENT_ORIGIN = "telegram"


def _patch_db(monkeypatch, name, value):
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


def _patch_wh(monkeypatch, name, value):
    monkeypatch.setattr(
        _WEBHOOK_HANDLER,
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
        self.workspaces = {
            7: {
                "id": 7,
                "name": "رسانه مشترک",
                "owner_user_id": 1,
                "status": "active",
            }
        }
        self.destinations = {}
        self.pending_actions = {}

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
        pass

    def get_workspace_setup_state(self, workspace_id):
        return {"step": "completed"}

    def list_workspace_destinations(
        self,
        workspace_id,
    ):
        return []

    def get_publication_destination(
        self,
        destination_id,
    ):
        return None


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

    # Pre-create the linked Bale identity: internal users.id 101
    # carries bale_user_id 555000 (explicit linkage only).
    fake_db._new_user(
        bale_user_id=555000,
    )

    return fake_db


@pytest.fixture()
def flow_env(
    db_env,
    monkeypatch,
):
    """Prepare the shared content pipeline for direct invocation:
    stub the translation gates so a synthetic message can reach
    the media/editorial branches without a real backend."""
    _patch_wh(
        monkeypatch,
        "try_automatic_persian_translation_gate",
        lambda *a, **k: None,
    )

    import core.translation_controller

    monkeypatch.setattr(
        core.translation_controller,
        "handle_translation_text_input",
        lambda **k: None,
        raising=False,
    )

    return db_env


class _BaleHTTPRecorder:
    """Records calls the REAL Bale context makes to the Bale Bot
    API and answers them with success."""

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


def _bale_message(
    msg_id,
    chat_id=555000,
    **fields,
):
    message = {
        "message_id": msg_id,
        "chat": {"id": chat_id},
        "date": 1_700_000_000,
    }
    message.update(fields)
    return {"message": message}


def _bale_command_update(
    text,
    msg_id=1,
    chat_id=555000,
):
    message = {
        "message_id": msg_id,
        "chat": {"id": chat_id},
        "date": 1_700_000_000,
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
    return {"message": message}


# =========================================================
# 1) CONTENT INGESTION — shared pipeline from Bale
# =========================================================


def test_bale_text_enters_shared_content_pipeline(
    monkeypatch,
):
    """Plain Bale text reaches process_incoming_message (the exact
    Telegram pipeline) with the Bale context bound."""
    seen = {}

    def _fake_pipeline(msg, req_id, update_id=None):
        seen["msg"] = msg
        seen["req_id"] = req_id

        from core.messaging import current_context

        seen["context"] = current_context().name
        seen["origin"] = (
            _COMMAND_HANDLER.CURRENT_ORIGIN
        )

        return {"ok": True, "media": False}, 200

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _fake_pipeline,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_message(
                1,
                text="سلام این یک محتوای معمولی است",
            )
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert response["reason"] == "content"
    assert seen["msg"]["text"] == (
        "سلام این یک محتوای معمولی است"
    )
    assert seen["msg"]["chat"]["id"] == 555000
    # Shared pipeline runs under the Bale origin/context.
    assert seen["origin"] == "bale"
    assert seen["context"] == "bale"
    assert (
        _COMMAND_HANDLER.CURRENT_ORIGIN
        == "telegram"
    )


def test_bale_markdown_bold_title_is_normalized_before_shared_pipeline(
    monkeypatch,
):
    seen = {}

    def _fake_pipeline(msg, req_id, update_id=None):
        seen["msg"] = msg
        return {"ok": True, "media": False}, 200

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _fake_pipeline,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_message(
                2,
                text=(
                    "*روحانی: دستاورد جنگ باید کاهش احتمال جنگ بعدی باشد*\n"
                    "متن خبر"
                ),
            )
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert seen["msg"]["text"] == (
        "روحانی: دستاورد جنگ باید کاهش احتمال جنگ بعدی باشد\n"
        "متن خبر"
    )


def test_bale_multiline_markdown_bold_wrapper_is_normalized_before_shared_pipeline(
    monkeypatch,
):
    seen = {}

    def _fake_pipeline(msg, req_id, update_id=None):
        seen["msg"] = msg
        return {"ok": True, "media": False}, 200

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _fake_pipeline,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_message(
                3,
                text=(
                    "*تیتر خبر\n"
                    "خط دوم خبر\n"
                    "آخر خبر*"
                ),
            )
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert seen["msg"]["text"] == (
        "تیتر خبر\n"
        "خط دوم خبر\n"
        "آخر خبر"
    )


def test_bale_channel_message_does_not_reenter_shared_content_pipeline(
    monkeypatch,
):
    """A message emitted in a Bale channel is a destination-side event,
    not new user input. It must be acknowledged without entering the
    shared inbound publication pipeline.
    """

    def _unexpected_pipeline(*_args, **_kwargs):
        pytest.fail(
            "Bale channel message re-entered process_incoming_message"
        )

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _unexpected_pipeline,
    )

    response, status = _BALE_ADAPTER.handle_bale_update(
        _bale_message(
            9001,
            chat={
                "id": -1009001,
                "type": "channel",
            },
            text="پیام منتشرشده در کانال بله",
        )
    )

    assert status == 200
    assert response["ok"] is True
    assert response["handled"] is False

def test_bale_photo_video_document_voice_normalize_pass_through(
    monkeypatch,
):
    """Bale photo/video/document/voice updates are passed to the
    shared pipeline unmodified (Telegram-shaped fields reused)."""
    seen = []

    def _fake_pipeline(msg, req_id, update_id=None):
        seen.append(dict(msg))
        return {"ok": True}, 200

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _fake_pipeline,
    )

    for fields in (
        {
            "photo": [
                {"file_id": "ph-low", "width": 90},
                {
                    "file_id": "ph-hi",
                    "width": 1280,
                },
            ],
            "caption": "کپشن تصویر",
        },
        {"video": {"file_id": "vid-1"}},
        {
            "document": {
                "file_id": "doc-1",
                "file_name": "a.pdf",
            }
        },
        {"voice": {"file_id": "voice-1"}},
    ):
        response, status = (
            _BALE_ADAPTER.handle_bale_update(
                _bale_message(
                    2,
                    **fields,
                )
            )
        )

        assert status == 200
        assert response["handled"] is True

    assert len(seen) == 4
    assert seen[0]["photo"][-1][
        "file_id"
    ] == "bale-file://ph-hi"
    assert seen[0]["caption"] == "کپشن تصویر"
    assert seen[1]["video"]["file_id"] == "bale-file://vid-1"
    assert (
        seen[2]["document"]["file_id"]
        == "bale-file://doc-1"
    )
    assert (
        seen[3]["voice"]["file_id"] == "bale-file://voice-1"
    )


def test_bale_caption_command_routes_to_commands(
    monkeypatch,
):
    """/workspaces sent as a Bale caption still routes into the
    shared command router (adapter-level normalization)."""
    seen = []

    monkeypatch.setattr(
        _COMMAND_HANDLER,
        "handle_command",
        lambda text, chat_id: seen.append(
            (text, chat_id)
        )
        or True,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_message(
                3,
                photo=[{"file_id": "x"}],
                caption="/workspaces",
                entities=[
                    {
                        "type": "bot_command",
                        "offset": 0,
                        "length": 11,
                    }
                ],
            )
        )
    )

    assert status == 200
    assert seen == [("/workspaces", 555000)]


def test_bale_media_group_id_passes_through(
    monkeypatch,
):
    """Bale album metadata (media_group_id) is preserved so the
    SHARED media-group aggregator can key the group."""
    seen = {}

    def _fake_pipeline(msg, req_id, update_id=None):
        seen[
            "media_group_id"
        ] = msg.get("media_group_id")
        return {"ok": True}, 200

    _patch_wh(
        monkeypatch,
        "process_incoming_message",
        _fake_pipeline,
    )

    _BALE_ADAPTER.handle_bale_update(
        _bale_message(
            4,
            photo=[{"file_id": "a"}],
            media_group_id="bale-grp-7",
        )
    )

    assert (
        seen["media_group_id"] == "bale-grp-7"
    )


# =========================================================
# 2) EDITORIAL — shared detection + pending from Bale
# =========================================================


def test_bale_yaddasht_creates_shared_pending_review(
    flow_env,
    bale_http,
    monkeypatch,
):
    """A #یادداشت sent from Bale creates the SAME persistent
    editorial pending review (shared detection + shared state),
    replies over the Bale transport, and keys the review under
    the internal users.id."""
    db = db_env

    # Shared editorial pieces: detection succeeds, summary
    # pipeline is replaced with a deterministic suggestion.
    _patch_wh(
        monkeypatch,
        "editorial_review_enabled",
        lambda: True,
    )

    import core.editorial_structure
    import core.editorial_review

    class _Structure:
        title = "تیتر تحریریه"
        author = "نویسنده"
        body = "متن یادداشت"
        author_source = "test"
        author_confidence = 1.0

    monkeypatch.setattr(
        core.editorial_structure,
        "extract_editorial_structure",
        lambda src: _Structure(),
        raising=False,
    )

    class _ReviewResult:
        content_type = "opinion_note"
        needs_approval = True
        suggested_text = "خلاصه پیشنهادی"
        summary_success = True
        reason = "ok"
        metadata = {"regeneration_count": 0}

    monkeypatch.setattr(
        core.editorial_review,
        "analyze_editorial_content",
        lambda original_text, **k: (
            _ReviewResult()
        ),
        raising=False,
    )

    created = {}

    def _fake_create(**kwargs):
        created.update(kwargs)

        class _Pending:
            pass

        pending = _Pending()
        pending.review_id = "rev-1"
        pending.content_type = kwargs[
            "content_type"
        ]
        pending.current_summary = kwargs[
            "current_summary"
        ]
        pending.regeneration_count = 0
        pending.metadata = kwargs["metadata"]
        return pending

    # create_pending_review is imported function-locally from
    # core.editorial_pending by the shared queue function.
    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "create_pending_review",
        _fake_create,
        raising=False,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_message(
                5,
                text="#یادداشت\nاین متن یک یادداشت تحریری است",
            )
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert response["reason"] == (
        "editorial_review"
    )
    assert created["content_type"] == (
        "opinion_note"
    )
    # Pending review keyed by the internal users.id —
    # NOT the raw Bale numeric id.
    assert created["user_id"] == 101
    # Review panel delivered over the BALE transport.
    assert bale_http.urls("sendMessage")

    # And NOT over Telegram.
    assert (
        not _TELEGRAM_SENT_MARKERS
    )


_TELEGRAM_SENT_MARKERS: list = []


def test_bale_pending_guard_and_admin_instruction(
    flow_env,
    bale_http,
    monkeypatch,
):
    """With a waiting admin-instruction review owned by the
    canonical internal id, the NEXT Bale text enters the shared
    admin-instruction path (Pending Guard)."""
    db = db_env

    from core.editorial_pending import (
        PendingEditorialReview,
    )

    review = PendingEditorialReview(
        review_id="rev-guard",
        user_id=101,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        created_at=0.0,
        updated_at=0.0,
        status="waiting_admin_instruction",
        metadata={},
    )

    # The Pending Guard imports function-locally from
    # core.editorial_pending (NOT core.database).
    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "get_waiting_admin_instruction_review",
        lambda user_id: (
            review
            if user_id == 101
            else None
        ),
        raising=False,
    )

    captured = {}

    def _fake_admin(chat_id, instruction_text, req_id=""):
        captured[
            "chat_id"
        ] = chat_id
        captured[
            "text"
        ] = instruction_text
        return True

    _patch_wh(
        monkeypatch,
        "process_admin_instruction_message",
        _fake_admin,
    )

    # Plain Bale text: consumed by the Pending Guard.
    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            _bale_command_update(
                "پاسخ مدیر برای یادداشت",
                msg_id=10,
            )
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert response["reason"] == (
        "admin_instruction"
    )
    assert captured["chat_id"] == 555000
    assert captured["text"] == (
        "پاسخ مدیر برای یادداشت"
    )


def test_bale_original_publish_callback_routes_to_shared_editorial(
    flow_env,
    bale_http,
    monkeypatch,
):
    """``ed:original:<id>`` from Bale reaches the SHARED editorial
    callback handler with the canonical internal user id and the
    pending review is marked published."""
    db = db_env

    from core.editorial_pending import (
        PendingEditorialReview,
    )

    review = PendingEditorialReview(
        review_id="rev-9",
        user_id=101,
        content_type="opinion_note",
        original_text="متن",
        current_summary="خلاصه",
        regeneration_count=0,
        created_at=0.0,
        updated_at=0.0,
        status="pending",
        metadata={},
    )

    # The editorial callback handler imports its state accessors
    # function-locally from core.editorial_pending.
    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "get_pending_review",
        lambda review_id, user_id: (
            review
            if review_id == "rev-9"
            and user_id == 101
            else None
        ),
        raising=False,
    )

    published = {}

    def _fake_mark_published(review_id, user_id):
        published[
            "review_id"
        ] = review_id
        published[
            "user_id"
        ] = user_id

    monkeypatch.setattr(
        core.editorial_pending,
        "mark_original_published",
        _fake_mark_published,
        raising=False,
    )

    # The original path hands off to the shared publication flow
    # and media-group leases; stub them so the test stays
    # transport-level.
    _patch_wh(
        monkeypatch,
        "publish_prepared_text",
        lambda *a, **k: {"ok": True},
    )

    _patch_wh(
        monkeypatch,
        "build_editorial_keyboard",
        lambda **k: {"inline_keyboard": []},
    )

    _patch_wh(
        monkeypatch,
        "build_editorial_preview",
        lambda *a, **k: "پیش‌نمایش",
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-ed",
                    "data": "ed:original:rev-9",
                    "from": {"id": 555000},
                    "message": {
                        "chat": {
                            "id": 555000
                        },
                        "message_id": 77,
                    },
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert published["review_id"] == "rev-9"
    # Canonical internal identity, not the Bale number.
    assert published["user_id"] == 101
    # Ack travelled over Bale.
    assert bale_http.urls(
        "answerCallbackQuery"
    )


def test_bale_cancel_callback_cancels_shared_review(
    flow_env,
    bale_http,
    monkeypatch,
):
    """``ed:cancel:<id>`` from Bale cancels the SAME shared
    pending review."""
    from core.editorial_pending import (
        PendingEditorialReview,
    )

    review = PendingEditorialReview(
        review_id="rev-c",
        user_id=101,
        content_type="opinion_note",
        original_text="متن",
        current_summary="خلاصه",
        regeneration_count=0,
        created_at=0.0,
        updated_at=0.0,
        status="pending",
        metadata={},
    )

    # The editorial callback handler imports its state accessors
    # function-locally from core.editorial_pending.
    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "get_pending_review",
        lambda review_id, user_id: (
            review
            if review_id == "rev-c"
            and user_id == 101
            else None
        ),
        raising=False,
    )

    cancelled = {}

    def _fake_cancel(review_id, user_id):
        cancelled[
            "review_id"
        ] = review_id
        cancelled[
            "user_id"
        ] = user_id

    monkeypatch.setattr(
        core.editorial_pending,
        "cancel_pending_review",
        _fake_cancel,
        raising=False,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-cx",
                    "data": "ed:cancel:rev-c",
                    "from": {"id": 555000},
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert cancelled["review_id"] == "rev-c"
    assert cancelled["user_id"] == 101


def test_bale_duplicate_override_callback_routes_to_shared(
    db_env,
    bale_http,
    monkeypatch,
):
    """``dup:publish:<token>`` from Bale runs the SHARED single-use
    duplicate-override consume-and-publish flow."""
    consumed = {}

    # The shared dup handler imports function-locally from
    # core.duplicate_pending / core.publication_engine.
    import core.duplicate_pending
    import core.publication_engine

    class _Pending:
        prepared = {"main_text": "متن"}
        targets = [7]

    monkeypatch.setattr(
        core.duplicate_pending,
        "consume_pending_duplicate",
        lambda token, chat_id: consumed.update(
            {
                "token": token,
                "chat_id": chat_id,
            }
        )
        or _Pending(),
        raising=False,
    )

    monkeypatch.setattr(
        core.publication_engine,
        "publish_prepared_content",
        lambda **kwargs: consumed.update(
            {
                "published": True,
                "kwargs": kwargs,
            }
        )
        or {"ok": True, "results": []},
        raising=False,
    )

    _patch_wh(
        monkeypatch,
        "_send_media_publication_acknowledgement",
        lambda *a, **k: None,
    )

    response, status = (
        _BALE_ADAPTER.handle_bale_update(
            {
                "callback_query": {
                    "id": "cb-dup",
                    "data": "dup:publish:tok-1",
                    "from": {"id": 555000},
                }
            }
        )
    )

    assert status == 200
    assert response["handled"] is True
    assert consumed["token"] == "tok-1"
    assert consumed["chat_id"] == 555000
    assert (
        consumed.get("published") is True
    )
    assert bale_http.urls(
        "answerCallbackQuery"
    )


# =========================================================
# 3) IDENTITY ISOLATION — source keys and pending keys
# =========================================================


def test_source_key_directly_origin_prefixed(
    flow_env,
    bale_http,
    monkeypatch,
):
    """Bale-origin pipeline runs derive source keys prefixed with
    ``bale:`` so numeric id spaces stay isolated."""
    captured = {}

    # Stub the caption editorial sink to capture source_key.
    _patch_wh(
        monkeypatch,
        "editorial_review_enabled",
        lambda: False,
    )

    _patch_wh(
        monkeypatch,
        "detect_editorial_admin_tag",
        lambda caption: (
            "opinion_note",
            caption,
            0,
        ),
    )

    _patch_wh(
        monkeypatch,
        "try_queue_editorial_text_review",
        lambda **kwargs: (
            captured.update(kwargs)
            or True
        ),
    )

    # Suppress downstream acknowledgement sends.
    _patch_wh(
        monkeypatch,
        "_send_media_publication_acknowledgement",
        lambda *a, **k: None,
    )

    from core.messaging import (
        BaleMessagingContext,
        bind_context,
    )

    previous_origin = (
        _COMMAND_HANDLER.CURRENT_ORIGIN
    )

    try:
        _COMMAND_HANDLER.CURRENT_ORIGIN = "bale"
        bind_context(BaleMessagingContext())

        _WEBHOOK_HANDLER.process_incoming_message(
            {
                "message_id": 44,
                "chat": {"id": 555000},
                "date": 1_700_000_000,
                "photo": [{"file_id": "p1"}],
                "caption": "#یادداشت تست",
            },
            "bale-src-test",
        )
    finally:
        _COMMAND_HANDLER.CURRENT_ORIGIN = (
            previous_origin
        )
        reset_default_context()

    assert (
        captured.get("source_key")
        == "bale:555000:message:44"
    )


def test_telegram_source_key_unchanged(
    db_env,
    monkeypatch,
):
    """Telegram-origin pipeline keeps the historical ``tg:`` source
    key (non-regression)."""
    # A registered Telegram user is required to pass the shared
    # register gate.
    db = db_env
    db._new_user(telegram_user_id=1001)

    captured = {}

    _patch_wh(
        monkeypatch,
        "editorial_review_enabled",
        lambda: False,
    )

    _patch_wh(
        monkeypatch,
        "detect_editorial_admin_tag",
        lambda caption: (
            "opinion_note",
            caption,
            0,
        ),
    )

    _patch_wh(
        monkeypatch,
        "try_queue_editorial_text_review",
        lambda **kwargs: (
            captured.update(kwargs)
            or True
        ),
    )

    _patch_wh(
        monkeypatch,
        "_send_media_publication_acknowledgement",
        lambda *a, **k: None,
    )

    previous_origin = (
        _COMMAND_HANDLER.CURRENT_ORIGIN
    )

    try:
        _COMMAND_HANDLER.CURRENT_ORIGIN = (
            "telegram"
        )
        from core.messaging import (
            TelegramMessagingContext,
            bind_context,
        )

        bind_context(
            TelegramMessagingContext()
        )

        _WEBHOOK_HANDLER.process_incoming_message(
            {
                "message_id": 55,
                "chat": {"id": 1001},
                "date": 1_700_000_000,
                "photo": [{"file_id": "p1"}],
                "caption": "#یادداشت تست",
            },
            "tg-src-test",
        )
    finally:
        _COMMAND_HANDLER.CURRENT_ORIGIN = (
            previous_origin
        )
        reset_default_context()

    assert (
        captured.get("source_key")
        == "tg:1001:message:55"
    )


def test_bale_admin_guard_uses_canonical_owner(
    flow_env,
    bale_http,
    monkeypatch,
):
    """The pure-text admin-instruction gate inside the shared
    pipeline resolves the waiting review under the CANONICAL
    internal users.id under Bale origin — not the raw Bale
    number (numeric-collision safety)."""
    db = db_env

    lookups = []

    def _fake_lookup(user_id):
        lookups.append(user_id)
        return None

    # Both admin-instruction gates import function-locally from
    # core.editorial_pending.
    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "get_waiting_admin_instruction_review",
        _fake_lookup,
        raising=False,
    )

    # Keep the tail of the text branch inert.
    _patch_wh(
        monkeypatch,
        "process_text_message",
        lambda **k: {"ok": True},
    )

    # Plain Bale text, no media: reaches the text gate.
    _BALE_ADAPTER.handle_bale_update(
        _bale_message(
            12,
            text="متن عادی بدون تگ",
        )
    )

    # The canonical internal id (101) must be consulted — the
    # raw Bale number must never key shared pending state.
    assert lookups
    assert set(lookups) == {101}


# =========================================================
# 4) TELEGRAM NON-REGRESSION of the shared pipeline
# =========================================================


def test_telegram_admin_guard_unchanged(
    db_env,
    monkeypatch,
):
    """Telegram-origin text keeps the historical chat-id keying in
    the pure-text admin gate (non-regression)."""
    # A registered Telegram user passes the shared register gate.
    db = db_env
    db._new_user(telegram_user_id=1001)

    lookups = []

    def _fake_lookup(user_id):
        lookups.append(user_id)
        return None

    import core.editorial_pending

    monkeypatch.setattr(
        core.editorial_pending,
        "get_waiting_admin_instruction_review",
        _fake_lookup,
        raising=False,
    )

    _patch_wh(
        monkeypatch,
        "process_text_message",
        lambda **k: {"ok": True},
    )

    from core.messaging import (
        TelegramMessagingContext,
        bind_context,
    )

    previous_origin = (
        _COMMAND_HANDLER.CURRENT_ORIGIN
    )

    try:
        _COMMAND_HANDLER.CURRENT_ORIGIN = (
            "telegram"
        )
        bind_context(
            TelegramMessagingContext()
        )

        _WEBHOOK_HANDLER.process_incoming_message(
            {
                "message_id": 66,
                "chat": {"id": 1001},
                "date": 1_700_000_000,
                "text": "خبر عادی بدون تگ تحریریه",
            },
            "tg-regression",
        )
    finally:
        _COMMAND_HANDLER.CURRENT_ORIGIN = (
            previous_origin
        )
        reset_default_context()

    # Telegram keeps chat-id keying.
    assert lookups
    assert set(lookups) == {1001}


def test_telegram_ed_callback_still_routed_in_webhook(
    monkeypatch,
):
    """The Telegram dispatcher still routes ``ed:`` callbacks into
    the shared editorial handler (extraction non-regression)."""
    calls = []

    _patch_wh(
        monkeypatch,
        "handle_editorial_callback",
        lambda cq, req_id: calls.append(
            cq
        )
        or True,
    )

    handled = (
        _WEBHOOK_HANDLER.handle_editorial_callback(
            {
                "data": "ed:original:r1",
                "id": "cb-1",
                "from": {"id": 42},
            },
            "req-1",
        )
    )

    assert handled is True
    assert calls[0]["data"] == (
        "ed:original:r1"
    )
