"""Deterministic, production-agnostic planner for canonical media backfills."""

from copy import deepcopy
from typing import Dict, Iterable, List, Tuple

from core.canonical_media import canonical_destination_key


BLOCKED_BRANDING = "BLOCKED_BRANDING"
BLOCKED_ACCESS = "BLOCKED_ACCESS"
BLOCKED_WORKSPACE = "BLOCKED_WORKSPACE"
BLOCKED_IDENTITY = "BLOCKED_IDENTITY"
BLOCKED_AUTHORIZATION = "BLOCKED_AUTHORIZATION"
NO_MIGRATION_REQUIRED = "NO_MIGRATION_REQUIRED"

INSERT_TABLES = ("media_identities", "destinations", "media_members", "associations")
UPDATE_TABLES = ("media_identities", "destinations", "associations", "legacy_preferences")


def _media_key(row: Dict) -> str:
    return str(row.get("media_key") or "").strip()


def _empty_writes() -> Dict:
    return {
        "inserts": {name: [] for name in INSERT_TABLES},
        "updates": {name: [] for name in UPDATE_TABLES},
        "deletes": [],
    }


def _counts(writes: Dict) -> Dict[str, int]:
    return {
        "inserts": sum(len(rows) for rows in writes["inserts"].values()),
        "updates": sum(len(rows) for rows in writes["updates"].values()),
        "deletes": len(writes["deletes"]),
    }


def _append_unique(rows: List[Dict], row: Dict) -> None:
    if row not in rows:
        rows.append(row)


def _merge_writes(target: Dict, source: Dict) -> None:
    for table in INSERT_TABLES:
        for row in source["inserts"][table]:
            _append_unique(target["inserts"][table], row)
    for table in UPDATE_TABLES:
        for row in source["updates"][table]:
            _append_unique(target["updates"][table], row)


def _block(blockers: List[Dict], status: str, media_key: str, **details) -> None:
    legacy_types = {
        BLOCKED_BRANDING: "branding_conflict",
        BLOCKED_ACCESS: "unverified_access",
        BLOCKED_WORKSPACE: "workspace_conflict",
        BLOCKED_IDENTITY: "identity_conflict",
        BLOCKED_AUTHORIZATION: "authorization_conflict",
    }
    row = {
        "status": status,
        "type": details.pop("conflict_type", legacy_types[status]),
        "media_key": media_key,
        **details,
    }
    if row not in blockers:
        blockers.append(row)


def _branding(mapping: Dict) -> Dict:
    return {
        "media_name": str(mapping.get("media_name") or "").strip(),
        "hashtag": str(mapping.get("hashtag") or "").strip(),
        "channel_tag": str(mapping.get("channel_tag") or "").strip(),
        "publication_icons": list(mapping.get("publication_icons") or []),
        "icons_enabled": bool(mapping.get("icons_enabled", False)),
        "publication_profile": dict(mapping.get("publication_profile") or {}),
    }


def _stable_branding_signature(branding: Dict) -> str:
    import json
    return json.dumps(branding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _destination_update(destination: Dict, media_ref, normalized: str, mapping: Dict):
    fields = {
        "media_identity_id": media_ref,
        "normalized_external_id": normalized,
    }
    if mapping.get("platform_chat_id_verified") and mapping.get("platform_chat_id") not in (None, ""):
        fields["platform_chat_id"] = str(mapping["platform_chat_id"])
    old_values = {field: destination.get(field) for field in fields}
    if old_values == fields:
        return None
    return {"id": int(destination["id"]), "old_values": old_values, "new_values": fields}


def _build_identity_writes(
    rows: List[Dict], existing_media: Dict, existing_destinations: Dict,
    existing_members: set, existing_associations: Dict,
) -> Tuple[Dict, Dict]:
    """Build intended writes for one Media Identity."""
    writes = _empty_writes()
    first = rows[0]
    media_key = _media_key(first)
    desired_branding = _branding(first)
    media = existing_media.get(media_key)
    if media:
        media_ref = int(media["id"])
        old_values = {field: media.get(field) for field in desired_branding}
        if old_values != desired_branding:
            writes["updates"]["media_identities"].append({
                "id": media_ref, "identity_key": media_key,
                "old_values": old_values, "new_values": desired_branding,
            })
    else:
        media = {"ref": f"media:{media_key}", "identity_key": media_key, **desired_branding}
        media_ref = media["ref"]
        writes["inserts"]["media_identities"].append(media)

    planned_destinations = {}
    for mapping in rows:
        key = canonical_destination_key(mapping.get("platform"), mapping.get("external_id"))
        destination = existing_destinations.get(key) or planned_destinations.get(key)
        if not destination:
            destination = {
                "ref": f"destination:{key[0]}:{key[1]}",
                "media_ref": media_ref,
                "workspace_id": int(mapping["workspace_id"]),
                "platform": key[0],
                "external_id": mapping.get("external_id"),
                "normalized_external_id": key[1],
            }
            if mapping.get("platform_chat_id_verified") and mapping.get("platform_chat_id") not in (None, ""):
                destination["platform_chat_id"] = str(mapping["platform_chat_id"])
            planned_destinations[key] = destination
            _append_unique(writes["inserts"]["destinations"], destination)
        elif destination.get("id") is not None:
            update = _destination_update(destination, media_ref, key[1], mapping)
            if update:
                _append_unique(writes["updates"]["destinations"], update)

        user_id = int(mapping["user_id"])
        member_key = (media_ref, user_id) if isinstance(media_ref, int) else None
        if member_key not in existing_members:
            _append_unique(writes["inserts"]["media_members"], {
                "media_ref": media_ref,
                "user_id": user_id,
                "role": mapping.get("media_role", "publisher"),
            })

        destination_ref = destination.get("id") or destination["ref"]
        association = existing_associations.get(int(destination_ref)) if isinstance(destination_ref, int) else None
        workspace_id = int(mapping["workspace_id"])
        if association and int(association["workspace_id"]) != workspace_id:
            _append_unique(writes["updates"]["associations"], {
                "destination_id": destination_ref,
                "from_workspace_id": int(association["workspace_id"]),
                "to_workspace_id": workspace_id,
            })
        elif not association:
            _append_unique(writes["inserts"]["associations"], {
                "destination_ref": destination_ref,
                "workspace_id": workspace_id,
            })
    return writes, media


def build_backfill_plan(snapshot: Dict, mappings: Iterable[Dict]) -> Dict:
    """Return an exact, conflict-first dry-run plan; never contacts a database."""
    current = deepcopy(snapshot or {})
    mappings = [dict(row) for row in mappings]
    active_destinations = {}
    removed_destinations = []
    for row in current.get("destinations", []):
        key = canonical_destination_key(row.get("platform"), row.get("external_id"))
        if row.get("status") == "removed":
            removed_destinations.append(deepcopy(row))
        elif key[1]:
            active_destinations[key] = row
    existing_media = {
        str(row.get("identity_key") or ""): row
        for row in current.get("media_identities", []) if row.get("identity_key")
    }
    existing_members = {
        (int(row["media_identity_id"]), int(row["user_id"]))
        for row in current.get("media_members", []) if row.get("status") == "active"
    }
    existing_associations = {
        int(row["destination_id"]): row
        for row in current.get("workspace_destinations", []) if row.get("status") == "active"
    }

    excluded_routes = []
    grouped: Dict[str, List[Dict]] = {}
    key_to_media: Dict[Tuple[str, str], set] = {}
    for mapping in mappings:
        key = canonical_destination_key(mapping.get("platform"), mapping.get("external_id"))
        if mapping.get("migrate") is False or mapping.get("placeholder"):
            excluded_routes.append({
                "status": NO_MIGRATION_REQUIRED, "identity": list(key),
                "reason": mapping.get("exclusion_reason") or "explicitly excluded",
            })
            continue
        media_key = _media_key(mapping)
        grouped.setdefault(media_key, []).append(mapping)
        key_to_media.setdefault(key, set()).add(media_key)

    executable = _empty_writes()
    conditional = _empty_writes()
    blockers: List[Dict] = []
    identity_statuses = []

    for media_key, rows in grouped.items():
        identity_blockers: List[Dict] = []
        if not media_key or any(not canonical_destination_key(r.get("platform"), r.get("external_id"))[1] for r in rows):
            _block(identity_blockers, BLOCKED_IDENTITY, media_key, reason="invalid media or destination identity")

        if len({_stable_branding_signature(_branding(row)) for row in rows}) > 1:
            _block(identity_blockers, BLOCKED_BRANDING, media_key, reason="inconsistent branding sources")
        for row in rows:
            if row.get("branding_verified") is False or row.get("branding_conflicts"):
                _block(identity_blockers, BLOCKED_BRANDING, media_key,
                       reason=row.get("branding_conflicts") or "branding is not verified")
            if not row.get("access_verified"):
                _block(identity_blockers, BLOCKED_ACCESS, media_key,
                       user_id=row.get("user_id"), reason="media access is not verified")
            if row.get("authorization_verified") is False:
                _block(identity_blockers, BLOCKED_AUTHORIZATION, media_key,
                       user_id=row.get("user_id"), reason="authorization is not verified")
            if row.get("workspace_id") is None or row.get("workspace_verified") is False:
                _block(identity_blockers, BLOCKED_WORKSPACE, media_key,
                       workspace_id=row.get("workspace_id"), reason="workspace association is not verified")
            if row.get("create_workspace_membership"):
                _block(identity_blockers, BLOCKED_AUTHORIZATION, media_key,
                       user_id=row.get("user_id"), reason="planner cannot create workspace membership")

            key = canonical_destination_key(row.get("platform"), row.get("external_id"))
            media_candidates = sorted(value for value in key_to_media.get(key, set()) if value)
            if len(media_candidates) > 1:
                _block(identity_blockers, BLOCKED_IDENTITY, media_key,
                       identity=list(key), media_keys=media_candidates,
                       reason="physical destination maps to multiple media identities",
                       conflict_type="physical_destination_media_conflict")
            destination = active_destinations.get(key)
            existing_media_row = existing_media.get(media_key)
            expected_id = existing_media_row.get("id") if existing_media_row else None
            if destination and destination.get("media_identity_id") not in (None, expected_id):
                _block(identity_blockers, BLOCKED_IDENTITY, media_key,
                       identity=list(key), destination_id=destination.get("id"),
                       reason="existing destination belongs to another media identity")

        workspace_ids = {int(row["workspace_id"]) for row in rows if row.get("workspace_id") is not None}
        if len(workspace_ids) > 1:
            _block(identity_blockers, BLOCKED_WORKSPACE, media_key,
                   workspace_ids=sorted(workspace_ids), reason="physical destinations span proposed groups",
                   conflict_type="physical_destination_group_conflict")

        if media_key and all(row.get("workspace_id") is not None for row in rows):
            intended, _ = _build_identity_writes(
                rows, existing_media, active_destinations, existing_members, existing_associations
            )
        else:
            intended = _empty_writes()
        if identity_blockers:
            _merge_writes(conditional, intended)
            blockers.extend(identity_blockers)
            statuses = sorted({row["status"] for row in identity_blockers})
        else:
            _merge_writes(executable, intended)
            statuses = ["READY"]
        identity_statuses.append({"media_key": media_key, "statuses": statuses})

    executable["counts"] = _counts(executable)
    conditional["counts"] = _counts(conditional)
    rollback = {
        "transaction_scope": "executable plan only",
        "inserted_refs": [
            row.get("ref") for table in ("destinations", "media_identities")
            for row in executable["inserts"][table] if row.get("ref")
        ],
        "existing_business_rows_deleted": 0,
        "protected_tables": [
            "tenants", "workspaces", "workspace_branding",
            "publication_message_links", "history", "retry", "idempotency",
        ],
    }
    return {
        "dry_run": True,
        "safe_to_apply": not blockers,
        "blockers": blockers,
        "conflicts": blockers,
        "identity_statuses": identity_statuses,
        "excluded_routes": excluded_routes,
        "historical_removed_destinations": removed_destinations,
        "executable": executable,
        "conditional": conditional,
        "inserts": executable["inserts"],
        "updates": executable["updates"],
        "deletes": executable["deletes"],
        "counts": executable["counts"],
        "rollback": rollback,
    }


def apply_backfill_plan(plan: Dict, transaction) -> Dict:
    """Apply only an approved executable plan in one caller-provided transaction."""
    if not plan.get("safe_to_apply") or plan.get("blockers") or plan.get("conflicts"):
        raise ValueError("Backfill blockers must be resolved before apply")
    transaction.begin()
    try:
        executable = plan.get("executable") or {
            "inserts": plan.get("inserts", {}),
            "updates": plan.get("updates", {}),
            "deletes": plan.get("deletes", []),
        }
        result = transaction.apply(executable)
        transaction.verify(executable, result)
        transaction.commit()
        return result
    except Exception:
        transaction.rollback()
        raise
