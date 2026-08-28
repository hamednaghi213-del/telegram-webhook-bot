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
