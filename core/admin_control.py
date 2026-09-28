import os
from typing import Optional


def admin_control_enabled() -> bool:
    return (
        os.getenv("ENABLE_ADMIN_CONTROL", "false")
        .strip()
        .lower()
        == "true"
    )


def _read_positive_int_env(name: str) -> Optional[int]:
    raw_value = (os.getenv(name, "") or "").strip()
    if not raw_value:
        return None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    if value <= 0:
        return None

    return value


def admin_telegram_user_id() -> Optional[int]:
    return _read_positive_int_env("ADMIN_TELEGRAM_USER_ID")


def admin_bale_user_id() -> Optional[int]:
    return _read_positive_int_env("ADMIN_BALE_USER_ID")


def is_admin_identity(
    platform: str,
    external_user_id: int,
) -> bool:
    try:
        normalized_user_id = int(external_user_id)
    except (TypeError, ValueError):
        return False

    normalized_platform = (platform or "").strip().lower()

    if normalized_platform == "telegram":
        admin_user_id = admin_telegram_user_id()
    elif normalized_platform == "bale":
        admin_user_id = admin_bale_user_id()
    else:
        return False

    return (
        admin_user_id is not None
        and normalized_user_id == admin_user_id
    )


def new_user_status_for_identity(
    platform: str,
    external_user_id: int,
) -> str:
    if not admin_control_enabled():
        return "active"

    if is_admin_identity(platform, external_user_id):
        return "active"

    return "pending"