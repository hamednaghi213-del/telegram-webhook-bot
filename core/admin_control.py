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


def _normalize_destination_external_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    return normalized


def destination_admin_state(destination_id: int) -> str:
    """Return active/paused/blocked.

    Admin Control is backward-compatible:
    disabled, missing rows, or lookup failures are treated as active.
    """
    if not admin_control_enabled():
        return "active"

    try:
        from core.database import get_admin_destination_control

        row = get_admin_destination_control(
            int(destination_id)
        )

        if not row:
            return "active"

        state = str(
            row.get("admin_state") or "active"
        ).strip().lower()

        if state not in {
            "active",
            "paused",
            "blocked",
        }:
            return "active"

        return state

    except Exception:
        return "active"


def destination_admin_allowed(destination_id: int) -> bool:
    return destination_admin_state(destination_id) == "active"


def external_destination_is_blocked(
    platform: str,
    external_id: str,
) -> bool:
    """Prevent a blocked physical destination being re-added.

    The admin identity itself remains exempt in command_handler.
    """
    if not admin_control_enabled():
        return False

    wanted_platform = str(
        platform or ""
    ).strip().lower()

    wanted_external_id = _normalize_destination_external_id(
        external_id
    )

    if not wanted_platform or not wanted_external_id:
        return False

    try:
        from core.database import list_admin_destination_inventory

        for row in list_admin_destination_inventory() or []:
            row_platform = str(
                row.get("platform") or ""
            ).strip().lower()

            row_external_id = _normalize_destination_external_id(
                row.get("external_id")
            )

            if (
                row_platform == wanted_platform
                and row_external_id == wanted_external_id
                and str(
                    row.get("admin_state") or "active"
                ).strip().lower() == "blocked"
            ):
                return True

    except Exception:
        return False

    return False
