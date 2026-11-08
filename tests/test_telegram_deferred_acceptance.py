from types import SimpleNamespace
import os
import sys

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.test")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

_previous_supabase = sys.modules.get("supabase")
sys.modules["supabase"] = SimpleNamespace(create_client=lambda *_: object())
try:
    from core import database, media_handler, publication_engine as engine
finally:
    if _previous_supabase is None:
        sys.modules.pop("supabase", None)
    else:
        sys.modules["supabase"] = _previous_supabase
from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore
from core.target_resolver import canonical_target_identity
from core.transport_errors import DeliveryOutcomeUnknown


def response(result, ok=True):
    return SimpleNamespace(status_code=200, json=lambda: {"ok": ok, "result": result})


@pytest.mark.parametrize("result", [
    {"message_id": 0},
    [{"message_id": 0}, {"message_id": 0}],
    [{"message_id": 91}, {"message_id": 0}],
])
def test_deferred_success_is_not_a_retryable_failure(result):
    with pytest.raises(DeliveryOutcomeUnknown, match="deferred publication"):
        media_handler.telegram_response_ok(response(result), "sendMediaGroup")


@pytest.mark.parametrize("result", [{"message_id": 91}, [{"message_id": 91}, {"message_id": 92}]])
def test_immediate_success_is_unchanged(result):
    assert media_handler.telegram_response_ok(response(result), "sendMediaGroup")


@pytest.mark.parametrize("album", [False, True])
def test_accepted_media_is_not_sent_again_on_pipeline_retry(monkeypatch, album):
    import core

    # The legacy suite replaces core modules during collection. Pin the real
    # tested transport for this test so every HTTP call stays on our fake.
    monkeypatch.setitem(sys.modules, "core.media_handler", media_handler)
    monkeypatch.setattr(core, "media_handler", media_handler)
    monkeypatch.setitem(sys.modules, "core.database", database)
    monkeypatch.setattr(core, "database", database)
    monkeypatch.setattr(media_handler.requests, "post", lambda *a, **k: pytest.fail("Unexpected HTTP request"))
    targets = [PublicationTarget(f"t:{i}", "workspace", "telegram", f"@target{i}", i, i) for i in (1, 2)]
    files = [{"type": "video", "file_id": "video"}]
    if album:
        files += [{"type": "photo", "file_id": f"photo{i}"} for i in range(3)]
    prepared = PreparedContent(main_text="متن", source_key=f"deferred:{album}", files=files)
    plan = {"media_caption": "متن", "media_parse_mode": None, "media_caption_entities": [], "followup_messages": [], "blockquote_messages": []}
    monkeypatch.setattr(engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(engine, "_target_content_and_branding", lambda *_: ("متن", ""))
    monkeypatch.setattr(database, "get_user_by_telegram_id", lambda _: None)
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_: SimpleNamespace(telegram=plan, bale=plan, text={}))
    calls = []

    def post(endpoint, payload, **kwargs):
        calls.append((endpoint, payload["chat_id"]))
        ids = [0] * len(files) if payload["chat_id"] == "@target1" else list(range(100, 100 + len(files)))
        result = [{"message_id": i} for i in ids] if album else {"message_id": ids[0]}
        return response(result)

    monkeypatch.setattr(media_handler, "telegram_post", post)
    store = InMemoryPublicationStateStore()
    engine.publish_prepared_content(1, "api", prepared, targets, store)
    engine.publish_prepared_content(1, "api", prepared, targets, store)

    assert calls == [("sendMediaGroup" if album else "sendVideo", "@target1"), ("sendMediaGroup" if album else "sendVideo", "@target2")]
    identity = canonical_target_identity(targets[0])
    assert store.get_delivery(prepared.source_key, identity).status == "failed_terminal"
    assert not store.part_completed(prepared.source_key, identity, "primary")
