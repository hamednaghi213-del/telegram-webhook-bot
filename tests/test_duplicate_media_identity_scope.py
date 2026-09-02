from core.content_model import PublicationTarget
from core.publication_engine import _unique_media_identity_ids


def _canonical_target(
    *,
    key: str,
    platform: str,
    destination_id: int,
    media_identity_id,
):
    return PublicationTarget(
        key=key,
        kind="workspace",
        platform=platform,
        external_id=f"destination-{destination_id}",
        workspace_id=10,
        destination_id=destination_id,
        destination={
            "_canonical_media": True,
            "media_identity": {
                "id": media_identity_id,
            },
        },
    )


def test_same_media_identity_is_returned_once_for_telegram_and_bale():
    targets = [
        _canonical_target(
            key="telegram-target",
            platform="telegram",
            destination_id=101,
            media_identity_id=7,
        ),
        _canonical_target(
            key="bale-target",
            platform="bale",
            destination_id=102,
            media_identity_id=7,
        ),
    ]

    assert _unique_media_identity_ids(targets) == [7]


def test_different_media_identities_remain_separate():
    targets = [
        _canonical_target(
            key="media-a",
            platform="telegram",
            destination_id=101,
            media_identity_id=7,
        ),
        _canonical_target(
            key="media-b",
            platform="telegram",
            destination_id=201,
            media_identity_id=9,
        ),
    ]

    assert _unique_media_identity_ids(targets) == [7, 9]


def test_duplicate_destinations_do_not_duplicate_media_identity():
    targets = [
        _canonical_target(
            key="one",
            platform="telegram",
            destination_id=101,
            media_identity_id=5,
        ),
        _canonical_target(
            key="two",
            platform="telegram",
            destination_id=102,
            media_identity_id=5,
        ),
        _canonical_target(
            key="three",
            platform="bale",
            destination_id=103,
            media_identity_id=5,
        ),
    ]

    assert _unique_media_identity_ids(targets) == [5]


def test_noncanonical_target_is_ignored():
    target = PublicationTarget(
        key="legacy",
        kind="legacy",
        platform="telegram",
        external_id="@legacy",
        destination={},
    )

    assert _unique_media_identity_ids([target]) == []


def test_canonical_target_without_media_identity_is_ignored():
    target = PublicationTarget(
        key="missing-media",
        kind="workspace",
        platform="telegram",
        external_id="@channel",
        workspace_id=10,
        destination_id=100,
        destination={
            "_canonical_media": True,
        },
    )

    assert _unique_media_identity_ids([target]) == []


def test_invalid_media_identity_id_is_ignored():
    targets = [
        _canonical_target(
            key="invalid",
            platform="telegram",
            destination_id=101,
            media_identity_id="not-an-id",
        ),
        _canonical_target(
            key="valid",
            platform="bale",
            destination_id=102,
            media_identity_id="12",
        ),
    ]

    assert _unique_media_identity_ids(targets) == [12]


def test_result_is_stably_sorted():
    targets = [
        _canonical_target(
            key="three",
            platform="telegram",
            destination_id=103,
            media_identity_id=30,
        ),
        _canonical_target(
            key="one",
            platform="telegram",
            destination_id=101,
            media_identity_id=10,
        ),
        _canonical_target(
            key="two",
            platform="bale",
            destination_id=102,
            media_identity_id=20,
        ),
    ]

    assert _unique_media_identity_ids(targets) == [10, 20, 30]
