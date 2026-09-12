"""Mocked provider/storage E2E coverage through the real controller and bridge."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import automatic_translation_review as automatic
from core import translation_controller as controller
from core import translation_editorial_policy as editorial
from core import translation_pipeline as pipeline
from core import translation_provider as provider
from core import translation_state as states
from core import translation_telegram as telegram


SOURCE = "The latest news was published."
MACHINE = "خبر تازه منتشر شد."


@pytest.fixture
def flow(monkeypatch):
    rows, stages = {}, []

    def update(rid, **values):
        row = rows[rid]
        expected = values.pop("expected_status", None)
        if expected is not None and row["status"] != expected:
            return None
        metadata = values.pop("metadata", None)
        if metadata:
            row["metadata"].update(deepcopy(metadata))
        for key in ("target_language_code", "source_key"):
            value = values.pop(key, None)
            if value is not None:
                row["metadata"][key] = value
        kind = values.pop("source_kind", None)
        if kind is not None:
            row["content_kind"] = kind
        row.update({k: deepcopy(v) for k, v in values.items() if v is not None})
        return deepcopy(row)

    def create(**values):
        rid = values.pop("review_id")
        rows[rid] = dict(review_id=rid, status="waiting_language", metadata={},
                         translated_text="", edited_text="")
        return update(rid, **values)

    db = SimpleNamespace(
        create_persistent_translation_review=create,
        get_persistent_translation_review=lambda rid: deepcopy(rows.get(rid)),
        update_persistent_translation_review=update,
        mark_persistent_translation_review_failed=lambda rid, **kw: update(rid, status="failed", **kw),
        mark_persistent_translation_review_confirmed=lambda rid: update(rid, status="confirmed"),
    )
    monkeypatch.setattr(states, "_database", lambda: db)
    monkeypatch.setattr(controller, "get_active_translation_state", lambda **kw:
                        states._state_from_row(next(reversed(rows.values()))))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "_detect_language", lambda text: None)
    monkeypatch.setattr(pipeline, "_deterministic_language", lambda result: "auto")

    def detect(text):
        stages.append("detect")
        return {"success": True, "language": "en"}
    monkeypatch.setattr(pipeline, "_provider_language_detection", detect)

    def reply(status=200, details=None):
        data = ({"candidates": [{"content": {"parts": [{"text": MACHINE}]}}]}
                if status == 200 else {"error": {"details": details or []}})
        return SimpleNamespace(ok=status == 200, status_code=status, headers={}, json=lambda: data)

    responses = []
    def post(*args, **kwargs):
        stages.append("translate")
        return responses.pop(0) if responses else reply()
    monkeypatch.setattr(provider, "provider_post", post)
    original_policy = editorial.apply_editorial_translation_policy
    def policy(**kwargs):
        stages.append("policy")
        return original_policy(**kwargs)
    monkeypatch.setattr(editorial, "apply_editorial_translation_policy", policy)
    def quality(**kwargs):
        stages.append("quality")
        return {"passed": True, "semantic_verified": True}
    monkeypatch.setattr(pipeline, "_quality_check", quality)
    send, publish = Mock(), Mock(return_value={"ok": True})

    def click(rid, action, user=1):
        return telegram.handle_translation_telegram_callback(
            callback_query={"id": "cb", "data": f"tr:{action}:{rid}",
                            "from": {"id": user}, "message": {"chat": {"id": 1}}},
            send_message=send, answer_callback_query=Mock(), publish_prepared_text=publish,
        )

    def start(**kwargs):
        return automatic.start_automatic_persian_translation_review(
            chat_id=1, user_id=1, original_text=kwargs.pop("original_text", SOURCE), **kwargs)

    return SimpleNamespace(rows=rows, stages=stages, responses=responses, reply=reply,
                           start=start, click=click, send=send, publish=publish, update=update)


@pytest.mark.parametrize("kind,files", [
    ("text", []), ("photo", [{"type": "photo", "file_id": "cached-photo"}]),
    ("video", [{"type": "video", "file_id": "cached-video", "width": 640}]),
])
def test_automatic_to_confirm_uses_shared_bridge(flow, kind, files):
    metadata = {"files": files, "forward_source": {"source_title": "Source"}}
    result = flow.start(source_kind=kind, metadata=metadata)
    assert result.success
    assert flow.stages == ["detect", "translate", "policy", "quality"]
    telegram.render_translation_result(result=result.controller_result, chat_id=1, send_message=flow.send)
    assert MACHINE in flow.send.call_args.args[1]
    assert flow.send.call_args.kwargs["link_preview_options"] == {"is_disabled": True}
    flow.publish.assert_not_called()
    assert flow.click(result.review_id, "confirm").success
    payload = flow.publish.call_args.kwargs
    assert payload["main_text"] == MACHINE and payload["files"] == files
    assert "link_preview_options" not in payload
    assert len(flow.rows) == 1 and flow.rows[result.review_id]["status"] == "confirmed"
    assert flow.stages == ["detect", "translate", "policy", "quality"]


def test_edit_provenance_preview_confirm_no_ai_rerun(flow):
    result = flow.start(original_text="  " + SOURCE + "\n")
    rid = result.review_id
    assert flow.click(rid, "edit").success
    edited = "واژه‌های انتخابی من با https://example.org/evidence در متن."
    result = controller.submit_translation_edit(chat_id=1, user_id=1, translated_text=edited)
    assert result.success
    assert result.state.original_text == "  " + SOURCE + "\n"
    assert result.state.translated_text == MACHINE
    assert result.state.edited_text == edited
    telegram.render_translation_result(result=result, chat_id=1, send_message=flow.send)
    preview = flow.send.call_args.args[1]
    assert "──────────\n" + edited + "\n──────────" in preview
    assert "متن اصلاح‌شده" in preview and "زبان مقصد:" not in preview
    before = list(flow.stages)
    flow.click(rid, "confirm")
    assert flow.publish.call_args.kwargs["main_text"] == edited
    assert flow.stages == before
    assert flow.rows[rid]["translated_text"] == MACHINE


def test_retranslation_uses_original_same_review(flow, monkeypatch):
    result = flow.start()
    rid = result.review_id
    flow.click(rid, "edit")
    controller.submit_translation_edit(chat_id=1, user_id=1, translated_text="اصلاح من")
    original_run = controller.run_manual_translation_pipeline
    run = Mock(wraps=original_run)
    monkeypatch.setattr(controller, "run_manual_translation_pipeline", run)
    flow.click(rid, "retranslate")
    run.assert_not_called()
    assert flow.click(rid, "retryok").success
    assert run.call_args.kwargs["text"] == SOURCE
    assert len(flow.rows) == 1 and flow.rows[rid]["edited_text"] == ""
    assert flow.stages == ["detect", "translate", "policy", "quality"] * 2
    flow.publish.assert_not_called()


@pytest.mark.parametrize("quota", [False, True])
def test_deferred_failure_later_retries_same_review(flow, quota):
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]
    if quota:
        details.append({"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{}]})
    flow.responses.append(flow.reply(429, details))
    files = [{"type": "photo", "file_id": "cached"}]
    result = flow.start(source_kind="photo", metadata={"files": files, "forward_source": {"source_title": "Source"}})
    rid = result.review_id
    assert not result.success and flow.rows[rid]["status"] == "failed"
    assert flow.stages == ["detect", "translate"]
    assert not flow.rows[rid]["translated_text"]
    telegram.render_translation_result(result=result.controller_result, chat_id=1, send_message=flow.send)
    assert "quota" not in flow.send.call_args.args[1] and "429" not in flow.send.call_args.args[1]
    button = flow.send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]
    assert button["callback_data"] == f"tr:retry:{rid}"
    before = deepcopy(flow.rows[rid])
    assert not flow.click(rid, "confirm").success
    assert not flow.click(rid, "retry", user=2).success
    assert flow.rows[rid] == before
    assert flow.click(rid, "retry").success
    assert flow.rows[rid]["status"] == "preview" and len(flow.rows) == 1
    assert flow.rows[rid]["metadata"]["files"] == files
    assert flow.rows[rid]["original_text"] == SOURCE
    assert flow.stages == ["detect", "translate", "detect", "translate", "policy", "quality"]
    assert not flow.click(rid, "retry").success
    flow.publish.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_failure_has_no_retry(flow, status):
    flow.responses.append(flow.reply(status))
    result = flow.start()
    assert not result.success
    telegram.render_translation_result(result=result.controller_result, chat_id=1, send_message=flow.send)
    assert not flow.send.call_args.kwargs["reply_markup"]
    assert not flow.click(result.review_id, "retry").success
    assert flow.stages == ["detect", "translate"]
    flow.publish.assert_not_called()


def test_stale_retry_does_not_mutate_new_review(flow):
    first = flow.start()
    second = flow.start()
    before = deepcopy(flow.rows)
    assert not flow.click(first.review_id, "retry").success
    assert not flow.click("missing", "retry").success
    assert flow.rows == before
    assert second.review_id != first.review_id
    flow.publish.assert_not_called()


def test_failed_retry_claim_is_consumed_before_provider_call(flow):
    flow.responses.append(flow.reply(429))
    result = flow.start()
    rid = result.review_id
    claimed = states.set_translation_language(rid, target_language="Persian", retry_failed=True)
    assert claimed.status == "translating"
    assert states.set_translation_language(rid, target_language="Persian", retry_failed=True) is None
    assert not flow.click(rid, "retry").success
    assert flow.stages == ["detect", "translate"]


def test_exhausted_transient_failure_can_retry_later(flow, monkeypatch):
    from core import translation_service as service
    sleep = Mock()
    monkeypatch.setattr(service.time, "sleep", sleep)
    flow.responses.extend([flow.reply(503)] * 3)
    result = flow.start()
    assert not result.success
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    assert flow.stages == ["detect", "translate", "translate", "translate"]
    assert flow.click(result.review_id, "retry").success
    assert len(flow.rows) == 1 and flow.rows[result.review_id]["status"] == "preview"
    flow.publish.assert_not_called()


def test_automatic_webhook_failure_renders_retry_and_preserves_source(flow, monkeypatch):
    from core import webhook_handler as webhook
    monkeypatch.setattr(webhook, "send_message", flow.send)
    flow.responses.append(flow.reply(429))
    source = "  " + SOURCE + "\n"
    result = webhook.try_automatic_persian_translation_gate(
        chat_id=1, text=source, source_kind="text", source_key="source-message")
    assert result["translation_blocked"]
    row = next(iter(flow.rows.values()))
    assert row["original_text"] == source
    assert flow.send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"tr:retry:{row['review_id']}"
    assert flow.send.call_args.kwargs["link_preview_options"] == {"is_disabled": True}
    flow.publish.assert_not_called()


def test_retry_old_failed_review_preserves_new_review(flow):
    flow.responses.append(flow.reply(429))
    first = flow.start()
    second = flow.start()
    before = deepcopy(flow.rows[second.review_id])
    assert flow.click(first.review_id, "retry").success
    assert flow.rows[second.review_id] == before
    assert len(flow.rows) == 2
    flow.publish.assert_not_called()


@pytest.mark.parametrize("current_status", ["failed", "translating", "confirmed", "cancelled"])
def test_database_retry_update_is_conditional(monkeypatch, current_status):
    # Load the real adapter independently of legacy tests' core.database stubs.
    import importlib.util
    from pathlib import Path
    import supabase
    monkeypatch.setenv("SUPABASE_URL", "https://database.example")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setattr(supabase, "create_client", Mock())
    spec = importlib.util.spec_from_file_location("lifecycle_database", Path(states.__file__).with_name("database.py"))
    database = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(database)
    filters = {}
    query = Mock()
    query.table.return_value = query
    query.update.return_value = query
    def eq(key, value):
        filters[key] = value
        return query
    query.eq.side_effect = eq
    query.execute.side_effect = lambda: SimpleNamespace(data=
        [{"review_id": "review", "status": "translating"}]
        if filters.get("status", current_status) == current_status else [])
    monkeypatch.setattr(database, "_translation_service_client", lambda: query)
    # A concurrent callback may already have changed the row since this read.
    monkeypatch.setattr(database, "get_persistent_translation_review",
                        lambda rid: {"review_id": rid, "status": "failed", "metadata": {"files": ["photo"]}})
    result = database.update_persistent_translation_review(
        "review", status="translating", expected_status="failed",
        metadata={"translation_retry_available": False})
    assert bool(result) == (current_status == "failed")
    assert filters == {"review_id": "review", "status": "failed"}
    assert query.update.call_args.args[0]["metadata"]["files"] == ["photo"]
    query.execute.assert_called_once()
