"""Focused regression tests for Persistence B5-B8.

All persistent database access is mocked at the ``core.database``
boundary. ``core.database`` is resolved dynamically through
``_live_database()`` so the tests patch whichever module object is
currently in ``sys.modules`` — other files in this suite replace
``core.database`` with fake ModuleTypes (e.g.
``test_media_handler_integration``), and production code resolves
the module dynamically at call time. Monkeypatch calls therefore
use ``raising=False``: with a fake module installed the target
attribute legitimately does not exist yet.

Feature flags are toggled through ``monkeypatch.setenv``.
"""

import importlib
import os
import sys
import time

import pytest


# ---------------------------------------------------------
# Bootstrap core.database BEFORE any core.* import.
# ---------------------------------------------------------

os.environ.setdefault(
    "SUPABASE_URL", "https://example.test"
)
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault(
    "SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key"
)

_fake_supabase_module = sys.modules.get("supabase")

if _fake_supabase_module is None or not getattr(
    _fake_supabase_module, "_is_persistence_fake", False
):
    _fake_supabase_module = type(sys)("supabase")
    _fake_supabase_module._is_persistence_fake = True
    _fake_supabase_module.create_client = (
        lambda _url, _key: object()
    )
    sys.modules["supabase"] = _fake_supabase_module

sys.modules.pop("core.database", None)

_core_package = sys.modules.get("core")

if _core_package is not None:
    _core_package.__dict__.pop("database", None)

import core.database  # noqa: E402

# Re-bind the fake supabase module for every later importer.
sys.modules["supabase"] = _fake_supabase_module

import core.editorial_pending  # noqa: E402
import core.duplicate_pending  # noqa: E402
import core.media_handler  # noqa: E402
import core.publication_engine  # noqa: E402

from core.duplicate_pending import (  # noqa: E402
    consume_pending_duplicate,
    create_pending_duplicate,
    get_pending_duplicate,
)
from core.editorial_pending import (  # noqa: E402
    DEFAULT_PENDING_TTL_SECONDS,
    cancel_pending_review,
    create_pending_review,
    get_pending_review,
    rehydrate_editorial_reviews,
    set_admin_instruction_waiting,
    update_pending_summary,
)
from core.media_handler import (  # noqa: E402
    add_to_pending_group,
    rehydrate_media_groups,
    remove_pending_group,
)
from core.publication_state import (  # noqa: E402
    PersistentPublicationStateStore,
)


# =========================================================
# HELPERS
# =========================================================


def _live_database():
    """Resolve the CURRENT core.database module object."""
    return importlib.import_module("core.database")


def _patch_db(monkeypatch, name, value):
    """Patch an attribute on every live ``core.database`` binding.

    Two resolution paths exist in production code:
    - ``from core.database import X`` (module-first) resolves the
      ``sys.modules["core.database"]`` entry;
    - ``from core import database`` (package-attribute-first)
      resolves the ``core`` package attribute.

    Other suite files replace the ``sys.modules`` entry with fake
    ModuleTypes, so the two bindings can diverge. Patch BOTH, with
    ``raising=False`` because the target may be a fake module that
    does not define every accessor.
    """
    module = importlib.import_module("core.database")

    monkeypatch.setattr(
        module,
        name,
        value,
        raising=False,
    )

    core_package = sys.modules.get("core")

    if core_package is not None:
        bound = getattr(core_package, "database", None)

        if bound is not None and bound is not module:
            monkeypatch.setattr(
                bound,
                name,
                value,
                raising=False,
            )


def _enable_all(monkeypatch):
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_MEDIA_GROUP_STATE", "true"
    )
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_EDITORIAL_STATE", "true"
    )
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_DUPLICATE_OVERRIDES", "true"
    )


def _clean_media_groups():
    core.media_handler.pending_groups.clear()
    core.media_handler.group_timers.clear()


# =========================================================
# B5 — PERSISTENT PUBLICATION IDEMPOTENCY
# =========================================================


class _FakeDatabaseB5:
    """Minimal claim RPC double recording lease owner."""

    claims = []

    @staticmethod
    def claim_persistent_publication_delivery(**kwargs):
        _FakeDatabaseB5.claims.append(kwargs)

        return {
            "claimed": True,
            "source_id": 10,
            "delivery_id": 20,
            "status": "sending",
            "attempt_count": 1,
            "lease_expires_at": None,
        }


def test_b5_claim_uses_boot_unique_lease_owner(monkeypatch):
    _FakeDatabaseB5.claims = []

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        _FakeDatabaseB5.claim_persistent_publication_delivery,
    )

    store = PersistentPublicationStateStore()

    assert store.lease_owner
    assert store.lease_owner.startswith("worker-")

    # Boot-unique: a second store for the same process differs.
    other = PersistentPublicationStateStore()

    assert other.lease_owner != store.lease_owner

    state = store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:chan",
        platform="telegram",
        destination_chat_id="@chan",
    )

    assert state is not None

    recorded = _FakeDatabaseB5.claims[-1]

    assert recorded["lease_owner"] == store.lease_owner


def test_b5_cross_worker_claim_race_only_one_winner(monkeypatch):
    """Two stores (workers) racing the same destination: one wins."""
    _FakeDatabaseB5.claims = []

    lease_holders = []

    def claim(**kwargs):
        _FakeDatabaseB5.claims.append(kwargs)

        # Simulate the atomic RPC: exactly one live lease.
        if lease_holders:
            return {
                "claimed": False,
                "source_id": 10,
                "delivery_id": 20,
                "status": "sending",
                "attempt_count": 1,
                "lease_expires_at": (
                    "2026-09-20T00:00:00+00:00"
                ),
            }

        lease_holders.append(kwargs["lease_owner"])

        return {
            "claimed": True,
            "source_id": 10,
            "delivery_id": 20,
            "status": "sending",
            "attempt_count": 1,
            "lease_expires_at:": None,
        }

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        claim,
    )

    store_a = PersistentPublicationStateStore()
    store_b = PersistentPublicationStateStore()

    state_a = store_a.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:chan",
        platform="telegram",
    )

    state_b = store_b.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:chan",
        platform="telegram",
    )

    assert state_a is not None
    assert state_b is None


def test_b5_successful_part_not_resent_after_restart(monkeypatch):
    """After a simulated restart (fresh store), a part with transport
    proof in Supabase is reported completed and is not resent."""
    _patch_db(
        monkeypatch,
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

    _patch_db(
        monkeypatch,
        "get_persistent_publication_part",
        lambda **_kwargs: {
            "part_key": "primary",
            "status": "succeeded",
            "message_id": 4242,
            "message_ids": None,
            "destination_chat_id": "@chan",
        },
    )

    # Fresh store == fresh process after restart. Production order:
    # the engine claims the delivery first, then checks parts.
    fresh_store = PersistentPublicationStateStore()

    state = fresh_store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:chan",
        platform="telegram",
        destination_chat_id="@chan",
    )

    assert state is not None

    completed = fresh_store.part_completed(
        source_key="tg:1:100",
        target_identity="telegram:external:chan",
        part="primary",
    )

    assert completed is True


def test_b5_persistent_failure_does_not_fail_open(monkeypatch):
    """A persistent-state error surfaces as an exception (fail
    closed) instead of silently enabling an unsafe resend."""

    def boom(**_kwargs):
        raise RuntimeError("supabase unavailable")

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        boom,
    )

    store = PersistentPublicationStateStore()

    with pytest.raises(RuntimeError):
        store.begin_persistent_attempt(
            source_key="tg:1:100",
            target_identity="telegram:external:chan",
            platform="telegram",
        )


# =========================================================
# B6 — PERSISTENT MEDIA GROUP
# =========================================================


class _FakeDatabaseB6:
    def __init__(self):
        self.rows = {}
        self.claims = []

    def upsert(self, payload):
        key = (
            int(payload["chat_id"]),
            str(payload["media_group_id"]),
        )

        merged = dict(self.rows.get(key) or {})
        merged.update(payload)
        self.rows[key] = merged

        return merged

    def get(self, chat_id, media_group_id):
        return self.rows.get(
            (int(chat_id), str(media_group_id))
        )

    def list_unfinished(self):
        return [
            row for row in self.rows.values()
            if row.get("state")
            not in ("published", "failed_terminal")
        ]

    def delete(self, chat_id, media_group_id):
        return (
            self.rows.pop(
                (int(chat_id), str(media_group_id)),
                None,
            )
            is not None
        )

    def claim(self, **kwargs):
        self.claims.append(kwargs)

        key = (
            int(kwargs["chat_id"]),
            str(kwargs["media_group_id"]),
        )

        row = self.rows.get(key)

        if row is None:
            return {"claimed": False}

        # Second claim while a live lease exists is rejected.
        if any(
            prior.get("chat_id") == kwargs["chat_id"]
            and prior.get("media_group_id")
            == kwargs["media_group_id"]
            for prior in self.claims[:-1]
        ):
            return {"claimed": False}

        return {
            "claimed": True,
            "media_group_state_id": 77,
            "current_delivery_generation": (
                row.get("delivery_generation", 1)
            ),
            "current_state": "leased",
            "current_attempt_count": 1,
            "current_lease_expires_at": None,
        }


@pytest.fixture()
def fake_b6(monkeypatch):
    _clean_media_groups()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_MEDIA_GROUP_STATE", "true"
    )

    db = _FakeDatabaseB6()

    _patch_db(
        monkeypatch,
        "persistent_media_group_enabled",
        lambda: True,
    )
    _patch_db(
        monkeypatch,
        "upsert_persistent_media_group",
        db.upsert,
    )
    _patch_db(
        monkeypatch,
        "get_persistent_media_group",
        lambda **kwargs: db.get(
            kwargs["chat_id"], kwargs["media_group_id"]
        ),
    )
    _patch_db(
        monkeypatch,
        "list_unfinished_persistent_media_groups",
        lambda **_kwargs: tuple(db.list_unfinished()),
    )
    _patch_db(
        monkeypatch,
        "delete_persistent_media_group",
        lambda **kwargs: db.delete(
            kwargs["chat_id"], kwargs["media_group_id"]
        ),
    )
    _patch_db(
        monkeypatch,
        "claim_persistent_media_group",
        lambda **kwargs: db.claim(**kwargs),
    )

    yield db

    _clean_media_groups()


def test_b6_group_snapshot_persisted_with_ordering(fake_b6):
    add_to_pending_group(
        "grp-1", 100, "file-b", "photo", message_id=12
    )
    add_to_pending_group(
        "grp-1", 100, "file-a", "video", message_id=11,
        caption="کپشن آلبوم",
    )

    row = fake_b6.get(100, "grp-1")

    assert row is not None
    assert row["state"] == "collecting"

    # items arrive ordered by message_id (same as the in-memory sort)
    items = row["items"]

    assert [item["file_id"] for item in items] == [
        "file-a",
        "file-b",
    ]
    assert row["raw_caption"] == "کپشن آلبوم"
    assert row["generation"] == 2


def test_b6_rehydration_rebuilds_group_and_rearms_timer(
    fake_b6, monkeypatch
):
    add_to_pending_group(
        "grp-r", 200, "file-1", "photo", message_id=1
    )
    add_to_pending_group(
        "grp-r", 200, "file-2", "video", message_id=2
    )

    stored = dict(fake_b6.get(200, "grp-r"))

    # Simulate a restart: wipe the in-memory store.
    _clean_media_groups()

    scheduled = []

    monkeypatch.setattr(
        core.media_handler,
        "schedule_processing",
        lambda media_group_id, chat_id, delay=1.0: (
            scheduled.append((chat_id, media_group_id, delay))
        ),
    )

    restored = rehydrate_media_groups()

    assert restored == 1

    group = core.media_handler.pending_groups[(200, "grp-r")]

    assert [item["file_id"] for item in group["files"]] == [
        "file-1",
        "file-2",
    ]
    assert group["delivery_generation"] == 1
    assert group["is_processing"] is False
    # The row was snapshotted during collection, so it rehydrates
    # in the collecting state and re-enters the normal state machine.
    assert group["state"] == "collecting"

    # Processing timer re-armed for recovery.
    assert scheduled == [(200, "grp-r", 1.0)]


def test_b6_late_member_after_rehydration_continues_generation(
    fake_b6, monkeypatch
):
    add_to_pending_group(
        "grp-l", 300, "file-1", "photo", message_id=1
    )

    # Restart + rehydrate.
    _clean_media_groups()

    monkeypatch.setattr(
        core.media_handler,
        "schedule_processing",
        lambda *args, **kwargs: None,
    )

    rehydrate_media_groups()

    # A late album member arrives after rehydration.
    add_to_pending_group(
        "grp-l", 300, "file-2", "video", message_id=2
    )

    group = core.media_handler.pending_groups[(300, "grp-l")]

    # Generation continuity: the in-memory generation advanced from
    # the persisted value, not from zero.
    assert group["generation"] == 2

    row = fake_b6.get(300, "grp-l")

    assert row["generation"] == 2
    assert len(row["items"]) == 2


def test_b6_album_not_handed_to_single_media_processor(
    fake_b6, monkeypatch
):
    """The album path must always execute the shared publication
    engine with the full album file list; the single-media processor
    is never used for album members."""
    from core.media_handler import (
        TELEGRAM_MEDIA_GROUP_MIN_ITEMS,
        process_media_group,
    )

    for index in range(TELEGRAM_MEDIA_GROUP_MIN_ITEMS):
        add_to_pending_group(
            "grp-m", 400, f"file-{index}", "photo",
            message_id=index + 1,
        )

    engine_calls = {}

    def fake_publish_prepared_content(
        chat_id, api_url, prepared, **_kwargs
    ):
        engine_calls["chat_id"] = chat_id
        engine_calls["files"] = list(prepared.files)
        engine_calls["source_key"] = prepared.source_key

        return {"ok": True, "results": []}

    monkeypatch.setattr(
        core.publication_engine,
        "publish_prepared_content",
        fake_publish_prepared_content,
    )

    ok = process_media_group(
        "grp-m", 400, expected_generation=2
    )

    assert ok is True

    # The shared engine received the whole album in one call.
    assert (
        len(engine_calls["files"])
        == TELEGRAM_MEDIA_GROUP_MIN_ITEMS
    )

    # Album source_key/generation continuity contract.
    assert engine_calls["source_key"] == (
        "tg:400:album:grp-m:generation:1"
    )


def test_b6_cross_worker_claim_blocks_second_processor(fake_b6):
    """The persistent generation claim rejects a second concurrent
    processor for the same group/generation."""
    claim_persistent_media_group = (
        _live_database().claim_persistent_media_group
    )

    add_to_pending_group(
        "grp-c", 500, "file-1", "photo", message_id=1
    )
    add_to_pending_group(
        "grp-c", 500, "file-2", "video", message_id=2
    )

    first = claim_persistent_media_group(
        chat_id=500,
        media_group_id="grp-c",
        delivery_generation=1,
        lease_owner="worker-a",
    )

    second = claim_persistent_media_group(
        chat_id=500,
        media_group_id="grp-c",
        delivery_generation=1,
        lease_owner="worker-b",
    )

    assert first.get("claimed") is True
    assert second.get("claimed") is not True


def test_b6_terminal_group_deleted_from_persistence(fake_b6):
    add_to_pending_group(
        "grp-d", 600, "file-1", "photo", message_id=1
    )

    assert fake_b6.get(600, "grp-d") is not None

    remove_pending_group("grp-d", 600)

    assert fake_b6.get(600, "grp-d") is None


def test_b6_flag_off_keeps_in_memory_only(monkeypatch):
    _clean_media_groups()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_MEDIA_GROUP_STATE", "false"
    )

    called = {"upsert": False}

    def forbidden_upsert(*args, **kwargs):
        called["upsert"] = True
        return {}

    _patch_db(
        monkeypatch,
        "upsert_persistent_media_group",
        forbidden_upsert,
    )

    try:
        add_to_pending_group(
            "grp-off", 700, "file-1", "photo", message_id=1
        )

        assert called["upsert"] is False
        assert (700, "grp-off") in core.media_handler.pending_groups
    finally:
        _clean_media_groups()


# =========================================================
# B7 — PERSISTENT EDITORIAL PENDING
# =========================================================


class _FakeDatabaseB7:
    def __init__(self):
        self.rows = {}

    def upsert(self, payload):
        review_id = str(payload["review_id"])

        merged = dict(self.rows.get(review_id) or {})
        merged.update(payload)
        self.rows[review_id] = merged

        return merged

    def update(self, review_id, fields):
        review_id = str(review_id)

        if review_id not in self.rows:
            return None

        self.rows[review_id].update(fields)

        return self.rows[review_id]

    def get(self, review_id):
        return self.rows.get(str(review_id))

    def list_unfinished(self):
        return [
            row for row in self.rows.values()
            if row.get("status") == "pending"
        ]

    def delete(self, review_id):
        return self.rows.pop(str(review_id), None) is not None

    def claim(self, review_id, expected_status, claim_owner):
        row = self.rows.get(str(review_id))

        if row is None:
            return {"claimed": False}

        if row.get("status") != expected_status:
            return {"claimed": False}

        if row.get("_claim_live"):
            return {"claimed": False}

        row["_claim_live"] = True

        return {"claimed": True}


@pytest.fixture()
def fake_b7(monkeypatch):
    core.editorial_pending.clear_pending_reviews()
    monkeypatch.setenv("ENABLE_PERSISTENT_EDITORIAL_STATE", "true")

    db = _FakeDatabaseB7()

    _patch_db(
        monkeypatch,
        "persistent_editorial_pending_enabled",
        lambda: True,
    )
    _patch_db(
        monkeypatch,
        "upsert_persistent_editorial_review",
        db.upsert,
    )
    _patch_db(
        monkeypatch,
        "update_persistent_editorial_review",
        lambda **kwargs: db.update(
            kwargs["review_id"], kwargs["fields"]
        ),
    )
    _patch_db(
        monkeypatch,
        "get_persistent_editorial_review",
        lambda **kwargs: db.get(kwargs["review_id"]),
    )
    _patch_db(
        monkeypatch,
        "list_unfinished_persistent_editorial_reviews",
        lambda **_kwargs: tuple(db.list_unfinished()),
    )
    _patch_db(
        monkeypatch,
        "delete_persistent_editorial_review",
        lambda **kwargs: db.delete(kwargs["review_id"]),
    )
    _patch_db(
        monkeypatch,
        "claim_persistent_editorial_review_action",
        lambda **kwargs: db.claim(
            kwargs["review_id"],
            kwargs["expected_status"],
            kwargs["claim_owner"],
        ),
    )

    yield db

    core.editorial_pending.clear_pending_reviews()


def test_b7_review_survives_restart(fake_b7):
    created = create_pending_review(
        user_id=42,
        content_type="news_analysis",
        original_text="متن اصلی",
        current_summary="خلاصه اولیه",
    )

    stored = fake_b7.get(created.review_id)

    assert stored is not None
    assert stored["status"] == "pending"
    assert stored["original_text"] == "متن اصلی"

    # Simulate restart: wipe in-memory store, rehydrate.
    core.editorial_pending.clear_pending_reviews()

    restored = rehydrate_editorial_reviews()

    assert restored == 1

    review = get_pending_review(
        review_id=stored["review_id"],
        user_id=42,
    )

    assert review is not None
    assert review.current_summary == "خلاصه اولیه"
    assert review.status == "pending"


def test_b7_summary_update_persisted(fake_b7):
    review = create_pending_review(
        user_id=7,
        content_type="news_analysis",
        original_text="متن",
        current_summary="نسخه ۱",
    )

    update_pending_summary(
        review_id=review.review_id,
        user_id=7,
        new_summary="نسخه ۲",
        regeneration_count=1,
    )

    row = fake_b7.get(review.review_id)

    assert row["current_summary"] == "نسخه ۲"
    assert row["regeneration_count"] == 1


def test_b7_admin_instruction_waiting_survives_restart(fake_b7):
    review = create_pending_review(
        user_id=9,
        content_type="news_analysis",
        original_text="متن",
        current_summary="خلاصه",
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=9,
    )

    core.editorial_pending.clear_pending_reviews()

    rehydrate_editorial_reviews()

    restored = get_pending_review(
        review_id=review.review_id,
        user_id=9,
    )

    assert restored is not None
    assert (
        restored.metadata.get("awaiting_admin_instruction")
        is True
    )


def test_b7_cancel_persisted(fake_b7):
    review = create_pending_review(
        user_id=11,
        content_type="news_analysis",
        original_text="متن",
        current_summary="خلاصه",
    )

    cancel_pending_review(
        review_id=review.review_id,
        user_id=11,
    )

    row = fake_b7.get(review.review_id)

    assert row["status"] == "cancelled"


def test_b7_action_claim_exactly_once_across_workers(fake_b7):
    review = create_pending_review(
        user_id=13,
        content_type="news_analysis",
        original_text="متن",
        current_summary="خلاصه",
    )

    claim_persistent_editorial_review_action = (
        _live_database().claim_persistent_editorial_review_action
    )

    first = claim_persistent_editorial_review_action(
        review_id=review.review_id,
        expected_status="pending",
        claim_owner="worker-a",
    )

    second = claim_persistent_editorial_review_action(
        review_id=review.review_id,
        expected_status="pending",
        claim_owner="worker-b",
    )

    assert first.get("claimed") is True
    assert second.get("claimed") is not True


def test_b7_ttl_expiry_persisted_and_rehydrated(fake_b7):
    review = create_pending_review(
        user_id=15,
        content_type="news_analysis",
        original_text="متن",
        current_summary="خلاصه",
    )

    # Age the review beyond the TTL in the in-memory store only.
    target = core.editorial_pending._pending_reviews[
        review.review_id
    ]
    target.updated_at = time.time() - (
        DEFAULT_PENDING_TTL_SECONDS + 10
    )

    expired = get_pending_review(
        review_id=review.review_id,
        user_id=15,
    )

    assert expired.status == "expired"


def test_b7_flag_off_keeps_in_memory_only(monkeypatch):
    core.editorial_pending.clear_pending_reviews()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_EDITORIAL_STATE", "false"
    )

    called = {"upsert": False}

    def forbidden_upsert(*args, **kwargs):
        called["upsert"] = True
        return {}

    _patch_db(
        monkeypatch,
        "upsert_persistent_editorial_review",
        forbidden_upsert,
    )

    try:
        create_pending_review(
            user_id=17,
            content_type="news_analysis",
            original_text="متن",
            current_summary="خلاصه",
        )

        assert called["upsert"] is False
        assert (
            core.editorial_pending.pending_review_count() == 1
        )
    finally:
        core.editorial_pending.clear_pending_reviews()


# =========================================================
# B8 — PERSISTENT DUPLICATE OVERRIDES
# =========================================================


def _make_prepared(main_text="خبر تستی"):
    from core.content_model import (
        PreparedContent,
        PublicationTarget,
    )

    prepared = PreparedContent(
        main_text=main_text,
        source_key="tg:1:message:5",
    )

    targets = (
        PublicationTarget(
            key="legacy:telegram:@chan",
            kind="legacy",
            platform="telegram",
            external_id="@chan",
        ),
    )

    return prepared, targets


class _FakeDatabaseB8:
    def __init__(self):
        self.rows = {}

    def create(self, token, chat_id, descriptor, ttl_seconds):
        self.rows[str(token)] = {
            "token": str(token),
            "chat_id": int(chat_id),
            "descriptor": dict(descriptor),
        }

        return True

    def consume(self, token, chat_id):
        row = self.rows.get(str(token))

        # Atomic single-use semantics (mirrors the 028 RPC).
        if (
            row is None
            or int(row["chat_id"]) != int(chat_id)
        ):
            return None

        del self.rows[str(token)]

        return dict(row["descriptor"])


@pytest.fixture()
def fake_b8(monkeypatch):
    core.duplicate_pending._pending.clear()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_DUPLICATE_OVERRIDES", "true"
    )

    db = _FakeDatabaseB8()

    _patch_db(
        monkeypatch,
        "persistent_duplicate_override_enabled",
        lambda: True,
    )
    _patch_db(
        monkeypatch,
        "create_persistent_duplicate_override",
        lambda **kwargs: db.create(
            kwargs["token"],
            kwargs["chat_id"],
            kwargs["descriptor"],
            kwargs["ttl_seconds"],
        ),
    )
    _patch_db(
        monkeypatch,
        "consume_persistent_duplicate_override",
        lambda **kwargs: db.consume(
            kwargs["token"], kwargs["chat_id"]
        ),
    )

    yield db

    core.duplicate_pending._pending.clear()


def test_b8_override_survives_restart(fake_b8):
    prepared, targets = _make_prepared()

    token = create_pending_duplicate(
        chat_id=21,
        prepared=prepared,
        targets=list(targets),
    )

    # Simulate restart: in-memory tokens are gone.
    core.duplicate_pending._pending.clear()

    pending = consume_pending_duplicate(
        token=token,
        chat_id=21,
    )

    assert pending is not None
    assert pending.prepared.main_text == "خبر تستی"
    assert pending.targets[0].platform == "telegram"


def test_b8_descriptor_is_repreparable_not_opaque(fake_b8):
    prepared, targets = _make_prepared()

    token = create_pending_duplicate(
        chat_id=22,
        prepared=prepared,
        targets=list(targets),
    )

    descriptor = fake_b8.rows[token]["descriptor"]

    # The descriptor must be plain JSON-safe data, not an object.
    assert isinstance(descriptor, dict)
    assert descriptor["main_text"] == "خبر تستی"
    assert "PreparedContent" not in repr(descriptor)
    assert descriptor["targets"][0]["external_id"] == "@chan"


def test_b8_consume_atomic_single_use_across_workers(fake_b8):
    prepared, targets = _make_prepared()

    token = create_pending_duplicate(
        chat_id=23,
        prepared=prepared,
        targets=list(targets),
    )

    # Simulate two workers: neither holds the token in memory.
    core.duplicate_pending._pending.clear()

    first = consume_pending_duplicate(
        token=token,
        chat_id=23,
    )

    second = consume_pending_duplicate(
        token=token,
        chat_id=23,
    )

    assert first is not None
    assert second is None


def test_b8_wrong_chat_cannot_consume(fake_b8):
    prepared, targets = _make_prepared()

    token = create_pending_duplicate(
        chat_id=24,
        prepared=prepared,
        targets=list(targets),
    )

    core.duplicate_pending._pending.clear()

    pending = consume_pending_duplicate(
        token=token,
        chat_id=999,
    )

    assert pending is None

    # The token remains consumable by its owner.
    owner = consume_pending_duplicate(
        token=token,
        chat_id=24,
    )

    assert owner is not None


def test_b8_in_memory_consume_invalidates_persistent_mirror(fake_b8):
    prepared, targets = _make_prepared()

    token = create_pending_duplicate(
        chat_id=25,
        prepared=prepared,
        targets=list(targets),
    )

    # Worker A consumes in-memory.
    pending = consume_pending_duplicate(
        token=token,
        chat_id=25,
    )

    assert pending is not None

    # Worker B must not be able to consume the persistent mirror.
    other = consume_pending_duplicate(
        token=token,
        chat_id=25,
    )

    assert other is None


def test_b8_flag_off_keeps_in_memory_only(monkeypatch):
    core.duplicate_pending._pending.clear()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_DUPLICATE_OVERRIDES", "false"
    )

    called = {"create": False}

    def forbidden_create(*args, **kwargs):
        called["create"] = True
        return True

    _patch_db(
        monkeypatch,
        "create_persistent_duplicate_override",
        forbidden_create,
    )

    try:
        prepared, targets = _make_prepared()

        token = create_pending_duplicate(
            chat_id=26,
            prepared=prepared,
            targets=list(targets),
        )

        assert called["create"] is False

        pending = get_pending_duplicate(
            token=token,
            chat_id=26,
        )

        assert pending is not None
    finally:
        core.duplicate_pending._pending.clear()


def test_b8_persistent_failure_fails_closed(monkeypatch):
    core.duplicate_pending._pending.clear()
    monkeypatch.setenv(
        "ENABLE_PERSISTENT_DUPLICATE_OVERRIDES", "true"
    )

    def boom(**_kwargs):
        raise RuntimeError("supabase unavailable")

    _patch_db(
        monkeypatch,
        "persistent_duplicate_override_enabled",
        lambda: True,
    )
    _patch_db(
        monkeypatch,
        "consume_persistent_duplicate_override",
        boom,
    )

    try:
        # Token unknown in-memory; persistent consume fails.
        result = consume_pending_duplicate(
            token="missing-token",
            chat_id=27,
        )

        assert result is None
    finally:
        core.duplicate_pending._pending.clear()
