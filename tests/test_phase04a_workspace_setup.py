def test_26f_onboarding_activates_owned_workspace_instead_of_manager_workspace(
    monkeypatch
):
    """
    Regression:
    A user may already be manager of another workspace.

    When /start creates the user's own onboarding workspace, that new owned
    workspace must become the active setup context. Subsequent branding must
    never overwrite the workspace where the user is only a manager.
    """
    _, ch_mod, db, _ = _load_modules(monkeypatch)

    telegram_id = 2027

    # Existing media owned by somebody else.
    existing_owner = db.get_or_create_user_by_telegram_id(90001)
    existing_workspace = db.create_workspace(
        "بی‌نشانه",
        existing_owner["id"],
    )
    db.upsert_workspace_branding(
        existing_workspace["id"],
        "بی‌نشانه",
        "#بی_نشانه",
        "@beneshaneh",
    )

    # The new user already exists because they were added as manager
    # of the existing media.
    new_user = db.get_or_create_user_by_telegram_id(telegram_id)
    db.add_workspace_member(
        existing_workspace["id"],
        new_user["id"],
        role="manager",
        status="active",
    )

    # Simulate the previously selected manager workspace.
    db.set_active_workspace(
        new_user["id"],
        existing_workspace["id"],
    )

    # /start must create the user's own workspace.
    assert ch_mod.handle_start(telegram_id) is True

    owned_workspaces = db.list_owned_workspaces(
        new_user["id"],
        include_inactive=True,
    )

    assert len(owned_workspaces) == 1

    owned_workspace = owned_workspaces[0]

    assert owned_workspace["id"] != existing_workspace["id"]

    # Critical regression guard:
    # onboarding must switch the active context to the workspace
    # that belongs to this user.
    preference = db.get_active_workspace_preference(
        new_user["id"]
    )

    assert preference is not None
    assert preference["context_type"] == "workspace"
    assert preference["active_workspace_id"] == owned_workspace["id"]

    # Any following setup command must write only to the owned workspace.
    assert ch_mod.handle_command(
        "/setbranding فردای نو #فردای_نو @farda_no",
        telegram_id,
    ) is True

    old_branding = db.get_workspace_branding(
        existing_workspace["id"]
    )
    new_branding = db.get_workspace_branding(
        owned_workspace["id"]
    )

    # Existing media must remain byte-for-byte untouched.
    assert old_branding["media_name"] == "بی‌نشانه"
    assert old_branding["hashtag"] == "#بی_نشانه"
    assert old_branding["channel_tag"] == "@beneshaneh"

    # New user's branding belongs only to their own workspace.
    assert new_branding is not None
    assert new_branding["media_name"] == "فردای نو"
    assert new_branding["hashtag"] == "#فردای_نو"
    assert new_branding["channel_tag"] == "@farda_no"
