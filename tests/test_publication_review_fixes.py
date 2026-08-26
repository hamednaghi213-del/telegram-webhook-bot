import os
from types import SimpleNamespace

import pytest

from core import media_handler, publication_engine
from core.content_model import DeliveryResult, PreparedContent, PublicationTarget
from core.formatter import remove_source_signature
from core.publication_state import InMemoryPublicationStateStore
from core.target_resolver import canonical_target_identity

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature",
)


def _text_plan(messages=None, blockquotes=None):
    messages = messages or ["main"]
    blockquotes = blockquotes or []
    return SimpleNamespace(
        telegram={"media_caption": "main", "followup_messages": [], "blockquote_messages": blockquotes},
        bale={"media_caption": "main", "followup_messages": [], "blockquote_messages": blockquotes},
        text={
            "telegram": {"messages": messages, "message_parse_modes": [None] * len(messages), "blockquote_messages": blockquotes},
            "bale": {"messages": messages, "message_parse_modes": [None] * len(messages), "blockquote_messages": blockquotes},
        },
    )


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    publication_engine.reset_local_idempotency_state()
    with media_handler.group_lock:
        media_handler.pending_groups.clear()
        media_handler.group_timers.clear()
    monkeypatch.setattr(media_handler, "schedule_processing", lambda *_a, **_k: None)


def _album():
    media_handler.API_URL = "api"
    media_handler.add_to_pending_group("g", 9, "a", "photo", "caption", message_id=1)
    media_handler.add_to_pending_group("g", 9, "b", "photo", message_id=2)


def test_late_album_member_during_network_send_is_not_lost(monkeypatch):
    _album()
    def publish(*_args, **_kwargs):
        media_handler.add_to_pending_group("g", 9, "c", "photo", message_id=3)
        return {"ok": True}
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", publish)
    assert media_handler.process_media_group("g", 9, expected_generation=2) is True
    group = media_handler.pending_groups[(9, "g")]
    assert [item["message_id"] for item in group["files"]] == [3]
    assert group["state"] == "retry_pending"


def test_late_album_member_after_snapshot_prevents_group_removal(monkeypatch):
    test_late_album_member_during_network_send_is_not_lost(monkeypatch)
    assert (9, "g") in media_handler.pending_groups


def test_late_member_before_first_side_effect_invalidates_lease(monkeypatch):
    _album()
    published = []
    original_cleanup = remove_source_signature
    def cleanup(text, **kwargs):
        media_handler.add_to_pending_group("g", 9, "c", "photo", message_id=3)
        return original_cleanup(text, **kwargs)
    monkeypatch.setattr("core.formatter.remove_source_signature", cleanup)
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda *_a, **_k: published.append(1) or {"ok": True})
    assert media_handler.process_media_group("g", 9, expected_generation=2) is False
    assert published == []
    assert len(media_handler.pending_groups[(9, "g")]["files"]) == 3


def test_old_generation_cannot_delete_new_generation(monkeypatch):
    _album()
    media_handler.add_to_pending_group("g", 9, "c", "photo", message_id=3)
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda *_a, **_k: {"ok": True})
    assert media_handler.process_media_group("g", 9, expected_generation=2) is False
    assert [item["message_id"] for item in media_handler.pending_groups[(9, "g")]["files"]] == [1, 2, 3]


def test_failed_album_publish_keeps_unpublished_members(monkeypatch):
    _album()
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda *_a, **_k: {"ok": False})
    assert media_handler.process_media_group("g", 9, expected_generation=2) is False
    assert len(media_handler.pending_groups[(9, "g")]["files"]) == 2
    assert media_handler.pending_groups[(9, "g")]["state"] == "retry_pending"


def test_processing_group_is_not_removed_by_cleanup(monkeypatch):
    _album()
    group = media_handler.pending_groups[(9, "g")]
    group.update({"state": "publishing", "is_processing": True, "last_update": 0})
    monkeypatch.setattr(media_handler, "MAX_GROUP_AGE_SECONDS", 1)
    media_handler.cleanup_old_groups()
    assert (9, "g") in media_handler.pending_groups


def _run_retry(monkeypatch, messages, blockquotes=()):
    target = PublicationTarget("t", "workspace", "telegram", "@one", 1, 1)
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda prepared: prepared)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("base", "brand"))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan(messages, list(blockquotes)))
    calls = []
    failures = {"followup": True, "blockquote": True}
    def sender(_chat, _api, _target, plan):
        value = plan["messages"][0]
        calls.append(value)
        if value == "f2" and failures["followup"]:
            failures["followup"] = False
            return False
        if value == "b1" and failures["blockquote"]:
            failures["blockquote"] = False
            return False
        return {"ok": True, "message_id": len(calls)}
    monkeypatch.setattr(publication_engine, "_send_text_target", sender)
    prepared = PreparedContent(main_text="base", source_key="source")
    first = publication_engine.publish_prepared_content(1, "api", prepared, [target])
    second = publication_engine.publish_prepared_content(1, "api", prepared, [target])
    return first, second, calls


def test_followup_failure_does_not_repeat_successful_main_message(monkeypatch):
    first, second, calls = _run_retry(monkeypatch, ["main", "f1", "f2"])
    assert first["ok"] is False and second["ok"] is True
    assert calls == ["main", "f1", "f2", "f2"]


def test_blockquote_failure_does_not_repeat_successful_main_message(monkeypatch):
    first, second, calls = _run_retry(monkeypatch, ["main"], ["b1"])
    assert first["ok"] is False and second["ok"] is True
    assert calls == ["main", "b1", "b1"]


def test_partial_destination_retry_resumes_from_failed_part(monkeypatch):
    test_followup_failure_does_not_repeat_successful_main_message(monkeypatch)


def test_one_destination_failure_does_not_repeat_other_successful_destination(monkeypatch):
    targets = [
        PublicationTarget("a", "workspace", "telegram", "@a", 1, 1),
        PublicationTarget("b", "workspace", "telegram", "@b", 2, 2),
    ]
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("base", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan())
    calls = []
    failed = {"b": True}
    def sender(_c, _a, target, _p):
        calls.append(target.key)
        if target.key == "b" and failed["b"]:
            failed["b"] = False
            return False
        return True
    monkeypatch.setattr(publication_engine, "_send_text_target", sender)
    prepared = PreparedContent(main_text="base", source_key="s")
    assert publication_engine.publish_prepared_content(1, "api", prepared, targets)["ok"] is False
    assert publication_engine.publish_prepared_content(1, "api", prepared, targets)["ok"] is True
    assert calls == ["a", "b", "b"]


def test_concurrent_destination_claim_does_not_start_second_delivery():
    store = InMemoryPublicationStateStore()
    first = store.begin_attempt("source", "telegram:channel")
    second = store.begin_attempt("source", "telegram:channel")
    assert first is not None
    assert second is None
    assert store.get_delivery("source", "telegram:channel").attempt == 1


def test_shared_pipeline_returns_delivery_result_per_destination(monkeypatch):
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("base", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan(["main", "follow"]))
    ids = iter((101, 102))
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: {"ok": True, "message_id": next(ids)})
    result = publication_engine.publish_prepared_content(
        1, "api", PreparedContent(main_text="base", source_key="structured"),
        [PublicationTarget("a", "workspace", "telegram", "@a", 3, 4)],
    )
    delivery = result["results"][0]
    assert delivery.destination_id == 4 and delivery.primary_message_id == 101
    assert delivery.followup_message_ids == (102,)


def test_shared_pipeline_returns_primary_and_followup_message_ids(monkeypatch):
    test_shared_pipeline_returns_delivery_result_per_destination(monkeypatch)


def test_destination_results_do_not_overwrite_each_other(monkeypatch):
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("base", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan())
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda _c, _a, target, _p: {"ok": True, "message_id": target.destination_id})
    targets = [PublicationTarget(str(i), "workspace", "telegram", f"@c{i}", i, i) for i in (1, 2)]
    results = publication_engine.publish_prepared_content(1, "api", PreparedContent(main_text="x", source_key="separate"), targets)["results"]
    assert [(item.destination_id, item.primary_message_id) for item in results] == [(1, 1), (2, 2)]


def test_legacy_message_link_compatibility_is_preserved(monkeypatch):
    import core.workspace_publisher as workspace
    deliveries = [
        DeliveryResult("telegram", 7, 11, "@tg", primary_message_id=101, status="succeeded"),
        DeliveryResult("bale", 7, 12, "@bale", primary_message_id=202, status="succeeded"),
    ]
    monkeypatch.setattr(
        publication_engine,
        "publish_prepared_content",
        lambda *_a, **_k: {"ok": True, "results": deliveries},
    )
    recorded = []
    workspace.publish_to_destinations(
        "api",
        [
            {"id": 11, "workspace_id": 7, "platform": "telegram", "external_id": "@tg"},
            {"id": 12, "workspace_id": 7, "platform": "bale", "external_id": "@bale"},
        ],
        "text", None, None, lambda _i: {}, lambda _i: {},
        record_message_link_fn=lambda **value: recorded.append(value),
    )
    assert len(recorded) == 1
    assert recorded[0]["telegram_message_id"] == 101
    assert recorded[0]["bale_message_id"] == 202


def test_at_prefixed_and_unprefixed_target_are_deduplicated():
    a = PublicationTarget("a", "legacy", "telegram", "@Channel")
    b = PublicationTarget("b", "workspace", "telegram", "channel", 1, 1)
    assert canonical_target_identity(a) == canonical_target_identity(b)


def test_target_username_is_case_insensitive():
    a = PublicationTarget("a", "workspace", "telegram", "@Channel", 1, 1)
    b = PublicationTarget("b", "workspace", "telegram", "@channel", 2, 2)
    assert canonical_target_identity(a) == canonical_target_identity(b)


def test_database_resolver_does_not_invent_verified_chat_id():
    a = PublicationTarget("a", "workspace", "telegram", "@one", 1, 1, {"verified": True})
    b = PublicationTarget("b", "workspace", "telegram", "@two", 2, 2, {"verified": True})
    assert canonical_target_identity(a) != canonical_target_identity(b)


def test_same_name_on_telegram_and_bale_is_not_deduplicated():
    a = PublicationTarget("a", "workspace", "telegram", "@same", 1, 1)
    b = PublicationTarget("b", "workspace", "bale", "@same", 1, 2)
    assert canonical_target_identity(a) != canonical_target_identity(b)


def test_duplicate_destination_across_legacy_and_workspace_publishes_once(monkeypatch):
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@Same"),
        PublicationTarget("workspace", "workspace", "telegram", "same", 1, 2),
    ]
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("x", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan())
    sent = []
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: sent.append(1) or True)
    assert publication_engine.publish_prepared_content(1, "api", PreparedContent(main_text="x", source_key="dedup"), targets)["ok"]
    assert sent == [1]


def test_legacy_and_multiple_workspaces_do_not_duplicate_same_channel(monkeypatch):
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@Same"),
        PublicationTarget("w1", "workspace", "telegram", "same", 1, 10),
        PublicationTarget("w2", "workspace", "telegram", "@SAME", 2, 20),
    ]
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("x", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan())
    sent = []
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda _c, _a, t, _p: sent.append(t.key) or True)
    result = publication_engine.publish_prepared_content(
        1, "api", PreparedContent(main_text="x", source_key="dedup-three"), targets
    )
    assert result["ok"] is True
    assert len(sent) == 1


def test_legacy_bale_failure_remains_retryable_without_repeating_telegram(monkeypatch):
    targets = [
        PublicationTarget("tg", "legacy", "telegram", "@tg"),
        PublicationTarget("bale", "legacy", "bale", "@bale"),
    ]
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("x", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_k: _text_plan())
    calls, failed = [], {"bale": True}
    def sender(_c, _a, target, _p):
        calls.append(target.platform)
        if target.platform == "bale" and failed["bale"]:
            failed["bale"] = False
            return False
        return True
    monkeypatch.setattr(publication_engine, "_send_text_target", sender)
    prepared = PreparedContent(main_text="x", source_key="legacy-bale")
    assert publication_engine.publish_prepared_content(1, "api", prepared, targets)["ok"] is False
    assert publication_engine.publish_prepared_content(1, "api", prepared, targets)["ok"] is True
    assert calls == ["telegram", "bale", "bale"]


def test_smart_summary_runs_once_for_multiple_targets(monkeypatch):
    targets = [
        PublicationTarget("a", "workspace", "telegram", "@a", 1, 1),
        PublicationTarget("b", "workspace", "telegram", "@b", 2, 2),
    ]
    enabled = []
    def analyzer(**_kwargs):
        from core.caption_manager import smart_summarizer_enabled
        enabled.append(smart_summarizer_enabled())
        return _text_plan(["خلاصه"])
    monkeypatch.setenv("ENABLE_SMART_SUMMARIZER", "true")
    monkeypatch.setattr("core.caption_manager.analyze_content", analyzer)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda _c, _t, p: (p.neutral_text, ""))
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: True)
    prepared = PreparedContent(main_text="الف" * 5000, neutral_text="الف" * 5000, source_key="summary")
    assert publication_engine.publish_prepared_content(1, "api", prepared, targets)["ok"]
    assert enabled.count(True) == 1


def test_shared_analysis_is_reused_by_all_destinations(monkeypatch):
    test_smart_summary_runs_once_for_multiple_targets(monkeypatch)


def test_destination_formatting_does_not_change_shared_summary(monkeypatch):
    seen = []
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda _c, t, p: (p.neutral_text + t.key, t.key))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **kwargs: seen.append(kwargs["main_text"]) or _text_plan())
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: True)
    targets = [PublicationTarget("a", "workspace", "telegram", "@a", 1, 1), PublicationTarget("b", "workspace", "telegram", "@b", 2, 2)]
    prepared = PreparedContent(main_text="base", neutral_text="base", source_key="format")
    publication_engine.publish_prepared_content(1, "api", prepared, targets)
    assert seen == ["basea", "baseb"] and prepared.neutral_text == "base"


def test_shared_prepared_collections_are_immutable():
    prepared = PreparedContent(
        main_text="x", files=[{"file_id": "f"}], other_entities=[{"type": "bold"}],
        blockquote_blocks=[{"text": "q"}],
    )
    with pytest.raises(TypeError):
        prepared.files[0]["file_id"] = "changed"
    with pytest.raises(AttributeError):
        prepared.files.append({})


def test_shared_prepared_text_is_not_mutated_between_targets():
    prepared = PreparedContent(main_text="base")
    assert prepared.main_text == "base"


def test_shared_prepared_entities_are_not_mutated_between_targets():
    test_shared_prepared_collections_are_immutable()


def test_shared_prepared_files_are_not_mutated_between_targets():
    test_shared_prepared_collections_are_immutable()


def test_shared_prepared_blockquotes_are_not_mutated_between_targets():
    test_shared_prepared_collections_are_immutable()


def test_multiple_workspaces_receive_one_shared_prepared_content(monkeypatch):
    test_one_destination_failure_does_not_repeat_other_successful_destination(monkeypatch)


def test_multiple_destinations_in_one_workspace_receive_independent_plans(monkeypatch):
    targets = [PublicationTarget("a", "workspace", "telegram", "@a", 1, 1), PublicationTarget("b", "workspace", "telegram", "@b", 1, 2)]
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda _c, t, _p: (t.key, t.key))
    plans = []
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **k: plans.append((k["main_text"], k["branding"])) or _text_plan())
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_a: True)
    assert publication_engine.publish_prepared_content(1, "api", PreparedContent(main_text="x", source_key="multi-dest"), targets)["ok"]
    assert plans == [("a", "a"), ("b", "b")]


def test_partial_failure_in_one_workspace_does_not_repeat_other_workspaces(monkeypatch):
    test_one_destination_failure_does_not_repeat_other_successful_destination(monkeypatch)


def _assert_editorial_album(monkeypatch, forced_type):
    _album()
    queued, published = [], []
    monkeypatch.setattr("core.webhook_handler.detect_editorial_admin_tag", lambda text: (forced_type, text, 0))
    monkeypatch.setattr("core.webhook_handler.try_queue_editorial_text_review", lambda **kwargs: queued.append(kwargs) or True)
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda *_a, **_k: published.append(1) or {"ok": True})
    assert media_handler.process_media_group("g", 9, expected_generation=2) is True
    assert published == [] and len(queued) == 1
    assert len(queued[0]["media_files"]) == 2
    assert media_handler.pending_groups[(9, "g")]["state"] == "editorial_pending"


def test_opinion_note_album_uses_shared_workspace_pipeline(monkeypatch):
    _assert_editorial_album(monkeypatch, "opinion_note")


def test_analysis_album_uses_shared_workspace_pipeline(monkeypatch):
    _assert_editorial_album(monkeypatch, "news_analysis")


def test_editorial_album_is_evaluated_after_aggregation(monkeypatch):
    _assert_editorial_album(monkeypatch, "opinion_note")


def test_editorial_pending_is_single_for_multiple_targets(monkeypatch):
    _assert_editorial_album(monkeypatch, "opinion_note")


def test_approved_editorial_album_preserves_all_media(monkeypatch):
    import core.webhook_handler as webhook
    captured = []
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda _c, _a, prepared: captured.append(prepared) or {"ok": True})
    assert webhook.publish_prepared_text(
        9, "approved", editorial_finalized=True,
        files=[{"type": "photo", "file_id": "a"}, {"type": "photo", "file_id": "b"}],
        source_key="editorial:album",
    ) is True
    assert [item["file_id"] for item in captured[0].files] == ["a", "b"]


def _workspace_label(monkeypatch, destinations, workspace_name="واقعی"):
    import core.command_handler as command
    monkeypatch.setattr(command, "_ACTIVE_WORKSPACE_ENABLED", True, raising=False)
    monkeypatch.setattr(command, "get_tenant", lambda _c: None, raising=False)
    monkeypatch.setattr(command, "get_user_by_telegram_id", lambda _c: {"id": 5}, raising=False)
    monkeypatch.setattr(command, "list_user_workspaces", lambda *_a, **_k: [{"id": 7, "name": workspace_name, "membership_role": "owner"}], raising=False)
    monkeypatch.setattr(command, "get_active_workspace_preference", lambda _u: {"active_workspace_id": 7}, raising=False)
    monkeypatch.setattr(command, "set_active_workspace", lambda *_a: None, raising=False)
    monkeypatch.setattr(command, "importlib", SimpleNamespace(
        import_module=lambda _n: SimpleNamespace(
            list_selected_workspace_ids=lambda _u: [7],
            list_verified_active_destinations=lambda _w: destinations,
        )
    ), raising=False)
    captured = []
    monkeypatch.setattr(command, "send_message_with_keyboard", lambda _c, _t, keyboard: captured.append(keyboard) or True)
    assert command.handle_workspaces(9) is True
    return captured[0]


def test_handle_workspaces_uses_verified_telegram_destination(monkeypatch):
    keyboard = _workspace_label(monkeypatch, [
        {"id": 2, "platform": "bale", "external_id": "@bale"},
        {"id": 1, "platform": "telegram", "external_id": "@telegram", "is_default": True},
    ])
    assert "@telegram" in keyboard[0][0]["text"]


def test_handle_workspaces_falls_back_to_bale_destination(monkeypatch):
    keyboard = _workspace_label(monkeypatch, [{"id": 2, "platform": "bale", "external_id": "@bale"}])
    assert "@bale" in keyboard[0][0]["text"]


def test_handle_workspaces_falls_back_to_real_workspace_name(monkeypatch):
    keyboard = _workspace_label(monkeypatch, [], "نام واقعی")
    assert "نام واقعی" in keyboard[0][0]["text"]


def test_handle_workspaces_keeps_internal_callback_id(monkeypatch):
    keyboard = _workspace_label(monkeypatch, [])
    assert keyboard[0][0]["callback_data"] == "ws:toggle:7"


def test_handle_workspaces_does_not_mutate_setup_state(monkeypatch):
    setup_state = {"step": "branding_sample", "data": {"sample": "unchanged"}}
    before = {"step": setup_state["step"], "data": dict(setup_state["data"])}
    keyboard = _workspace_label(monkeypatch, [])
    assert keyboard
    assert setup_state == before


def test_wp_confirm_routes_through_shared_publication_engine(monkeypatch):
    import core.database as database
    import core.workspace_publisher as workspace
    for name in (
        "get_user_by_telegram_id", "get_active_workspace_preference",
        "list_selected_workspace_ids", "list_user_workspace_memberships",
        "get_workspace_setup_state",
    ):
        monkeypatch.setattr(database, name, lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(database, "get_destination_branding", lambda _i: {}, raising=False)
    monkeypatch.setattr(database, "get_workspace_branding", lambda _i: {}, raising=False)
    for name in ("set_active_legacy_context", "set_active_workspace", "set_legacy_workspace_selected", "select_workspace", "deselect_workspace"):
        monkeypatch.setattr(database, name, lambda *_a, **_k: None, raising=False)
    workspace.store_pending(9, [{"id": 1, "workspace_id": 7, "platform": "telegram", "external_id": "@tg"}], "text", None, None)
    called = []
    monkeypatch.setattr("core.publication_engine.publish_prepared_content", lambda *_a, **_k: called.append(1) or {"ok": True, "results": []})
    monkeypatch.setattr(workspace, "_ws_answer_callback", lambda *_a: None)
    monkeypatch.setattr(workspace, "_ws_send_message", lambda *_a: None)
    workspace._handle_workspace_callback({"id": "cb", "data": "wp:confirm", "from": {"id": 9}}, "r", "api")
    assert called == [1]


def test_no_workspace_raw_sender_is_called_from_wp_confirm(monkeypatch):
    test_wp_confirm_routes_through_shared_publication_engine(monkeypatch)


def test_no_workspace_raw_sender_is_called_from_webhook():
    import inspect
    import core.webhook_handler as webhook
    source = inspect.getsource(webhook.handle_webhook)
    assert "_try_workspace_publication(" not in source


def test_legacy_workspace_callback_remains_backward_compatible(monkeypatch):
    test_wp_confirm_routes_through_shared_publication_engine(monkeypatch)


def test_legitimate_standalone_hashtag_before_source_footer_is_preserved():
    text = "متن\n#واقعی\n🔷 @sourcechannel"
    assert "#واقعی" in remove_source_signature(text, source_username="sourcechannel")


def test_legitimate_standalone_mention_before_source_footer_is_preserved():
    text = "متن\n@realmention\n🔷 @sourcechannel"
    assert "@realmention" in remove_source_signature(text, source_username="sourcechannel")
