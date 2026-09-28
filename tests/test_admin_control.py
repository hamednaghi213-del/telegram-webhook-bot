from core.admin_control import new_user_status_for_identity


def test_admin_control_disabled_keeps_new_user_active(monkeypatch):
    monkeypatch.delenv("ENABLE_ADMIN_CONTROL", raising=False)
    monkeypatch.delenv("ADMIN_TELEGRAM_USER_ID", raising=False)
    monkeypatch.delenv("ADMIN_BALE_USER_ID", raising=False)

    assert (
        new_user_status_for_identity(
            "telegram",
            123456789,
        )
        == "active"
    )


def test_admin_control_enabled_makes_normal_telegram_user_pending(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_CONTROL", "true")
    monkeypatch.delenv("ADMIN_TELEGRAM_USER_ID", raising=False)

    assert (
        new_user_status_for_identity(
            "telegram",
            123456789,
        )
        == "pending"
    )


def test_admin_control_enabled_makes_normal_bale_user_pending(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_CONTROL", "true")
    monkeypatch.delenv("ADMIN_BALE_USER_ID", raising=False)

    assert (
        new_user_status_for_identity(
            "bale",
            987654321,
        )
        == "pending"
    )


def test_telegram_admin_remains_active(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_CONTROL", "true")
    monkeypatch.setenv(
        "ADMIN_TELEGRAM_USER_ID",
        "123456789",
    )

    assert (
        new_user_status_for_identity(
            "telegram",
            123456789,
        )
        == "active"
    )


def test_bale_admin_remains_active(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_CONTROL", "true")
    monkeypatch.setenv(
        "ADMIN_BALE_USER_ID",
        "987654321",
    )

    assert (
        new_user_status_for_identity(
            "bale",
            987654321,
        )
        == "active"
    )


def test_unknown_platform_is_pending_when_admin_control_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_CONTROL", "true")

    assert (
        new_user_status_for_identity(
            "unknown",
            123456789,
        )
        == "pending"
    )