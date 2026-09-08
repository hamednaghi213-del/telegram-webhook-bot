import importlib
import sys
import types
import pytest

fake_database = types.ModuleType("core.database")
fake_database.get_publication_sync_targets_for_telegram_message = (
    lambda *args, **kwargs: None
)
fake_database.mark_persistent_publication_delivery_delete_state = (
    lambda **kwargs: kwargs
)

fake_bale_forwarder = types.ModuleType(
    "core.bale_forwarder"
)
fake_bale_forwarder.delete_bale_message = (
    lambda *args, **kwargs: {
        "ok": True,
        "response": {},
    }
)

workspace_publisher = importlib.import_module(
    "core.workspace_publisher"
)


class _FakeResponse:
    def __init__(self, *, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {"ok": True, "result": True}

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _stub_modules(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )
    monkeypatch.setitem(
        sys.modules,
        "core.bale_forwarder",
        fake_bale_forwarder,
    )


def test_delete_sync_unknown_mapping_is_noop_after_telegram_delete(
    monkeypatch,
):
    telegram_calls = []
    bale_calls = []

    monkeypatch.setattr(
        fake_database,
        "get_publication_sync_targets_for_telegram_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        workspace_publisher.requests,
        "post",
        lambda url, json, timeout: (
            telegram_calls.append((url, json, timeout))
            or _FakeResponse()
        ),
    )
    monkeypatch.setattr(
        fake_bale_forwarder,
        "delete_bale_message",
        lambda *args, **kwargs: bale_calls.append((args, kwargs)),
    )

    assert (
        workspace_publisher.delete_telegram_publication_and_sync_bale(
            api_url="https://api.telegram.test",
            telegram_chat_id="-1001",
            telegram_message_id=42,
        )
        is True
    )
    assert len(telegram_calls) == 1
    assert bale_calls == []


def test_delete_sync_treats_bale_not_found_as_idempotent_success(
    monkeypatch,
):
    states = []
    bale_calls = []

    monkeypatch.setenv("BALE_BOT_TOKEN", "token-1")
    monkeypatch.setattr(
        fake_database,
        "get_publication_sync_targets_for_telegram_message",
        lambda *args, **kwargs: {
            "telegram": {
                "chat_id": "-1001",
                "message_ids": (42,),
            },
            "bale_deliveries": (
                {
                    "delivery_id": 7,
                    "chat_id": "bale-1",
                    "message_ids": (101, 102),
                    "delete_status": "pending",
                    "delete_attempt_count": 0,
                },
            ),
        },
    )
    monkeypatch.setattr(
        fake_database,
        "mark_persistent_publication_delivery_delete_state",
        lambda **kwargs: states.append(kwargs),
    )
    monkeypatch.setattr(
        workspace_publisher.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(),
    )
    monkeypatch.setattr(
        fake_bale_forwarder,
        "delete_bale_message",
        lambda *args, **kwargs: (
            bale_calls.append((args, kwargs))
            or {
                "ok": False,
                "response": "message not found",
            }
        ),
    )

    assert (
        workspace_publisher.delete_telegram_publication_and_sync_bale(
            api_url="https://api.telegram.test",
            telegram_chat_id="-1001",
            telegram_message_id=42,
            max_bale_retries=2,
        )
        is True
    )
    assert len(bale_calls) == 2
    assert states[0] == {
        "delivery_id": 7,
        "delete_status": "sending",
        "delete_attempt_count": 1,
    }
    assert states[1]["delivery_id"] == 7
    assert states[1]["delete_status"] == "succeeded"
    assert states[1]["delete_attempt_count"] == 1
    assert states[1]["delete_last_error"] is None
    assert states[1]["deleted_at"]


def test_delete_sync_honors_retry_budget_and_marks_terminal_failure(
    monkeypatch,
):
    states = []
    bale_calls = []

    monkeypatch.setenv("BALE_BOT_TOKEN", "token-1")
    monkeypatch.setattr(
        fake_database,
        "get_publication_sync_targets_for_telegram_message",
        lambda *args, **kwargs: {
            "telegram": {
                "chat_id": "-1001",
                "message_ids": (42,),
            },
            "bale_deliveries": (
                {
                    "delivery_id": 8,
                    "chat_id": "bale-1",
                    "message_ids": (201,),
                    "delete_status": "failed",
                    "delete_attempt_count": 1,
                },
            ),
        },
    )
    monkeypatch.setattr(
        fake_database,
        "mark_persistent_publication_delivery_delete_state",
        lambda **kwargs: states.append(kwargs),
    )
    monkeypatch.setattr(
        workspace_publisher.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(),
    )
    monkeypatch.setattr(
        fake_bale_forwarder,
        "delete_bale_message",
        lambda *args, **kwargs: (
            bale_calls.append((args, kwargs))
            or {
                "ok": False,
                "response": "permission denied",
            }
        ),
    )

    assert (
        workspace_publisher.delete_telegram_publication_and_sync_bale(
            api_url="https://api.telegram.test",
            telegram_chat_id="-1001",
            telegram_message_id=42,
            max_bale_retries=2,
        )
        is False
    )
    assert len(bale_calls) == 1
    assert states[0] == {
        "delivery_id": 8,
        "delete_status": "sending",
        "delete_attempt_count": 2,
    }
    assert states[1] == {
        "delivery_id": 8,
        "delete_status": "failed_terminal",
        "delete_attempt_count": 2,
        "delete_last_error": "bale_delete_failed",
    }
