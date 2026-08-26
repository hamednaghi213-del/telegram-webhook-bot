import os
import inspect
import threading
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature")

from core import media_handler, publication_engine
from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore
from core.formatter import remove_source_signature


def _plan():
    return SimpleNamespace(
        telegram={"media_caption": "caption", "followup_messages": [], "blockquote_messages": []},
        bale={"media_caption": "caption", "followup_messages": [], "blockquote_messages": []},
        text={
            "telegram": {"messages": ["body"], "message_parse_modes": [None], "blockquote_messages": []},
            "bale": {"messages": ["body"], "message_parse_modes": [None], "blockquote_messages": []},
        },
    )


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    publication_engine.reset_local_idempotency_state()
    with media_handler.group_lock:
        for timer in media_handler.group_timers.values():
            timer.cancel()
        media_handler.pending_groups.clear()
        media_handler.group_timers.clear()
    monkeypatch.setattr(media_handler, "schedule_processing", lambda *_a, **_k: None)
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda value: value)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("body", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _plan())
    target = PublicationTarget("legacy:telegram:@dest", "legacy", "telegram", "@dest")
    monkeypatch.setattr(publication_engine, "resolve_publication_targets", lambda _chat: ([target], []))
    media_handler.API_URL = "https://api.test/bot"


def _add(group, count, start=1):
    for number in range(start, start + count):
        media_handler.add_to_pending_group(group, 9, f"f{number}", "photo", "caption" if number == 1 else "", message_id=number)


def test_late_members_are_delivered_after_first_snapshot_succeeds(monkeypatch):
    _add("late", 2)
    calls = []

    def send(_chat, _api, _target, files, _plan):
        calls.append([item["message_id"] for item in files])
        if len(calls) == 1:
            _add("late", 2, 3)
        return {"ok": True, "message_id": 100 + len(calls)}

    monkeypatch.setattr(publication_engine, "_send_media_target", send)
    assert media_handler.process_media_group("late", 9)
    assert media_handler.process_media_group("late", 9)
    assert calls == [[1, 2], [3, 4]]


def test_late_member_recovery_uses_distinct_delivery_generation(monkeypatch):
    _add("generation", 2)
    calls = []
    def sender(*_args):
        calls.append(1)
        if len(calls) == 1:
            _add("generation", 2, 3)
        return {"ok": True, "message_id": len(calls)}
    monkeypatch.setattr(publication_engine, "_send_media_target", sender)
    assert media_handler.process_media_group("generation", 9)
    assert media_handler.process_media_group("generation", 9)
    keys = tuple(publication_engine._state_store._sources)
    assert keys[0] != keys[1]
    assert keys == (
        "tg:9:album:generation:generation:1",
        "tg:9:album:generation:generation:2",
    )


def test_successful_old_generation_does_not_skip_new_generation(monkeypatch):
    _add("skip", 2)
    sent = []
    def sender(*_args):
        sent.append(1)
        if len(sent) == 1:
            _add("skip", 2, 3)
        return {"ok": True, "message_id": len(sent)}
    monkeypatch.setattr(publication_engine, "_send_media_target", sender)
    assert media_handler.process_media_group("skip", 9)
    assert media_handler.process_media_group("skip", 9)
    assert len(sent) == 2


def test_single_late_member_is_sent_after_recovery_deadline(monkeypatch):
    _add("single", 2)
    sent = []

    def sender(*_args):
        sent.append([item["message_id"] for item in _args[3]])
        if len(sent) == 1:
            _add("single", 1, 3)
        return {"ok": True, "message_id": len(sent)}

    monkeypatch.setattr(publication_engine, "_send_media_target", sender)
    assert media_handler.process_media_group("single", 9)
    with media_handler.group_lock:
        media_handler.pending_groups[(9, "single")]["recovery_started_at"] = time.time() - 100
    assert media_handler.process_media_group("single", 9)
    assert sent == [[1, 2], [3]]


def test_album_over_ten_items_is_split_without_infinite_retry(monkeypatch):
    _add("large", 12)
    sent = []
    monkeypatch.setattr(publication_engine, "_send_media_target", lambda *_a: sent.append(len(_a[3])) or {"ok": True, "message_id": len(sent)})
    assert media_handler.process_media_group("large", 9)
    assert media_handler.process_media_group("large", 9)
    assert sent == [10, 2]
    assert (9, "large") not in media_handler.pending_groups


def test_last_single_remainder_is_delivered(monkeypatch):
    _add("eleven", 11)
    sent = []
    monkeypatch.setattr(publication_engine, "_send_media_target", lambda *_a: sent.append(len(_a[3])) or {"ok": True, "message_id": len(sent)})
    assert media_handler.process_media_group("eleven", 9)
    with media_handler.group_lock:
        media_handler.pending_groups[(9, "eleven")]["recovery_started_at"] = time.time() - 100
    assert media_handler.process_media_group("eleven", 9)
    assert sent == [10, 1]


def test_concurrent_claim_allows_only_one_sender():
    store = InMemoryPublicationStateStore()
    barrier = threading.Barrier(3)
    outcomes = []

    def claim():
        barrier.wait()
        outcomes.append(store.begin_attempt("source", "target") is not None)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [False, True]


def test_nested_entity_payload_is_deeply_immutable():
    original = {"type": "link", "payload": {"items": [1, {"x": 2}]}}
    prepared = PreparedContent(other_entities=(original,))
    original["payload"]["items"][1]["x"] = 99
    assert prepared.other_entities[0]["payload"]["items"][1]["x"] == 2
    with pytest.raises(TypeError):
        prepared.other_entities[0]["payload"]["items"][1]["x"] = 3


def test_nested_file_metadata_is_not_shared_between_targets():
    metadata = {"file_id": "f", "meta": {"tags": ["a"]}}
    prepared = PreparedContent(files=(metadata,))
    metadata["meta"]["tags"].append("b")
    assert prepared.files[0]["meta"]["tags"] == ("a",)


def test_nested_blockquote_metadata_is_not_mutated():
    block = {"text": "x", "meta": {"levels": [1]}}
    prepared = PreparedContent(blockquote_blocks=(block,))
    block["meta"]["levels"].append(2)
    assert prepared.blockquote_blocks[0]["meta"]["levels"] == (1,)


def test_target_processing_cannot_modify_other_target_content():
    prepared = PreparedContent(files=({"file_id": "f", "meta": {"x": [1]}},))
    first = prepared.files[0]
    second = prepared.files[0]
    with pytest.raises(AttributeError):
        first["meta"]["x"].append(2)
    assert second["meta"]["x"] == (1,)


def test_boolean_sender_result_is_not_treated_as_message_id():
    assert publication_engine._message_id_from_outcome(True) is None


def test_database_resolver_uses_real_verification_chat_id_when_available():
    from pathlib import Path
    schema = (Path(__file__).parents[1] / "schema" / "003_phase4a_workspace_setup.sql").read_text(encoding="utf-8")
    verification_table = schema.split("CREATE TABLE IF NOT EXISTS destination_verification", 1)[1]
    verification_table = verification_table.split(");", 1)[0]
    assert "chat_id" not in verification_table


def test_database_resolver_does_not_invent_verified_chat_id():
    target = PublicationTarget("x", "workspace", "telegram", "@RealName", 1, 1, {"verified": True})
    assert publication_engine.canonical_target_identity(target) == "telegram:external:realname"


def test_username_deduplication_works_without_verification_chat_id():
    first = PublicationTarget("a", "legacy", "telegram", "@Channel")
    second = PublicationTarget("b", "workspace", "telegram", "channel", 1, 2)
    assert publication_engine.canonical_target_identity(first) == publication_engine.canonical_target_identity(second)


def test_workspace_context_database_failure_does_not_raise_name_error():
    from core import webhook_handler
    source = inspect.getsource(webhook_handler.handle_webhook)
    error_block = source[source.index("Active media context lookup failed"):]
    error_block = error_block[:error_block.index("# Workspace publication no longer happens here")]
    assert "metadata.get" not in error_block
    assert "workspace_context_active = False" in error_block


def test_workspace_context_database_failure_preserves_correct_media_group():
    from core import webhook_handler
    source = inspect.getsource(webhook_handler.handle_webhook)
    error_block = source[source.index("Active media context lookup failed"):]
    error_block = error_block[:error_block.index("# Workspace publication no longer happens here")]
    assert "remove_pending_group" not in error_block


def test_source_state_only_succeeds_after_blocking_deliveries(monkeypatch):
    store = InMemoryPublicationStateStore()
    targets = [
        PublicationTarget("a", "workspace", "telegram", "@a", 1, 1),
        PublicationTarget("b", "workspace", "telegram", "@b", 2, 2),
    ]
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda _c, _a, target, _p: {"ok": target.key == "a", "message_id": 1})
    result = publication_engine.publish_prepared_content(9, "api", PreparedContent(main_text="x", source_key="s"), targets, store)
    assert not result["ok"]
    assert store.get_source("s").status == "partial"


def test_retry_over_limit_becomes_failed_terminal():
    store = InMemoryPublicationStateStore()
    for number in range(5):
        assert store.begin_attempt("source", "target") is not None
        store.mark_failed("source", "target", f"failure-{number}")
    assert store.begin_attempt("source", "target") is None
    assert store.get_delivery("source", "target").status == "failed_terminal"


def test_stale_failed_terminal_group_is_cleaned(monkeypatch):
    _add("dead", 1)
    with media_handler.group_lock:
        group = media_handler.pending_groups[(9, "dead")]
        group["state"] = "failed_terminal"
        group["last_update"] = time.time() - media_handler.MAX_GROUP_AGE_SECONDS - 1
    media_handler.cleanup_old_groups()
    assert (9, "dead") not in media_handler.pending_groups


def test_source_cleanup_is_idempotent():
    text = "متن اصلی\n\n🔷 #N\n🔷 @mahdaviatakhbar"
    once = remove_source_signature(text, source_username="mahdaviatakhbar")
    assert once == "متن اصلی"
    assert remove_source_signature(once, source_username="mahdaviatakhbar") == once


def test_short_hashtag_only_message_is_preserved():
    assert remove_source_signature("#خبر") == "#خبر"


def test_short_mention_only_message_is_preserved():
    assert remove_source_signature("@reporter") == "@reporter"


def test_multiline_footer_cleanup_preserves_previous_body_separator():
    text = "بند اول\n\n#موضوع_واقعی\n\n🔷 #N\n🔷 @mahdaviatakhbar"
    cleaned = remove_source_signature(text, source_username="mahdaviatakhbar")
    assert cleaned == "بند اول\n\n#موضوع_واقعی"


def test_real_telegram_text_executor_returns_message_id(monkeypatch):
    from core import webhook_handler
    class Response:
        status_code = 200
        text = "ok"
        def json(self):
            return {"ok": True, "result": {"message_id": 42}}
    monkeypatch.setattr(webhook_handler, "API_URL", "https://api.test")
    monkeypatch.setattr(webhook_handler, "CHANNEL_ID", "@dest")
    monkeypatch.setattr(webhook_handler.requests, "post", lambda *_a, **_k: Response())
    outcome = webhook_handler.send_to_channel("hello", return_result=True)
    assert outcome["ok"] is True
    assert outcome["message_id"] == 42


def test_real_telegram_media_executor_returns_message_id(monkeypatch):
    monkeypatch.setattr(media_handler, "execute_telegram_plan", lambda *_a, **_k: True)
    monkeypatch.setattr(media_handler, "get_last_media_message_id", lambda: 51)
    target = PublicationTarget("legacy", "legacy", "telegram", "@dest")
    outcome = publication_engine._send_media_target(9, "api", target, [{"file_id": "f", "type": "photo"}], {})
    assert outcome.success and outcome.primary_message_id == 51


def test_real_bale_executor_returns_message_id(monkeypatch):
    from core import bale_forwarder
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True, "result": {"message_id": 61}}
    monkeypatch.setattr(bale_forwarder.requests, "post", lambda *_a, **_k: Response())
    assert bale_forwarder.send_text_to_bale("c", "t", "hello", return_result=True)["message_id"] == 61


def test_album_executor_returns_primary_message_id(monkeypatch):
    monkeypatch.setattr(media_handler, "execute_telegram_plan", lambda *_a, **_k: True)
    monkeypatch.setattr(media_handler, "get_last_media_message_id", lambda: 71)
    target = PublicationTarget("legacy", "legacy", "telegram", "@dest")
    outcome = publication_engine._send_media_target(9, "api", target,
        [{"file_id": "a", "type": "photo"}, {"file_id": "b", "type": "photo"}], {})
    assert outcome.primary_message_id == 71


def test_followup_executor_returns_message_id(monkeypatch):
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: {"ok": True, "message_id": 81})
    target = PublicationTarget("x", "workspace", "telegram", "@dest", 1, 1)
    outcome = publication_engine._execute_delivery_part(9, "api", target,
        PreparedContent(main_text="x"), {"messages": ["main", "next"], "message_parse_modes": [None, None]}, "followup", 0)
    assert publication_engine._message_id_from_outcome(outcome) == 81


def test_message_link_is_created_from_real_executor_results(monkeypatch):
    store = InMemoryPublicationStateStore()
    target = PublicationTarget("x", "workspace", "telegram", "@dest", 1, 1)
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: {"ok": True, "message_id": 91, "result": {"chat": {"id": -100}}})
    result = publication_engine.publish_prepared_content(9, "api", PreparedContent(main_text="x", source_key="link"), [target], store)
    assert result["results"][0].primary_message_id == 91
    assert result["results"][0].destination_chat_id == "-100"


def _cancel_editorial_album(monkeypatch):
    from core import editorial_pending, webhook_handler
    review = editorial_pending.create_pending_review(
        user_id=9,
        content_type="opinion_note",
        original_text="#یادداشت\nمتن",
        current_summary="خلاصه",
        metadata={"media_group_id": "cancel-group", "files": [{"file_id": "a"}]},
    )
    _add("cancel-group", 2)
    class Timer:
        cancelled = False
        def cancel(self):
            self.cancelled = True
    timer = Timer()
    media_handler.group_timers[(9, "cancel-group")] = timer
    monkeypatch.setattr(webhook_handler, "answer_callback_query", lambda *_a, **_k: True)
    monkeypatch.setattr(webhook_handler, "send_message", lambda *_a, **_k: True)
    handled = webhook_handler.handle_editorial_callback(
        {"id": "cb", "data": f"ed:cancel:{review.review_id}", "from": {"id": 9}},
        "req",
    )
    return handled, timer


def test_cancelled_editorial_album_removes_pending_media_group(monkeypatch):
    handled, _timer = _cancel_editorial_album(monkeypatch)
    assert handled is True
    assert (9, "cancel-group") not in media_handler.pending_groups


def test_cancelled_editorial_album_cancels_timer(monkeypatch):
    _handled, timer = _cancel_editorial_album(monkeypatch)
    assert timer.cancelled is True
    assert (9, "cancel-group") not in media_handler.group_timers


def test_cancelled_editorial_album_is_never_published(monkeypatch):
    published = []
    monkeypatch.setattr(publication_engine, "_send_media_target", lambda *_a: published.append(1) or True)
    _cancel_editorial_album(monkeypatch)
    media_handler._scheduled_process("cancel-group", 9)
    assert published == []


def test_editorial_album_full_flow_from_aggregator_to_executor(monkeypatch):
    _add("editorial-flow", 2)
    queued = []
    sent = []
    monkeypatch.setattr("core.webhook_handler.detect_editorial_admin_tag",
                        lambda text: ("opinion_note", text.replace("#یادداشت", "").strip(), True))
    monkeypatch.setattr("core.webhook_handler.try_queue_editorial_text_review",
                        lambda **kwargs: queued.append(kwargs) or True)
    monkeypatch.setattr(publication_engine, "_send_media_target",
                        lambda *_a: sent.append(1) or {"ok": True, "message_id": 1})
    with media_handler.group_lock:
        media_handler.pending_groups[(9, "editorial-flow")]["main_text"] = "#یادداشت\nتیتر\nمتن"
    assert media_handler.process_media_group("editorial-flow", 9) is True
    assert len(queued) == 1
    assert len(queued[0]["media_files"]) == 2
    assert sent == []
    assert media_handler.pending_groups[(9, "editorial-flow")]["state"] == "editorial_pending"


def _approve_editorial_album(monkeypatch, group, publish, metadata_files=None):
    from core import editorial_pending, webhook_handler
    with media_handler.group_lock:
        files = list(
            metadata_files
            if metadata_files is not None
            else media_handler.pending_groups[(9, group)]["files"]
        )
        media_handler.pending_groups[(9, group)]["state"] = "editorial_pending"
    review = editorial_pending.create_pending_review(
        user_id=9,
        content_type="opinion_note",
        original_text="تیتر\nمتن نهایی",
        current_summary="خلاصه",
        metadata={
            "media_group_id": group,
            "files": files,
            "main_text": "تیتر\nمتن نهایی",
            "source_key": f"tg:9:album:{group}:generation:1",
        },
    )
    monkeypatch.setattr(webhook_handler, "publish_prepared_text", publish)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", lambda *_a, **_k: True)
    monkeypatch.setattr(webhook_handler, "send_message", lambda *_a, **_k: True)
    assert webhook_handler.handle_editorial_callback(
        {"id": "cb", "data": f"ed:original:{review.review_id}", "from": {"id": 9}},
        "req",
    ) is True


def test_late_member_during_editorial_pending_is_included_on_approval(monkeypatch):
    _add("editorial-late", 2)
    with media_handler.group_lock:
        media_handler.pending_groups[(9, "editorial-late")]["state"] = "editorial_pending"
        stale_files = list(media_handler.pending_groups[(9, "editorial-late")]["files"])
    _add("editorial-late", 1, 3)
    published = []
    _approve_editorial_album(
        monkeypatch,
        "editorial-late",
        lambda **kwargs: published.append(
            [item["message_id"] for item in kwargs["files"]]
        ) or True,
        metadata_files=stale_files,
    )
    assert published == [[1, 2, 3]]
    assert (9, "editorial-late") not in media_handler.pending_groups


def test_late_member_during_approved_album_publish_reaches_recovery_generation(monkeypatch):
    _add("editorial-race", 2)
    calls = []

    def approved_publish(**kwargs):
        calls.append((kwargs["source_key"], [item["message_id"] for item in kwargs["files"]]))
        _add("editorial-race", 1, 3)
        return True

    _approve_editorial_album(monkeypatch, "editorial-race", approved_publish)
    group = media_handler.pending_groups[(9, "editorial-race")]
    assert [item["message_id"] for item in group["files"]] == [3]
    assert group["delivery_generation"] == 2
    group["recovery_started_at"] = time.time() - media_handler.MEDIA_GROUP_RECOVERY_WINDOW_SECONDS - 1
    monkeypatch.setattr(
        publication_engine,
        "_send_media_target",
        lambda _c, _a, _t, files, _p: calls.append(
            (media_handler.pending_groups[(9, "editorial-race")]["delivery_generation"],
             [item["message_id"] for item in files])
        ) or {"ok": True, "message_id": 300},
    )
    assert media_handler.process_media_group("editorial-race", 9) is True
    assert calls == [
        ("tg:9:album:editorial-race:generation:1", [1, 2]),
        (2, [3]),
    ]
    assert (9, "editorial-race") not in media_handler.pending_groups


def test_bale_media_group_array_result_preserves_all_message_ids(monkeypatch):
    from core import bale_forwarder

    class Response:
        status_code = 200
        text = "ok"
        def json(self):
            return {"ok": True, "result": [{"message_id": 401}, {"message_id": 402}]}

    monkeypatch.setenv("ENABLE_BALE", "true")
    monkeypatch.setattr(
        bale_forwarder, "download_file_from_telegram",
        lambda file_id: (b"data", f"{file_id}.jpg"),
    )
    monkeypatch.setattr(bale_forwarder.requests, "post", lambda *_a, **_k: Response())
    result = bale_forwarder.send_media_group_to_bale(
        9,
        [{"type": "photo", "file_id": "a"}, {"type": "photo", "file_id": "b"}],
        "caption",
        bale_channel="@bale",
        bale_token="token",
        return_result=True,
    )
    assert result["ok"] is True
    assert result["message_id"] == 401
    assert result["message_ids"] == [401, 402]


def test_bale_album_ids_reach_delivery_result_and_success_is_not_failed(monkeypatch):
    monkeypatch.setenv("BALE_BOT_TOKEN", "token")
    from core import bale_forwarder
    monkeypatch.setattr(
        bale_forwarder, "send_media_group_to_bale",
        lambda *_a, **_k: {
            "ok": True, "message_id": 501, "message_ids": [501, 502],
            "status_code": 200,
        },
    )
    target = PublicationTarget("bale", "workspace", "bale", "@bale", 10, 20)
    result = publication_engine.publish_prepared_content(
        9, "api",
        PreparedContent(
            main_text="x", source_key="bale-album",
            files=[{"type": "photo", "file_id": "a"}, {"type": "photo", "file_id": "b"}],
        ),
        [target],
        InMemoryPublicationStateStore(),
    )
    delivery = result["results"][0]
    assert result["ok"] is True
    assert delivery.status == "succeeded"
    assert delivery.primary_message_id == 501
    assert delivery.message_ids == (501, 502)


def test_retry_does_not_repeat_successful_telegram_or_bale_destination(monkeypatch):
    store = InMemoryPublicationStateStore()
    telegram = PublicationTarget("tg", "workspace", "telegram", "@tg", 1, 1)
    bale = PublicationTarget("bale", "workspace", "bale", "@bale", 2, 2)
    calls = {"telegram": 0, "bale": 0}

    def sender(_chat, _api, target, _plan):
        calls[target.platform] += 1
        if target.platform == "bale" and calls["bale"] == 1:
            return {"ok": False, "error": "temporary"}
        return {"ok": True, "message_id": 600 + calls[target.platform]}

    monkeypatch.setattr(publication_engine, "_send_text_target", sender)
    prepared = PreparedContent(main_text="x", source_key="mixed-retry")
    first = publication_engine.publish_prepared_content(9, "api", prepared, [telegram, bale], store)
    second = publication_engine.publish_prepared_content(9, "api", prepared, [telegram, bale], store)
    assert first["ok"] is False
    assert second["ok"] is True
    assert calls == {"telegram": 1, "bale": 2}


def test_failed_editorial_batch_keeps_late_members_for_next_generation():
    _add("editorial-partial", 2)
    first = media_handler.lease_editorial_group_for_publication("editorial-partial", 9)
    _add("editorial-partial", 1, 3)
    media_handler.finish_editorial_group_publication(
        "editorial-partial", 9, first, False, approved_text="متن تأییدشده"
    )
    retry = media_handler.lease_editorial_group_for_publication("editorial-partial", 9)
    assert retry["source_key"].endswith("generation:1")
    assert [item["message_id"] for item in retry["files"]] == [1, 2]
    media_handler.finish_editorial_group_publication(
        "editorial-partial", 9, retry, True, approved_text="متن تأییدشده"
    )
    recovery = media_handler.lease_editorial_group_for_publication("editorial-partial", 9)
    assert recovery["source_key"].endswith("generation:2")
    assert [item["message_id"] for item in recovery["files"]] == [3]


def test_legacy_bale_album_ids_reach_delivery_result(monkeypatch):
    monkeypatch.setattr(
        media_handler, "send_album_to_bale",
        lambda *_a, **_k: {
            "ok": True, "message_id": 701, "message_ids": [701, 702],
            "status_code": 200,
        },
    )
    target = PublicationTarget("legacy-bale", "legacy", "bale", "@bale")
    result = publication_engine.publish_prepared_content(
        9, "api",
        PreparedContent(
            main_text="x", source_key="legacy-bale-album",
            files=[{"type": "photo", "file_id": "a"}, {"type": "photo", "file_id": "b"}],
        ),
        [target],
        InMemoryPublicationStateStore(),
    )
    delivery = result["results"][0]
    assert result["ok"] is True
    assert delivery.primary_message_id == 701
    assert delivery.message_ids == (701, 702)


def test_successful_group_cleanup_has_no_out_of_lock_remove_gap(monkeypatch):
    _add("atomic-cleanup", 2)
    monkeypatch.setattr(
        publication_engine, "_send_media_target",
        lambda *_a, **_k: {"ok": True, "message_id": 801},
    )
    monkeypatch.setattr(
        media_handler, "remove_pending_group",
        lambda *_a, **_k: pytest.fail("cleanup must be atomic under group_lock"),
    )
    assert media_handler.process_media_group("atomic-cleanup", 9) is True
    assert (9, "atomic-cleanup") not in media_handler.pending_groups
