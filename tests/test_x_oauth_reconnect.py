import sys
import types

from core import workspace_publisher
from core import x_oauth


def _flatten_buttons(keyboard):
    return [
        button
        for row in keyboard
        for button in row
    ]


def _fake_database_module(
    *,
    role="owner",
    connection_status="reconnect_required",
    active_workspace_calls=None,
):
    module = types.ModuleType(
        "core.database"
    )

    module.get_destination_branding = (
        lambda *_args, **_kwargs: {}
    )

    module.get_workspace_branding = (
        lambda *_args, **_kwargs: {}
    )

    module.set_active_legacy_context = (
        lambda *_args, **_kwargs: None
    )

    def set_active_workspace(
        user_id,
        workspace_id,
    ):
        if active_workspace_calls is not None:
            active_workspace_calls.append(
                (
                    user_id,
                    workspace_id,
                )
            )

        return True

    module.set_active_workspace = (
        set_active_workspace
    )

    module.set_legacy_workspace_selected = (
        lambda *_args, **_kwargs: None
    )

    module.get_active_workspace_preference = (
        lambda *_args, **_kwargs: {}
    )

    module.list_selected_workspace_ids = (
        lambda *_args, **_kwargs: []
    )

    module.select_workspace = (
        lambda *_args, **_kwargs: None
    )

    module.deselect_workspace = (
        lambda *_args, **_kwargs: None
    )

    module.list_user_workspace_memberships = (
        lambda *_args, **_kwargs: []
    )

    module.get_workspace_setup_state = (
        lambda *_args, **_kwargs: {
            "step": "completed",
        }
    )

    module.get_publication_destination = (
        lambda destination_id: {
            "id": destination_id,
            "workspace_id": 101,
            "platform": "x",
            "external_id": "x:123456789",
            "status": "active",
        }
    )

    module.get_workspace = (
        lambda workspace_id: {
            "id": workspace_id,
            "status": "active",
        }
    )

    module.get_workspace_member = (
        lambda workspace_id,
        user_id: {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": role,
            "status": "active",
        }
    )

    module.get_x_oauth_connection = (
        lambda destination_id: {
            "destination_id": destination_id,
            "workspace_id": 101,
            "connection_status": (
                connection_status
            ),
        }
    )

    return module


def test_workspace_management_panel_shows_reconnect_only_when_required():
    workspace = {
        "id": 101,
        "name": "Test Workspace",
    }

    destinations = [
        {
            "id": 3,
            "workspace_id": 101,
            "platform": "x",
            "external_id": "x:123456789",
            "status": "active",
        },
    ]

    text, keyboard = (
        workspace_publisher.build_workspace_management_panel(
            workspace,
            destinations,
            {
                3: "reconnect_required",
            },
        )
    )

    buttons = _flatten_buttons(
        keyboard
    )

    assert (
        "⚠️ اتصال حساب X نیاز به اتصال مجدد دارد."
        in text
    )

    assert any(
        button.get("text")
        == "🔄 اتصال مجدد X"
        and button.get("callback_data")
        == "ws:reconnectx:3"
        for button in buttons
    )

    connected_text, connected_keyboard = (
        workspace_publisher.build_workspace_management_panel(
            workspace,
            destinations,
            {
                3: "connected",
            },
        )
    )

    connected_buttons = _flatten_buttons(
        connected_keyboard
    )

    assert (
        "⚠️ اتصال حساب X نیاز به اتصال مجدد دارد."
        not in connected_text
    )

    assert not any(
        button.get("callback_data")
        == "ws:reconnectx:3"
        for button in connected_buttons
    )


def test_ws_reconnectx_owner_starts_reconnect_for_same_destination(
    monkeypatch,
):
    oauth_calls = []
    active_workspace_calls = []
    answers = []
    keyboards = []
    messages = []

    fake_database = (
        _fake_database_module(
            role="owner",
            connection_status=(
                "reconnect_required"
            ),
            active_workspace_calls=(
                active_workspace_calls
            ),
        )
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_identity_for_chat",
        lambda _chat_id: {
            "id": 55,
        },
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda api_url,
        callback_id,
        text="": answers.append(
            (
                api_url,
                callback_id,
                text,
            )
        ),
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message_with_keyboard",
        lambda api_url,
        chat_id,
        text,
        keyboard: keyboards.append(
            (
                api_url,
                chat_id,
                text,
                keyboard,
            )
        ),
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message",
        lambda api_url,
        chat_id,
        text: messages.append(
            (
                api_url,
                chat_id,
                text,
            )
        ),
    )

    def fake_start_x_oauth(
        *,
        workspace_id,
        requested_by_user_id,
        destination_id=None,
        action="connect",
    ):
        oauth_calls.append(
            {
                "workspace_id":
                    workspace_id,
                "requested_by_user_id":
                    requested_by_user_id,
                "destination_id":
                    destination_id,
                "action":
                    action,
            }
        )

        return (
            "https://x.example/"
            "authorize?state=reconnect"
        )

    monkeypatch.setattr(
        x_oauth,
        "start_x_oauth",
        fake_start_x_oauth,
    )

    callback_query = {
        "id": "callback-x-reconnect",
        "data": "ws:reconnectx:3",
        "from": {
            "id": 777,
        },
    }

    workspace_publisher._handle_workspace_callback(
        callback_query,
        "req-x-reconnect",
        "https://api.telegram.test",
    )

    assert oauth_calls == [
        {
            "workspace_id": 101,
            "requested_by_user_id": 55,
            "destination_id": 3,
            "action": "reconnect",
        }
    ]

    assert active_workspace_calls == [
        (
            55,
            101,
        )
    ]

    assert keyboards
    assert not messages

    (
        api_url,
        chat_id,
        text,
        keyboard,
    ) = keyboards[0]

    assert (
        api_url
        == "https://api.telegram.test"
    )

    assert chat_id == 777
    assert "اتصال مجدد" in text

    buttons = _flatten_buttons(
        keyboard
    )

    assert any(
        button.get("text")
        == "🔄 اتصال مجدد X"
        and button.get("url")
        == (
            "https://x.example/"
            "authorize?state=reconnect"
        )
        for button in buttons
    )

    assert any(
        item[2]
        == "لینک اتصال مجدد X آماده شد"
        for item in answers
    )


def test_ws_reconnectx_non_manager_cannot_start_reconnect(
    monkeypatch,
):
    oauth_calls = []
    answers = []
    keyboards = []
    messages = []

    fake_database = (
        _fake_database_module(
            role="publisher",
            connection_status=(
                "reconnect_required"
            ),
        )
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_identity_for_chat",
        lambda _chat_id: {
            "id": 55,
        },
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_answer_callback",
        lambda api_url,
        callback_id,
        text="": answers.append(
            (
                api_url,
                callback_id,
                text,
            )
        ),
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message_with_keyboard",
        lambda *args,
        **kwargs: keyboards.append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        workspace_publisher,
        "_ws_send_message",
        lambda api_url,
        chat_id,
        text: messages.append(
            (
                api_url,
                chat_id,
                text,
            )
        ),
    )

    def fake_start_x_oauth(
        **kwargs,
    ):
        oauth_calls.append(
            kwargs
        )

        return (
            "https://x.example/"
            "should-not-be-used"
        )

    monkeypatch.setattr(
        x_oauth,
        "start_x_oauth",
        fake_start_x_oauth,
    )

    callback_query = {
        "id": "callback-x-reconnect-denied",
        "data": "ws:reconnectx:3",
        "from": {
            "id": 777,
        },
    }

    workspace_publisher._handle_workspace_callback(
        callback_query,
        "req-x-reconnect-denied",
        "https://api.telegram.test",
    )

    assert oauth_calls == []
    assert keyboards == []
    assert messages

    assert any(
        item[2]
        == "اتصال مجدد X آماده نشد"
        for item in answers
    )