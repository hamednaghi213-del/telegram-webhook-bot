import sys
import types
from types import SimpleNamespace

import pytest

from core.content_model import PreparedContent, PublicationTarget
from core import publication_engine


def _plan():
    return SimpleNamespace(
        telegram={"media_caption": "tg"},
        bale={"media_caption": "bale"},
        text={"telegram": {"messages": ["tg"]}, "bale": {"messages": ["bale"]}},
    )


@pytest.mark.parametrize("count", [2, 3, 10])
@pytest.mark.parametrize("target_count", [1, 3])
def test_complete_album_is_fanned_out_once_per_target(monkeypatch, count, target_count):
    targets = [
        PublicationTarget(
            key=f"workspace:1:destination:{index}",
            kind="workspace",
            platform="telegram",
            external_id=f"@channel_{index}",
            workspace_id=1,
            destination_id=index,
        )
        for index in range(1, target_count + 1)
    ]
    files = [
        {"type": "photo", "file_id": f"f{index}", "message_id": index}
        for index in range(1, count + 1)
    ]
    sent = []
    monkeypatch.setattr(publication_engine, "analyze_content", _plan, raising=False)
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("base", "brand"),
    )
    monkeypatch.setattr(
        publication_engine,
        "_send_media_target",
        lambda _chat, _api, target, actual_files, _plan: sent.append(
            (target.key, list(actual_files))
        ) or True,
    )
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_kwargs: _plan())
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        7,
        "https://api.telegram.org/botTEST",
        PreparedContent(main_text="base", files=files, source_key=f"album:{count}:{target_count}"),
        targets=targets,
    )

    assert result["ok"] is True
    assert len(sent) == target_count
    assert all(len(actual_files) == count for _, actual_files in sent)
    assert all([item["file_id"] for item in actual_files] == [f"f{i}" for i in range(1, count + 1)] for _, actual_files in sent)


def test_duplicate_target_and_retry_are_idempotent(monkeypatch):
    target = PublicationTarget("one", "workspace", "telegram", "@same", 1, 1)
    duplicate = PublicationTarget("two", "legacy", "telegram", "@SAME")
    sent = []
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_kwargs: _plan())
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_args: ("base", "brand"))
    monkeypatch.setattr(publication_engine, "_send_media_target", lambda *_args: sent.append(1) or True)
    publication_engine.reset_local_idempotency_state()
    prepared = PreparedContent(
        main_text="base",
        files=[{"type": "photo", "file_id": "f1"}, {"type": "photo", "file_id": "f2"}],
        source_key="album:stable",
    )

    first = publication_engine.publish_prepared_content(1, "api", prepared, [target])
    second = publication_engine.publish_prepared_content(1, "api", prepared, [duplicate])

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(sent) == 1


def test_same_news_different_source_keys_cannot_publish_concurrently_for_shared_media(
    monkeypatch,
):
    target = PublicationTarget(
        key="workspace:1:destination:1",
        kind="workspace",
        platform="telegram",
        external_id="@shared",
        workspace_id=1,
        destination_id=1,
        destination={
            "_canonical_media": True,
            "media_identity": {"id": 77},
        },
    )

    history_rows = []
    claims = {}
    sent = []
    nested_result = {}

    fake_database = types.ModuleType("core.database")

    def get_recent_duplicate_news(media_identity_id, limit=50):
        return [
            row
            for row in history_rows
            if row["media_identity_id"] == media_identity_id
        ][:limit]

    def record_duplicate_news_history(**kwargs):
        row = {
            "id": len(history_rows) + 1,
            "media_identity_id": kwargs["media_identity_id"],
            "actor_user_id": kwargs.get("actor_user_id"),
            "source_key": kwargs["source_key"],
            "content_text": kwargs["content_text"],
            "normalized_text": kwargs["normalized_text"],
            "fingerprint": kwargs["fingerprint"],
            "published_at": "2026-09-26T00:00:00Z",
        }
        history_rows.append(row)
        return row

    def claim_duplicate_news_publication(
        *,
        media_identity_id,
        fingerprint,
        source_key,
        actor_user_id=None,
        lease_seconds=300,
    ):
        key = (
            int(media_identity_id),
            str(fingerprint),
        )

        existing = claims.get(key)

        if (
            existing is None
            or existing["source_key"] == source_key
        ):
            claims[key] = {
                "source_key": source_key,
                "actor_user_id": actor_user_id,
            }

            return {
                "claimed": True,
                "owner_source_key": source_key,
                "lease_expires_at":
                    "2026-09-26T00:05:00Z",
            }

        return {
            "claimed": False,
            "owner_source_key":
                existing["source_key"],
            "lease_expires_at":
                "2026-09-26T00:05:00Z",
        }

    def finalize_duplicate_news_publication(
        *,
        media_identity_id,
        fingerprint,
        source_key,
        actor_user_id,
        content_text,
        normalized_text,
    ):
        key = (
            int(media_identity_id),
            str(fingerprint),
        )

        existing = claims.get(key)

        if (
            existing is None
            or existing["source_key"] != source_key
        ):
            return False

        record_duplicate_news_history(
            media_identity_id=media_identity_id,
            actor_user_id=actor_user_id,
            source_key=source_key,
            content_text=content_text,
            normalized_text=normalized_text,
            fingerprint=fingerprint,
        )

        claims.pop(
            key,
            None,
        )

        return True

    def release_duplicate_news_publication(
        *,
        media_identity_id,
        fingerprint,
        source_key,
    ):
        key = (
            int(media_identity_id),
            str(fingerprint),
        )

        existing = claims.get(key)

        if (
            existing is None
            or existing["source_key"] != source_key
        ):
            return False

        claims.pop(
            key,
            None,
        )

        return True

    fake_database.get_recent_duplicate_news = get_recent_duplicate_news
    fake_database.record_duplicate_news_history = record_duplicate_news_history
    fake_database.claim_duplicate_news_publication = (
        claim_duplicate_news_publication
    )
    fake_database.finalize_duplicate_news_publication = (
        finalize_duplicate_news_publication
    )
    fake_database.release_duplicate_news_publication = (
        release_duplicate_news_publication
    )
    fake_database.get_user_by_telegram_id = lambda _chat_id: {"id": 1}
    fake_database.mark_persistent_publication_source = lambda **_kwargs: None

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )

    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: _plan(),
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("same news body", "brand"),
    )

    first_prepared = PreparedContent(
        main_text="same news body",
        neutral_text="same news body",
        source_key="tg:update:1001",
    )
    second_prepared = PreparedContent(
        main_text="same news body",
        neutral_text="same news body",
        source_key="tg:update:1002",
    )

    def fake_send(*_args):
        sent.append(1)

        if len(sent) == 1:
            nested_result["value"] = (
                publication_engine.publish_prepared_content(
                    11,
                    "api",
                    second_prepared,
                    [target],
                )
            )

        return True

    monkeypatch.setattr(
        publication_engine,
        "_send_text_target",
        fake_send,
    )

    publication_engine.reset_local_idempotency_state()

    first_result = publication_engine.publish_prepared_content(
        10,
        "api",
        first_prepared,
        [target],
    )

    assert first_result["ok"] is True
    assert nested_result["value"].get("duplicate_warning") is True
    assert len(sent) == 1


def test_destination_branding_changes_plan_but_base_is_shared(monkeypatch):
    targets = [
        PublicationTarget("a", "workspace", "telegram", "@a", 1, 1),
        PublicationTarget("b", "workspace", "telegram", "@b", 2, 2),
    ]
    analyzed = []
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda _chat, target, prepared: (prepared.neutral_text, f"brand:{target.key}"),
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **kwargs: analyzed.append(kwargs) or _plan(),
    )
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_args: True)

    result = publication_engine.publish_prepared_content(
        1, "api", PreparedContent(main_text="legacy", neutral_text="same base"), targets
    )

    assert result["ok"] is True
    assert [item["main_text"] for item in analyzed] == ["same base", "same base"]
    assert [item["branding"] for item in analyzed] == ["brand:a", "brand:b"]


def test_legacy_and_workspace_receive_the_same_complete_album(monkeypatch):
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20),
    ]
    files = [{"type": "photo", "file_id": f"f{i}"} for i in range(3)]
    sent = []
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_kwargs: _plan())
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_args: ("base", "brand"))
    monkeypatch.setattr(
        publication_engine,
        "_send_media_target",
        lambda _chat, _api, target, actual, _plan: sent.append((target.key, list(actual))) or True,
    )
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        1, "api", PreparedContent(main_text="base", files=files, source_key="mixed-album"), targets
    )

    assert result["ok"] is True
    assert [len(actual) for _, actual in sent] == [3, 3]


def test_editorial_finalized_is_applied_once_per_destination_plan(monkeypatch):
    targets = [PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20)]
    calls = []
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_args: ("یادداشت", "brand"))
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **kwargs: calls.append(kwargs) or _plan(),
    )
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_args: True)

    result = publication_engine.publish_prepared_content(
        1,
        "api",
        PreparedContent(main_text="یادداشت", editorial_finalized=True, source_key="editorial:1"),
        targets,
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0]["editorial_finalized"] is True


def test_long_finalized_editorial_is_summarized_to_one_message(monkeypatch):
    target = PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20)
    calls = []
    sent = []

    def fake_analyze(**kwargs):
        calls.append(kwargs)
        if kwargs["branding"] == "":
            return SimpleNamespace(
                telegram={}, bale={},
                text={
                    "telegram": {"messages": ["خلاصه هوشمند"]},
                    "bale": {"messages": ["خلاصه هوشمند"]},
                },
            )
        return SimpleNamespace(
            telegram={}, bale={},
            text={
                "telegram": {"messages": [kwargs["main_text"]]},
                "bale": {"messages": [kwargs["main_text"]]},
            },
        )

    monkeypatch.setattr("core.caption_manager.analyze_content", fake_analyze)
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda _chat, _target, prepared: (prepared.neutral_text, "brand"),
    )
    monkeypatch.setattr(
        publication_engine,
        "_send_text_target",
        lambda _chat, _api, _target, plan: sent.extend(plan["messages"]) or True,
    )
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        1,
        "api",
        PreparedContent(
            main_text="متن بلند " * 700,
            editorial_finalized=True,
            require_single_message=True,
            source_key="editorial:long:summary",
        ),
        [target],
    )

    assert result["ok"] is True
    assert sent == ["خلاصه هوشمند"]
    assert calls[0]["editorial_finalized"] is False
    assert len(calls) == 2


def test_long_editorial_is_not_split_when_summary_is_unavailable(monkeypatch):
    target = PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20)
    sent = []
    target_processing = []

    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: SimpleNamespace(
            telegram={}, bale={},
            text={
                "telegram": {"messages": ["قسمت اول", "قسمت دوم", "قسمت سوم"]},
                "bale": {"messages": ["قسمت اول", "قسمت دوم", "قسمت سوم"]},
            },
        ),
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: target_processing.append(True) or ("base", "brand"),
    )
    monkeypatch.setattr(
        publication_engine,
        "_send_text_target",
        lambda *_args: sent.append(True) or True,
    )
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        1,
        "api",
        PreparedContent(
            main_text="متن بلند " * 700,
            editorial_finalized=True,
            require_single_message=True,
            source_key="editorial:long:unavailable",
        ),
        [target],
    )

    assert result["ok"] is False
    assert result["errors"] == ["editorial_summary_unavailable"]
    assert target_processing == []
    assert sent == []

def test_destination_translation_policy_supports_arbitrary_language():
    from core.content_model import PublicationTarget
    from core.publication_engine import (
        _destination_translation_policy,
    )

    target = PublicationTarget(
        key="workspace:6:destination:99",
        kind="workspace",
        platform="telegram",
        external_id="@german_channel",
        workspace_id=6,
        destination_id=99,
        destination={
            "target_language_code": "de",
            "translation_enabled": True,
        },
    )

    policy = _destination_translation_policy(
        target
    )

    assert policy is not None
    assert policy.destination_language == "de"
    assert policy.translation_mode == "auto"
    assert policy.enabled is True
    assert policy.fail_closed is True

def test_destination_translation_policy_disabled_returns_none():
    from core.content_model import PublicationTarget
    from core.publication_engine import (
        _destination_translation_policy,
    )

    target = PublicationTarget(
        key="workspace:6:destination:100",
        kind="workspace",
        platform="bale",
        external_id="@persian_channel",
        workspace_id=6,
        destination_id=100,
        destination={
            "target_language_code": "fa",
            "translation_enabled": False,
        },
    )

    policy = _destination_translation_policy(
        target
    )

    assert policy is None

def test_destination_translation_reuses_cache_for_same_language(
    monkeypatch,
):
    from core.content_model import (
        PreparedContent,
        PublicationTarget,
    )
    from core.publication_engine import (
        _translated_prepared_for_target,
    )

    calls = []

    def fake_translate_prepared_content(
        prepared,
        policy,
        content_kind,
    ):
        calls.append(
            policy.destination_language
        )

        class Result:
            success = True
            blocked = False
            reason = ""
            payload = {
                "main_text": "translated-de",
                "neutral_text": "translated-de",
                "blockquote_blocks": (),
                "expandable_blocks": (),
                "other_entities": (),
                "files": prepared.files,
                "media_presentation": (
                    prepared.media_presentation
                ),
                "editorial_finalized": (
                    prepared.editorial_finalized
                ),
                "require_single_message": (
                    prepared.require_single_message
                ),
                "source_key": prepared.source_key,
            }

        return Result()

    monkeypatch.setattr(
        "core.translation_prepared_content."
        "translate_prepared_content",
        fake_translate_prepared_content,
    )

    prepared = PreparedContent(
        main_text="original",
        neutral_text="original",
        source_key="source-1",
    )

    target_telegram = PublicationTarget(
        key="workspace:6:destination:101",
        kind="workspace",
        platform="telegram",
        external_id="@german_telegram",
        workspace_id=6,
        destination_id=101,
        destination={
            "target_language_code": "de",
            "translation_enabled": True,
        },
    )

    target_bale = PublicationTarget(
        key="workspace:6:destination:102",
        kind="workspace",
        platform="bale",
        external_id="@german_bale",
        workspace_id=6,
        destination_id=102,
        destination={
            "target_language_code": "de",
            "translation_enabled": True,
        },
    )

    cache = {}

    first = _translated_prepared_for_target(
        target_telegram,
        prepared,
        cache,
    )

    second = _translated_prepared_for_target(
        target_bale,
        prepared,
        cache,
    )

    assert calls == ["de"]
    assert first.main_text == "translated-de"
    assert second.main_text == "translated-de"
    assert first is second

def test_destination_translation_runs_separately_for_different_languages(
    monkeypatch,
):
    from core.content_model import (
        PreparedContent,
        PublicationTarget,
    )
    from core.publication_engine import (
        _translated_prepared_for_target,
    )

    calls = []

    def fake_translate_prepared_content(
        prepared,
        policy,
        content_kind,
    ):
        language = policy.destination_language
        calls.append(language)

        class Result:
            success = True
            blocked = False
            reason = ""
            payload = {
                "main_text": f"translated-{language}",
                "neutral_text": f"translated-{language}",
                "blockquote_blocks": (),
                "expandable_blocks": (),
                "other_entities": (),
                "files": prepared.files,
                "media_presentation": (
                    prepared.media_presentation
                ),
                "editorial_finalized": (
                    prepared.editorial_finalized
                ),
                "require_single_message": (
                    prepared.require_single_message
                ),
                "source_key": prepared.source_key,
            }

        return Result()

    monkeypatch.setattr(
        "core.translation_prepared_content."
        "translate_prepared_content",
        fake_translate_prepared_content,
    )

    prepared = PreparedContent(
        main_text="original",
        neutral_text="original",
        source_key="source-2",
    )

    target_de = PublicationTarget(
        key="workspace:6:destination:103",
        kind="workspace",
        platform="telegram",
        external_id="@german_channel",
        workspace_id=6,
        destination_id=103,
        destination={
            "target_language_code": "de",
            "translation_enabled": True,
        },
    )

    target_ru = PublicationTarget(
        key="workspace:6:destination:104",
        kind="workspace",
        platform="telegram",
        external_id="@russian_channel",
        workspace_id=6,
        destination_id=104,
        destination={
            "target_language_code": "ru",
            "translation_enabled": True,
        },
    )

    cache = {}

    translated_de = _translated_prepared_for_target(
        target_de,
        prepared,
        cache,
    )

    translated_ru = _translated_prepared_for_target(
        target_ru,
        prepared,
        cache,
    )

    assert calls == ["de", "ru"]
    assert translated_de.main_text == "translated-de"
    assert translated_ru.main_text == "translated-ru"
