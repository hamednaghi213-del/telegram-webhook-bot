"""Compatibility-only bridge from legacy tenant destinations to Workspaces."""

from typing import Dict, Iterable, List, Tuple

from core.workspace_destinations import canonical_destination_identity, can_manage_destinations

_PLACEHOLDERS = {"", "@channel", "channel"}


def legacy_destination_specs(tenant: Dict) -> List[Dict]:
    specs = []
    for platform, field in (("telegram", "telegram_channel"), ("bale", "bale_channel")):
        external_id = str(tenant.get(field) or "").strip()
        if external_id.casefold() in _PLACEHOLDERS:
            continue
        specs.append({
            "platform": platform,
            "external_id": external_id,
            "tenant_id": int(tenant["id"]),
            "move_key": f"l{int(tenant['id'])}{platform[0]}",
            "legacy_source": True,
            "status": "active",
        })
    return specs


def _ambiguous_legacy_identities(database, tenant: Dict) -> set:
    """Return identities claimed by another Legacy owner; fail closed on ambiguity."""
    list_tenants = getattr(database, "get_all_tenants", None)
    if not list_tenants:
        return set()
    current_owner = str(tenant.get("user_id") or "")
    current_id = int(tenant["id"])
    identities = {canonical_destination_identity(row) for row in legacy_destination_specs(tenant)}
    ambiguous = set()
    for other in list_tenants() or []:
        if int(other.get("id") or -1) == current_id:
            continue
        if str(other.get("user_id") or "") == current_owner:
            continue
        other_identities = {
            canonical_destination_identity(row) for row in legacy_destination_specs(other)
        }
        ambiguous.update(identities.intersection(other_identities))
    return ambiguous


def list_legacy_move_candidates(database, user_id: int, target_workspace_id: int) -> List[Dict]:
    get_user = getattr(database, "get_user_by_id", None)
    get_tenant = getattr(database, "get_tenant", None)
    if not get_user or not get_tenant:
        return []
    user = get_user(user_id)
    tenant = get_tenant(user["telegram_user_id"]) if user else None
    if not tenant:
        return []
    manageable = {
        int(row["id"]): row
        for row in database.list_user_workspace_memberships(user_id)
        if row.get("status") == "active" and can_manage_destinations(row.get("member_role"))[0]
    }
    if int(target_workspace_id) not in manageable:
        raise ValueError("گروه مقصد معتبر نیست یا اجازه مدیریت آن را ندارید.")
    canonical_rows = database.list_publication_destinations_for_workspaces(list(manageable))
    canonical_keys = {canonical_destination_identity(row) for row in canonical_rows}
    ambiguous_keys = _ambiguous_legacy_identities(database, tenant)
    label = str(tenant.get("channel_tag") or tenant.get("telegram_channel") or "رسانه").strip()
    candidates = []
    for spec in legacy_destination_specs(tenant):
        identity = canonical_destination_identity(spec)
        if identity in canonical_keys or identity in ambiguous_keys:
            continue
        item = dict(spec)
        item["source_workspace_name"] = label
        candidates.append(item)
    return candidates


def claim_legacy_destinations(
    database,
    user_id: int,
    target_workspace_id: int,
    move_keys: Iterable[str],
) -> List[Dict]:
    """Fail-safe claim: canonical first, Legacy suppression last."""
    user = database.get_user_by_id(user_id)
    tenant = database.get_tenant(user["telegram_user_id"]) if user else None
    if not tenant:
        raise ValueError("رسانه قابل انتقالی یافت نشد.")
    manageable = {
        int(row["id"]): row
        for row in database.list_user_workspace_memberships(user_id)
        if row.get("status") == "active" and can_manage_destinations(row.get("member_role"))[0]
    }
    if int(target_workspace_id) not in manageable:
        raise ValueError("گروه مقصد معتبر نیست یا اجازه مدیریت آن را ندارید.")
    specs = {row["move_key"]: row for row in legacy_destination_specs(tenant)}
    requested = list(dict.fromkeys(str(key) for key in move_keys))
    if not requested or any(key not in specs for key in requested):
        raise ValueError("مقصد Legacy معتبر نیست.")
    ambiguous_keys = _ambiguous_legacy_identities(database, tenant)
    if any(canonical_destination_identity(specs[key]) in ambiguous_keys for key in requested):
        raise ValueError("مالکیت این مقصد Legacy مبهم است و انتقال خودکار امن نیست.")

    canonical = bool(getattr(database, "canonical_media_enabled", lambda: False)())
    rows = (
        database.list_canonical_destinations_for_workspaces(list(manageable))
        if canonical
        else database.list_publication_destinations_for_workspaces(list(manageable))
    )
    by_identity = {canonical_destination_identity(row): row for row in rows}
    claimed = []
    for key in requested:
        spec = specs[key]
        identity = canonical_destination_identity(spec)
        existing = by_identity.get(identity)
        if canonical:
            existing = database.claim_legacy_destination_canonical(
                user_id=user_id,
                workspace_id=int(target_workspace_id),
                identity_key=f"legacy-tenant:{int(tenant['id'])}",
                platform=spec["platform"],
                external_id=spec["external_id"],
                media_name=str(tenant.get("channel_tag") or spec["external_id"]).strip(),
                hashtag=str(tenant.get("hashtag") or "").strip(),
                channel_tag=str(tenant.get("channel_tag") or "").strip(),
            )
        elif existing:
            if int(existing["workspace_id"]) != int(target_workspace_id):
                moved = database.move_publication_destinations([existing["id"]], target_workspace_id)
                existing = moved[0]
        else:
            existing = database.create_publication_destination(
                workspace_id=int(target_workspace_id),
                platform=spec["platform"],
                destination_type="channel",
                name=spec["external_id"],
                external_id=spec["external_id"],
                status="active",
                is_default=False,
            )
        by_identity[identity] = existing
        claimed.append(existing)

    database.select_workspace(user_id, int(target_workspace_id))
    target_rows = (
        database.list_canonical_destinations_for_workspaces([int(target_workspace_id)])
        if canonical
        else database.list_workspace_destinations(int(target_workspace_id))
    )
    target_keys = {canonical_destination_identity(row) for row in target_rows}
    legacy_keys = {canonical_destination_identity(row) for row in specs.values()}
    if legacy_keys.issubset(target_keys):
        database.set_legacy_workspace_selected(user_id, False)
    return claimed


def legacy_is_fully_canonical(tenant: Dict, destinations: Iterable[Dict]) -> bool:
    legacy_keys = {canonical_destination_identity(row) for row in legacy_destination_specs(tenant)}
    canonical_keys = {canonical_destination_identity(row) for row in destinations}
    return bool(legacy_keys) and legacy_keys.issubset(canonical_keys)
