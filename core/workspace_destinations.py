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
