"""Authorized orchestration for moving existing publication destinations."""

from typing import Dict, Iterable, List, Tuple

from core.workspace_destinations import can_manage_destinations, validate_destination_move


def _manageable_workspaces(database, user_id: int) -> Dict[int, Dict]:
    return {
        int(row["id"]): row
        for row in database.list_user_workspace_memberships(user_id)
        if row.get("status") == "active"
        and can_manage_destinations(row.get("member_role"))[0]
    }


def list_move_candidates(database, user_id: int, target_workspace_id: int) -> Tuple[Dict, List[Dict]]:
    manageable = _manageable_workspaces(database, user_id)
    target = manageable.get(int(target_workspace_id))
    if not target:
        raise ValueError("گروه مقصد معتبر نیست یا اجازه مدیریت آن را ندارید.")
    rows = database.list_publication_destinations_for_workspaces(list(manageable))
    names = {workspace_id: row.get("name") or str(workspace_id) for workspace_id, row in manageable.items()}
    candidates = []
    for row in rows:
        source_id = int(row["workspace_id"])
        if source_id == int(target_workspace_id):
            continue
        item = dict(row)
        item["move_key"] = f"d{int(row['id'])}"
        item["source_workspace_name"] = names[source_id]
        candidates.append(item)
    from core.legacy_workspace_compat import list_legacy_move_candidates
    candidates.extend(list_legacy_move_candidates(database, user_id, target_workspace_id))
    return target, candidates


def move_destinations(database, user_id: int, target_workspace_id: int, destination_ids: Iterable[int]) -> List[Dict]:
    manageable = _manageable_workspaces(database, user_id)
    if int(target_workspace_id) not in manageable:
        raise ValueError("گروه مقصد معتبر نیست یا اجازه مدیریت آن را ندارید.")
    rows = database.list_publication_destinations_for_workspaces(list(manageable))
    allowed, reason, moving = validate_destination_move(rows, destination_ids, target_workspace_id)
    if not allowed:
        raise ValueError(reason)
    manageable_ids = set(manageable)
    if any(int(row["workspace_id"]) not in manageable_ids for row in moving):
        raise ValueError("اجازه مدیریت یکی از کانال‌های انتخاب‌شده را ندارید.")
    return database.move_publication_destinations([row["id"] for row in moving], target_workspace_id)
