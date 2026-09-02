import core.publication_engine as publication_engine

from core.content_model import PreparedContent, PublicationTarget


def _canonical_target(
    *,
    media_identity_id: int,
    platform: str,
    destination_id: int,
) -> PublicationTarget:
    return PublicationTarget(
        key=f"{platform}:{destination_id}",
        kind="workspace",
        platform=platform,
        external_id=f"channel-{destination_id}",
        workspace_id=1,
        destination_id=destination_id,
        destination={
            "_canonical_media": True,
            "media_identity": {
                "id": media_identity_id,
            },
        },
    )


def test_same_media_telegram_and_bale_checked_once(monkeypatch):
    calls = []

    def fake_check_duplicate_against_history(
        *,
        media_identity_id,
        text,
        source_key=None,
        history_limit=50,
        near_duplicate_threshold=0.88,
    ):
        calls.append(
            {
                "media_identity_id": media_identity_id,
                "text": text,
                "source_key": source_key,
            }
        )

        return object()

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="خبر آزمایشی برای بررسی تکراری بودن انتشار",
        source_key="source:test:1",
    )

    targets = [
        _canonical_target(
            media_identity_id=7,
            platform="telegram",
            destination_id=10,
        ),
        _canonical_target(
            media_identity_id=7,
            platform="bale",
            destination_id=11,
        ),
    ]

    decisions = publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert list(decisions) == [7]
    assert len(calls) == 1
    assert calls[0] == {
        "media_identity_id": 7,
        "text": "خبر آزمایشی برای بررسی تکراری بودن انتشار",
        "source_key": "source:test:1",
    }


def test_different_media_identities_checked_independently(
    monkeypatch,
):
    calls = []

    def fake_check_duplicate_against_history(
        *,
        media_identity_id,
        text,
        source_key=None,
        **_kwargs,
    ):
        calls.append(media_identity_id)
        return media_identity_id

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="خبر مشترک برای دو رسانه مستقل",
        source_key="source:test:2",
    )

    targets = [
        _canonical_target(
            media_identity_id=9,
            platform="telegram",
            destination_id=20,
        ),
        _canonical_target(
            media_identity_id=4,
            platform="telegram",
            destination_id=21,
        ),
    ]

    decisions = publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert calls == [4, 9]
    assert decisions == {
        4: 4,
        9: 9,
    }


def test_neutral_text_has_priority_over_main_text(monkeypatch):
    observed = {}

    def fake_check_duplicate_against_history(
        *,
        media_identity_id,
        text,
        source_key=None,
        **_kwargs,
    ):
        observed["text"] = text
        return object()

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="متن فرمت شده",
        neutral_text="متن خنثی اصلی خبر",
        source_key="source:test:3",
    )

    targets = [
        _canonical_target(
            media_identity_id=7,
            platform="telegram",
            destination_id=30,
        )
    ]

    publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert observed["text"] == "متن خنثی اصلی خبر"


def test_empty_text_skips_duplicate_check(monkeypatch):
    called = False

    def fake_check_duplicate_against_history(**_kwargs):
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="",
        neutral_text="",
        source_key="source:test:4",
    )

    targets = [
        _canonical_target(
            media_identity_id=7,
            platform="telegram",
            destination_id=40,
        )
    ]

    decisions = publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert decisions == {}
    assert called is False


def test_noncanonical_targets_do_not_trigger_duplicate_check(
    monkeypatch,
):
    called = False

    def fake_check_duplicate_against_history(**_kwargs):
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="خبر آزمایشی",
        source_key="source:test:5",
    )

    target = PublicationTarget(
        key="legacy:telegram",
        kind="legacy",
        platform="telegram",
        external_id="@example",
        workspace_id=None,
        destination_id=None,
        destination={},
    )

    decisions = publication_engine._duplicate_decisions_for_targets(
        prepared,
        [target],
    )

    assert decisions == {}
    assert called is False


def test_duplicate_guard_failure_is_fail_open(monkeypatch):
    def broken_check(**_kwargs):
        raise RuntimeError("duplicate guard unavailable")

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        broken_check,
    )

    prepared = PreparedContent(
        main_text="این خبر باید مسیر انتشار را خراب نکند",
        source_key="source:test:6",
    )

    targets = [
        _canonical_target(
            media_identity_id=15,
            platform="telegram",
            destination_id=50,
        )
    ]

    decisions = publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert decisions == {}


def test_publication_identity_is_used_when_source_key_missing(
    monkeypatch,
):
    observed = {}

    def fake_check_duplicate_against_history(
        *,
        media_identity_id,
        text,
        source_key=None,
        **_kwargs,
    ):
        observed["source_key"] = source_key
        return object()

    monkeypatch.setattr(
        "core.duplicate_guard.check_duplicate_against_history",
        fake_check_duplicate_against_history,
    )

    prepared = PreparedContent(
        main_text="خبر بدون source key صریح",
    )

    targets = [
        _canonical_target(
            media_identity_id=7,
            platform="telegram",
            destination_id=60,
        )
    ]

    publication_engine._duplicate_decisions_for_targets(
        prepared,
        targets,
    )

    assert observed["source_key"] == prepared.publication_identity
    assert observed["source_key"].startswith("ephemeral:")
