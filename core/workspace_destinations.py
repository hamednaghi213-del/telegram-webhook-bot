"""Pure Phase 7 rules for workspace destination management."""

from typing import Dict, Iterable, Optional, Tuple


def can_manage_destinations(role: Optional[str]) -> Tuple[bool, str]:
    if role not in {"owner", "manager"}:
        return False, "فقط مالک یا مدیر رسانه می‌تواند مقصدها را مدیریت کند."
    return True, ""


def find_workspace_destination(
    destinations: Iterable[Dict], destination_id: int
) -> Optional[Dict]:
    """Find a non-removed destination from the current workspace list."""
    for destination in destinations:
        if (
            destination.get("id") == destination_id
            and destination.get("status") != "removed"
        ):
            return destination
    return None


def canonical_destination_identity(destination: Dict) -> Tuple[str, str]:
    """Identity used for duplicate protection across workspace moves."""
    platform = str(destination.get("platform") or "").strip().casefold()
    external_id = str(destination.get("external_id") or "").strip()
    return platform, external_id.lstrip("@").casefold()


def validate_destination_move(
    destinations: Iterable[Dict],
    selected_ids: Iterable[int],
    target_workspace_id: int,
) -> Tuple[bool, str, list]:
    """Validate a complete move before the single atomic update is issued."""
    selected = {int(value) for value in selected_ids}
    rows = [row for row in destinations if row.get("status") != "removed"]
    moving = [row for row in rows if int(row.get("id", -1)) in selected]
    if not selected or len(moving) != len(selected):
        return False, "حداقل یک کانال معتبر انتخاب کنید.", []
    if any(int(row.get("workspace_id", -1)) == int(target_workspace_id) for row in moving):
        return False, "کانال انتخاب‌شده از قبل در گروه مقصد است.", []

    target_keys = {
        canonical_destination_identity(row)
        for row in rows
        if int(row.get("workspace_id", -1)) == int(target_workspace_id)
    }
    moving_keys = [canonical_destination_identity(row) for row in moving]
    if any(key in target_keys for key in moving_keys) or len(set(moving_keys)) != len(moving_keys):
        return False, "کانالی با همین شناسه و پلتفرم در گروه مقصد وجود دارد.", []
    return True, "", sorted(moving, key=lambda row: int(row["id"]))
