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
    canonical = bool(getattr(database, "canonical_media_enabled", lambda: False)())
    rows = (
        database.list_canonical_publication_destinations(user_id, list(manageable))
        if canonical
        else database.list_publication_destinations_for_workspaces(list(manageable))
    )
    names = {workspace_id: row.get("name") or str(workspace_id) for workspace_id, row in manageable.items()}
    candidates = []
    for row in rows:
        if canonical:
            from core.canonical_media import media_access_allows
            if not media_access_allows(row.get("media_member"), manage=True):
                continue
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
    canonical = bool(getattr(database, "canonical_media_enabled", lambda: False)())
    rows = (
        database.list_canonical_publication_destinations(user_id, list(manageable))
        if canonical
        else database.list_publication_destinations_for_workspaces(list(manageable))
    )
    if canonical:
        from core.canonical_media import media_access_allows
        selected = {int(value) for value in destination_ids}
        selected_rows = [row for row in rows if int(row["id"]) in selected]
        if any(not media_access_allows(row.get("media_member"), manage=True) for row in selected_rows):
            raise ValueError("اجازه مدیریت هویت رسانه یکی از کانال‌ها را ندارید.")
    allowed, reason, moving = validate_destination_move(rows, destination_ids, target_workspace_id)
    if not allowed:
        raise ValueError(reason)
    manageable_ids = set(manageable)
    if any(int(row["workspace_id"]) not in manageable_ids for row in moving):
        raise ValueError("اجازه مدیریت یکی از کانال‌های انتخاب‌شده را ندارید.")
    if canonical:
        database.move_canonical_destination_associations(
    user_id,
    [row["id"] for row in moving],
    target_workspace_id,
    )
        refreshed = database.list_canonical_publication_destinations(
            user_id, [target_workspace_id]
        )
        moved_ids = {int(row["id"]) for row in moving}
        return [row for row in refreshed if int(row["id"]) in moved_ids]
    return database.move_publication_destinations([row["id"] for row in moving], target_workspace_id)
