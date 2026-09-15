"""Feature Lock / Regression Contract for the shared publication engine."""

from types import SimpleNamespace
import pytest

from core.content_model import PreparedContent, PublicationTarget
from core import publication_engine
from core.language_detector import detect_language, detection_is_clearly_non_persian


def _target():
    return PublicationTarget(
        key="workspace:1:destination:1",
        kind="workspace",
        platform="telegram",
        external_id="@feature_lock",
        workspace_id=1,
        destination_id=1,
    )


def _text_plan(messages):
    return SimpleNamespace(
        telegram={},
        bale={},
        text={
            "telegram": {"messages": list(messages)},
            "bale": {"messages": list(messages)},
        },
    )


def test_feature_lock_long_editorial_summary_is_one_message(monkeypatch):
    calls = []
    sent = []

    def fake_analyze(**kwargs):
        calls.append(kwargs)
        if kwargs["branding"] == "":
            return _text_plan(["خلاصه هوشمند"])
        return _text_plan([kwargs["main_text"]])

    monkeypatch.setattr("core.caption_manager.analyze_content", fake_analyze)
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda _chat, _target, prepared: (
            prepared.neutral_text or prepared.main_text,
            "brand",
        ),
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
            source_key="feature-lock:editorial:summary",
        ),
        [_target()],
    )

    assert result["ok"] is True
    assert sent == ["خلاصه هوشمند"]
    assert len(calls) == 2
    assert calls[0]["editorial_finalized"] is False


def test_feature_lock_long_editorial_never_silently_splits(monkeypatch):
    sent = []
    target_processing = []

    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: _text_plan(["قسمت اول", "قسمت دوم", "قسمت سوم"]),
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
            source_key="feature-lock:editorial:no-summary",
        ),
        [_target()],
    )

    assert result["ok"] is False
    assert result["errors"] == ["editorial_summary_unavailable"]
    assert target_processing == []
    assert sent == []


def test_feature_lock_legacy_and_workspace_share_same_base(monkeypatch):
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget(
            "workspace", "workspace", "telegram", "@workspace", 2, 20
        ),
    ]
    analyzed = []

    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda _chat, target, prepared: (
            prepared.neutral_text or prepared.main_text,
            f"brand:{target.key}",
        ),
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **kwargs: analyzed.append(kwargs) or _text_plan([kwargs["main_text"]]),
    )
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *_args: True)
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        1,
        "api",
        PreparedContent(
            main_text="متن پایه",
            neutral_text="متن مشترک",
            source_key="feature-lock:shared-base",
        ),
        targets,
    )

    assert result["ok"] is True
    assert len(analyzed) == 2
    assert {item["main_text"] for item in analyzed} == {"متن مشترک"}


def test_feature_lock_album_is_not_multiplied_by_targets(monkeypatch):
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget(
            "workspace", "workspace", "telegram", "@workspace", 2, 20
        ),
    ]
    files = [
        {"type": "photo", "file_id": f"file-{i}", "message_id": i}
        for i in range(1, 4)
    ]
    sent = []

    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: SimpleNamespace(
            telegram={"media_caption": "caption"},
            bale={"media_caption": "caption"},
            text={
                "telegram": {"messages": ["caption"]},
                "bale": {"messages": ["caption"]},
            },
        ),
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("base", "brand"),
    )
    monkeypatch.setattr(
        publication_engine,
        "_send_media_target",
        lambda _chat, _api, target, actual_files, _plan: (
            sent.append(
                (target.key, tuple(item["file_id"] for item in actual_files))
            )
            or True
        ),
    )
    publication_engine.reset_local_idempotency_state()

    result = publication_engine.publish_prepared_content(
        1,
        "api",
        PreparedContent(
            main_text="آلبوم",
            files=files,
            source_key="feature-lock:album",
        ),
        targets,
    )

    assert result["ok"] is True
    assert len(sent) == 2
    assert all(
        actual == ("file-1", "file-2", "file-3")
        for _, actual in sent
    )


@pytest.mark.parametrize(
    "text",
    [
        "این یک خبر فارسی برای بررسی مسیر انتشار است.",
        "گزارش تازه درباره تحولات منطقه منتشر شد.",
    ],
)
def test_feature_lock_reliable_persian_is_not_non_persian(text):
    detection = detect_language(text)
    assert detection.language == "fa"
    assert detection.reliable is True
    assert detection_is_clearly_non_persian(detection) is False


@pytest.mark.parametrize(
    "text",
    [
        "The government released a new report on regional developments and security.",
        "نائب الرئيس الأميركي يرد على مطالب إبطاء تطور الذكاء الاصطناعي في الكونغرس",
        "Правительство опубликовало новый доклад о последних событиях в регионе.",
    ],
)
def test_feature_lock_clear_non_persian_is_detectable_without_whitelist(text):
    detection = detect_language(text)
    assert detection.language != "fa"
    assert detection_is_clearly_non_persian(detection) is True

