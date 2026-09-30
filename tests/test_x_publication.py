import sys
import types
from types import SimpleNamespace

import pytest
import requests

from core import publication_engine as engine, x_publisher as x, x_oauth
from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore
from core.x_publication_state import execute_x_delivery


@pytest.fixture
def context(monkeypatch):
    connection = {"connection_status": "connected", "x_user_id": "123",
                  "x_username": "account", "granted_scopes": ["tweet.write", "media.write"]}
    db = types.ModuleType("core.database")
    db.get_x_oauth_connection = lambda *_: connection
    db.get_user_by_telegram_id = lambda *_: None
    db.update_x_oauth_connection_status = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "core.database", db)
    import core
    monkeypatch.setattr(core, "database", db, raising=False)
    monkeypatch.setattr(x_oauth, "get_valid_x_access_token", lambda *_: "secret-token")
    monkeypatch.setattr(x.time, "sleep", lambda *_: None)
    target = PublicationTarget("x1", "workspace", "x", "x:123", 1, 9)
    return target, connection, db


def response(status=201, body=None, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {},
                           json=lambda: body if body is not None else {"data": {"id": "987654321012345678"}})


def publish(context, monkeypatch, responses, files=()):
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(x.requests, "request", request)
    armed = []
    released = []
    result = x.publish_x(context[0], "caption", files,
                         lambda: armed.append(True) or True,
                         lambda: released.append(True))
    return result, calls, armed, released


def test_text_uses_user_token_and_returns_transport_proof(context, monkeypatch):
    result, calls, armed, released = publish(context, monkeypatch, [response()])
    assert result.success and result.primary_message_id == 987654321012345678
    assert calls[0][1] == "https://api.x.com/2/tweets"
    assert calls[0][2]["json"] == {"text": "caption"}
    assert calls[0][2]["headers"] == {"Authorization": "Bearer secret-token"}
    assert calls[0][2]["allow_redirects"] is False
    assert armed and not released
    assert result.raw_result["message_url"].endswith(str(result.primary_message_id))


@pytest.mark.parametrize("status", [400, 403, 422])
def test_definite_rejection_releases_guard(context, monkeypatch, status):
    result, calls, _, released = publish(context, monkeypatch, [response(status)])
    assert not result.success and result.status_code == status
    assert len(calls) == 1 and released


@pytest.mark.parametrize("failure", [requests.Timeout("secret-token"), response(503),
                                    response(body={"data": {}}), response(body=[])])
def test_ambiguous_response_never_replays_post(context, monkeypatch, failure):
    result, calls, _, released = publish(context, monkeypatch, [failure])
    assert not result.success and result.error.startswith("x_delivery_unknown")
    assert len(calls) == 1 and not released
    assert "secret-token" not in result.error


def test_401_refreshes_once_using_existing_lifecycle(context, monkeypatch):
    refreshed = []
    monkeypatch.setattr(x_oauth, "refresh_x_oauth_connection",
                        lambda dest: refreshed.append(dest) or SimpleNamespace(access_token="new-token"))
    result, calls, _, _ = publish(context, monkeypatch, [response(401), response()])
    assert result.success and refreshed == [9]
    assert calls[1][2]["headers"]["Authorization"] == "Bearer new-token"


def test_repeated_401_marks_reconnect(context, monkeypatch):
    statuses = []
    context[2].update_x_oauth_connection_status = lambda *args, **kw: statuses.append(args)
    monkeypatch.setattr(x_oauth, "refresh_x_oauth_connection",
                        lambda _: SimpleNamespace(access_token="new-token"))
    result, calls, _, released = publish(context, monkeypatch, [response(401), response(401)])
    assert not result.success and len(calls) == 2 and released
    assert statuses == [(9, "reconnect_required")]


def test_refresh_failure_is_safe_retry(context, monkeypatch):
    def fail(_):
        raise x_oauth.XOAuthRefreshError("secret")
    monkeypatch.setattr(x_oauth, "refresh_x_oauth_connection", fail)
    result, calls, _, released = publish(context, monkeypatch, [response(401)])
    assert result.error == "x_refresh_failed" and released and len(calls) == 1


def test_rate_limit_bounded_and_honors_long_wait(context, monkeypatch):
    result, calls, _, released = publish(context, monkeypatch, [
        response(429, headers={"Retry-After": "900"})])
    assert result.error == "x_rate_limited" and released and len(calls) == 1


def test_short_rate_limit_retries(context, monkeypatch):
    result, calls, _, _ = publish(context, monkeypatch, [response(429), response()])
    assert result.success and len(calls) == 2


@pytest.mark.parametrize("field,value,error", [
    ("connection_status", "disconnected", "x_reconnect_required"),
    ("x_user_id", "456", "x_destination_account_mismatch"),
    ("granted_scopes", [], "x_missing_scope"),
])
def test_invalid_connection_never_calls_transport(context, monkeypatch, field, value, error):
    context[1][field] = value
    result, calls, armed, _ = publish(context, monkeypatch, [])
    assert result.error.startswith(error)
    assert not calls and not armed


def test_media_uploaded_before_post_and_waits_for_processing(context, monkeypatch):
    monkeypatch.setattr(x, "download_media", lambda _: (b"\x00\x00\x00\x20ftyp" + b"v"*30, "video.mp4"))
    replies = [
        response(body={"data": {"id": "22"}}), response(204),
        response(body={"data": {"processing_info": {"state": "pending", "check_after_secs": 1}}}),
        response(body={"data": {"processing_info": {"state": "succeeded"}}}),
        response(),
    ]
    result, calls, _, _ = publish(context, monkeypatch, replies, [{"type": "video", "file_id": "tg-video"}])
    assert result.success
    assert calls[0][2]["json"]["media_category"] == "tweet_video"
    assert calls[1][2]["data"] == {"segment_index": "0"}
    assert calls[3][2]["params"] == {"command": "STATUS", "media_id": "22"}
    assert calls[-1][2]["json"] == {"text": "caption", "media": {"media_ids": ["22"]}}


def test_mixed_video_album_fails_before_upload(context, monkeypatch):
    monkeypatch.setattr(x, "download_media", lambda _: (b"0000ftypvideo", "v.mp4"))
    result, calls, armed, _ = publish(context, monkeypatch, [],
                                    [{"type": "video", "file_id": "a"}]*2)
    assert result.error == "x_invalid_media_combination" and not calls and not armed


@pytest.mark.parametrize("files,error", [
    ([{"type": "photo"}]*5, "x_too_many_media"),
    ([{"type": "voice"}], "x_unsupported_media"),
])
def test_unsupported_media_not_silently_dropped(context, monkeypatch, files, error):
    result, calls, _, _ = publish(context, monkeypatch, [], files)
    assert result.error == error and not calls


def test_finalized_caption_and_links_survive_x_plan():
    plan = SimpleNamespace(telegram={"media_caption": ""},
                           text={"telegram": {"messages": ['<b>Title</b> <a href="https://example.com">source</a>'],
                                              "message_parse_modes": ["HTML"],
                                              "blockquote_messages": ["<blockquote>quote &amp; more</blockquote>"]}})
    assert x.build_x_plan(plan)["x_text"] == "Title source (https://example.com)\n\nquote & more"
    assert x.plain_text("a < b & c") == "a < b & c"


def test_engine_x_success_is_idempotent_and_has_link(context, monkeypatch):
    monkeypatch.setattr(engine, "_target_content_and_branding", lambda *_: ("caption", ""))
    monkeypatch.setattr(engine, "_shared_content_analysis", lambda p: p)
    calls = []
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: calls.append(kw) or response())
    content = PreparedContent(main_text="caption", routing_platforms=("x",), source_key="stable", editorial_finalized=True)
    store = InMemoryPublicationStateStore()
    first = engine.publish_prepared_content(1, "api", content, [context[0]], store, allow_duplicate=True)
    second = engine.publish_prepared_content(1, "api", content, [context[0]], store, allow_duplicate=True)
    assert first["ok"] and second["ok"]
    assert len(calls) == 1
    assert second["results"][0].message_url == "https://x.com/i/status/987654321012345678"


def test_engine_default_routing_still_excludes_x(context, monkeypatch):
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: pytest.fail("ordinary publication reached X"))
    result = engine.publish_prepared_content(1, "api", PreparedContent(main_text="hello"), [context[0]])
    assert not result["ok"] and not result["results"]


def test_ambiguous_attempt_guard_survives_retry(context, monkeypatch):
    calls = []
    def timeout(*a, **kw):
        calls.append(1)
        raise requests.Timeout()
    monkeypatch.setattr(x.requests, "request", timeout)
    store = InMemoryPublicationStateStore()
    store.claim_destination("s", "x")
    first = execute_x_delivery(store, "s", "x", context[0], "text", [])
    second = execute_x_delivery(store, "s", "x", context[0], "text", [])
    assert first.error.startswith("x_delivery_unknown") and second.error.startswith("x_delivery_unknown")
    assert calls == [1]


def test_definite_failure_can_retry_same_source(context, monkeypatch):
    replies = iter([response(403), response()])
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: next(replies))
    store = InMemoryPublicationStateStore()
    store.claim_destination("s", "x")
    assert not execute_x_delivery(store, "s", "x", context[0], "text", []).success
    assert execute_x_delivery(store, "s", "x", context[0], "text", []).success


class IntentDatabase:
    """Simulate the database unique key across independent worker stores."""
    def __init__(self):
        self.rows = {}
        self.failure = False

    def table(self, name):
        assert name == "publication_delivery_parts"
        database = self
        class Query:
            def __init__(self):
                self.filters = {}
            def upsert(self, payload, *, on_conflict, ignore_duplicates):
                assert on_conflict == "delivery_id,part_key" and ignore_duplicates
                self.payload = payload
                self.operation = "upsert"
                return self
            def delete(self):
                self.operation = "delete"
                return self
            def eq(self, key, value):
                self.filters[key] = value
                return self
            def execute(self):
                if database.failure:
                    raise RuntimeError("database unavailable")
                if self.operation == "upsert":
                    key = (self.payload["delivery_id"], self.payload["part_key"])
                    if key in database.rows:
                        return SimpleNamespace(data=[])
                    database.rows[key] = dict(self.payload)
                    return SimpleNamespace(data=[dict(self.payload)])
                for key, row in list(database.rows.items()):
                    if all(row.get(k) == v for k, v in self.filters.items()):
                        del database.rows[key]
                return SimpleNamespace(data=[])
        return Query()


def durable_store():
    store = InMemoryPublicationStateStore()
    state = store.claim_destination("s", "x")
    state.persistent_delivery_id = 77
    return store


def test_crash_after_post_before_success_persistence_never_reposts(context, monkeypatch):
    context[2].service_supabase = IntentDatabase()
    calls = []
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: calls.append(1) or response())
    assert execute_x_delivery(durable_store(), "s", "x", context[0], "text", []).success
    # New process has no local state and success could not be persisted.
    recovered = execute_x_delivery(durable_store(), "s", "x", context[0], "text", [])
    assert recovered.error.startswith("x_delivery_unknown")
    assert calls == [1]


def test_guard_database_failure_prevents_post(context, monkeypatch):
    backend = IntentDatabase()
    backend.failure = True
    context[2].service_supabase = backend
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: pytest.fail("sent without durable guard"))
    assert not execute_x_delivery(durable_store(), "s", "x", context[0], "text", []).success


def test_durable_rejection_releases_marker_for_another_worker(context, monkeypatch):
    context[2].service_supabase = IntentDatabase()
    replies = iter([response(403), response()])
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: next(replies))
    assert not execute_x_delivery(durable_store(), "s", "x", context[0], "text", []).success
    assert not context[2].service_supabase.rows
    assert execute_x_delivery(durable_store(), "s", "x", context[0], "text", []).success


def test_failed_media_processing_does_not_create_post(context, monkeypatch):
    monkeypatch.setattr(x, "download_media", lambda _: (b"GIF89a" + b"x"*10, "a.gif"))
    result, calls, armed, _ = publish(context, monkeypatch, [
        response(body={"data": {"id": "22"}}), response(204),
        response(body={"data": {"processing_info": {"state": "failed"}}}),
    ], [{"type": "animation", "file_id": "gif"}])
    assert result.error == "x_media_processing_failed" and not armed
    assert all(not call[1].endswith("/tweets") for call in calls)


def test_empty_finalize_response_cannot_publish_media(context, monkeypatch):
    monkeypatch.setattr(x, "download_media", lambda _: (b"GIF89a" + b"x"*10, "a.gif"))
    result, calls, armed, _ = publish(context, monkeypatch, [
        response(body={"data": {"id": "22"}}), response(204), response(body={}),
    ], [{"type": "animation", "file_id": "gif"}])
    assert result.error == "x_invalid_media_response" and not armed


def test_four_photos_are_attached_to_one_post(context, monkeypatch):
    monkeypatch.setattr(x, "download_media", lambda _: (b"\xff\xd8\xff" + b"x"*10, "a.jpg"))
    replies = []
    for media_id in range(1, 5):
        replies.extend([response(body={"data": {"id": str(media_id)}}),
                        response(204), response(body={"data": {"id": str(media_id)}})])
    replies.append(response())
    result, calls, _, _ = publish(context, monkeypatch, replies, [{"type": "photo", "file_id": "pic"}]*4)
    assert result.success and calls[-1][2]["json"]["media"]["media_ids"] == ["1", "2", "3", "4"]
    assert sum(call[1].endswith("/tweets") for call in calls) == 1


def test_media_scope_missing_requires_reconnect_without_losing_attachment(context, monkeypatch):
    context[1]["granted_scopes"] = ["tweet.write"]
    result, calls, armed, _ = publish(context, monkeypatch, [], [{"type": "photo", "file_id": "a"}])
    assert result.error.startswith("x_missing_scope") and not calls and not armed


def test_x_media_editorial_uses_full_caption(context, monkeypatch):
    monkeypatch.setattr(engine, "_target_content_and_branding", lambda *_: ("Final caption", ""))
    monkeypatch.setattr(engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(x, "download_media", lambda _: (b"\xff\xd8\xffphoto", "a.jpg"))
    replies = iter([response(body={"data": {"id": "22"}}), response(204),
                    response(body={"data": {"id": "22"}}), response()])
    payloads = []
    def send(*args, **kwargs):
        payloads.append(kwargs.get("json"))
        return next(replies)
    monkeypatch.setattr(x.requests, "request", send)
    prepared = PreparedContent(main_text="Final caption", files=[{"type": "photo", "file_id": "a"}],
                               routing_platforms=("x",), editorial_finalized=True)
    result = engine.publish_prepared_content(1, "api", prepared, [context[0]], allow_duplicate=True)
    assert result["ok"] and payloads[-1]["text"] == "Final caption"


def test_bale_qualified_reference_uses_bale_downloader(monkeypatch):
    from core import bale_media
    monkeypatch.setattr(bale_media, "download_bale_media", lambda ref: (b"photo", ref))
    assert x.download_media("bale-file://abc") == (b"photo", "bale-file://abc")


def test_entity_link_with_emoji_is_preserved():
    plan = SimpleNamespace(text={"telegram": {"messages": ["😀 source & detail"]}})
    text = x.build_x_plan(plan, [{"type": "text_link", "text": "source", "offset": 3,
                                 "length": 6, "url": "https://example.org"}])["x_text"]
    assert text == "😀 source (https://example.org) & detail"


def test_persisted_x_success_restores_id_and_link_without_network(context, monkeypatch):
    from core.publication_state import PersistentPublicationStateStore
    context[2].claim_persistent_publication_delivery = lambda **kw: {
        "claimed": False, "delivery_id": 77, "status": "succeeded", "attempt_count": 1,
    }
    context[2].list_persistent_publication_parts = lambda **kw: [{
        "part_key": "primary", "status": "succeeded", "message_id": 987654321012345678,
        "message_ids": [987654321012345678], "destination_chat_id": "123",
    }, {"part_key": "x-send-intent", "status": "sending"}]
    context[2].mark_persistent_publication_source = lambda **kw: None
    monkeypatch.setattr(engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(x.requests, "request", lambda *a, **kw: pytest.fail("reposted restored delivery"))
    content = PreparedContent(main_text="caption", routing_platforms=("x",), source_key="stable")
    result = engine.publish_prepared_content(
        1, "api", content, [context[0]], PersistentPublicationStateStore(), allow_duplicate=True,
    )
    assert result["ok"]
    assert result["results"][0].message_url == "https://x.com/i/status/987654321012345678"


def test_workspace_resolver_preserves_x_and_authorization(context):
    from core.target_resolver import resolve_publication_targets
    db = context[2]
    db.get_tenant = lambda _: None
    db.get_user_by_telegram_id = lambda _: {"id": 7}
    db.list_selected_workspace_ids = lambda _: [1]
    db.list_user_workspace_memberships = lambda _: [{"id": 1}]
    db.get_workspace_setup_state = lambda _: {"step": "completed"}
    db.get_workspace_member = lambda *args: {"status": "active", "role": "publisher"}
    db.list_verified_active_destinations = lambda _: [
        {"id": 9, "workspace_id": 1, "platform": "x", "external_id": "x:123"},
    ]
    targets, errors = resolve_publication_targets(100)
    assert not errors and len(targets) == 1 and targets[0].platform == "x"
    db.get_workspace_member = lambda *args: {"status": "active", "role": "viewer"}
    targets, errors = resolve_publication_targets(100)
    assert not targets and errors


def test_username_change_keeps_canonical_x_destination_working(context, monkeypatch):
    context[1]["x_username"] = "renamed_account"
    result, calls, _, _ = publish(context, monkeypatch, [response()])
    assert result.success and len(calls) == 1
