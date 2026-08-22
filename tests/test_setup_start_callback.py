import sys
import types

from flask import Flask

import core.webhook_handler as webhook_handler


app = Flask(__name__)


def _callback(data="setup:start", user_id=101, callback_id="cb-1"):
    return {
        "id": callback_id,
        "from": {"id": user_id},
        "data": data,
        "message": {"chat": {"id": user_id}, "message_id": 1},
    }


def test_setup_start_callback_answers_and_reuses_existing_setup(monkeypatch):
    answers = []
    setup_calls = []

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda callback_id, text="": answers.append((callback_id, text)) or True,
    )

    fake_command_handler = types.ModuleType("core.command_handler")
    fake_command_handler.handle_setup = (
        lambda chat_id: setup_calls.append(chat_id) or True
    )
    monkeypatch.setitem(
        sys.modules,
        "core.command_handler",
        fake_command_handler,
    )

    handled = webhook_handler.handle_setup_callback(
        _callback(),
        "setup-test",
    )

    assert handled is True
    assert setup_calls == [101]
    assert answers == [("cb-1", "در حال شروع راه‌اندازی...")]


def test_setup_callback_is_routed_before_editorial(monkeypatch):
    webhook_handler.initialize(
        api_url="https://api.telegram.org/botTEST_TOKEN",
        channel_id="@test_channel",
        secret_token="test-secret",
    )
    setup_callbacks = []
    editorial_callbacks = []

    monkeypatch.setattr(
        webhook_handler,
        "handle_setup_callback",
        lambda callback_query, req_id: setup_callbacks.append(callback_query) or True,
    )
    monkeypatch.setattr(
        webhook_handler,
        "handle_editorial_callback",
        lambda callback_query, req_id: editorial_callbacks.append(callback_query) or True,
    )

    payload = {"update_id": 1, "callback_query": _callback()}
    with app.test_request_context(
        "/",
        method="POST",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
    ):
        body, status = webhook_handler.handle_webhook()

    assert status == 200
    assert body == {"ok": True, "callback_handled": True}
    assert setup_callbacks == [payload["callback_query"]]
    assert editorial_callbacks == []


def test_unknown_setup_callback_is_answered_without_starting_setup(monkeypatch):
    answers = []
    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda callback_id, text="": answers.append((callback_id, text)) or True,
    )

    setup_calls = []

    assert webhook_handler.handle_setup_callback(
        _callback(data="setup:unknown"),
        "setup-invalid",
    ) is True
    assert setup_calls == []
    assert answers == [("cb-1", "دستور راه‌اندازی نامعتبر است.")]


def test_post_setup_callbacks_are_answered_and_explain_next_action(monkeypatch):
    answers = []
    messages = []
    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda callback_id, text="": answers.append((callback_id, text)) or True,
    )
    monkeypatch.setattr(
        webhook_handler,
        "send_message",
        lambda chat_id, text: messages.append((chat_id, text)) or True,
    )

    create_calls = []
    fake_command_handler = types.ModuleType("core.command_handler")
    fake_command_handler.handle_create_workspace = (
        lambda chat_id: create_calls.append(chat_id) or True
    )
    monkeypatch.setitem(sys.modules, "core.command_handler", fake_command_handler)

    expectations = {
        "setup:done": "راه‌اندازی کامل شد",
        "setup:later": "/destinations",
    }
    for callback_data, expected_text in expectations.items():
        answers.clear()
        messages.clear()
        assert webhook_handler.handle_setup_callback(
            _callback(data=callback_data),
            "setup-post-action",
        ) is True
        assert answers and answers[0][0] == "cb-1"
        assert len(messages) == 1
        assert messages[0][0] == 101
        assert expected_text in messages[0][1]

    for callback_data in ("setup:create_workspace", "setup:add_media"):
        answers.clear()
        assert webhook_handler.handle_setup_callback(
            _callback(data=callback_data),
            "setup-create-workspace",
        ) is True
        assert answers and answers[0][0] == "cb-1"

    assert create_calls == [101, 101]


def test_existing_callback_prefixes_are_not_claimed_by_setup_handler():
    for callback_data in (
        "ws:select:1",
        "wp:confirm",
        "ed:summary:review-1",
    ):
        assert webhook_handler.handle_setup_callback(
            _callback(data=callback_data),
            "existing-prefix",
        ) is False
