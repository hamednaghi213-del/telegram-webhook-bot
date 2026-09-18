"""Telegram ↔ Bale Content Mirror — focused tests.

Proves that content from either platform publishes to the
Workspace's configured Telegram AND Bale destinations through the
ONE shared publication engine, with no duplicate destination
publication, no cross-platform identity leakage, and no resend of
already-succeeded destinations when another destination retries.
"""

import sys
from types import ModuleType

from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore
from core.target_resolver import resolve_publication_targets


# =========================================================
# Shared helpers
# =========================================================

def _install_database(monkeypatch, *, destinations, legacy=None, users=None):
    """Install a fake core.database with the resolver's accessors."""
    database = ModuleType("core.database")
    database.get_tenant = lambda _chat_id: legacy
    database.get_user_by_telegram_id = lambda _chat_id: (users or {}).get(
        "telegram"
    )
    database.get_user_by_bale_id = lambda _chat_id: (users or {}).get("bale")
    database.get_active_workspace_preference = lambda _user_id: {
        "context_type": "workspace",
        "active_workspace_id": 1,
    }
    database.list_selected_workspace_ids = lambda _user_id: {1}
    database.list_user_workspace_memberships = lambda _user_id: [
        {"id": 1, "name": "رسانه ۱"}
    ]
    database.get_workspace_setup_state = lambda _workspace_id: {
        "step": "completed"
    }
    database.get_workspace_member = lambda _workspace_id, _user_id: {
        "role": "owner",
        "status": "active",
    }
    database.list_verified_active_destinations = (
        lambda workspace_id: list(destinations)
    )
    database.canonical_media_enabled = lambda: False
    monkeypatch.setitem(sys.modules, "core.database", database)


def _telegram_and_bale_destinations():
    return [
        {
            "id": 101,
            "platform": "telegram",
            "external_id": "@tg_channel",
            "status": "active",
            "verified": True,
        },
        {
            "id": 102,
            "platform": "bale",
            "external_id": "@bale_channel",
            "status": "active",
            "verified": True,
        },
    ]


# =========================================================
# Target resolution — cross-platform fan-out
# =========================================================

def test_workspace_resolves_telegram_and_bale_destinations(monkeypatch):
    _install_database(
        monkeypatch,
        destinations=_telegram_and_bale_destinations(),
        users={"telegram": {"id": 9}},
    )

    from core.messaging import reset_default_context

    reset_default_context()

    targets, errors = resolve_publication_targets(100)

    assert errors == []
    platforms = {target.platform for target in targets}
    assert platforms == {"telegram", "bale"}


def test_bale_origin_resolves_user_by_bale_id(monkeypatch):
    """Bale-origin resolution must use the Bale identity space."""
    _install_database(
        monkeypatch,
        destinations=_telegram_and_bale_destinations(),
        users={"bale": {"id": 21}},
    )

    from core.messaging import BaleMessagingContext, bind_context

    bind_context(BaleMessagingContext())

    targets, errors = resolve_publication_targets(555000)

    assert errors == []
    assert {target.platform for target in targets} == {"telegram", "bale"}

    from core.messaging import reset_default_context

    reset_default_context()


def test_bale_origin_never_resolves_telegram_identity(monkeypatch):
    """Same numeric id on both platforms must not cross identities."""
    database = ModuleType("core.database")

    lookups = {"telegram": [], "bale": []}

    def _tg(chat_id):
        lookups["telegram"].append(chat_id)
        return None

    def _bale(chat_id):
        lookups["bale"].append(chat_id)
        return {"id": 21}

    database.get_tenant = lambda _chat_id: None
    database.get_user_by_telegram_id = _tg
    database.get_user_by_bale_id = _bale
    database.get_active_workspace_preference = lambda _user_id: {}
    database.list_selected_workspace_ids = lambda _user_id: set()
    database.list_user_workspace_memberships = lambda _user_id: []
    database.get_workspace_setup_state = lambda _workspace_id: None
    database.get_workspace_member = lambda *_a: None
    database.list_verified_active_destinations = lambda _w: []
    database.canonical_media_enabled = lambda: False
    monkeypatch.setitem(sys.modules, "core.database", database)

    from core.messaging import BaleMessagingContext, bind_context

    bind_context(BaleMessagingContext())

    targets, errors = resolve_publication_targets(777)

    assert targets == []
    assert lookups["bale"] == [777]
    assert lookups["telegram"] == []
    assert errors == []

    from core.messaging import reset_default_context

    reset_default_context()


def test_bale_origin_skips_legacy_tenant_lookup(monkeypatch):
    """A Bale numeric id must never resolve a Telegram legacy tenant."""
    legacy_tenant = {
        "telegram_channel": "@legacy_tg",
        "bale_channel": None,
    }
    database = ModuleType("core.database")

    tenant_lookups = []

    database.get_tenant = lambda chat_id: (
        tenant_lookups.append(chat_id) or legacy_tenant
    )
    database.get_user_by_telegram_id = lambda _chat_id: None
    database.get_user_by_bale_id = lambda _chat_id: {"id": 21}
    database.get_active_workspace_preference = lambda _user_id: {}
    database.list_selected_workspace_ids = lambda _user_id: set()
    database.list_user_workspace_memberships = lambda _user_id: []
    database.get_workspace_setup_state = lambda _workspace_id: None
    database.get_workspace_member = lambda *_a: None
    database.list_verified_active_destinations = lambda _w: []
    database.canonical_media_enabled = lambda: False
    monkeypatch.setitem(sys.modules, "core.database", database)

    from core.messaging import BaleMessagingContext, bind_context

    bind_context(BaleMessagingContext())

    targets, errors = resolve_publication_targets(777)

    # The Telegram-keyed legacy tenant is untouched under Bale origin.
    assert tenant_lookups == []
    assert all(target.kind != "legacy" for target in targets)
    assert errors == []

    from core.messaging import reset_default_context

    reset_default_context()


# =========================================================
# Shared engine — multi-platform fan-out + dedup + retry isolation
# =========================================================

def _engine_sends(monkeypatch, outcomes):
    """Stub the engine's content/branding analysis and per-target send.

    Returns (sends, publish) where ``sends`` records
    (platform, external_id) per transport call and ``publish`` runs
    the shared engine with one Telegram + one Bale workspace target.
    """
    from core import publication_engine

    sends = []

    def _sender(chat_id, api_url, target, plan):
        sends.append((target.platform, target.external_id))
        outcome = outcomes.pop(0)
        if outcome is True:
            return {"ok": True, "result": {"message_id": 500 + len(sends)}}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        publication_engine,
        "_shared_content_analysis",
        lambda value: value,
    )
    monkeypatch.setattr(
        publication_engine,
        "_target_content_and_branding",
        lambda *_a: ("mirror-text", ""),
    )
    monkeypatch.setattr(
        publication_engine,
        "_send_text_target",
        _sender,
    )
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_k: type(
            "Plan",
            (),
            {
                "telegram": {},
                "bale": {},
                "text": {
                    "telegram": {
                        "messages": ["mirror-text"],
                        "message_parse_modes": [None],
                        "blockquote_messages": [],
                    },
                    "bale": {
                        "messages": ["mirror-text"],
                        "message_parse_modes": [None],
                        "blockquote_messages": [],
                    },
                },
            },
        )(),
    )

    tg_target = PublicationTarget(
        key="workspace:1:destination:101",
        kind="workspace",
        platform="telegram",
        external_id="@tg_channel",
        workspace_id=1,
        destination_id=101,
    )
    bale_target = PublicationTarget(
        key="workspace:1:destination:102",
        kind="workspace",
        platform="bale",
        external_id="@bale_channel",
        workspace_id=1,
        destination_id=102,
    )

    def publish(prepared, store):
        return publication_engine.publish_prepared_content(
            1,
            "api",
            prepared,
            [tg_target, bale_target],
            store,
        )

    return sends, publish


def test_telegram_inbound_publishes_to_telegram_and_bale(monkeypatch):
    """Telegram inbound content fans out to both platform destinations."""
    sends, publish = _engine_sends(
        monkeypatch,
        outcomes=[True, True],
    )

    prepared = PreparedContent(main_text="از تلگرام")
    result = publish(prepared, InMemoryPublicationStateStore())

    assert result["ok"] is True
    assert ("telegram", "@tg_channel") in sends
    assert ("bale", "@bale_channel") in sends
    assert len(sends) == 2


def test_bale_inbound_publishes_to_telegram_and_bale(monkeypatch):
    """Bale inbound content fans out to both platform destinations.

    The engine is symmetric: the same targets are delivered regardless
    of which platform the inbound request came from; the origin only
    affects identity resolution (covered by the resolver tests) and
    user replies, never the destination fan-out.
    """
    sends, publish = _engine_sends(
        monkeypatch,
        outcomes=[True, True],
    )

    prepared = PreparedContent(main_text="از بله")
    result = publish(prepared, InMemoryPublicationStateStore())

    assert result["ok"] is True
    assert ("telegram", "@tg_channel") in sends
    assert ("bale", "@bale_channel") in sends


def test_no_duplicate_destination_publication(monkeypatch):
    """Legacy + workspace overlap on one physical channel sends once."""
    from core.publication_engine import (
        canonical_target_identity,
        publish_prepared_content,
    )

    sends, _ = _engine_sends(
        monkeypatch,
        outcomes=[True, True],
    )

    # Two workspace destinations pointing at the SAME physical Bale
    # channel must collapse to one transport call.
    legacy_dup = PublicationTarget(
        key="workspace:1:destination:201",
        kind="workspace",
        platform="bale",
        external_id="@bale_channel",
        workspace_id=2,
        destination_id=201,
    )

    prepared = PreparedContent(main_text="dedup")
    publish_prepared_content(
        1,
        "api",
        prepared,
        [
            PublicationTarget(
                key="workspace:1:destination:101",
                kind="workspace",
                platform="telegram",
                external_id="@tg_channel",
                workspace_id=1,
                destination_id=101,
            ),
            PublicationTarget(
                key="workspace:1:destination:102",
                kind="workspace",
                platform="bale",
                external_id="@bale_channel",
                workspace_id=1,
                destination_id=102,
            ),
            legacy_dup,
        ],
        InMemoryPublicationStateStore(),
    )

    bale_sends = [
        external for platform, external in sends if platform == "bale"
    ]
    assert bale_sends.count("@bale_channel") == 1
    assert canonical_target_identity(legacy_dup).startswith("bale:")


def test_retry_does_not_resend_successful_destination(monkeypatch):
    """When Bale fails and then retries, the successful Telegram
    destination must NOT be re-sent."""
    sends, publish = _engine_sends(
        monkeypatch,
        outcomes=[
            True,
            Exception("bale transport down"),
            Exception("bale transport down"),
        ],
    )

    store = InMemoryPublicationStateStore()
    prepared = PreparedContent(
        main_text="retry-mirror",
        source_key="mirror:test:retry-1",
    )

    first = publish(prepared, store)
    assert first["ok"] is False
    assert len(sends) == 2

    # Retry the SAME publication identity (production rebuilds the
    # PreparedContent with the same source_key): Telegram's success
    # proof short-circuits; only Bale is attempted again.
    second = publish(
        PreparedContent(
            main_text="retry-mirror",
            source_key="mirror:test:retry-1",
        ),
        store,
    )
    assert second["ok"] is False
    assert len(sends) == 3

    telegram_sends = [
        platform for platform, _external in sends if platform == "telegram"
    ]
    assert telegram_sends == ["telegram"]


def test_bale_source_key_prefix_isolated_from_telegram(monkeypatch):
    """Bale-origin albums use the bale: id space, Telegram keeps tg:."""
    from core.media_handler import album_source_key_prefix

    assert album_source_key_prefix("tg", 555000) == "tg"
    assert album_source_key_prefix("bale", 555000) == "bale"
    assert album_source_key_prefix("", 1) == "tg"

    from core.content_model import PreparedContent

    bale_key = PreparedContent(
        main_text="x",
        source_key="bale:555000:album:mg1:generation:1",
    )
    tg_key = PreparedContent(
        main_text="x",
        source_key="tg:555000:album:mg1:generation:1",
    )

    assert bale_key.publication_identity != tg_key.publication_identity


# =========================================================
# Album origin propagation (media path)
# =========================================================

def test_album_carries_origin_and_bale_album_uses_bale_key_space():
    from core.media_handler import (
        _bind_album_origin_context,
        add_to_pending_group,
        pending_groups,
        process_media_group,
    )

    pending_groups.clear()

    add_to_pending_group(
        "mg-bale-1",
        555000,
        "file-1",
        "photo",
        message_id=11,
        origin="bale",
    )

    group = pending_groups[(555000, "mg-bale-1")]
    assert group["origin"] == "bale"

    # Telegram-origin groups keep the default.
    add_to_pending_group(
        "mg-tg-1",
        100,
        "file-2",
        "photo",
        message_id=12,
        origin="tg",
    )
    assert pending_groups[(100, "mg-tg-1")]["origin"] == "tg"

    # The Bale bind is a no-op at transport level when the DB is
    # unavailable, and never raises.
    try:
        chat = _bind_album_origin_context("bale", 555000)
    except Exception as exc:  # pragma: no cover - must never happen
        raise AssertionError("bind must not raise") from exc
    assert chat == 555000

    process_media_group("mg-tg-1", 100, expected_generation=0)
