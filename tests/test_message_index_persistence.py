"""B11 focused tests: persistent Telegram/Bale message mapping.

Proves that every successful publication part records its real
transport message IDs in ``publication_delivery_message_index``
(the canonical mapping infrastructure from migration 023), with
deterministic primary marking, idempotent re-recording, and no
impact on publication/no-resend semantics.
"""

import importlib
import os
import sys
import types
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------
# Bootstrap core.database before core.* imports (suite-wide
# established pattern).
# ---------------------------------------------------------

os.environ.setdefault(
    "SUPABASE_URL", "https://example.test"
)
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault(
    "SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key"
)

_fake_supabase = sys.modules.get("supabase")

if _fake_supabase is None or not getattr(
    _fake_supabase, "_is_persistence_fake", False
):
    _fake_supabase = type(sys)("supabase")
    _fake_supabase._is_persistence_fake = True
    _fake_supabase.create_client = (
        lambda _url, _key: object()
    )
    sys.modules["supabase"] = _fake_supabase

sys.modules.pop("core.database", None)

_core_package = sys.modules.get("core")

if _core_package is not None:
    _core_package.__dict__.pop("database", None)

import core.database  # noqa: E402

# The REAL module object captured at collection time. Some suite
# files later replace sys.modules["core.database"] with fake
# ModuleTypes that only stub their own functions; unit tests that
# call real database functions must use this object.
_REAL_DATABASE = core.database

sys.modules["supabase"] = _fake_supabase

import core.publication_engine  # noqa: E402
import core.publication_state  # noqa: E402

from core.content_model import (  # noqa: E402
    ExecutorResult,
    PreparedContent,
    PublicationTarget,
)
from core.publication_state import (  # noqa: E402
    PersistentPublicationStateStore,
)


def _live_db():
    return importlib.import_module("core.database")


def _patch_real_db(monkeypatch, name, value):
    """Patch the REAL core.database module object.

    Unit tests call real database functions; those functions read
    module globals from the module where they are defined, so the
    patch must land there regardless of any fake module that other
    suite files installed under sys.modules["core.database"].
    """
    monkeypatch.setattr(
        _REAL_DATABASE,
        name,
        value,
        raising=False,
    )


def _patch_db(monkeypatch, name, value):
    """Patch both live core.database bindings (see B5-B8 tests)."""
    module = _live_db()

    monkeypatch.setattr(
        module,
        name,
        value,
        raising=False,
    )

    core_package = sys.modules.get("core")

    if core_package is not None:
        bound = getattr(
            core_package,
            "database",
            None,
        )

        if bound is not None and bound is not module:
            monkeypatch.setattr(
                bound,
                name,
                value,
                raising=False,
            )


class _IndexSpy:
    """Records index rows like the 023 unique key would."""

    def __init__(self):
        self.rows_by_key = {}
        self.calls = []

    def record(
        self,
        *,
        delivery_id,
        part_key,
        message_id=None,
        message_ids=None,
        destination_chat_id=None,
        primary_message_id=None,
    ):
        self.calls.append(
            {
                "delivery_id": delivery_id,
                "part_key": part_key,
                "message_id": message_id,
                "message_ids": message_ids,
                "destination_chat_id": (
                    destination_chat_id
                ),
                "primary_message_id": (
                    primary_message_id
                ),
            }
        )

        # Emulate delivery platform/chat resolution.
        delivery = _DELIVERIES[int(delivery_id)]

        candidates = list(message_ids or ())

        if (
            message_id is not None
            and isinstance(message_id, int)
            and not isinstance(message_id, bool)
        ):
            candidates.append(int(message_id))

        for value in candidates:
            key = (
                delivery["platform"],
                str(
                    destination_chat_id
                    if destination_chat_id is not None
                    else delivery["destination_chat_id"]
                ),
                int(value),
            )

            self.rows_by_key[key] = {
                "delivery_id": int(delivery_id),
                "part_key": str(part_key),
                "is_primary": bool(
                    primary_message_id is not None
                    and int(value)
                    == int(primary_message_id)
                ),
            }

    def primary_rows(self):
        return [
            key
            for key, row in self.rows_by_key.items()
            if row["is_primary"]
        ]


_DELIVERIES = {
    101: {
        "platform": "telegram",
        "destination_chat_id": "@tg-channel",
    },
    202: {
        "platform": "bale",
        "destination_chat_id": "@bale-channel",
    },
}


# =========================================================
# UNIT — record_persistent_publication_message_index
# =========================================================


class _FakeTableQuery:
    def __init__(self, sink):
        self._sink = sink

    def upsert(
        self,
        payload,
        on_conflict=None,
    ):
        self._sink.append(
            (payload, on_conflict)
        )

        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeServiceSupabase:
    def __init__(self):
        self.upserts = []

    def table(self, name):
        assert name == (
            "publication_delivery_message_index"
        )
        return _FakeTableQuery(self.upserts)


def test_record_index_uses_unique_key_upsert(db_env):
    """Rows are upserted on the existing 023 unique constraint
    (idempotent re-recording, no duplicate rows)."""
    db = _REAL_DATABASE
    fake = _FakeServiceSupabase()

    _patch_real_db(
        db_env,
        "service_supabase",
        fake,
    )
    _patch_real_db(
        db_env,
        "get_persistent_publication_delivery_by_id",
        lambda delivery_id: {
            "platform": "telegram",
            "destination_chat_id": "@tg-channel",
        },
    )

    db.record_persistent_publication_message_index(
        delivery_id=101,
        part_key="primary",
        message_id=555,
        primary_message_id=555,
    )

    assert len(fake.upserts) == 1

    payload, on_conflict = fake.upserts[0]

    assert on_conflict == (
        "platform,destination_chat_id,message_id"
    )
    assert payload == [
        {
            "delivery_id": 101,
            "platform": "telegram",
            "destination_chat_id": "@tg-channel",
            "part_key": "primary",
            "message_id": 555,
            "is_primary": True,
        }
    ]

    # Idempotent re-record: same upsert key, no error path.
    db.record_persistent_publication_message_index(
        delivery_id=101,
        part_key="primary",
        message_id=555,
        primary_message_id=555,
    )

    assert len(fake.upserts) == 2
    assert fake.upserts[1][1] == on_conflict

    # Non-designated messages are never marked primary.
    db.record_persistent_publication_message_index(
        delivery_id=101,
        part_key="followup:1",
        message_id=556,
    )

    payload, _ = fake.upserts[-1]

    assert payload[0]["is_primary"] is False


def test_record_index_without_message_ids_is_noop(db_env):
    db = _REAL_DATABASE
    fake = _FakeServiceSupabase()

    _patch_real_db(
        db_env,
        "service_supabase",
        fake,
    )

    db.record_persistent_publication_message_index(
        delivery_id=101,
        part_key="primary",
        message_id=None,
        message_ids=(),
    )

    assert fake.upserts == []


@pytest.fixture()
def db_env(monkeypatch):
    """Provide a live core.database with service Supabase faked."""
    return monkeypatch


# =========================================================
# STORE HOOK — PersistentPublicationStateStore.part_succeeded
# =========================================================


def _persistent_claim_stub(delivery_id):
    def claim(**_kwargs):
        return {
            "claimed": True,
            "source_id": 1,
            "delivery_id": delivery_id,
            "status": "sending",
            "attempt_count": 1,
            "lease_expires_at": None,
        }

    return claim


def test_store_records_index_for_both_platform_parts(
    monkeypatch,
):
    """Telegram and Bale parts record their platform message IDs
    in the index through the store's part-success hook."""
    spy = _IndexSpy()

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        None,
    )  # placeholder replaced below

    # Telegram delivery claim.
    telegram_claim = _persistent_claim_stub(101)
    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        telegram_claim,
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )

    telegram_store = PersistentPublicationStateStore()

    telegram_store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:@tg-channel",
        platform="telegram",
        destination_chat_id="@tg-channel",
    )
    telegram_store.part_succeeded(
        "tg:1:100",
        "telegram:external:@tg-channel",
        "primary",
        message_id=1111,
        destination_chat_id="@tg-channel",
    )

    # Bale delivery claim.
    bale_claim = _persistent_claim_stub(202)
    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        bale_claim,
    )

    bale_store = PersistentPublicationStateStore()

    bale_store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="bale:external:@bale-channel",
        platform="bale",
        destination_chat_id="@bale-channel",
    )
    bale_store.part_succeeded(
        "tg:1:100",
        "bale:external:@bale-channel",
        "primary",
        message_id=2222,
        destination_chat_id="@bale-channel",
    )

    # Both platforms are indexed under the 023 unique key.
    assert (
        "telegram",
        "@tg-channel",
        1111,
    ) in spy.rows_by_key
    assert (
        "bale",
        "@bale-channel",
        2222,
    ) in spy.rows_by_key

    # Primary marking: the single transport message of a part
    # is primary; nothing else is.
    assert spy.primary_rows() == [
        ("telegram", "@tg-channel", 1111),
        ("bale", "@bale-channel", 2222),
    ]


def test_store_index_failure_never_blocks_publication(
    monkeypatch,
):
    """Index persistence failure is swallowed: the part stays
    recorded and no resend can be triggered by it."""

    def broken_index(**_kwargs):
        raise RuntimeError("supabase unavailable")

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        _persistent_claim_stub(101),
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        broken_index,
    )

    store = PersistentPublicationStateStore()

    store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:@tg-channel",
        platform="telegram",
        destination_chat_id="@tg-channel",
    )
    store.part_succeeded(
        "tg:1:100",
        "telegram:external:@tg-channel",
        "primary",
        message_id=3333,
        destination_chat_id="@tg-channel",
    )

    # The part itself remains completed with transport proof.
    assert (
        store.part_completed(
            "tg:1:100",
            "telegram:external:@tg-channel",
            "primary",
        )
        is True
    )


def test_store_multi_message_album_part_indexing(
    monkeypatch,
):
    """Album media groups record every album message ID for the
    primary part; only the designated primary ID is marked."""
    spy = _IndexSpy()

    _DELIVERIES[303] = {
        "platform": "telegram",
        "destination_chat_id": "@album-channel",
    }

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        _persistent_claim_stub(303),
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )

    store = PersistentPublicationStateStore()

    store.begin_persistent_attempt(
        source_key="tg:9:album:77:generation:1",
        target_identity=(
            "telegram:external:@album-channel"
        ),
        platform="telegram",
        destination_chat_id="@album-channel",
    )

    # Album sendMedia returns all album message IDs.
    store.part_succeeded(
        "tg:9:album:77:generation:1",
        "telegram:external:@album-channel",
        "primary",
        message_id=4001,
        message_ids=(4001, 4002, 4003),
        destination_chat_id="@album-channel",
    )

    indexed = sorted(
        key[2]
        for key in spy.rows_by_key
        if key[0] == "telegram"
    )

    assert indexed == [4001, 4002, 4003]

    assert all(
        row["part_key"] == "primary"
        for row in spy.rows_by_key.values()
    )

    # Only the album's first (primary) message is marked.
    assert spy.primary_rows() == [
        ("telegram", "@album-channel", 4001)
    ]

    assert (
        spy.rows_by_key[
            ("telegram", "@album-channel", 4002)
        ]["is_primary"]
        is False
    )

    assert (
        spy.rows_by_key[
            ("telegram", "@album-channel", 4003)
        ]["is_primary"]
        is False
    )


def test_store_repeated_part_recording_is_idempotent(
    monkeypatch,
):
    """Repeating the same part recording yields the same index
    rows (unique-key upsert semantics), never duplicates."""
    spy = _IndexSpy()

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        _persistent_claim_stub(101),
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )

    store = PersistentPublicationStateStore()

    store.begin_persistent_attempt(
        source_key="tg:1:100",
        target_identity="telegram:external:@tg-channel",
        platform="telegram",
        destination_chat_id="@tg-channel",
    )

    for _ in range(3):
        store.part_succeeded(
            "tg:1:100",
            "telegram:external:@tg-channel",
            "primary",
            message_id=1111,
            destination_chat_id="@tg-channel",
        )

    # Three recordings collapse onto one unique-key row.
    assert len(spy.rows_by_key) == 1
    assert spy.primary_rows() == [
        ("telegram", "@tg-channel", 1111)
    ]


# =========================================================
# FLOW — full publication populates the index
# =========================================================


def _flow_env(monkeypatch, sent):
    """Stub senders + persistent database for a full flow run."""

    def fake_send_media_target(
        _chat,
        _api,
        target,
        files,
        _plan,
    ):
        base = (
            7000
            if target.platform == "telegram"
            else 8000
        )

        per_target = (
            100
            if target.platform == "telegram"
            else 200
        )

        ids = tuple(
            base
            + per_target * len(sent)
            + offset
            for offset in range(1, len(files) + 1)
        )

        sent.append(
            (target.platform, list(ids))
        )

        return ExecutorResult(
            success=True,
            primary_message_id=ids[0],
            message_ids=ids,
        )

    def fake_send_text_target(
        _chat,
        _api,
        target,
        plan,
    ):
        base = (
            7100
            if target.platform == "telegram"
            else 8100
        )

        per_target = (
            100
            if target.platform == "telegram"
            else 200
        )

        message_id = base + per_target * len(sent)

        sent.append(
            (
                target.platform,
                plan.get("text", ""),
                message_id,
            )
        )

        return ExecutorResult(
            success=True,
            primary_message_id=message_id,
            message_ids=(message_id,),
        )

    monkeypatch.setattr(
        core.publication_engine,
        "_send_media_target",
        fake_send_media_target,
    )
    monkeypatch.setattr(
        core.publication_engine,
        "_send_text_target",
        fake_send_text_target,
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: SimpleNamespace(
            telegram={
                "media_caption": "cap",
                "messages": ["tg-1", "tg-2"],
                "followup_messages": [],
                "blockquote_messages": [],
            },
            bale={
                "media_caption": "cap",
                "messages": ["bale-1"],
                "followup_messages": [],
                "blockquote_messages": [],
            },
            text={
                "telegram": {"messages": ["tg-1", "tg-2"]},
                "bale": {"messages": ["bale-1"]},
            },
        ),
    )
    monkeypatch.setattr(
        core.publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("base", "brand"),
    )

    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "mark_persistent_publication_delivery_succeeded",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "mark_persistent_publication_source",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "list_persistent_publication_parts",
        lambda **_kwargs: (),
    )
    _patch_db(
        monkeypatch,
        "get_persistent_publication_part",
        lambda **_kwargs: None,
    )
    _patch_db(
        monkeypatch,
        "get_user_by_telegram_id",
        lambda *_args, **_kwargs: None,
    )


def test_full_publication_indexes_telegram_and_bale(
    monkeypatch,
):
    """One multi-destination publication records independent,
    platform-correct index rows for main/followup messages."""
    sent = []
    spy = _IndexSpy()

    _DELIVERIES[9001] = {
        "platform": "telegram",
        "destination_chat_id": "@tg-a",
    }
    _DELIVERIES[9002] = {
        "platform": "telegram",
        "destination_chat_id": "@tg-b",
    }
    _DELIVERIES[9003] = {
        "platform": "bale",
        "destination_chat_id": "@bale-a",
    }

    claims = iter(
        [
            _persistent_claim_stub(9001)(),
            _persistent_claim_stub(9002)(),
            _persistent_claim_stub(9003)(),
        ]
    )

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        lambda **_kwargs: next(claims),
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )

    _flow_env(monkeypatch, sent)

    targets = [
        PublicationTarget(
            key="ws:1:d:1",
            kind="workspace",
            platform="telegram",
            external_id="@tg-a",
            workspace_id=1,
            destination_id=1,
        ),
        PublicationTarget(
            key="ws:1:d:2",
            kind="workspace",
            platform="telegram",
            external_id="@tg-b",
            workspace_id=1,
            destination_id=2,
        ),
        PublicationTarget(
            key="ws:1:d:3",
            kind="workspace",
            platform="bale",
            external_id="@bale-a",
            workspace_id=1,
            destination_id=3,
        ),
    ]

    monkeypatch.setattr(
        core.publication_engine,
        "_state_store",
        PersistentPublicationStateStore(
            lease_owner="b11-test",
        ),
    )

    core.publication_engine.reset_local_idempotency_state()

    result = core.publication_engine.publish_prepared_content(
        7,
        "https://api.example/botT",
        PreparedContent(
            main_text="سلام",
            files=[],
            source_key="b11:flow:1",
        ),
        targets=targets,
    )

    assert result["ok"] is True

    # Text plan: telegram primary + followup; bale primary only.
    assert len(sent) == 5

    platforms_indexed = {
        key[0] for key in spy.rows_by_key
    }

    assert platforms_indexed == {
        "telegram",
        "bale",
    }

    # Independent mappings per destination chat.
    assert (
        "telegram",
        "@tg-a",
    ) in {
        (key[0], key[1])
        for key in spy.rows_by_key
    }
    assert (
        "telegram",
        "@tg-b",
    ) in {
        (key[0], key[1])
        for key in spy.rows_by_key
    }
    assert (
        "bale",
        "@bale-a",
    ) in {
        (key[0], key[1])
        for key in spy.rows_by_key
    }

    # Exactly one primary per delivery part set: the primary
    # part message of each destination.
    tg_primaries = [
        key
        for key in spy.primary_rows()
        if key[0] == "telegram"
    ]
    bale_primaries = [
        key
        for key in spy.primary_rows()
        if key[0] == "bale"
    ]

    assert len(tg_primaries) == 2
    assert len(bale_primaries) == 1

    # Followups are indexed with their own part_key and are
    # never marked primary.
    followup_rows = [
        row
        for row in spy.rows_by_key.values()
        if row["part_key"].startswith("followup")
    ]

    assert followup_rows
    assert all(
        row["is_primary"] is False
        for row in followup_rows
    )


def test_full_publication_album_indexes_all_media_ids(
    monkeypatch,
):
    """Album publications record every album message ID under the
    primary part key with one deterministic primary."""
    sent = []
    spy = _IndexSpy()

    _DELIVERIES[9101] = {
        "platform": "telegram",
        "destination_chat_id": "@album-tg",
    }
    _DELIVERIES[9102] = {
        "platform": "bale",
        "destination_chat_id": "@album-bale",
    }

    claims = iter(
        [
            _persistent_claim_stub(9101)(),
            _persistent_claim_stub(9102)(),
        ]
    )

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        lambda **_kwargs: next(claims),
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )

    _flow_env(monkeypatch, sent)

    targets = [
        PublicationTarget(
            key="ws:2:d:1",
            kind="workspace",
            platform="telegram",
            external_id="@album-tg",
            workspace_id=2,
            destination_id=1,
        ),
        PublicationTarget(
            key="ws:2:d:2",
            kind="workspace",
            platform="bale",
            external_id="@album-bale",
            workspace_id=2,
            destination_id=2,
        ),
    ]

    monkeypatch.setattr(
        core.publication_engine,
        "_state_store",
        PersistentPublicationStateStore(
            lease_owner="b11-test",
        ),
    )

    core.publication_engine.reset_local_idempotency_state()

    result = core.publication_engine.publish_prepared_content(
        7,
        "https://api.example/botT",
        PreparedContent(
            main_text="آلبوم",
            files=[
                {"type": "photo", "file_id": "f1"},
                {"type": "photo", "file_id": "f2"},
                {"type": "photo", "file_id": "f3"},
            ],
            source_key="b11:album:1",
        ),
        targets=targets,
    )

    assert result["ok"] is True

    tg_ids = sorted(
        key[2]
        for key in spy.rows_by_key
        if key[0] == "telegram"
    )
    bale_ids = sorted(
        key[2]
        for key in spy.rows_by_key
        if key[0] == "bale"
    )

    assert len(tg_ids) == 3
    assert len(bale_ids) == 3

    # Deterministic primary: first album message per platform.
    tg_primary = [
        key for key in spy.primary_rows()
        if key[0] == "telegram"
    ]
    bale_primary = [
        key for key in spy.primary_rows()
        if key[0] == "bale"
    ]

    assert len(tg_primary) == 1
    assert len(bale_primary) == 1
    assert tg_primary[0][2] == tg_ids[0]
    assert bale_primary[0][2] == bale_ids[0]

    # All album rows share the primary part key.
    assert all(
        row["part_key"] == "primary"
        for row in spy.rows_by_key.values()
    )


def test_publication_not_resent_for_index_recording(
    monkeypatch,
):
    """A second publication of the same source with the same store
    (service restart equivalent in-process) does not resend any
    completed part because of index recording."""
    sent = []
    spy = _IndexSpy()

    _DELIVERIES[9201] = {
        "platform": "telegram",
        "destination_chat_id": "@tg-a",
    }

    claim_results = []

    def claim(**_kwargs):
        if not claim_results:
            claim_results.append(True)

            return {
                "claimed": True,
                "source_id": 1,
                "delivery_id": 9201,
                "status": "sending",
                "attempt_count": 1,
                "lease_expires_at": None,
            }

        # Re-publication: delivery already succeeded with proof.
        return {
            "claimed": False,
            "source_id": 1,
            "delivery_id": 9201,
            "status": "succeeded",
            "attempt_count": 1,
            "lease_expires_at": None,
        }

    _patch_db(
        monkeypatch,
        "claim_persistent_publication_delivery",
        claim,
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_part_success",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "record_persistent_publication_message_index",
        spy.record,
    )
    _patch_db(
        monkeypatch,
        "mark_persistent_publication_delivery_succeeded",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "mark_persistent_publication_source",
        lambda **_kwargs: {},
    )

    monkeypatch.setattr(
        core.publication_engine,
        "_send_media_target",
        lambda *_args: sent.append("media")
        or ExecutorResult(success=True),
    )
    monkeypatch.setattr(
        core.publication_engine,
        "_send_text_target",
        lambda *_args: sent.append("text")
        or ExecutorResult(
            success=True,
            primary_message_id=9901,
            message_ids=(9901,),
        ),
    )
    _patch_db(
        monkeypatch,
        "list_persistent_publication_parts",
        lambda **_kwargs: (
            {
                "part_key": "primary",
                "status": "succeeded",
                "message_id": 9901,
                "message_ids": None,
                "destination_chat_id": "@tg-a",
            },
        ),
    )
    _patch_db(
        monkeypatch,
        "get_user_by_telegram_id",
        lambda *_args, **_kwargs: None,
    )
    _patch_db(
        monkeypatch,
        "record_duplicate_news_history",
        lambda **_kwargs: {},
    )
    _patch_db(
        monkeypatch,
        "get_persistent_publication_part",
        lambda **_kwargs: None,
    )
    _patch_db(
        monkeypatch,
        "mark_persistent_publication_delivery_failed",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_kwargs: SimpleNamespace(
            telegram={"messages": ["tg-1"]},
            bale={"messages": ["bale-1"]},
            text={
                "telegram": {"messages": ["tg-1"]},
                "bale": {"messages": ["bale-1"]},
            },
        ),
    )
    monkeypatch.setattr(
        core.publication_engine,
        "_target_content_and_branding",
        lambda *_args: ("base", "brand"),
    )

    targets = [
        PublicationTarget(
            key="ws:3:d:1",
            kind="workspace",
            platform="telegram",
            external_id="@tg-a",
            workspace_id=3,
            destination_id=1,
        ),
    ]

    prepared = PreparedContent(
        main_text="سلام",
        files=[],
        source_key="b11:noresend:1",
    )

    monkeypatch.setattr(
        core.publication_engine,
        "_state_store",
        PersistentPublicationStateStore(
            lease_owner="b11-test",
        ),
    )

    core.publication_engine.reset_local_idempotency_state()

    first = core.publication_engine.publish_prepared_content(
        7,
        "api",
        prepared,
        targets,
    )
    sends_after_first = len(sent)

    second = core.publication_engine.publish_prepared_content(
        7,
        "api",
        prepared,
        targets,
    )

    assert first["ok"] is True
    assert second["ok"] is True

    # No additional sends were triggered by index recording.
    assert len(sent) == sends_after_first


# =========================================================
# LEGACY COMPATIBILITY
# =========================================================


def test_legacy_message_link_fallback_remains_valid(
    monkeypatch,
):
    """Without service Supabase index rows, the 008 legacy link
    fallback still resolves Bale sync targets."""
    db = _REAL_DATABASE

    monkeypatch.setattr(
        db,
        "service_supabase",
        None,
        raising=False,
    )
    _patch_real_db(
        monkeypatch,
        "get_publication_message_link",
        lambda telegram_chat_id, telegram_message_id: {
            "telegram_chat_id": "-100111",
            "telegram_message_id": 42,
            "bale_chat_id": "-100222",
            "bale_message_id": 77,
        },
    )

    mapping = (
        db.get_publication_sync_targets_for_telegram_message(
            "-100111",
            42,
        )
    )

    assert mapping is not None
    assert mapping["telegram"] == {
        "chat_id": "-100111",
        "message_ids": (42,),
    }

    bale_deliveries = mapping["bale_deliveries"]

    assert len(bale_deliveries) == 1
    assert (
        bale_deliveries[0]["chat_id"]
        == "-100222"
    )
    assert (
        bale_deliveries[0]["message_ids"]
        == (77,)
    )
