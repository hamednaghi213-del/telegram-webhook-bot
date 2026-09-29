import importlib
import sys
import types
from types import SimpleNamespace

import werkzeug

if not hasattr(
    werkzeug,
    "__version__",
):
    werkzeug.__version__ = "3"


def _module(
    name,
    **attrs,
):
    module = types.ModuleType(
        name
    )

    for key, value in (
        attrs.items()
    ):
        setattr(
            module,
            key,
            value,
        )

    return module


def _load_main_safely(
    monkeypatch,
    *,
    member=None,
    oauth_result=None,
    calls=None,
    upsert_result=None,
    publication_destination=None,
    x_connection=None,
):
    calls = (
        calls
        if calls is not None
        else {}
    )

    calls.setdefault(
        "register",
        [],
    )

    calls.setdefault(
        "activate",
        [],
    )

    calls.setdefault(
        "upsert",
        [],
    )

    calls.setdefault(
        "complete",
        [],
    )

    calls.setdefault(
        "get_destination",
        [],
    )

    calls.setdefault(
        "get_x_connection",
        [],
    )

    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )

    monkeypatch.setenv(
        "TELEGRAM_SECRET_TOKEN",
        "test-secret",
    )

    monkeypatch.setenv(
        "ENABLE_SELF_PING",
        "false",
    )

    fake_webhook = _module(
        "core.webhook_handler",
        initialize=(
            lambda *_a, **_k: None
        ),
        handle_webhook=(
            lambda: (
                {
                    "ok": True,
                },
                200,
            )
        ),
    )

    fake_cleaner = _module(
        "core.cleaner",
        initialize=(
            lambda *_a, **_k: None
        ),
    )

    fake_formatter = _module(
        "core.formatter",
        initialize=(
            lambda *_a, **_k: None
        ),
    )

    fake_media_handler = _module(
        "core.media_handler",
        initialize=(
            lambda *_a, **_k: None
        ),
        rehydrate_media_groups=(
            lambda: 0
        ),
    )

    fake_command_handler = _module(
        "core.command_handler",
        initialize=(
            lambda *_a, **_k: None
        ),
    )

    fake_deep_reply = _module(
        "core.deep_reply_handler",
        initialize=(
            lambda *_a, **_k: None
        ),
    )

    fake_editorial_pending = _module(
        "core.editorial_pending",
        rehydrate_editorial_reviews=(
            lambda: 0
        ),
    )

    def register_setup_destination_canonical(
        workspace_id,
        platform,
        external_id,
        name,
    ):
        calls["register"].append(
            {
                "workspace_id":
                    workspace_id,
                "platform":
                    platform,
                "external_id":
                    external_id,
                "name":
                    name,
            }
        )

        return (
            {
                "id": 909,
                "workspace_id":
                    workspace_id,
                "platform":
                    platform,
                "external_id":
                    external_id,
                "status":
                    "inactive",
            },
            "associated",
        )

    def update_publication_destination_status(
        destination_id,
        status,
    ):
        calls["activate"].append(
            (
                destination_id,
                status,
            )
        )

        return {
            "id":
                destination_id,
            "status":
                status,
        }

    def upsert_x_oauth_connection(
        **kwargs,
    ):
        calls["upsert"].append(
            kwargs
        )

        if upsert_result is False:
            return None

        return {
            "id": 1,
            **kwargs,
        }

    if publication_destination is None:
        publication_destination = {
            "id": 909,
            "workspace_id": 101,
            "platform": "x",
            "external_id": "x:123456789",
            "status": "active",
        }

    if x_connection is None:
        x_connection = {
            "destination_id": 909,
            "workspace_id": 101,
            "x_user_id": "123456789",
            "x_username": "example_user",
            "connection_status": "connected",
        }

    def get_publication_destination(
        destination_id,
    ):
        calls["get_destination"].append(
            destination_id
        )

        if (
            publication_destination
            and int(
                publication_destination.get("id")
                or 0
            ) == int(destination_id)
        ):
            return publication_destination

        return None

    def get_x_oauth_connection(
        destination_id,
    ):
        calls["get_x_connection"].append(
            destination_id
        )

        if (
            x_connection
            and int(
                x_connection.get("destination_id")
                or 0
            ) == int(destination_id)
        ):
            return x_connection

        return None

    fake_database = _module(
        "core.database",
        init_db=(
            lambda: None
        ),
        get_workspace_member=(
            lambda workspace_id,
            user_id: member
        ),
        get_publication_destination=(
            get_publication_destination
        ),
        get_x_oauth_connection=(
            get_x_oauth_connection
        ),
        register_setup_destination_canonical=(
            register_setup_destination_canonical
        ),
        update_publication_destination_status=(
            update_publication_destination_status
        ),
        upsert_x_oauth_connection=(
            upsert_x_oauth_connection
        ),
    )

    fake_smart_summarizer = _module(
        "core.smart_summarizer",
        summarize_text_safely=(
            lambda *_a, **_k: None
        ),
    )

    fake_ai_provider = _module(
        "core.ai_summarizer_provider",
        summarize_with_gemini=(
            lambda *_a, **_k: None
        ),
    )

    fake_release_readiness = _module(
        "core.release_readiness",
        parse_bool=(
            lambda value: (
                str(value)
                .strip()
                .lower()
                == "true"
            )
        ),
    )

    fake_bale_adapter = _module(
        "core.bale_adapter",
        initialize=(
            lambda *_a, **_k: None
        ),
        handle_bale_update=(
            lambda data: (
                {
                    "ok": True,
                },
                200,
            )
        ),
        validate_bale_webhook_token=(
            lambda request: True
        ),
    )

    fake_workspace_destinations = _module(
        "core.workspace_destinations",
        can_manage_destinations=(
            lambda role: (
                (
                    True,
                    "",
                )
                if role
                in {
                    "owner",
                    "manager",
                }
                else (
                    False,
                    "forbidden",
                )
            )
        ),
    )

    if oauth_result is None:
        oauth_result = (
            SimpleNamespace(
                workspace_id=101,
                destination_id=None,
                requested_by_user_id=55,
                action="connect",
                x_user_id="123456789",
                x_username="example_user",
                x_display_name="Example User",
                access_token_ciphertext=(
                    "encrypted-access"
                ),
                refresh_token_ciphertext=(
                    "encrypted-refresh"
                ),
                token_expires_at=(
                    1234567890.0
                ),
                granted_scopes=(
                    "tweet.read",
                    "tweet.write",
                    "users.read",
                    "offline.access",
                ),
            )
        )

    def complete_x_oauth_callback(
        *,
        state,
        code,
    ):
        calls["complete"].append(
            {
                "state":
                    state,
                "code":
                    code,
            }
        )

        return oauth_result

    fake_x_oauth = _module(
        "core.x_oauth",
        complete_x_oauth_callback=(
            complete_x_oauth_callback
        ),
    )

    modules = {
        "core.webhook_handler":
            fake_webhook,
        "core.cleaner":
            fake_cleaner,
        "core.formatter":
            fake_formatter,
        "core.media_handler":
            fake_media_handler,
        "core.command_handler":
            fake_command_handler,
        "core.deep_reply_handler":
            fake_deep_reply,
        "core.editorial_pending":
            fake_editorial_pending,
        "core.database":
            fake_database,
        "core.smart_summarizer":
            fake_smart_summarizer,
        "core.ai_summarizer_provider":
            fake_ai_provider,
        "core.release_readiness":
            fake_release_readiness,
        "core.bale_adapter":
            fake_bale_adapter,
        "core.workspace_destinations":
            fake_workspace_destinations,
        "core.x_oauth":
            fake_x_oauth,
    }

    for name, module in (
        modules.items()
    ):
        monkeypatch.setitem(
            sys.modules,
            name,
            module,
        )

    sys.modules.pop(
        "main",
        None,
    )

    main = importlib.import_module(
        "main"
    )

    main.app.config.update(
        TESTING=True,
    )

    return (
        main,
        calls,
    )


def test_x_oauth_callback_requires_state_and_code(
    monkeypatch,
):
    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role":
                    "owner",
                "status":
                    "active",
            },
        )
    )

    client = (
        main.app.test_client()
    )

    response = client.get(
        "/oauth/x/callback"
    )

    assert (
        response.status_code
        == 400
    )

    assert (
        calls["complete"]
        == []
    )

    assert (
        calls["register"]
        == []
    )

    assert (
        calls["activate"]
        == []
    )

    assert (
        calls["upsert"]
        == []
    )


def test_x_oauth_callback_handles_provider_error(
    monkeypatch,
):
    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role":
                    "owner",
                "status":
                    "active",
            },
        )
    )

    client = (
        main.app.test_client()
    )

    response = client.get(
        "/oauth/x/callback"
        "?error=access_denied"
    )

    assert (
        response.status_code
        == 400
    )

    assert (
        calls["complete"]
        == []
    )

    assert (
        calls["register"]
        == []
    )


def test_x_oauth_callback_binds_and_activates_destination(
    monkeypatch,
):
    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role":
                    "owner",
                "status":
                    "active",
            },
        )
    )

    client = (
        main.app.test_client()
    )

    response = client.get(
        "/oauth/x/callback"
        "?state=test-state"
        "&code=test-code"
    )

    assert (
        response.status_code
        == 200
    )

    assert (
        calls["complete"]
        == [
            {
                "state":
                    "test-state",
                "code":
                    "test-code",
            }
        ]
    )

    assert (
        calls["register"]
        == [
            {
                "workspace_id":
                    101,
                "platform":
                    "x",
                "external_id":
                    "x:123456789",
                "name":
                    "Example User",
            }
        ]
    )

    assert (
        calls["activate"]
        == [
            (
                909,
                "active",
            )
        ]
    )

    assert (
        len(
            calls["upsert"]
        )
        == 1
    )

    connection = (
        calls["upsert"][0]
    )

    assert (
        connection[
            "destination_id"
        ]
        == 909
    )

    assert (
        connection[
            "workspace_id"
        ]
        == 101
    )

    assert (
        connection[
            "connected_by_user_id"
        ]
        == 55
    )

    assert (
        connection[
            "x_user_id"
        ]
        == "123456789"
    )

    assert (
        connection[
            "x_username"
        ]
        == "example_user"
    )

    assert (
        connection[
            "x_display_name"
        ]
        == "Example User"
    )

    assert (
        connection[
            "access_token_ciphertext"
        ]
        == "encrypted-access"
    )

    assert (
        connection[
            "refresh_token_ciphertext"
        ]
        == "encrypted-refresh"
    )

    assert (
        connection[
            "connection_status"
        ]
        == "connected"
    )

    assert (
        connection[
            "last_error"
        ]
        is None
    )


def test_x_oauth_callback_rechecks_workspace_permission(
    monkeypatch,
):
    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role":
                    "publisher",
                "status":
                    "active",
            },
        )
    )

    client = (
        main.app.test_client()
    )

    response = client.get(
        "/oauth/x/callback"
        "?state=test-state"
        "&code=test-code"
    )

    assert (
        response.status_code
        == 403
    )

    assert (
        len(
            calls["complete"]
        )
        == 1
    )

    assert (
        calls["register"]
        == []
    )

    assert (
        calls["activate"]
        == []
    )

    assert (
        calls["upsert"]
        == []
    )


def test_x_oauth_callback_does_not_activate_if_connection_persist_fails(
    monkeypatch,
):
    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role":
                    "owner",
                "status":
                    "active",
            },
            upsert_result=False,
        )
    )

    client = (
        main.app.test_client()
    )

    response = client.get(
        "/oauth/x/callback"
        "?state=test-state"
        "&code=test-code"
    )

    assert (
        response.status_code
        == 500
    )

    assert (
        len(
            calls["complete"]
        )
        == 1
    )

    assert (
        len(
            calls["register"]
        )
        == 1
    )

    assert (
        len(
            calls["upsert"]
        )
        == 1
    )

    assert (
        calls["activate"]
        == []
    )


def test_x_oauth_callback_reconnects_same_destination_without_registering_new_one(
    monkeypatch,
):
    oauth_result = SimpleNamespace(
        workspace_id=101,
        destination_id=909,
        requested_by_user_id=55,
        action="reconnect",
        x_user_id="123456789",
        x_username="example_user",
        x_display_name="Example User",
        access_token_ciphertext=(
            "encrypted-new-access"
        ),
        refresh_token_ciphertext=(
            "encrypted-new-refresh"
        ),
        token_expires_at=(
            2234567890.0
        ),
        granted_scopes=(
            "tweet.read",
            "tweet.write",
            "users.read",
            "offline.access",
        ),
    )

    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role": "owner",
                "status": "active",
            },
            oauth_result=oauth_result,
            publication_destination={
                "id": 909,
                "workspace_id": 101,
                "platform": "x",
                "external_id": "x:123456789",
                "status": "active",
            },
            x_connection={
                "destination_id": 909,
                "workspace_id": 101,
                "x_user_id": "123456789",
                "x_username": "example_user",
                "connection_status": "reconnect_required",
            },
        )
    )

    client = main.app.test_client()

    response = client.get(
        "/oauth/x/callback"
        "?state=test-state"
        "&code=test-code"
    )

    assert response.status_code == 200

    assert calls["register"] == []

    assert calls["get_destination"] == [
        909
    ]

    assert calls["get_x_connection"] == [
        909
    ]

    assert len(
        calls["upsert"]
    ) == 1

    connection = calls["upsert"][0]

    assert (
        connection["destination_id"]
        == 909
    )

    assert (
        connection["workspace_id"]
        == 101
    )

    assert (
        connection["x_user_id"]
        == "123456789"
    )

    assert (
        connection["connection_status"]
        == "connected"
    )

    assert calls["activate"] == [
        (
            909,
            "active",
        )
    ]


def test_x_oauth_callback_reconnect_rejects_different_x_account(
    monkeypatch,
):
    oauth_result = SimpleNamespace(
        workspace_id=101,
        destination_id=909,
        requested_by_user_id=55,
        action="reconnect",
        x_user_id="DIFFERENT-X-USER",
        x_username="wrong_user",
        x_display_name="Wrong User",
        access_token_ciphertext=(
            "encrypted-wrong-access"
        ),
        refresh_token_ciphertext=(
            "encrypted-wrong-refresh"
        ),
        token_expires_at=(
            2234567890.0
        ),
        granted_scopes=(
            "tweet.read",
            "tweet.write",
            "users.read",
            "offline.access",
        ),
    )

    main, calls = (
        _load_main_safely(
            monkeypatch,
            member={
                "role": "owner",
                "status": "active",
            },
            oauth_result=oauth_result,
            publication_destination={
                "id": 909,
                "workspace_id": 101,
                "platform": "x",
                "external_id": "x:123456789",
                "status": "active",
            },
            x_connection={
                "destination_id": 909,
                "workspace_id": 101,
                "x_user_id": "123456789",
                "x_username": "example_user",
                "connection_status": "reconnect_required",
            },
        )
    )

    client = main.app.test_client()

    response = client.get(
        "/oauth/x/callback"
        "?state=test-state"
        "&code=test-code"
    )

    assert response.status_code == 403

    assert calls["register"] == []
    assert calls["upsert"] == []
    assert calls["activate"] == []
