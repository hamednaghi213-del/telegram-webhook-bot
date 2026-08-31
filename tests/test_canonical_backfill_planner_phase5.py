from core.canonical_media_backfill import build_backfill_plan


FARDA_PROFILE = {
    "title_icon": "❇️",
    "body_icons": ["🔹"],
}


def _branding(media_key):
    values = {
        "donya24news": ("Donya24News", "#دنیا_۲۴_نیوز", "@Donya24News"),
        "donya24news_en": ("Donya24_En", "#دنیا_۲۴_نیوز_انگلیسی", "@Donya24News_En"),
        "farda_no": ("فردای‌نو", "#فردای_نو", "@farda_no"),
        "beneshaneh": ("بی‌نشانه", "#بی_نشانه", "@beneshaneh"),
        "siasat24": ("سیاست۲۴", "#سیاست۲۴", "@siasat24"),
    }
    return values[media_key]


def _formatting(media_key):
    values = {
        "donya24news": ([], False, {}),
        "donya24news_en": (
            ["❇️", "🔹"], True,
            {"all_icons": ["❇️", "🔹"], "title_icon": "❇️", "body_icons": ["🔹"],
             "cta_icons": [], "cta_lines": [], "hashtags": ["#دنیا_۲۴_نیوز_انگلیسی"],
             "mentions": ["@Donya24News_En"], "bale_url": "", "bale_channel": "", "bold_texts": []},
        ),
        "farda_no": (["❇️", "🔹"], True, FARDA_PROFILE),
        "beneshaneh": (
            ["❇️", "🔹"], True,
            {"all_icons": ["✅", "🔹"], "title_icon": "✅", "body_icons": ["🔹"],
             "cta_icons": [], "cta_lines": [], "hashtags": ["#بی_نشانه"],
             "mentions": ["@beneshaneh"], "bale_url": "", "bale_channel": "",
             "bold_texts": ["پنتاگون در پی توسعه پایگاه هوایی مورون در اسپانیاست"]},
        ),
        "siasat24": (
            ["🔺", "🔹️"], True,
            {"all_icons": ["🔺", "🔹️"], "title_icon": "🔺", "body_icons": ["🔹️"],
             "cta_icons": [], "cta_lines": [], "hashtags": ["#سیاست۲۴"],
             "mentions": ["@siasat24"], "bale_url": "", "bale_channel": "",
             "bold_texts": ["دادگاه آمریکا اخراج دانشجویان مخالف اسرائیل را متوقف کرد"]},
        ),
    }
    return values[media_key]


def _row(media_key, destination_id, workspace_id, user_id, role, platform, external_id, **extra):
    name, hashtag, tag = _branding(media_key)
    icons, icons_enabled, profile = _formatting(media_key)
    row = {
        "media_key": media_key,
        "media_name": name,
        "hashtag": hashtag,
        "channel_tag": tag,
        "publication_icons": icons,
        "icons_enabled": icons_enabled,
        "publication_profile": profile,
        "destination_id": destination_id,
        "workspace_id": workspace_id,
        "workspace_verified": True,
        "user_id": user_id,
        "media_role": role,
        "platform": platform,
        "external_id": external_id,
        "branding_verified": True,
        "access_verified": True,
        "authorization_verified": True,
    }
    row.update(extra)
    return row


def _dest(destination_id, workspace_id, platform, external_id):
    return {
        "id": destination_id, "workspace_id": workspace_id,
        "platform": platform, "external_id": external_id, "status": "active",
        "media_identity_id": None, "normalized_external_id": None,
        "platform_chat_id": None,
    }


def final_rows():
    rows = [
        _row("donya24news_en", 3, 6, 3, "owner", "telegram", "@Donya24News_En"),
        _row("donya24news_en", 4, 6, 3, "owner", "bale", "@donya24_news_en"),
        _row("beneshaneh", 7, 4, 1, "owner", "telegram", "@beneshaneh"),
        _row("beneshaneh", 8, 4, 2, "manager", "bale", "@beneshaneh"),
        _row("farda_no", 9, 1, 1, "owner", "telegram", "@farda_no"),
        _row("farda_no", 10, 1, 2, "manager", "bale", "@farda_no"),
        _row("siasat24", 11, 5, 2, "owner", "telegram", "@siasat24"),
        _row("siasat24", 12, 5, 2, "owner", "bale", "@siasat24"),
        _row("donya24news", None, 6, 3, "owner", "telegram", "@Donya24News"),
        _row("donya24news", None, 6, 3, "owner", "bale", "@donya24_news"),
        _row(
            "donya24news", None, 6, 2, "manager", "bale", "@donya24_news",
            create_workspace_membership=True, workspace_membership_approved=True,
            workspace_role="manager", workspace_membership_approval_source="phase_5_user_decision",
            select_workspace=True, workspace_selection_approved=True,
            workspace_selection_approval_source="phase_5_user_decision",
        ),
        {
            "media_key": "excluded", "platform": "telegram", "external_id": "@channel",
            "migrate": False, "placeholder": True, "exclusion_reason": "placeholder",
        },
    ]
    return rows


def final_snapshot():
    return {
        "destinations": [
            _dest(3, 6, "telegram", "@Donya24News_En"),
            _dest(4, 6, "bale", "@donya24_news_en"),
            _dest(7, 4, "telegram", "@beneshaneh"),
            _dest(8, 4, "bale", "@beneshaneh"),
            _dest(9, 1, "telegram", "@farda_no"),
            _dest(10, 1, "bale", "@farda_no"),
            _dest(11, 5, "telegram", "@siasat24"),
            _dest(12, 5, "bale", "@siasat24"),
            _dest(1, 1, "telegram", "@removed1") | {"status": "removed"},
            _dest(2, 1, "bale", "@removed2") | {"status": "removed"},
            _dest(5, 3, "telegram", "@removed5") | {"status": "removed"},
            _dest(6, 3, "bale", "@removed6") | {"status": "removed"},
        ],
        "workspace_members": [
            {"id": 1, "workspace_id": 1, "user_id": 1, "role": "owner", "status": "active"},
            {"id": 2, "workspace_id": 1, "user_id": 2, "role": "manager", "status": "active"},
            {"id": 6, "workspace_id": 4, "user_id": 1, "role": "owner", "status": "active"},
            {"id": 5, "workspace_id": 4, "user_id": 2, "role": "manager", "status": "active"},
            {"id": 7, "workspace_id": 5, "user_id": 2, "role": "owner", "status": "active"},
            {"id": 8, "workspace_id": 6, "user_id": 3, "role": "owner", "status": "active"},
        ],
        "selected_workspaces": [
            {"user_id": 1, "workspace_id": 1}, {"user_id": 1, "workspace_id": 4},
            {"user_id": 2, "workspace_id": 1}, {"user_id": 2, "workspace_id": 4},
            {"user_id": 2, "workspace_id": 5}, {"user_id": 3, "workspace_id": 6},
        ],
        "planned_legacy_suppression": [
            {"user_id": 1, "old_values": {"legacy_selected": True},
             "new_values": {"legacy_selected": False}, "reason": "canonical_coverage_complete"},
            {"user_id": 2, "old_values": {"legacy_selected": True},
             "new_values": {"legacy_selected": False}, "reason": "canonical_coverage_complete"},
            {"user_id": 3, "old_values": {"legacy_selected": True},
             "new_values": {"legacy_selected": False}, "reason": "canonical_coverage_complete"},
        ],
    }


def test_final_human_decisions_make_all_five_media_ready():
    plan = build_backfill_plan(final_snapshot(), final_rows())
    assert plan["safe_to_apply"]
    assert {row["media_key"] for row in plan["identity_statuses"]} == {
        "donya24news", "donya24news_en", "farda_no", "beneshaneh", "siasat24",
    }
    assert all(row["statuses"] == ["READY"] for row in plan["identity_statuses"])


def test_donya_decisions_plan_owner_manager_workspace_and_single_bale():
    plan = build_backfill_plan(final_snapshot(), final_rows())
    members = plan["inserts"]["media_members"]
    donya = [row for row in members if row["media_ref"] == "media:donya24news"]
    assert {(row["user_id"], row["role"]) for row in donya} == {(3, "owner"), (2, "manager")}
    assert plan["inserts"]["workspace_members"] == [{
        "workspace_id": 6, "user_id": 2, "role": "manager", "status": "active",
    }]
    assert plan["inserts"]["workspace_selections"] == [{
        "user_id": 2, "workspace_id": 6,
    }]
    assert plan["decision_evidence"] == ["phase_5_user_decision"]
    bale = [row for row in plan["inserts"]["destinations"] if row["platform"] == "bale" and row["normalized_external_id"] == "donya24_news"]
    assert len(bale) == 1


def test_farda_profile_is_clean_and_media_are_independent():
    plan = build_backfill_plan(final_snapshot(), final_rows())
    identities = {row["identity_key"]: row for row in plan["inserts"]["media_identities"]}
    farda = identities["farda_no"]
    assert farda["media_name"] == "فردای‌نو"
    assert farda["hashtag"] == "#فردای_نو"
    assert farda["channel_tag"] == "@farda_no"
    assert farda["publication_profile"] == FARDA_PROFILE
    assert "بی_نشانه" not in str(farda)
    assert "Donya24News" not in str(farda)
    assert "سیاسی" not in str(identities)


def test_exact_final_plan_has_no_duplicate_targets_and_preserves_history():
    snapshot = final_snapshot()
    snapshot.update({
        "publication_message_links": [{"id": 100}],
        "history": [{"id": 200}], "retry": [{"id": 300}], "idempotency": [{"id": 400}],
    })
    plan = build_backfill_plan(snapshot, final_rows())
    destination_keys = [
        (row["platform"], row["normalized_external_id"])
        for row in plan["inserts"]["destinations"]
    ]
    assert len(destination_keys) == len(set(destination_keys))
    assert plan["deletes"] == []
    assert {row["id"] for row in plan["historical_removed_destinations"]} == {1, 2, 5, 6}
    assert set(plan["rollback"]["protected_tables"]) >= {
        "publication_message_links", "history", "retry", "idempotency",
    }


def test_final_exact_counts_and_target_simulation():
    plan = build_backfill_plan(final_snapshot(), final_rows())
    assert plan["counts"] == {"inserts": 27, "updates": 11, "deletes": 0}
    simulation = plan["target_simulation"]
    assert {(row["media_key"], row["platform"]) for row in simulation["1"]} == {
        ("farda_no", "telegram"), ("farda_no", "bale"),
        ("beneshaneh", "telegram"), ("beneshaneh", "bale"),
    }
    assert {(row["media_key"], row["platform"]) for row in simulation["2"]} == {
        ("farda_no", "telegram"), ("farda_no", "bale"),
        ("beneshaneh", "telegram"), ("beneshaneh", "bale"),
        ("siasat24", "telegram"), ("siasat24", "bale"),
        ("donya24news", "telegram"), ("donya24news", "bale"),
    }
    assert {(row["media_key"], row["platform"]) for row in simulation["3"]} == {
        ("donya24news_en", "telegram"), ("donya24news_en", "bale"),
        ("donya24news", "telegram"), ("donya24news", "bale"),
    }
    for targets in simulation.values():
        keys = [(row["platform"], row["normalized_external_id"]) for row in targets]
        assert len(keys) == len(set(keys))
