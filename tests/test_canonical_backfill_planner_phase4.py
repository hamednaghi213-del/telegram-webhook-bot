from copy import deepcopy

import pytest

from core.canonical_media import canonical_target_is_ready, resolve_media_branding
from core.canonical_media_backfill import (
    BLOCKED_ACCESS,
    BLOCKED_AUTHORIZATION,
    BLOCKED_BRANDING,
    BLOCKED_WORKSPACE,
    apply_backfill_plan,
    build_backfill_plan,
)


def mapping(**overrides):
    row = {
        "user_id": 3,
        "workspace_id": 6,
        "workspace_verified": True,
        "media_key": "donya24news_en",
        "media_name": "Donya24_En",
        "platform": "telegram",
        "external_id": "@Donya24News_En",
        "hashtag": "#دنیا_۲۴_نیوز_انگلیسی",
        "channel_tag": "@Donya24News_En",
        "publication_icons": ["❇️", "🔹"],
        "icons_enabled": True,
        "publication_profile": {"title_icon": "❇️", "body_icons": ["🔹"]},
        "branding_verified": True,
        "access_verified": True,
        "authorization_verified": True,
        "media_role": "owner",
    }
    row.update(overrides)
    return row


def existing_destination(**overrides):
    row = {
        "id": 3, "workspace_id": 6, "platform": "telegram",
        "external_id": "@Donya24News_En", "status": "active",
        "media_identity_id": None, "normalized_external_id": None,
        "platform_chat_id": None,
    }
    row.update(overrides)
    return row


def test_reused_destination_emits_exact_canonical_update_and_preserves_id():
    plan = build_backfill_plan({"destinations": [existing_destination()]}, [mapping()])
    update = plan["executable"]["updates"]["destinations"][0]
    assert update == {
        "id": 3,
        "old_values": {"media_identity_id": None, "normalized_external_id": None},
        "new_values": {
            "media_identity_id": "media:donya24news_en",
            "normalized_external_id": "donya24news_en",
        },
    }
    assert plan["executable"]["inserts"]["destinations"] == []


def test_platform_chat_id_is_never_guessed_and_only_verified_value_is_planned():
    base = {"destinations": [existing_destination()]}
    omitted = build_backfill_plan(base, [mapping(platform_chat_id="-100123")])
    assert "platform_chat_id" not in omitted["updates"]["destinations"][0]["new_values"]
    verified = build_backfill_plan(
        base, [mapping(platform_chat_id="-100123", platform_chat_id_verified=True)]
    )
    assert verified["updates"]["destinations"][0]["new_values"]["platform_chat_id"] == "-100123"


@pytest.mark.parametrize("enabled", [True, False])
def test_media_insert_preserves_icons_enabled(enabled):
    plan = build_backfill_plan({}, [mapping(icons_enabled=enabled)])
    media = plan["executable"]["inserts"]["media_identities"][0]
    assert media["icons_enabled"] is enabled
    assert media["publication_icons"] == ["❇️", "🔹"]
    assert media["publication_profile"]["title_icon"] == "❇️"


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("branding_verified", False, BLOCKED_BRANDING),
        ("access_verified", False, BLOCKED_ACCESS),
        ("workspace_verified", False, BLOCKED_WORKSPACE),
        ("authorization_verified", False, BLOCKED_AUTHORIZATION),
    ],
)
def test_structured_blocker_moves_identity_to_conditional(field, value, status):
    plan = build_backfill_plan({}, [mapping(**{field: value})])
    assert not plan["safe_to_apply"]
    assert status in plan["identity_statuses"][0]["statuses"]
    assert plan["executable"]["counts"] == {"inserts": 0, "updates": 0, "deletes": 0}
    assert plan["conditional"]["counts"]["inserts"] == 4


def test_access_and_workspace_blockers_are_reported_independently():
    plan = build_backfill_plan(
        {}, [mapping(access_verified=False, workspace_verified=False)]
    )
    assert set(plan["identity_statuses"][0]["statuses"]) == {
        BLOCKED_ACCESS, BLOCKED_WORKSPACE,
    }


def test_exact_accounting_matches_every_row_list():
    plan = build_backfill_plan(
        {"destinations": [existing_destination()]}, [mapping()]
    )
    executable = plan["executable"]
    assert executable["counts"]["inserts"] == sum(
        len(rows) for rows in executable["inserts"].values()
    )
    assert executable["counts"]["updates"] == sum(
        len(rows) for rows in executable["updates"].values()
    )
    assert executable["counts"]["deletes"] == len(executable["deletes"]) == 0


def test_shared_bale_multi_user_creates_one_physical_destination_and_two_grants():
    rows = [
        mapping(
            media_key="donya24news", platform="bale", external_id="@donya24_news",
            user_id=3, media_role="owner",
        ),
        mapping(
            media_key="donya24news", platform="bale", external_id="@donya24_news",
            user_id=2, media_role="publisher",
        ),
    ]
    plan = build_backfill_plan({}, rows)
    assert len(plan["inserts"]["destinations"]) == 1
    assert len(plan["inserts"]["media_members"]) == 2


def test_shared_bale_unverified_grants_keep_one_destination_conditional():
    rows = [
        mapping(
            media_key="donya24news", platform="bale", external_id="@donya24_news",
            user_id=3, access_verified=False,
        ),
        mapping(
            media_key="donya24news", platform="bale", external_id="@donya24_news",
            user_id=2, access_verified=False,
        ),
    ]
    plan = build_backfill_plan({}, rows)
    assert not plan["safe_to_apply"]
    assert len(plan["conditional"]["inserts"]["destinations"]) == 1
    assert len(plan["conditional"]["inserts"]["media_members"]) == 2


def test_existing_canonical_rows_become_noop_on_repeated_run():
    media = {
        "id": 20, "identity_key": "donya24news_en",
        "media_name": "Donya24_En", "hashtag": "#دنیا_۲۴_نیوز_انگلیسی",
        "channel_tag": "@Donya24News_En", "publication_icons": ["❇️", "🔹"],
        "icons_enabled": True,
        "publication_profile": {"title_icon": "❇️", "body_icons": ["🔹"]},
    }
    snapshot = {
        "media_identities": [media],
        "destinations": [existing_destination(
            media_identity_id=20, normalized_external_id="donya24news_en"
        )],
        "media_members": [{
            "media_identity_id": 20, "user_id": 3, "role": "owner", "status": "active",
        }],
        "workspace_destinations": [{
            "workspace_id": 6, "destination_id": 3, "status": "active",
        }],
    }
    first = build_backfill_plan(snapshot, [mapping()])
    second = build_backfill_plan(deepcopy(snapshot), [mapping()])
    assert first["counts"] == second["counts"] == {"inserts": 0, "updates": 0, "deletes": 0}


def test_removed_historical_destination_is_reported_but_never_touched():
    removed = existing_destination(id=1, status="removed")
    plan = build_backfill_plan({"destinations": [removed]}, [mapping()])
    assert plan["historical_removed_destinations"] == [removed]
    assert all(row.get("id") != 1 for row in plan["updates"]["destinations"])
    assert plan["deletes"] == []


def test_farda_contamination_is_first_class_and_stale_donya_is_not_selected():
    farda = mapping(
        media_key="farda_no", media_name="فردای‌نو", hashtag="#فردای_نو",
        channel_tag="@farda_no", external_id="@farda_no", workspace_id=1,
        branding_verified=False,
        branding_conflicts=[
            "workspace profile references Beneshaneh",
            "legacy scalar branding references Donya24News",
        ],
        publication_profile={},
    )
    plan = build_backfill_plan({}, [farda])
    assert plan["identity_statuses"][0]["statuses"] == [BLOCKED_BRANDING]
    media = plan["conditional"]["inserts"]["media_identities"][0]
    assert media["hashtag"] == "#فردای_نو"
    assert "دنیا" not in media["hashtag"]
    assert "بی_نشانه" not in str(media["publication_profile"])


def test_workspace_name_is_not_a_branding_input_and_profile_survives_move():
    plan = build_backfill_plan({}, [mapping(workspace_name="سیاسی")])
    media = plan["inserts"]["media_identities"][0]
    assert "سیاسی" not in media.values()
    assert media["publication_profile"]["title_icon"] == "❇️"


def test_placeholder_channel_is_explicitly_excluded():
    plan = build_backfill_plan({}, [mapping(
        platform="telegram", external_id="@channel", placeholder=True,
        migrate=False, exclusion_reason="placeholder",
    )])
    assert plan["excluded_routes"][0]["identity"] == ["telegram", "channel"]
    assert plan["counts"] == {"inserts": 0, "updates": 0, "deletes": 0}


def test_planner_never_creates_workspace_membership_or_auto_grants_it():
    plan = build_backfill_plan({}, [mapping(
        user_id=2, create_workspace_membership=True, authorization_verified=False,
    )])
    assert BLOCKED_AUTHORIZATION in plan["identity_statuses"][0]["statuses"]
    assert "workspace_members" not in plan["conditional"]["inserts"]


def test_history_message_links_retry_and_idempotency_are_ignored_and_protected():
    snapshot = {
        "publication_message_links": [{"id": 5, "telegram_destination_id": 3}],
        "history": [{"id": 7}],
        "retry": [{"id": 8}],
        "idempotency": [{"id": 9}],
    }
    before = deepcopy(snapshot)
    plan = build_backfill_plan(snapshot, [mapping()])
    assert snapshot == before
    assert set(plan["rollback"]["protected_tables"]) >= {
        "publication_message_links", "history", "retry", "idempotency",
    }
    assert plan["deletes"] == []


@pytest.mark.parametrize("extra", [{}, {"workspace_branding": None}, {"setup_step": "in_progress"}])
def test_canonical_readiness_does_not_depend_on_group_branding_or_old_setup(extra):
    row = {
        "association_status": "active", "status": "active",
        "media_status": "active", "verification": {"verified": True}, **extra,
    }
    assert canonical_target_is_ready(row)


def test_destination_override_resolution_is_media_then_explicit_override():
    media = {
        "media_name": "Donya24_En", "hashtag": "#base", "channel_tag": "@base",
        "publication_icons": ["❇️"], "icons_enabled": True,
        "publication_profile": {"title_icon": "❇️"},
    }
    resolved = resolve_media_branding(media, {
        "hashtag": "#override", "channel_tag": "", "publication_profile": None,
    })
    assert resolved["hashtag"] == "#override"
    assert resolved["channel_tag"] == "@base"
    assert resolved["publication_profile"] == {"title_icon": "❇️"}


class HalfwayFailure:
    def __init__(self):
        self.events = []
        self.existing = {"tenant": [1], "workspace": [3], "message_links": [5]}

    def begin(self):
        self.events.append("begin")

    def apply(self, _plan):
        self.events.append("apply")
        raise RuntimeError("halfway")

    def verify(self, *_args):
        self.events.append("verify")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


def test_halfway_failure_rolls_back_without_touching_existing_business_rows():
    transaction = HalfwayFailure()
    before = deepcopy(transaction.existing)
    with pytest.raises(RuntimeError):
        apply_backfill_plan(build_backfill_plan({}, [mapping()]), transaction)
    assert transaction.events == ["begin", "apply", "rollback"]
    assert transaction.existing == before
