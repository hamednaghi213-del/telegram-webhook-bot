"""Resolve Legacy and Workspace destinations without publishing content."""

from typing import Dict, List, Tuple

from core.content_model import PublicationTarget


def _normalise_external_id(value) -> str:
    return str(value or "").strip().lower()


def resolve_publication_targets(chat_id: int) -> Tuple[List[PublicationTarget], List[str]]:
    """Return every selected, authorised target and non-fatal resolution errors."""
    import importlib

    database = importlib.import_module("core.database")
    get_tenant = getattr(database, "get_tenant")
    get_user_by_telegram_id = getattr(database, "get_user_by_telegram_id", lambda _id: None)
    get_active_workspace_preference = getattr(
        database, "get_active_workspace_preference", lambda _id: {}
    )
    list_selected_workspace_ids = getattr(
        database, "list_selected_workspace_ids", lambda _id: []
    )
    list_user_workspace_memberships = getattr(
        database, "list_user_workspace_memberships", lambda _id: []
    )
    get_workspace_setup_state = getattr(
        database, "get_workspace_setup_state", lambda _id: None
    )
    get_workspace_member = getattr(database, "get_workspace_member", lambda *_args: None)
    list_verified_active_destinations = getattr(
        database, "list_verified_active_destinations", lambda _id: []
    )

    targets: List[PublicationTarget] = []
    errors: List[str] = []
    tenant = get_tenant(chat_id)
    user = get_user_by_telegram_id(chat_id)
    preference: Dict = {}
    selected_ids = set()
    if user:
        preference = get_active_workspace_preference(user["id"]) or {}
        selected_ids = set(list_selected_workspace_ids(user["id"]) or [])

    legacy_selected = bool(
        tenant
        and tenant.get("telegram_channel")
        and (
            preference.get("legacy_selected")
            if "legacy_selected" in preference
            else (not preference or preference.get("context_type") == "legacy")
        )
    )
    if legacy_selected:
        targets.append(PublicationTarget(
            key=f"legacy:telegram:{tenant['telegram_channel']}",
            kind="legacy",
            platform="telegram",
            external_id=str(tenant["telegram_channel"]),
            destination=dict(tenant),
        ))
        legacy_bale_identity = tenant.get("bale_channel") or f"user:{chat_id}"
        targets.append(PublicationTarget(
            key=f"legacy:bale:{legacy_bale_identity}",
            kind="legacy",
            platform="bale",
            external_id=str(legacy_bale_identity),
            destination=dict(tenant),
        ))

    if user:
        memberships = list_user_workspace_memberships(user["id"]) or []
        if len(memberships) == 1 and not selected_ids and not legacy_selected:
            selected_ids.add(memberships[0].get("id"))
        for workspace in memberships:
            workspace_id = workspace.get("id")
            if workspace_id not in selected_ids:
                continue
            setup = get_workspace_setup_state(workspace_id) or {}
            if setup.get("step") != "completed":
                errors.append(f"راه‌اندازی رسانه «{workspace.get('name') or workspace_id}» کامل نیست")
                continue
            member = get_workspace_member(workspace_id, user["id"]) or {}
            if member.get("status") != "active" or member.get("role") not in {
                "owner", "manager", "publisher"
            }:
                errors.append(f"مجوز انتشار رسانه «{workspace.get('name') or workspace_id}» معتبر نیست")
                continue
            for destination in list_verified_active_destinations(workspace_id) or []:
                targets.append(PublicationTarget(
                    key=f"workspace:{workspace_id}:destination:{destination['id']}",
                    kind="workspace",
                    platform=str(destination.get("platform") or "telegram"),
                    external_id=str(destination.get("external_id") or ""),
                    workspace_id=workspace_id,
                    destination_id=destination.get("id"),
                    destination=dict(destination),
                ))

    # One physical channel must receive a source item only once, even if it is
    # reachable through both the Legacy adapter and a Workspace destination.
    deduplicated: Dict[Tuple[str, str], PublicationTarget] = {}
    for target in targets:
        identity = (target.platform, _normalise_external_id(target.external_id))
        previous = deduplicated.get(identity)
        if previous is None or (previous.kind == "legacy" and target.kind == "workspace"):
            deduplicated[identity] = target
    return list(deduplicated.values()), errors
