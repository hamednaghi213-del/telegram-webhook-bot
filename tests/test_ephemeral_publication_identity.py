import gc

from core import publication_engine
from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore


def test_independent_ephemeral_contents_have_distinct_keys():
    first = PreparedContent(main_text="same")
    second = PreparedContent(main_text="same")
    assert first.publication_identity != second.publication_identity
    assert first.publication_identity.startswith("ephemeral:")
    assert second.publication_identity.startswith("ephemeral:")


def test_retry_of_same_content_preserves_ephemeral_key(monkeypatch):
    prepared = PreparedContent(main_text="retry")
    identity = prepared.publication_identity
    store = InMemoryPublicationStateStore()
    target = PublicationTarget("telegram", "workspace", "telegram", "@target", 1, 1)
    calls = []

    def sender(*_args):
        calls.append(1)
        return {"ok": len(calls) > 1, "message_id": 10 if len(calls) > 1 else None}

    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda value: value)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_a: ("retry", ""))
    monkeypatch.setattr(publication_engine, "_send_text_target", sender)
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_k: type("Plan", (), {
            "telegram": {}, "bale": {},
            "text": {
                "telegram": {"messages": ["retry"], "message_parse_modes": [None], "blockquote_messages": []},
                "bale": {"messages": ["retry"], "message_parse_modes": [None], "blockquote_messages": []},
            },
        })(),
    )

    assert publication_engine.publish_prepared_content(1, "api", prepared, [target], store)["ok"] is False
    assert publication_engine.publish_prepared_content(1, "api", prepared, [target], store)["ok"] is True
    assert tuple(store._sources) == (identity,)
    assert prepared.publication_identity == identity
    assert len(calls) == 2


def test_releasing_one_content_cannot_reuse_its_publication_identity():
    first = PreparedContent(main_text="same")
    first_identity = first.publication_identity
    del first
    gc.collect()
    second = PreparedContent(main_text="same")
    assert second.publication_identity != first_identity


def test_global_publication_state_starts_isolated_for_each_test():
    assert publication_engine._state_store._sources == {}
    assert publication_engine._state_store._deliveries == {}
