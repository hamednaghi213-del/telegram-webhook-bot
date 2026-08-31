"""Deterministic, production-agnostic planner for canonical media backfills."""

from copy import deepcopy
from typing import Dict, Iterable, List

from core.canonical_media import canonical_destination_key


def _media_key(row: Dict) -> str:
    return str(row.get("media_key") or "").strip()


def build_backfill_plan(snapshot: Dict, mappings: Iterable[Dict]) -> Dict:
    """Return an idempotent dry-run plan; never contacts a database."""
    current = deepcopy(snapshot or {})
    mappings = [dict(row) for row in mappings]
    existing_destinations = {
        canonical_destination_key(row.get("platform"), row.get("external_id")): row
        for row in current.get("destinations", [])
        if row.get("status") != "removed"
    }
    existing_media = {
        str(row.get("identity_key") or ""): row
        for row in current.get("media_identities", [])
        if row.get("identity_key")
    }
    existing_members = {
        (int(row["media_identity_id"]), int(row["user_id"]))
        for row in current.get("media_members", [])
        if row.get("status") == "active"
    }
    existing_associations = {
        int(row["destination_id"]): row
        for row in current.get("workspace_destinations", [])
        if row.get("status") == "active"
    }

    conflicts: List[Dict] = []
    inserts = {"media_identities": [], "destinations": [], "media_members": [], "associations": []}
    updates = {"associations": [], "legacy_preferences": []}
    symbolic_media = {}
    symbolic_destinations = {}
    seen_mapping = {}
    seen_workspace = {}

    for mapping in mappings:
        key = canonical_destination_key(mapping.get("platform"), mapping.get("external_id"))
        media_key = _media_key(mapping)
        if not key[1] or not media_key:
            conflicts.append({"type": "invalid_mapping", "mapping": mapping})
            continue
        previous_media_key = seen_mapping.setdefault(key, media_key)
        if previous_media_key != media_key:
            conflicts.append({
                "type": "physical_destination_media_conflict",
                "identity": key,
                "media_keys": sorted({previous_media_key, media_key}),
            })
            continue
        previous_workspace = seen_workspace.setdefault(key, int(mapping["workspace_id"]))
        if previous_workspace != int(mapping["workspace_id"]):
            conflicts.append({
                "type": "physical_destination_group_conflict",
                "identity": key,
                "workspace_ids": sorted({previous_workspace, int(mapping["workspace_id"])}),
            })
            continue
        if not mapping.get("access_verified"):
            conflicts.append({
                "type": "unverified_access",
                "identity": key,
                "user_id": mapping.get("user_id"),
            })
            continue

        media = existing_media.get(media_key) or symbolic_media.get(media_key)
        if not media:
            media = {
                "ref": f"media:{media_key}",
                "identity_key": media_key,
                "media_name": mapping.get("media_name"),
                "hashtag": mapping.get("hashtag", ""),
                "channel_tag": mapping.get("channel_tag", ""),
                "publication_icons": list(mapping.get("publication_icons") or []),
                "publication_profile": dict(mapping.get("publication_profile") or {}),
            }
            symbolic_media[media_key] = media
            inserts["media_identities"].append(media)

        destination = existing_destinations.get(key) or symbolic_destinations.get(key)
        if destination and destination.get("media_identity_id") not in (None, media.get("id")):
            conflicts.append({
                "type": "existing_destination_media_conflict",
                "identity": key,
                "destination_id": destination.get("id"),
            })
            continue
        if not destination:
            destination = {
                "ref": f"destination:{key[0]}:{key[1]}",
                "media_ref": media.get("id") or media["ref"],
                "platform": key[0],
                "external_id": mapping.get("external_id"),
                "normalized_external_id": key[1],
            }
            symbolic_destinations[key] = destination
            inserts["destinations"].append(destination)

        media_id = media.get("id")
        member_key = (int(media_id), int(mapping["user_id"])) if media_id is not None else None
        if member_key not in existing_members:
            candidate = {
                "media_ref": media_id or media["ref"],
                "user_id": int(mapping["user_id"]),
                "role": mapping.get("media_role", "publisher"),
            }
            if candidate not in inserts["media_members"]:
                inserts["media_members"].append(candidate)

        destination_id = destination.get("id")
        association = existing_associations.get(int(destination_id)) if destination_id is not None else None
        if association and int(association["workspace_id"]) != int(mapping["workspace_id"]):
            updates["associations"].append({
                "destination_id": destination_id,
                "from_workspace_id": int(association["workspace_id"]),
                "to_workspace_id": int(mapping["workspace_id"]),
            })
        elif not association:
            candidate = {
                "destination_ref": destination_id or destination["ref"],
                "workspace_id": int(mapping["workspace_id"]),
            }
            if candidate not in inserts["associations"]:
                inserts["associations"].append(candidate)

    safe = not conflicts
    rollback = {
        "delete_inserted_refs": [
            row.get("ref") for table in ("destinations", "media_identities")
            for row in reversed(inserts[table]) if row.get("ref")
        ],
        "restore_associations": [
            {
                "destination_id": row["destination_id"],
                "workspace_id": row["from_workspace_id"],
            }
            for row in updates["associations"]
        ],
        "legacy_rows_deleted": 0,
    }
    return {
        "dry_run": True,
        "safe_to_apply": safe,
        "conflicts": conflicts,
        "inserts": inserts if safe else {key: [] for key in inserts},
        "updates": updates if safe else {key: [] for key in updates},
        "deletes": [],
        "rollback": rollback if safe else {},
    }


def apply_backfill_plan(plan: Dict, transaction) -> Dict:
    """Apply through a caller-provided transaction; rollback on any failure."""
    if not plan.get("safe_to_apply") or plan.get("conflicts"):
        raise ValueError("Backfill conflicts must be resolved before apply")
    transaction.begin()
    try:
        result = transaction.apply(plan)
        transaction.verify(plan, result)
        transaction.commit()
        return result
    except Exception:
        transaction.rollback()
        raise
