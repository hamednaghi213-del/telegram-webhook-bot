"""Authorization rules for Phase 6 workspace member management."""

from typing import Optional, Tuple


ASSIGNABLE_ROLES = {"manager", "publisher", "writer"}
MANAGER_ASSIGNABLE_ROLES = {"publisher", "writer"}


def authorize_member_action(
    actor_role: Optional[str],
    target_role: Optional[str] = None,
    requested_role: Optional[str] = None,
) -> Tuple[bool, str]:
    """Return whether an actor may add, update, or remove a workspace member."""
    if actor_role not in {"owner", "manager"}:
        return False, "فقط مالک یا مدیر رسانه می‌تواند اعضا را مدیریت کند."

    if target_role == "owner":
        return False, "نقش مالک قابل تغییر یا حذف نیست."

    if requested_role is not None:
        if requested_role not in ASSIGNABLE_ROLES:
            return False, "نقش مجاز نیست."
        if actor_role == "manager" and requested_role not in MANAGER_ASSIGNABLE_ROLES:
            return False, "مدیر فقط می‌تواند نقش publisher یا writer تعیین کند."

    if actor_role == "manager" and target_role == "manager":
        return False, "مدیر نمی‌تواند مدیر دیگری را تغییر دهد یا حذف کند."

    return True, ""
