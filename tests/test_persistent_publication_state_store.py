from core.publication_state import (
    PersistentPublicationStateStore,
)


def test_begin_persistent_attempt_claims_delivery(
    monkeypatch,
):
    calls = {}

    class FakeDatabase:
        @staticmethod
        def claim_persistent_publication_delivery(
            **kwargs,
        ):
            calls.update(kwargs)

            return {
                "claimed": True,
                "source_id": 10,
                "delivery_id": 20,
                "status": "sending",
                "attempt_count": 2,
                "lease_expires_at": (
                    "2026-09-02T12:00:00+00:00"
                ),
            }

    import core.database
    import core.publication_state

    monkeypatch.setattr(
        core.publication_state,
        "database",
        FakeDatabase,
        raising=False,
    )

    monkeypatch.setattr(
        core.database,
        "claim_persistent_publication_delivery",
        FakeDatabase
        .claim_persistent_publication_delivery,
    )

    store = PersistentPublicationStateStore(
        lease_owner="worker-test",
        lease_seconds=120,
    )

    state = store.begin_persistent_attempt(
        source_key="telegram:1:100",
        target_identity=(
            "telegram:external:farda_no"
        ),
        platform="telegram",
        destination_chat_id="@farda_no",
        workspace_id=4,
        destination_id=8,
        delivery_generation=1,
    )

    assert state is not None
    assert state.status == "sending"
    assert state.attempt == 2
    assert state.persistent_delivery_id == 20
    assert state.error is None

    assert calls == {
        "source_key": "telegram:1:100",
        "canonical_identity": (
            "telegram:external:farda_no"
        ),
        "platform": "telegram",
        "destination_chat_id": (
            "@farda_no"
        ),
        "workspace_id": 4,
        "destination_id": 8,
        "delivery_generation": 1,
        "lease_owner": "worker-test",
        "lease_seconds": 120,
    }


def test_begin_persistent_attempt_returns_none_when_not_claimed(
    monkeypatch,
):
    import core.database

    monkeypatch.setattr(
        core.database,
        "claim_persistent_publication_delivery",
        lambda **_kwargs: {
            "claimed": False,
            "source_id": 10,
            "delivery_id": 20,
            "status": "sending",
            "attempt_count": 1,
            "lease_expires_at": (
                "2026-09-02T12:00:00+00:00"
            ),
        },
    )

    store = PersistentPublicationStateStore(
        lease_owner="worker-test",
    )

    state = store.begin_persistent_attempt(
        source_key="telegram:1:100",
        target_identity=(
            "telegram:external:farda_no"
        ),
        platform="telegram",
    )

    assert state is None


def test_persistent_store_clamps_lease_seconds():
    low = PersistentPublicationStateStore(
        lease_seconds=1,
    )
    high = PersistentPublicationStateStore(
        lease_seconds=5000,
    )

    assert low.lease_seconds == 30
    assert high.lease_seconds == 900

def test_part_succeeded_persists_to_database(
    monkeypatch,
):
    import core.database

    calls = {}

    monkeypatch.setattr(
        core.database,
        "claim_persistent_publication_delivery",
        lambda **_kwargs: {
            "claimed": True,
            "source_id": 10,
            "delivery_id": 20,
            "status": "sending",
            "attempt_count": 1,
            "lease_expires_at": None,
        },
    )

    def fake_record_success(**kwargs):
        calls.update(kwargs)
        return {
            "delivery_id": kwargs["delivery_id"],
            "part_key": kwargs["part_key"],
            "status": "succeeded",
        }

    monkeypatch.setattr(
        core.database,
        "record_persistent_publication_part_success",
        fake_record_success,
    )

    store = PersistentPublicationStateStore(
        lease_owner="worker-test",
    )

    state = store.begin_persistent_attempt(
        source_key="telegram:1:100",
        target_identity=(
            "telegram:external:farda_no"
        ),
        platform="telegram",
        destination_chat_id="@farda_no",
    )

    assert state is not None
    assert state.persistent_delivery_id == 20

    store.part_succeeded(
        "telegram:1:100",
        "telegram:external:farda_no",
        "primary",
        message_id=501,
        message_ids=(501, 502),
        destination_chat_id="@farda_no",
    )

    assert calls == {
        "delivery_id": 20,
        "part_key": "primary",
        "message_id": 501,
        "message_ids": (501, 502),
        "destination_chat_id": "@farda_no",
    }

    delivery = store.get_delivery(
        "telegram:1:100",
        "telegram:external:farda_no",
    )

    assert delivery is not None
    assert "primary" in delivery.completed_parts
    assert delivery.message_ids["primary"] == 501
    assert delivery.all_message_ids["primary"] == (
        501,
        502,
    )
    assert delivery.message_chat_ids["primary"] == (
        "@farda_no"
    )

def test_part_completed_restores_persisted_success(
    monkeypatch,
):
    import core.database

    monkeypatch.setattr(
        core.database,
        "claim_persistent_publication_delivery",
        lambda **_kwargs: {
            "claimed": True,
            "source_id": 10,
            "delivery_id": 20,
            "status": "sending",
            "attempt_count": 2,
            "lease_expires_at": None,
        },
    )

    monkeypatch.setattr(
        core.database,
        "get_persistent_publication_part",
        lambda **_kwargs: {
            "delivery_id": 20,
            "part_key": "primary",
            "status": "succeeded",
            "message_id": 501,
            "message_ids": [501, 502],
            "destination_chat_id": "@farda_no",
        },
    )

    store = PersistentPublicationStateStore(
        lease_owner="worker-test",
    )

    state = store.begin_persistent_attempt(
        source_key="telegram:1:100",
        target_identity=(
            "telegram:external:farda_no"
        ),
        platform="telegram",
        destination_chat_id="@farda_no",
    )

    assert state is not None

    assert store.part_completed(
        "telegram:1:100",
        "telegram:external:farda_no",
        "primary",
    ) is True

    delivery = store.get_delivery(
        "telegram:1:100",
        "telegram:external:farda_no",
    )

    assert delivery is not None
    assert "primary" in delivery.completed_parts
    assert delivery.message_ids["primary"] == 501
    assert delivery.all_message_ids["primary"] == (
        501,
        502,
    )
    assert delivery.message_chat_ids["primary"] == (
        "@farda_no"
    )
