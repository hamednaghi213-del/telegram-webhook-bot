import sys
from copy import deepcopy
from types import ModuleType

import pytest

from core.canonical_media import (
    canonical_destination_key,
    canonical_target_is_ready,
    group_access_allows,
    media_access_allows,
    resolve_media_branding,
    visible_group_ids,
)
from core.canonical_media_backfill import apply_backfill_plan, build_backfill_plan
from core.content_model import PreparedContent, PublicationTarget
from core.publication_engine import _target_content_and_branding
from core.target_resolver import resolve_publication_targets
from core.workspace_destination_moves import move_destinations
from core.workspace_publisher import prepare_workspace_display_rows


MEDIA = {
    "id": 20,
    "identity_key": "donya24-en",
    "media_name": "Donya24_En",
    "hashtag": "#دنیا_۲۴_نیوز_انگلیسی",
    "channel_tag": "@Donya24News_En",
    "publication_icons": ["❇️", "🔹"],
    "icons_enabled": True,
    "publication_profile": {"title_icon": "❇️", "body_icons": ["🔹"]},
    "status": "active",
}


def test_workspace_name_never_changes_media_branding_or_profile():
    before = resolve_media_branding(MEDIA)
    after = resolve_media_branding(MEDIA)
    assert before == after
    assert "سیاسی" not in before.values()
    assert before["hashtag"] == "#دنیا_۲۴_نیوز_انگلیسی"
    assert before["publication_icons"] == ["❇️", "🔹"]
    assert before["publication_profile"] == MEDIA["publication_profile"]


def test_destination_override_is_explicit_and_platform_scoped():
    result = resolve_media_branding(MEDIA, {
        "hashtag": "#english",
        "publication_icons": ["🟦"],
        "icons_enabled": True,
        "publication_profile": None,
    })
    assert result["hashtag"] == "#english"
    assert result["channel_tag"] == MEDIA["channel_tag"]
    assert result["publication_icons"] == ["🟦"]
    assert result["publication_profile"] == MEDIA["publication_profile"]


def test_canonical_branding_survives_move_to_political_group():
    target = PublicationTarget(
        key="workspace:6:destination:3", kind="workspace", platform="telegram",
        external_id="@Donya24News_En", workspace_id=6, destination_id=3,
        destination={
            "_canonical_media": True,
            "media_identity": MEDIA,
            "destination_branding": {},
        },
    )
    _content, branding = _target_content_and_branding(
        1, target, PreparedContent(main_text="خبر", neutral_text="خبر")
    )
    assert branding == "#دنیا_۲۴_نیوز_انگلیسی\n@Donya24News_En"
    assert "سیاسی" not in branding


class MoveDb:
    def __init__(self):
        self.destination = {
            "id": 3, "workspace_id": 3, "media_identity_id": 20,
            "platform": "telegram", "external_id": "@Donya24News_En",
            "status": "active", "media_identity": deepcopy(MEDIA),
            "media_member": {"role": "owner", "status": "active"},
        }
        self.associations = {3: 3}

    def canonical_media_enabled(self): return True
    def list_user_workspace_memberships(self, _user):
        return [
            {"id": 3, "name": "Donya24_En", "status": "active", "member_role": "owner"},
            {"id": 6, "name": "سیاسی", "status": "active", "member_role": "owner"},
        ]
    def list_canonical_publication_destinations(self, _user, workspace_ids):
        if self.associations[3] not in workspace_ids:
            return []
        return [{**deepcopy(self.destination), "workspace_id": self.associations[3]}]
    def move_canonical_destination_associations(self, ids, target):
        assert ids == [3]
        self.associations[3] = target
        return [{"workspace_id": target, "destination_id": 3, "status": "active"}]


def test_move_changes_association_only_and_preserves_destination_identity():
    db = MoveDb()
    before = deepcopy(db.destination)
    moved = move_destinations(db, 7, 6, [3])
    assert db.associations == {3: 6}
    assert moved[0]["id"] == before["id"]
    assert moved[0]["media_identity_id"] == before["media_identity_id"]
    assert moved[0]["media_identity"] == before["media_identity"]


def test_empty_group_visibility_is_association_based_and_reversible():
    rows = [{"workspace_id": 3, "association_status": "active", "status": "inactive"}]
    assert visible_group_ids(rows) == {3}


def test_canonical_workspace_ui_uses_group_name_and_hides_only_no_membership(monkeypatch):
    database = ModuleType("core.database")
    database.list_workspace_destinations = lambda workspace_id: (
        [{"id": 3, "status": "inactive"}] if workspace_id == 6 else []
    )
    monkeypatch.setitem(sys.modules, "core.database", database)
    rows = prepare_workspace_display_rows(
        [{"id": 3, "name": "Donya24_En"}, {"id": 6, "name": "سیاسی"}],
        lambda _workspace: [],
        lambda _workspace: {"media_name": "نباید نمایش داده شود"},
        canonical_group_mode=True,
    )
    assert [(row["id"], row["display_label"], row["destination_count"]) for row in rows] == [
        (6, "سیاسی", 1)
    ]
    rows.clear()
    assert visible_group_ids(rows) == set()
    rows.append({"workspace_id": 3, "association_status": "active", "status": "active"})
    assert visible_group_ids(rows) == {3}


def test_physical_identity_is_platform_scoped_and_normalized():
    assert canonical_destination_key("bale", "@donya24_news") == ("bale", "donya24_news")
    assert canonical_destination_key("telegram", "@same") != canonical_destination_key("bale", "same")


def test_group_and_media_permissions_are_both_required():
    assert group_access_allows({"member_role": "publisher", "status": "active"})
    assert media_access_allows({"role": "publisher", "status": "active"})
    assert not group_access_allows(None)
    assert not media_access_allows(None)
    assert not media_access_allows({"role": "writer", "status": "active"})


def _install_canonical_database(monkeypatch, *, group_role="owner", media_role="owner", selected=True, verified=True):
    database = ModuleType("core.database")
    database.canonical_media_enabled = lambda: True
    database.get_tenant = lambda _chat: None
    database.get_user_by_telegram_id = lambda _chat: {"id": 7}
    database.get_active_workspace_preference = lambda _user: {"legacy_selected": False}
    database.list_selected_workspace_ids = lambda _user: [6] if selected else []
    database.list_user_workspace_memberships = lambda _user: [
        {"id": 6, "name": "سیاسی", "member_role": group_role, "status": "active"}
    ]
    database.list_canonical_publication_destinations = lambda _user, ids: ([{
        "id": 3, "workspace_id": 6, "media_identity_id": 20,
        "platform": "telegram", "external_id": "@Donya24News_En",
        "status": "active", "association_status": "active",
        "verification": {"verified": verified}, "media_status": "active",
        "media_member": {"role": media_role, "status": "active"},
        "media_identity": MEDIA, "destination_branding": {},
    }] if ids else [])
    monkeypatch.setitem(sys.modules, "core.database", database)
    return database


def test_resolver_does_not_require_workspace_branding_setup(monkeypatch):
    _install_canonical_database(monkeypatch)
    targets, errors = resolve_publication_targets(100)
    assert errors == []
    assert [target.destination_id for target in targets] == [3]


def test_legacy_and_ready_canonical_destination_do_not_double_publish(monkeypatch):
    database = _install_canonical_database(monkeypatch)
    database.get_tenant = lambda _chat: {
        "id": 1, "telegram_channel": "@Donya24News_En", "bale_channel": "",
    }
    database.get_active_workspace_preference = lambda _user: {"legacy_selected": True}
    targets, _errors = resolve_publication_targets(100)
    telegram = [target for target in targets if target.platform == "telegram"]
    assert len(telegram) == 1
    assert telegram[0].kind == "workspace"


@pytest.mark.parametrize("group_role,media_role,selected", [
    ("writer", "owner", True),
    ("owner", "writer", True),
    ("owner", "owner", False),
])
def test_resolver_requires_group_access_media_access_and_selection(
    monkeypatch, group_role, media_role, selected,
):
    _install_canonical_database(
        monkeypatch, group_role=group_role, media_role=media_role, selected=selected
    )
    targets, _errors = resolve_publication_targets(100)
    assert targets == []


def test_destination_readiness_requires_active_verified_media_not_group_setup():
    row = {
        "association_status": "active", "status": "active",
        "media_status": "active", "verification": {"verified": True},
    }
    assert canonical_target_is_ready(row)
    row["verification"] = {"verified": False}
    assert not canonical_target_is_ready(row)


def _mapping(**overrides):
    row = {
        "tenant_id": 1, "user_id": 3, "workspace_id": 6,
        "media_key": "donya24", "media_name": "Donya24News",
        "platform": "bale", "external_id": "@donya24_news",
        "hashtag": "#دنیا_۲۴_نیوز", "channel_tag": "@Donya24News",
        "access_verified": True, "media_role": "owner",
    }
    row.update(overrides)
    return row


def test_shared_bale_destination_has_one_row_and_multiple_verified_members():
    plan = build_backfill_plan({}, [
        _mapping(user_id=3, media_role="owner"),
        _mapping(tenant_id=2, user_id=2, media_role="publisher"),
    ])
    assert plan["safe_to_apply"]
    assert len(plan["inserts"]["destinations"]) == 1
    assert {row["user_id"] for row in plan["inserts"]["media_members"]} == {2, 3}


def test_backfill_rejects_unverified_access_and_emits_no_writes():
    plan = build_backfill_plan({}, [_mapping(access_verified=False)])
    assert not plan["safe_to_apply"]
    assert plan["conflicts"][0]["type"] == "unverified_access"
    assert all(not rows for rows in plan["inserts"].values())


def test_backfill_rejects_one_physical_destination_mapped_to_two_media():
    plan = build_backfill_plan({}, [
        _mapping(media_key="first"), _mapping(user_id=2, media_key="second")
    ])
    assert not plan["safe_to_apply"]
    assert any(row["type"] == "physical_destination_media_conflict" for row in plan["conflicts"])


def test_backfill_rejects_one_physical_destination_in_two_active_groups():
    plan = build_backfill_plan({}, [
        _mapping(workspace_id=6), _mapping(user_id=2, workspace_id=5)
    ])
    assert not plan["safe_to_apply"]
    assert any(row["type"] == "physical_destination_group_conflict" for row in plan["conflicts"])


def test_repeated_backfill_is_idempotent():
    snapshot = {
        "media_identities": [{"id": 20, "identity_key": "donya24"}],
        "destinations": [{
            "id": 30, "media_identity_id": 20, "platform": "bale",
            "external_id": "donya24_news", "status": "active",
        }],
        "media_members": [{
            "media_identity_id": 20, "user_id": 3, "role": "owner", "status": "active",
        }],
        "workspace_destinations": [{
            "workspace_id": 6, "destination_id": 30, "status": "active",
        }],
    }
    plan = build_backfill_plan(snapshot, [_mapping()])
    assert plan["safe_to_apply"]
    assert all(not rows for rows in plan["inserts"].values())
    assert all(not rows for rows in plan["updates"].values())
    assert plan["deletes"] == []
    assert "message_links" not in plan["updates"]


class FailingTransaction:
    def __init__(self): self.events = []
    def begin(self): self.events.append("begin")
    def apply(self, _plan): self.events.append("apply"); raise RuntimeError("fail")
    def verify(self, _plan, _result): self.events.append("verify")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")


def test_backfill_apply_rolls_back_on_halfway_failure():
    transaction = FailingTransaction()
    with pytest.raises(RuntimeError):
        apply_backfill_plan(build_backfill_plan({}, [_mapping()]), transaction)
    assert transaction.events == ["begin", "apply", "rollback"]
