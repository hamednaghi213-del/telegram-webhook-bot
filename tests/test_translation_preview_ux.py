from dataclasses import replace
from unittest.mock import Mock

import pytest

from core import translation_controller as controller
from core import translation_state as states
from core import translation_telegram as telegram
from core.translation_ui import build_translation_preview_keyboard
from core.translation_publication import build_translation_publication_payload
from core.translation_pipeline import TranslationPipelineResult, PIPELINE_REVIEW_REQUIRED

A = "fdf90927-f25d-4909-a5ca-4ae37adac358"
B = "32424d3b-935e-439e-a442-17751b603f09"


def state(rid=A, **kwargs):
    values = dict(review_id=rid, chat_id=1, user_id=1, original_text="Original English story",
                  translated_text="متن فارسی", target_language="Persian", target_language_code="fa", status="preview")
    values.update(kwargs)
    return states.TranslationState(**values)


@pytest.fixture
def ui(monkeypatch):
    reviews = {A: state(A), B: state(B)}
    monkeypatch.setattr(telegram, "get_translation_state", reviews.get)
    active = Mock(return_value=B)
    monkeypatch.setattr(telegram, "_active_review_id", active)
    send, publish = Mock(), Mock()
    def click(action, rid=A):
        return telegram.handle_translation_telegram_callback(
            callback_query={"id": "cb", "data": f"tr:{action}" + (f":{rid}" if rid else ""),
                            "from": {"id": 1}, "message": {"chat": {"id": 1}}},
            answer_callback_query=Mock(), send_message=send, publish_prepared_text=publish,
        )
    return reviews, active, send, publish, click


def test_preview_callbacks_contain_full_identity():
    buttons = [button for row in build_translation_preview_keyboard(A) for button in row]
    assert {b.callback_data for b in buttons} == {
        f"tr:{action}:{A}" for action in ("confirm", "edit", "cancel", "original", "retranslate")
    }
    assert all(len(b.callback_data.encode()) <= 64 for b in buttons)


@pytest.mark.parametrize("action", ["confirm", "edit", "cancel", "original", "retranslate", "retryok", "keepedit"])
@pytest.mark.parametrize("status", ["cancelled", "confirmed", "failed"])
def test_stale_a_never_targets_b(ui, action, status):
    reviews, active, send, publish, click = ui
    reviews[A] = replace(reviews[A], status=status)
    before = reviews[B]
    assert not click(action).success
    active.assert_not_called()
    publish.assert_not_called()
    assert reviews[B] is before
    assert "#fdf90927" in send.call_args.args[1]


@pytest.mark.parametrize("action", ["confirm", "edit", "cancel", "original", "retranslate"])
def test_unbound_legacy_preview_buttons_rejected(ui, action):
    _, active, _, publish, click = ui
    assert not click(action, "").success
    active.assert_not_called()
    publish.assert_not_called()


@pytest.mark.parametrize("action,handler", [
    ("edit", "request_translation_edit"), ("cancel", "cancel_translation"),
    ("original", "get_translation_original"), ("retranslate", "retranslate_translation"),
    ("confirm", "confirm_translation"),
])
def test_action_targets_exact_a_not_active_b(ui, monkeypatch, action, handler):
    reviews, active, send, publish, click = ui
    result = controller.TranslationControllerResult(success=False, action=controller.RESULT_FAILED, review_id=A)
    handler_mock = Mock(return_value=result)
    monkeypatch.setattr(telegram, handler, handler_mock)
    click(action)
    assert handler_mock.call_args.kwargs["review_id"] == A
    active.assert_not_called()
    publish.assert_not_called()


def test_foreign_owner_rejected(ui):
    reviews, active, send, publish, click = ui
    reviews[A] = replace(reviews[A], user_id=2)
    assert not click("confirm").success
    publish.assert_not_called()


def test_successful_confirm_uses_a_state_even_when_b_active(ui, monkeypatch):
    reviews, active, send, publish, click = ui
    from types import SimpleNamespace
    confirmed = replace(reviews[A], status="confirmed")
    monkeypatch.setattr(telegram, "confirm_translation", Mock(return_value=
        controller.TranslationControllerResult(success=True, action=controller.RESULT_CONFIRMED, state=confirmed, review_id=A)))
    bridge = Mock(return_value=SimpleNamespace(success=True, published=True, review_id=A, reason=""))
    monkeypatch.setattr(telegram, "publish_confirmed_translation", bridge)
    click("confirm")
    assert bridge.call_args.kwargs["state"] is confirmed
    active.assert_not_called()
    assert all("#fdf90927" in call.args[1] for call in send.call_args_list)
    assert reviews[B].status == "preview"


def test_malformed_review_callback_rejected(ui):
    _, active, _, publish, click = ui
    assert not click("confirm", A + ":extra").success
    active.assert_not_called()
    publish.assert_not_called()


def test_edit_retranslation_needs_explicit_confirmation(ui, monkeypatch):
    reviews, _, send, publish, click = ui
    reviews[A] = replace(reviews[A], edited_text="my edit", translated_text="my edit")
    retry = Mock(return_value=controller.TranslationControllerResult(success=False, action=controller.RESULT_FAILED, review_id=A))
    monkeypatch.setattr(telegram, "retranslate_translation", retry)
    click("retranslate")
    retry.assert_not_called()
    assert "اصلاح دستی" in send.call_args.args[1]
    callbacks = [b["callback_data"] for row in send.call_args.kwargs["reply_markup"]["inline_keyboard"] for b in row]
    assert f"tr:retryok:{A}" in callbacks
    click("keepedit")
    retry.assert_not_called()
    assert reviews[A].edited_text == "my edit"
    click("retryok")
    assert retry.call_args.kwargs == dict(review_id=A, chat_id=1, user_id=1, replace_edit=True)
    publish.assert_not_called()


def test_preview_uses_clean_effective_text_and_policy_notice():
    body = "اصلاح دستی با https://example.com/evidence در متن خبر."
    current = state(translated_text=body + "\n\nhttps://source.example/article", edited_text=body,
                    metadata={"forward_source": {"source_title": "Source News"},
                              "translation_pipeline_metadata": {"editorial_policy": {"status": "review_required", "reason": "debug_code"}}})
    result = controller.TranslationControllerResult(success=True, action=controller.RESULT_PREVIEW,
        review_id=A, state=current, translated_text=current.translated_text, text="Preview")
    send = Mock()
    telegram.render_translation_result(result=result, chat_id=1, send_message=send)
    rendered = send.call_args.args[1]
    assert build_translation_publication_payload(current)["main_text"] in rendered
    assert body in rendered and "source.example" not in rendered
    assert "نیاز به بازبینی" in rendered
    assert "debug_code" not in rendered
    assert "#fdf90927" in rendered


@pytest.fixture
def restart(monkeypatch):
    store = {A: state(edited_text="manual edit", translated_text="manual edit")}
    monkeypatch.setattr(states, "get_translation_state", store.get)
    monkeypatch.setattr(controller, "get_translation_state", store.get)
    def update(rid, **kwargs):
        store[rid] = replace(store[rid], **kwargs)
        return store[rid]
    monkeypatch.setattr(states, "update_translation_state", update)
    pipe = Mock(return_value=TranslationPipelineResult(
        success=True, status=PIPELINE_REVIEW_REQUIRED, original_text="Original English story",
        output_text="ترجمه جدید", requires_review=True,
    ))
    monkeypatch.setattr(controller, "run_manual_translation_pipeline", pipe)
    return store, pipe


def test_retranslation_runs_original_then_preview_same_identity(restart):
    store, pipe = restart
    result = controller.retranslate_translation(review_id=A, chat_id=1, user_id=1, replace_edit=True)
    assert result.success and result.action == controller.RESULT_PREVIEW
    assert pipe.call_args.kwargs["text"] == "Original English story"
    assert store[A].status == "preview" and store[A].review_id == A
    assert store[A].edited_text == ""
    assert all(b["callback_data"].endswith(A) for row in result.reply_markup["inline_keyboard"] for b in row)


def test_controller_rejects_silent_edit_replacement(restart):
    store, pipe = restart
    assert not controller.retranslate_translation(review_id=A, chat_id=1, user_id=1).success
    pipe.assert_not_called()
    assert store[A].edited_text == "manual edit"


def test_restart_transition_keeps_edit_until_success(restart):
    store, _ = restart
    assert states.set_translation_language(A, target_language="fa") is None
    changed = states.set_translation_language(A, target_language="fa", restart_preview=True)
    assert changed.status == "translating" and changed.edited_text == "manual edit"


def test_terminal_restart_rejected(restart):
    store, pipe = restart
    store[A] = replace(store[A], status="confirmed")
    assert not controller.retranslate_translation(review_id=A, chat_id=1, user_id=1, replace_edit=True).success
    pipe.assert_not_called()
