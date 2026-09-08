"""
Regression test: External Review approval must never report a
Telegram publish as "succeeded" unless the Telegram transport (an
actual sendMessage/sendPhoto/sendVideo/sendMediaGroup HTTP call) was
made and returned proof (an HTTP 200 with a real message_id) — OR the
exact (platform, destination_chat_id, message_id) part was already
durably recorded as succeeded in a prior attempt.

This reproduces the confirmed production sequence:

    Publication Plan ready
    -> publish_prepared_content()
    -> delivery claim / part execution
    -> Telegram executor

and asserts the transport call is the thing that gates success, not a
vacuous "nothing to send" fallback.
"""

from types import SimpleNamespace

import pytest

from core.content_model import PreparedContent, PublicationTarget
from core import publication_engine


def _plan_with_messages(messages):
    return SimpleNamespace(
        telegram={"media_caption": "tg"},
        bale={"media_caption": "bale"},
        text={
            "telegram": {"messages": list(messages)},
            "bale": {"messages": list(messages)},
        },
    )


@pytest.fixture(autouse=True)
def _reset_state():
    publication_engine.reset_local_idempotency_state()
    yield
    publication_engine.reset_local_idempotency_state()


def test_empty_text_never_reports_success_without_a_telegram_call(monkeypatch):
    """
    Fresh External Review approval where the composed plan yields no
    real text to send (the exact defect that let a "primary" part be
    marked succeeded with no sendMessage call and no message_id).
    """

    target = PublicationTarget(
        "workspace",
        "workspace",
        "telegram",
        "@channel",
        1,
        1,
    )

    calls = []

    def _fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        raise AssertionError(
            "Telegram transport must not be called for empty content"
        )

    monkeypatch.setattr(
        "core.workspace_publisher.requests.post",
        _fake_post,
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("", "brand"),
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: _plan_with_messages([""]),
    )

    result = publication_engine.publish_prepared_content(
        1,
        "https://api.telegram.org/botTEST",
        PreparedContent(main_text="", source_key="empty:1"),
        [target],
    )

    assert calls == []
    assert result["ok"] is False

    delivery = result["results"][0]
    assert delivery.status != "succeeded"
    assert delivery.primary_message_id is None


def test_real_send_is_required_and_recorded_before_success(monkeypatch):
    """
    A genuine Telegram transport call (sendMessage -> HTTP 200 with a
    real message_id) is required before the delivery/part is reported
    as succeeded.
    """

    target = PublicationTarget(
        "workspace",
        "workspace",
        "telegram",
        "@channel",
        1,
        1,
    )

    calls = []

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": 555}}

    def _fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return _FakeResponse()

    monkeypatch.setattr(
        "core.workspace_publisher.requests.post",
        _fake_post,
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("real body", "brand"),
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: _plan_with_messages(["real body"]),
    )

    result = publication_engine.publish_prepared_content(
        1,
        "https://api.telegram.org/botTEST",
        PreparedContent(main_text="real body", source_key="real:1"),
        [target],
    )

    assert len(calls) == 1
    assert calls[0][0].endswith("/sendMessage")
    assert result["ok"] is True

    delivery = result["results"][0]
    assert delivery.status == "succeeded"
    assert delivery.primary_message_id == 555


def test_stale_partial_state_cannot_fabricate_success(monkeypatch):
    """
    A part previously left in a non-succeeded ("sending") state must
    not be treated as already delivered. Only a persisted "succeeded"
    part (proof of a prior genuine send) may be skipped without a new
    Telegram call.
    """

    from core.publication_state import InMemoryPublicationStateStore

    store = InMemoryPublicationStateStore()
    source_key = "stale:1"
    identity = "telegram:@channel"

    store.claim_destination(source_key, identity)
    state = store.begin_attempt(source_key, identity)
    assert state is not None
    # Stale/partial state: attempt started ("sending") but never
    # completed with a real message_id.
    assert store.part_completed(source_key, identity, "primary") is False
