from copy import deepcopy

import pytest

from core.legacy_workspace_compat import (
    claim_legacy_destinations,
    legacy_destination_specs,
    legacy_is_fully_canonical,
    list_legacy_move_candidates,
)
from core.workspace_publisher import visible_workspace_rows


class LegacyDb:
    def __init__(self):
        self.user = {"id": 3, "telegram_user_id": 101647751}
        self.tenant = {
            "id": 1,
            "user_id": 101647751,
            "telegram_channel": "@Donya24News",
            "bale_channel": "@donya24_news",
            "channel_tag": "@Donya24News",
        }
        self.memberships = [
            {"id": 3, "name": "old", "status": "active", "member_role": "owner"},
            {"id": 6, "name": "سیاسی", "status": "active", "member_role": "owner"},
        ]
        self.destinations = []
        self.selected = []
        self.legacy_selected = True
        self.members = deepcopy(self.memberships)
        self.branding = {3: {"media_name": "English"}, 6: {"media_name": "سیاسی"}}
        self.history = [{"tenant_id": 1, "message_id": 9}]
        self.next_id = 100
        self.other_tenants = []

    def get_user_by_id(self, user_id):
        return deepcopy(self.user) if user_id == self.user["id"] else None

    def get_tenant(self, telegram_user_id):
        return deepcopy(self.tenant) if telegram_user_id == self.user["telegram_user_id"] else None

    def get_all_tenants(self):
        return deepcopy([self.tenant, *self.other_tenants])

    def list_user_workspace_memberships(self, user_id):
        return deepcopy(self.memberships) if user_id == self.user["id"] else []

    def list_publication_destinations_for_workspaces(self, workspace_ids):
        return deepcopy([row for row in self.destinations if row["workspace_id"] in set(workspace_ids) and row["status"] != "removed"])

    def list_workspace_destinations(self, workspace_id):
        return deepcopy([row for row in self.destinations if row["workspace_id"] == workspace_id and row["status"] != "removed"])

    def create_publication_destination(self, **payload):
        self.next_id += 1
        row = {"id": self.next_id, **payload}
        self.destinations.append(row)
        return deepcopy(row)

    def move_publication_destinations(self, destination_ids, target_workspace_id):
        moved = []
        for row in self.destinations:
            if row["id"] in destination_ids:
                row["workspace_id"] = target_workspace_id
                moved.append(deepcopy(row))
        return moved

    def select_workspace(self, user_id, workspace_id):
        if workspace_id not in self.selected:
            self.selected.append(workspace_id)

    def set_legacy_workspace_selected(self, user_id, selected):
        self.legacy_selected = selected


def test_legacy_telegram_and_bale_are_independent_move_candidates():
    db = LegacyDb()
    rows = list_legacy_move_candidates(db, 3, 6)
    assert [(row["platform"], row["move_key"]) for row in rows] == [("telegram", "l1t"), ("bale", "l1b")]


def test_placeholder_legacy_channel_is_not_a_destination():
    tenant = {"id": 2, "telegram_channel": "@channel", "bale_channel": ""}
    assert legacy_destination_specs(tenant) == []


def test_unauthorized_legacy_destination_is_hidden():
    db = LegacyDb()
    db.memberships[1]["member_role"] = "viewer"
    with pytest.raises(ValueError):
        list_legacy_move_candidates(db, 3, 6)


def test_cross_owner_legacy_identity_is_hidden_and_claim_rejected_safely():
    db = LegacyDb()
    db.other_tenants.append({
        "id": 2,
        "user_id": 65341109,
        "telegram_channel": "@other",
        "bale_channel": "donya24_news",
    })
    rows = list_legacy_move_candidates(db, 3, 6)
    assert [(row["platform"], row["external_id"]) for row in rows] == [
        ("telegram", "@Donya24News")
    ]
    with pytest.raises(ValueError, match="مبهم"):
        claim_legacy_destinations(db, 3, 6, ["l1b"])
    assert db.destinations == []
    assert db.legacy_selected is True


def test_claim_creates_canonical_rows_and_suppresses_legacy_only_after_all_claimed():
    db = LegacyDb()
    first = claim_legacy_destinations(db, 3, 6, ["l1t"])
    assert first[0]["external_id"] == "@Donya24News"
    assert db.legacy_selected is True
    second = claim_legacy_destinations(db, 3, 6, ["l1b"])
    assert second[0]["platform"] == "bale"
    assert db.legacy_selected is False
    assert db.selected == [6]


def test_repeated_claim_is_idempotent_and_creates_no_duplicate():
    db = LegacyDb()
    claim_legacy_destinations(db, 3, 6, ["l1t", "l1b"])
    ids = [row["id"] for row in db.destinations]
    claim_legacy_destinations(db, 3, 6, ["l1t", "l1b"])
    assert [row["id"] for row in db.destinations] == ids


def test_existing_canonical_destination_is_moved_not_copied():
    db = LegacyDb()
    db.destinations.append({"id": 9, "workspace_id": 3, "platform": "telegram", "external_id": "donya24news", "status": "inactive", "verification": "kept"})
    claimed = claim_legacy_destinations(db, 3, 6, ["l1t"])
    assert claimed[0]["id"] == 9
    assert claimed[0]["workspace_id"] == 6
    assert claimed[0]["status"] == "inactive"
    assert claimed[0]["verification"] == "kept"
    assert len(db.destinations) == 1


def test_claim_preserves_members_branding_and_history():
    db = LegacyDb()
    before = (deepcopy(db.members), deepcopy(db.branding), deepcopy(db.history))
    claim_legacy_destinations(db, 3, 6, ["l1t", "l1b"])
    assert (db.members, db.branding, db.history) == before


def test_legacy_full_canonical_detection_is_platform_scoped():
    tenant = {"id": 1, "telegram_channel": "@same", "bale_channel": "@same"}
    assert not legacy_is_fully_canonical(tenant, [{"platform": "telegram", "external_id": "same"}])
    assert legacy_is_fully_canonical(tenant, [
        {"platform": "telegram", "external_id": "same"},
        {"platform": "bale", "external_id": "@same"},
    ])


def test_empty_workspace_visibility_is_soft_and_reversible():
    rows = [
        {"id": 1, "destination_count": 0, "canonical_visibility_known": True},
        {"id": 2, "destination_count": 1, "canonical_visibility_known": True},
    ]
    assert [row["id"] for row in visible_workspace_rows(rows)] == [2]
    rows[0]["destination_count"] = 1
    assert [row["id"] for row in visible_workspace_rows(rows)] == [1, 2]


def test_inactive_destination_keeps_workspace_visible():
    # Counts use all non-removed destinations, not only active publication targets.
    row = {"id": 1, "destination_count": 1, "canonical_visibility_known": True}
    assert visible_workspace_rows([row]) == [row]
