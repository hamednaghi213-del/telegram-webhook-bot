"""Pure canonical Media Identity rules shared by runtime and migration tooling."""

from typing import Dict, Iterable, List, Optional, Tuple


PUBLISH_ROLES = {"owner", "manager", "publisher"}
MANAGE_ROLES = {"owner", "manager"}


def normalize_external_identifier(value: object) -> str:
    return str(value or "").strip().lstrip("@").casefold()


def canonical_destination_key(platform: object, external_id: object) -> Tuple[str, str]:
    return str(platform or "").strip().casefold(), normalize_external_identifier(external_id)


def media_access_allows(member: Optional[Dict], *, manage: bool = False) -> bool:
    if not member or member.get("status") != "active":
        return False
    allowed = MANAGE_ROLES if manage else PUBLISH_ROLES
    return member.get("role") in allowed


def group_access_allows(member: Optional[Dict], *, manage: bool = False) -> bool:
    if not member or member.get("status") != "active":
        return False
    allowed = MANAGE_ROLES if manage else PUBLISH_ROLES
    return (member.get("member_role") or member.get("role")) in allowed


def canonical_target_is_ready(row: Dict) -> bool:
    """Group branding/setup is intentionally not part of publication readiness."""
    verification = row.get("verification") or row.get("destination_verification") or {}
    if isinstance(verification, list):
        verification = verification[0] if verification else {}
    return bool(
        row.get("association_status", "active") == "active"
        and row.get("status") == "active"
        and row.get("media_status", "active") == "active"
        and verification.get("verified")
    )


def resolve_media_branding(media: Dict, destination_override: Optional[Dict] = None) -> Dict:
    """Resolve identity from Media first, then explicit platform override."""
    result = {
        "media_name": str(media.get("media_name") or "").strip(),
        "hashtag": str(media.get("hashtag") or "").strip(),
        "channel_tag": str(media.get("channel_tag") or "").strip(),
        "publication_icons": list(media.get("publication_icons") or []),
        "icons_enabled": bool(media.get("icons_enabled", False)),
        "publication_profile": dict(media.get("publication_profile") or {}),
        "custom_footer": "",
        "footer_enabled": False,
    }
    override = destination_override or {}
    for field in ("hashtag", "channel_tag", "custom_footer"):
        if override.get(field) not in (None, ""):
            result[field] = str(override[field]).strip()
    if override.get("publication_icons") is not None:
        result["publication_icons"] = list(override.get("publication_icons") or [])
        result["icons_enabled"] = bool(override.get("icons_enabled", False))
    if override.get("publication_profile") is not None:
        result["publication_profile"] = dict(override.get("publication_profile") or {})
    if override.get("footer_enabled") is not None:
        result["footer_enabled"] = bool(override.get("footer_enabled"))
    return result


def visible_group_ids(associations: Iterable[Dict]) -> set:
    """Inactive physical destinations still keep a group visible."""
    return {
        int(row["workspace_id"])
        for row in associations
        if row.get("association_status", row.get("status", "active")) == "active"
    }


def deduplicate_physical_destinations(rows: Iterable[Dict]) -> List[Dict]:
    unique = {}
    for row in rows:
        key = canonical_destination_key(row.get("platform"), row.get("external_id"))
        if key[1] and key not in unique:
            unique[key] = row
    return list(unique.values())
