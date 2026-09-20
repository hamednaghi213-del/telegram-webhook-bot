"""Focused B11 lifecycle routing tests, with no live transport calls."""

import os
import sys
import importlib
import core

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
if "supabase" not in sys.modules:
    fake_supabase = type(sys)("supabase")
    fake_supabase.create_client = lambda _url, _key: object()
    sys.modules["supabase"] = fake_supabase

from core import workspace_publisher  # noqa: E402
from core import bale_adapter, media_handler  # noqa: E402


def _database():
    return importlib.import_module("core.database")


def _real_database():
    module = _database()
    if hasattr(module, "get_publication_lifecycle_mapping"):
        return module
    sys.modules.pop("core.database", None)
    core.__dict__.pop("database", None)
    return importlib.import_module("core.database")


def _row(index_id, platform, chat, message_id, part="primary", ordinal=0):
    return {
        "id": index_id,
        "platform": platform,
        "destination_chat_id": chat,
        "message_id": message_id,
        "part_key": part,
        "part_ordinal": ordinal,
        "edit_status": "pending",
        "edit_fingerprint": None,
        "delete_status": "pending",
        "delete_attempt_count": 0,
    }


@pytest.fixture
def lifecycle_db(monkeypatch):
    database = _database()
    tg = _row(1, "telegram", "@telegram", 101)
    bale = _row(2, "bale", "@bale", 201)
    all_rows = [tg, bale]

    def lookup(platform, chat, message_id):
        source = next((row for row in all_rows if
            row["platform"] == platform and row["destination_chat_id"] == str(chat)
            and row["message_id"] == int(message_id)), None)
        if source is None:
            return None
        siblings = [row for row in all_rows if row["platform"] != platform]
        return {
            "source": source,
            "source_rows": tuple(row for row in all_rows if row["platform"] == platform),
            "counterparts": tuple(row for row in siblings if
                row["part_key"] == source["part_key"] and
                row["part_ordinal"] == source["part_ordinal"]),
            "counterpart_rows": tuple(siblings),
        }

    def claim(*, index_id, action, fingerprint=None, **_kwargs):
        row = next(row for row in all_rows if row["id"] == index_id)
        if row[f"{action}_status"] == "succeeded" and (
            action == "delete" or row["edit_fingerprint"] == fingerprint
        ):
            return False
        row[f"{action}_status"] = "sending"
        if action == "edit":
            row["edit_fingerprint"] = fingerprint
        else:
            row["delete_attempt_count"] += 1
        return True

    def finish(*, index_id, action, succeeded, **_kwargs):
        row = next(row for row in all_rows if row["id"] == index_id)
        row[f"{action}_status"] = "succeeded" if succeeded else "failed"
        return True

    for module in {database, getattr(core, "database", database)}:
        monkeypatch.setattr(module, "get_publication_lifecycle_mapping", lookup, raising=False)
        monkeypatch.setattr(module, "claim_publication_lifecycle_action", claim, raising=False)
        monkeypatch.setattr(module, "finish_publication_lifecycle_action", finish, raising=False)
    monkeypatch.setenv("BALE_BOT_TOKEN", "test-bale-token")
    return all_rows


def test_telegram_primary_edit_updates_bale_once(lifecycle_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.bale_forwarder.edit_bale_message",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    update = {"chat": {"id": "@telegram"}, "message_id": 101, "text": "Edited"}
    assert workspace_publisher.sync_edited_channel_post_to_bale(update)
    assert workspace_publisher.sync_edited_channel_post_to_bale(update)
    assert calls == [(("@bale", "test-bale-token", 201, "Edited"), {"is_caption": False})]
    # The Bale echo of this automated edit must not bounce to Telegram.
    monkeypatch.setattr(
        workspace_publisher, "_edit_telegram_message",
        lambda *args, **kwargs: pytest.fail("edit echo bounced"),
    )
    assert not workspace_publisher.sync_edited_bale_message_to_telegram({
        "chat": {"id": "@bale"}, "message_id": 201, "text": "Edited",
    })


def test_bale_primary_caption_edit_updates_telegram(lifecycle_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "_edit_telegram_message",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    assert workspace_publisher.sync_edited_bale_message_to_telegram({
        "chat": {"id": "@bale"}, "message_id": 201, "caption": "Caption",
    })
    assert calls == [(("@telegram", 101, "Caption"), {"is_caption": True})]


@pytest.mark.parametrize("origin", ["telegram", "bale"])
def test_followup_edit_targets_only_matching_part(lifecycle_db, monkeypatch, origin):
    tg_follow = _row(3, "telegram", "@telegram", 102, "followup:0")
    bale_follow = _row(4, "bale", "@bale", 202, "followup:0")
    lifecycle_db.extend([tg_follow, bale_follow])
    calls = []
    if origin == "telegram":
        monkeypatch.setattr(
            "core.bale_forwarder.edit_bale_message",
            lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        )
        assert workspace_publisher.sync_edited_channel_post_to_bale({
            "chat": {"id": "@telegram"}, "message_id": 102, "text": "Part",
        })
        assert calls[0][0][2] == 202
    else:
        monkeypatch.setattr(
            workspace_publisher, "_edit_telegram_message",
            lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        )
        assert workspace_publisher.sync_edited_bale_message_to_telegram({
            "chat": {"id": "@bale"}, "message_id": 202, "text": "Part",
        })
        assert calls[0][0][1] == 102
    assert calls[0][1]["is_caption"] is False


def test_edit_missing_mapping_is_noop(lifecycle_db, monkeypatch):
    monkeypatch.setattr(_database(), "get_publication_message_link", lambda *_: None, raising=False)
    assert not workspace_publisher.sync_edited_channel_post_to_bale({
        "chat": {"id": "@telegram"}, "message_id": 999, "text": "No map",
    })
    assert not workspace_publisher.sync_edited_bale_message_to_telegram({
        "chat": {"id": "@bale"}, "message_id": 999, "text": "No map",
    })


def test_failed_target_retries_without_reediting_successful_target(lifecycle_db, monkeypatch):
    second_bale = _row(5, "bale", "@second", 301)
    lifecycle_db.append(second_bale)
    calls = []

    def edit(chat, *_args, **_kwargs):
        calls.append(chat)
        return chat != "@second" or calls.count("@second") > 1

    monkeypatch.setattr("core.bale_forwarder.edit_bale_message", edit)
    update = {"chat": {"id": "@telegram"}, "message_id": 101, "text": "Retry"}
    assert not workspace_publisher.sync_edited_channel_post_to_bale(update)
    assert workspace_publisher.sync_edited_channel_post_to_bale(update)
    assert calls == ["@bale", "@second", "@second"]


@pytest.mark.parametrize("origin", ["telegram", "bale"])
def test_bot_delete_removes_primary_and_followups_once(lifecycle_db, monkeypatch, origin):
    lifecycle_db.extend([
        _row(3, "telegram", "@telegram", 102, "followup:0"),
        _row(4, "bale", "@bale", 202, "followup:0"),
    ])
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "_delete_telegram_message",
        lambda _api, chat, message_id: calls.append(("telegram", chat, message_id)) or True,
    )
    monkeypatch.setattr(
        "core.bale_forwarder.delete_bale_message",
        lambda chat, token, message_id, **_kwargs: (
            calls.append(("bale", chat, message_id)) or {"ok": True}
        ),
    )
    if origin == "telegram":
        invoke = lambda: workspace_publisher.delete_telegram_publication_and_sync_bale(
            api_url="https://telegram.test", telegram_chat_id="@telegram",
            telegram_message_id=101,
        )
    else:
        invoke = lambda: workspace_publisher.delete_bale_publication_and_sync_telegram(
            bale_chat_id="@bale", bale_message_id=201,
            api_url="https://telegram.test",
        )
    assert invoke()
    assert invoke()
    assert len(calls) == 4
    assert {call[2] for call in calls} == {101, 102, 201, 202}


def test_delete_failure_retries_only_failed_message(lifecycle_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "_delete_telegram_message",
        lambda _api, chat, message_id: calls.append(message_id) or message_id != 101
        or calls.count(101) > 1,
    )
    monkeypatch.setattr(
        "core.bale_forwarder.delete_bale_message",
        lambda *_args, **_kwargs: {"ok": True},
    )
    invoke = lambda: workspace_publisher.delete_bale_publication_and_sync_telegram(
        bale_chat_id="@bale", bale_message_id=201,
        api_url="https://telegram.test",
    )
    assert not invoke()
    assert invoke()
    assert calls == [101, 101]


def test_bale_edited_command_is_consumed_as_lifecycle(monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "sync_edited_bale_message_to_telegram",
        lambda message: calls.append(message) or False,
    )
    monkeypatch.setattr(
        bale_adapter.command_handler, "handle_command",
        lambda *_args: pytest.fail("edited command entered command handler"),
    )
    result, status = bale_adapter.handle_bale_update({
        "edited_message": {
            "chat": {"id": 5, "type": "private"},
            "from": {"id": 5}, "message_id": 3, "text": "/status",
        }
    })
    assert status == 200
    assert result["handled"] is True
    assert calls[0]["_is_edited"] is True


def test_bale_edited_caption_is_extracted_without_content_fallthrough(monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "sync_edited_bale_message_to_telegram",
        lambda message: calls.append(message) or False,
    )
    result, status = bale_adapter.handle_bale_update({
        "edited_message": {
            "chat": {"id": 5}, "message_id": 4,
            "caption": "Changed", "photo": [{"file_id": "bale-id"}],
        }
    })
    assert status == 200 and result["handled"] is True
    assert calls[0]["caption"] == "Changed"


def test_telegram_album_returns_all_member_ids_for_b11_index(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "result": [
                {"message_id": 101}, {"message_id": 102},
            ]}

    monkeypatch.setattr(media_handler, "telegram_post", lambda *_args, **_kwargs: Response())
    outcome = media_handler.send_media_group_to_channel(
        [{"type": "photo", "file_id": "tg-file-1"},
         {"type": "photo", "file_id": "tg-file-2"}],
        channel_id="@telegram", api_url="https://telegram.test",
        return_result=True,
    )
    assert outcome["ok"] is True
    assert outcome["message_ids"] == (101, 102)


def test_b11_mapping_matches_part_and_album_ordinal(monkeypatch):
    source_delivery = {"id": 10, "source_id": 7, "delivery_generation": 1,
                       "platform": "telegram"}
    target_delivery = {"id": 20, "source_id": 7, "delivery_generation": 1,
                       "platform": "bale"}
    source = {**_row(11, "telegram", "@telegram", 102, ordinal=1),
              "delivery_id": 10}
    target_first = {**_row(21, "bale", "@bale", 201, ordinal=0),
                    "delivery_id": 20}
    target_second = {**_row(22, "bale", "@bale", 202, ordinal=1),
                     "delivery_id": 20}
    unrelated = {**_row(31, "bale", "@other", 301, "followup:0"),
                 "delivery_id": 20}

    class Query:
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def limit(self, *_args): return self
        def execute(self): return type("Result", (), {"data": [source]})()

    class Service:
        def table(self, name):
            assert name == "publication_delivery_message_index"
            return Query()

    db = _real_database()
    monkeypatch.setattr(db, "service_supabase", Service())
    monkeypatch.setattr(db, "get_persistent_publication_delivery_by_id",
                        lambda _id: source_delivery)
    monkeypatch.setattr(db, "list_persistent_publication_deliveries_for_source",
                        lambda **_kwargs: (source_delivery, target_delivery))
    monkeypatch.setattr(db, "list_persistent_publication_message_indexes",
                        lambda **_kwargs: (source, target_first, target_second, unrelated))
    mapping = db.get_publication_lifecycle_mapping("telegram", "@telegram", 102)
    assert [row["message_id"] for row in mapping["counterparts"]] == [202]
    assert {row["message_id"] for row in mapping["counterpart_rows"]} == {201, 202, 301}


def test_telegram_delete_without_mapping_is_handled(monkeypatch):
    db = _database()
    monkeypatch.setattr(db, "get_publication_lifecycle_mapping", lambda *_args: None, raising=False)
    monkeypatch.setattr(db, "get_publication_sync_targets_for_telegram_message",
                        lambda *_args: None, raising=False)
    monkeypatch.setattr(db, "mark_persistent_publication_delivery_delete_state",
                        lambda **_kwargs: None, raising=False)
    calls = []
    monkeypatch.setattr(
        workspace_publisher, "_delete_telegram_message",
        lambda *_args: calls.append(True) or True,
    )
    assert workspace_publisher.delete_telegram_publication_and_sync_bale(
        api_url="https://telegram.test", telegram_chat_id="@telegram",
        telegram_message_id=999,
    )
    assert calls == [True]


def test_already_deleted_bale_counterpart_is_idempotent(lifecycle_db, monkeypatch):
    monkeypatch.setattr(workspace_publisher, "_delete_telegram_message",
                        lambda *_args: True)
    monkeypatch.setattr(
        "core.bale_forwarder.delete_bale_message",
        lambda *_args, **_kwargs: {
            "ok": False,
            "response": {"description": "Bad Request: message to delete not found"},
        },
    )
    assert workspace_publisher.delete_telegram_publication_and_sync_bale(
        api_url="https://telegram.test", telegram_chat_id="@telegram",
        telegram_message_id=101,
    )
    assert lifecycle_db[1]["delete_status"] == "succeeded"


def test_persistent_index_claim_suppresses_echo_and_allows_new_edit(monkeypatch):
    row = {**_row(1, "telegram", "@telegram", 101),
           "edit_attempt_count": 0, "edit_lease_expires_at": None,
           "delete_lease_expires_at": None}

    class Query:
        def __init__(self):
            self.filters = []
            self.payload = None

        def select(self, *_args): return self
        def limit(self, *_args): return self
        def eq(self, key, value):
            self.filters.append((key, value))
            return self
        def update(self, payload):
            self.payload = payload
            return self
        def execute(self):
            found = all(row.get(key) == value for key, value in self.filters)
            if found and self.payload is not None:
                row.update(self.payload)
            return type("Result", (), {"data": [dict(row)] if found else []})()

    class Service:
        def table(self, name):
            assert name == "publication_delivery_message_index"
            return Query()

    db = _real_database()
    monkeypatch.setattr(db, "service_supabase", Service())
    assert db.claim_publication_lifecycle_action(
        index_id=1, action="edit", fingerprint="first",
    )
    assert not db.claim_publication_lifecycle_action(
        index_id=1, action="edit", fingerprint="first",
    )
    assert db.finish_publication_lifecycle_action(
        index_id=1, action="edit", fingerprint="first", succeeded=True,
    )
    assert not db.claim_publication_lifecycle_action(
        index_id=1, action="edit", fingerprint="first",
    )
    assert db.claim_publication_lifecycle_action(
        index_id=1, action="edit", fingerprint="second",
    )


def test_delete_updates_existing_delivery_state(lifecycle_db, monkeypatch):
    lifecycle_db[0]["delivery_id"] = 10
    lifecycle_db[1]["delivery_id"] = 20
    states = []
    monkeypatch.setattr(
        _database(), "mark_persistent_publication_delivery_delete_state",
        lambda **kwargs: states.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(workspace_publisher, "_delete_telegram_message",
                        lambda *_args: True)
    monkeypatch.setattr(
        "core.bale_forwarder.delete_bale_message",
        lambda *_args, **_kwargs: {"ok": True},
    )
    assert workspace_publisher.delete_telegram_publication_and_sync_bale(
        api_url="https://telegram.test", telegram_chat_id="@telegram",
        telegram_message_id=101,
    )
    assert {(item["delivery_id"], item["delete_status"]) for item in states} == {
        (10, "succeeded"), (20, "succeeded"),
    }
