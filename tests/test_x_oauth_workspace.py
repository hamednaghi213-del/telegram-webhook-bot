from urllib.parse import parse_qs, urlparse

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
    member=None,
    active_workspace_calls=None,
):
    import types

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

    module.get_workspace_member = (
        lambda *_args, **_kwargs: member
    )

    return module


def test_workspace_management_panel_adds_x_button_when_missing():
    workspace = {
        "id": 101,
        "name": "Test Workspace",
    }

    destinations = [
        {
            "id": 1,
            "workspace_id": 101,
            "platform": "telegram",
            "external_id": "@example",
            "status": "active",
        },
        {
            "id": 2,
            "workspace_id": 101,
            "platform": "bale",
            "external_id": "@example_bale",
            "status": "active",
        },
    ]

    text, keyboard = (
        workspace_publisher.build_workspace_management_panel(
            workspace,
            destinations,
        )
    )

    buttons = _flatten_buttons(
        keyboard
    )

    assert "➕ افزودن حساب X" in text

    assert any(
        button.get("text")
        == "➕ افزودن حساب X"
        and button.get("callback_data")
        == "ws:addx:101"
        for button in buttons
    )


def test_workspace_management_panel_hides_x_button_when_x_exists():
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
        )
    )

    buttons = _flatten_buttons(
        keyboard
    )

    assert not any(
        button.get("callback_data")
        == "ws:addx:101"
        for button in buttons
    )

    assert any(
        "— X" in button.get(
            "text",
            "",
        )
        for button in buttons
    )

    assert (
        "x:123456789 — X"
        in text
    )


def test_x_pkce_and_state_hash_are_deterministic():
    verifier = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-._~"
    )

    challenge_1 = (
        x_oauth.build_pkce_challenge(
            verifier
        )
    )

    challenge_2 = (
        x_oauth.build_pkce_challenge(
            verifier
        )
    )

    assert challenge_1
    assert (
        challenge_1
        == challenge_2
    )
    assert "=" not in challenge_1

    state = "known-oauth-state"

    state_hash_1 = (
        x_oauth.hash_oauth_state(
            state
        )
    )

    state_hash_2 = (
        x_oauth.hash_oauth_state(
            state
        )
    )

    assert state_hash_1
    assert (
        state_hash_1
        == state_hash_2
    )
    assert (
        state_hash_1
        != state
    )


def test_start_x_oauth_persists_only_hashed_state_and_encrypted_verifier(
    monkeypatch,
):
    import sys
    import types

    captured = {}

    monkeypatch.setattr(
        x_oauth,
        "X_CLIENT_ID",
        "test-client-id",
    )

    monkeypatch.setattr(
        x_oauth,
        "X_CLIENT_SECRET",
        "",
    )

    monkeypatch.setattr(
        x_oauth,
        "X_OAUTH_REDIRECT_URI",
        "https://example.com/oauth/x/callback",
    )

    monkeypatch.setattr(
        x_oauth,
        "X_OAUTH_ENCRYPTION_KEY",
        "test-key-for-mocked-encryption",
    )

    monkeypatch.setattr(
        x_oauth,
        "generate_oauth_state",
        lambda: "raw-test-state",
    )

    monkeypatch.setattr(
        x_oauth,
        "generate_pkce_verifier",
        lambda: "raw-test-verifier",
    )

    monkeypatch.setattr(
        x_oauth,
        "encrypt_x_secret",
        lambda value: (
            f"encrypted::{value}"
        ),
    )

    def fake_create_x_oauth_session(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return {
            "id": 1,
            **kwargs,
        }

    fake_database = (
        types.ModuleType(
            "core.database"
        )
    )

    fake_database.create_x_oauth_session = (
        fake_create_x_oauth_session
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )

    authorization_url = (
        x_oauth.start_x_oauth(
            workspace_id=101,
            requested_by_user_id=55,
            action="connect",
        )
    )

    parsed = urlparse(
        authorization_url
    )

    query = parse_qs(
        parsed.query
    )

    assert query["client_id"] == [
        "test-client-id"
    ]

    assert query[
        "redirect_uri"
    ] == [
        "https://example.com/oauth/x/callback"
    ]

    assert query[
        "response_type"
    ] == [
        "code"
    ]

    assert query[
        "state"
    ] == [
        "raw-test-state"
    ]

    assert query.get(
        "code_challenge"
    )

    assert query.get(
        "code_challenge_method"
    ) == [
        "S256"
    ]

    assert (
        captured["workspace_id"]
        == 101
    )

    assert (
        captured[
            "requested_by_user_id"
        ]
        == 55
    )

    assert (
        captured["action"]
        == "connect"
    )

    assert (
        captured["state_hash"]
        == x_oauth.hash_oauth_state(
            "raw-test-state"
        )
    )

    assert (
        captured["state_hash"]
        != "raw-test-state"
    )

    assert (
        captured[
            "code_verifier_ciphertext"
        ]
        == (
            "encrypted::"
            "raw-test-verifier"
        )
    )

    assert (
        captured[
            "code_verifier_ciphertext"
        ]
        != "raw-test-verifier"
    )

    assert (
        captured[
            "redirect_uri"
        ]
        == (
            "https://example.com/"
            "oauth/x/callback"
        )
    )


def test_ws_addx_owner_starts_oauth_and_sends_url_button(
    monkeypatch,
):
    import sys

    oauth_calls = []
    active_workspace_calls = []
    answers = []
    keyboards = []
    messages = []

    fake_database = (
        _fake_database_module(
            member={
                "role": "owner",
                "status": "active",
            },
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
        action,
    ):
        oauth_calls.append(
            {
                "workspace_id":
                    workspace_id,
                "requested_by_user_id":
                    requested_by_user_id,
                "action":
                    action,
            }
        )

        return (
            "https://x.example/"
            "authorize?state=test"
        )

    monkeypatch.setattr(
        x_oauth,
        "start_x_oauth",
        fake_start_x_oauth,
    )

    callback_query = {
        "id": "callback-x-1",
        "data": "ws:addx:101",
        "from": {
            "id": 777,
        },
    }

    workspace_publisher._handle_workspace_callback(
        callback_query,
        "req-x-1",
        "https://api.telegram.test",
    )

    assert oauth_calls == [
        {
            "workspace_id": 101,
            "requested_by_user_id": 55,
            "action": "connect",
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

    assert "X" in text

    buttons = _flatten_buttons(
        keyboard
    )

    assert any(
        button.get("text")
        == "🔗 اتصال حساب X"
        and button.get("url")
        == (
            "https://x.example/"
            "authorize?state=test"
        )
        for button in buttons
    )

    assert any(
        item[2]
        == "لینک اتصال X آماده شد"
        for item in answers
    )


def test_ws_addx_non_manager_cannot_start_oauth(
    monkeypatch,
):
    import sys

    oauth_calls = []
    keyboards = []
    answers = []

    fake_database = (
        _fake_database_module(
            member={
                "role": "publisher",
                "status": "active",
            },
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
        lambda *_args,
        **_kwargs: None,
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
        "id": "callback-x-denied",
        "data": "ws:addx:101",
        "from": {
            "id": 777,
        },
    }

    workspace_publisher._handle_workspace_callback(
        callback_query,
        "req-x-denied",
        "https://api.telegram.test",
    )

    assert oauth_calls == []
    assert keyboards == []

    assert any(
        item[2]
        == "گروه رسانه‌ای معتبر نیست"
        for item in answers
    )