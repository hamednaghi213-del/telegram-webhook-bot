"""
Phase 4A — Workspace Setup Coordinator
========================================
Implements the one-time guided setup wizard for a new workspace.

Flow (owner perspective):
  /start  →  detect incomplete setup  →  /setup
  Step 1: register publication channel(s)  (/addchannel @id)
  Step 2: optionally register Bale channel
  Step 3: configure workspace branding     (/setbranding name hashtag tag)
  Step 4: confirm a branding sample
  Step 5: add member (optional)            (/addmember TELEGRAM_ID role)
  Step 6: finish                           (/finishsetup)

State machine (persisted in workspace_setup_state table):
  not_started  →  in_progress (step=setup_channel)
               →  in_progress (step=setup_bale_channel)
               →  in_progress (step=setup_branding)
               →  in_progress (step=setup_branding_sample)
               →  in_progress (step=setup_member)
               →  completed

Rules:
- State persists in DB; never in process memory.
- Idempotent: repeated calls never duplicate records.
- Interrupted setup resumes from current_step_key.
- Completed setup is never restarted automatically.
- Legacy tenant users are completely unaffected (no import
  or call path touches get_tenant or legacy branding).
- Publication routing is NOT changed here.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from core.workspace_pairing import has_required_telegram_destination

from core.database import (
    add_workspace_member,
    register_setup_destination_canonical,
    get_destination_branding,
    get_destination_verification,
    get_or_create_user_by_telegram_id,
    get_workspace_branding,
    get_workspace_member,
    get_workspace_setup_state,
    list_workspace_destinations,
    upsert_destination_branding,
    upsert_destination_verification,
    upsert_workspace_branding,
    update_workspace_branding_sample,
    upsert_workspace_setup_state,
)

logger = logging.getLogger(__name__)


class DestinationOwnedElsewhereError(ValueError):
    """A canonical destination already belongs to another workspace."""

# Ordered setup steps; Bale and member steps are optional.
SETUP_STEPS: List[str] = [
    "setup_channel",
    "setup_bale_channel",
    "setup_branding",
    "setup_branding_sample",
    "setup_member",
]

# Roles assignable to non-owner members in the setup wizard.
ASSIGNABLE_ROLES = {"manager", "publisher", "writer"}


# =========================================================
# SETUP STATE HELPERS
# =========================================================

def get_or_init_setup_state(workspace_id: int) -> Dict[str, Any]:
    """Return existing state, or create a not_started record."""
    state = get_workspace_setup_state(workspace_id)
    if not state:
        state = upsert_workspace_setup_state(
            workspace_id, "not_started", None
        )
    return state or {"workspace_id": workspace_id, "step": "not_started", "current_step_key": None}


def start_setup(workspace_id: int) -> Dict[str, Any]:
    """Begin (or resume) setup.  Returns updated state."""
    state = get_workspace_setup_state(workspace_id)
    if state and state.get("step") == "completed":
        return state
    if state and state.get("step") == "in_progress":
        return state  # Resume from current_step_key
    # Transition not_started → in_progress at first step
    return upsert_workspace_setup_state(
        workspace_id, "in_progress", "setup_channel"
    )


def advance_to_step(workspace_id: int, step_key: str) -> Dict[str, Any]:
    """Move to a specific step within the setup flow."""
    return upsert_workspace_setup_state(
        workspace_id, "in_progress", step_key
    )


def is_setup_completed(workspace_id: int) -> bool:
    """Return True iff setup has been marked completed."""
    state = get_workspace_setup_state(workspace_id)
    return bool(state and state.get("step") == "completed")


# =========================================================
# STEP 1: CHANNEL REGISTRATION
# =========================================================

def register_channel_destination(
    workspace_id: int,
    external_id: str,
    name: str,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Register a Telegram channel as a publication destination.

    Returns (destination_row, is_duplicate).

    A physical channel is identified globally by platform and normalized ID.
    It is never moved away from another active workspace by this flow.
    """
    dest, outcome = register_setup_destination_canonical(
        workspace_id=workspace_id,
        platform="telegram",
        external_id=str(external_id).strip(),
        name=(name or external_id).strip(),
    )
    if outcome == "owned_elsewhere":
        raise DestinationOwnedElsewhereError(
            "این کانال قبلاً به گروه رسانه‌ای دیگری متصل شده است."
        )
    if outcome == "identity_conflict":
        raise DestinationOwnedElsewhereError(
            "چند کانال قدیمی با این شناسه وجود دارد؛ اتصال نیاز به بررسی دارد."
        )
    if outcome == "same_workspace":
        return dest, True
    if dest and not get_destination_verification(dest["id"]):
        upsert_destination_verification(
            dest["id"], verified=False,
            verification_note="pending_admin_verification",
        )
    return dest, False


def register_bale_destination(
    workspace_id: int,
    external_id: str,
    name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Register an optional Bale destination using the central Bale bot."""
    external_id = str(external_id).strip()
    destination, outcome = register_setup_destination_canonical(
        workspace_id=workspace_id,
        platform="bale",
        external_id=external_id,
        name=(name or external_id).strip(),
    )
    if outcome == "owned_elsewhere":
        raise DestinationOwnedElsewhereError(
            "این کانال بله قبلاً به گروه رسانه‌ای دیگری متصل شده است."
        )
    if outcome == "identity_conflict":
        raise DestinationOwnedElsewhereError(
            "چند کانال بله قدیمی با این شناسه وجود دارد؛ اتصال نیاز به بررسی دارد."
        )
    if outcome == "same_workspace":
        return destination, True
    if destination and not get_destination_verification(destination["id"]):
        upsert_destination_verification(
            destination["id"], verified=False,
            verification_note="pending_bale_admin_verification",
        )
    return destination, False


# =========================================================
# STEP 2: WORKSPACE BRANDING
# =========================================================

def save_workspace_branding(
    workspace_id: int,
    media_name: str,
    hashtag: str,
    channel_tag: str,
) -> Optional[Dict[str, Any]]:
    """
    Save workspace-level branding.

    Branding belongs to the WORKSPACE, not the Telegram user.
    Does NOT touch legacy tenant columns.
    """
    branding = upsert_workspace_branding(
        workspace_id,
        media_name=media_name,
        hashtag=hashtag,
        channel_tag=channel_tag,
    )
    logger.info(
        "Workspace branding saved | "
        f"workspace={workspace_id} media_name={media_name}"
    )
    return branding


# =========================================================
# DESTINATION BRANDING (per-channel override)
# =========================================================

def get_branding_for_destination(
    destination_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Return the destination-level branding record for *destination_id*, or None.

    Call site can fall back to workspace_branding when this returns None.
    Does NOT modify any record.
    """
    return get_destination_branding(destination_id)


def save_destination_branding(
    destination_id: int,
    hashtag: str = "",
    channel_tag: str = "",
    custom_footer: Optional[str] = None,
    footer_enabled: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Create or update per-destination branding.

    - destination_id must already exist in publication_destinations.
    - custom_footer is optional; pass None to leave it unset.
    - footer_enabled controls whether the footer text is applied.
    - Does NOT touch workspace_branding or legacy tenant columns.
    - Does NOT activate publication routing.
    """
    branding = upsert_destination_branding(
        destination_id=destination_id,
        hashtag=hashtag,
        channel_tag=channel_tag,
        custom_footer=custom_footer,
        footer_enabled=footer_enabled,
    )
    logger.info(
        "Destination branding saved | "
        f"destination_id={destination_id} footer_enabled={footer_enabled}"
    )
    return branding


# =========================================================
# STEP 3: MEMBER MANAGEMENT
# =========================================================

def add_member_to_workspace(
    workspace_id: int,
    telegram_user_id: int,
    role: str = "writer",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Add a Telegram user as a workspace member.

    Multi-workspace safe: the same Telegram user may belong to multiple
    workspaces.  No global workspace selection is stored on the user.

    Returns (membership_row, error_message).
    error_message is None on success, or 'duplicate' / reason string.
    """
    if role not in ASSIGNABLE_ROLES:
        return None, f"نقش نامعتبر: {role}. نقش‌های مجاز: {', '.join(sorted(ASSIGNABLE_ROLES))}"

    user = get_or_create_user_by_telegram_id(int(telegram_user_id))
    if not user:
        return None, "کاربر یافت نشد"

    existing = get_workspace_member(workspace_id, user["id"])
    if existing:
        return existing, "duplicate"

    membership = add_workspace_member(
        workspace_id=workspace_id,
        user_id=user["id"],
        role=role,
        status="active",
    )
    logger.info(
        "Member added to workspace | "
        f"workspace={workspace_id} telegram_user={telegram_user_id} role={role}"
    )
    return membership, None


# =========================================================
# SETUP COMPLETION
# =========================================================

def _telegram_destination_integrity_ready(
    destinations: List[Dict[str, Any]],
) -> bool:
    """
    Return True when setup has a valid Telegram destination.

    Legacy mode keeps the historical completion rule unchanged.
    Canonical mode requires an active and verified Telegram destination with
    an active workspace association and a canonical media identity.
    """
    import importlib

    database = importlib.import_module("core.database")
    canonical_enabled = bool(
        getattr(database, "canonical_media_enabled", lambda: False)()
    )
    if not canonical_enabled:
        return has_required_telegram_destination(destinations)

    for destination in destinations:
        if destination.get("platform") != "telegram":
            continue
        if destination.get("status") != "active":
            continue
        if destination.get("association_status", "active") != "active":
            continue
        if destination.get("media_identity_id") is None:
            continue

        verification = get_destination_verification(destination["id"]) or {}
        if not verification.get("verified"):
            continue

        return True

    return False

def can_complete_setup(
    workspace_id: int,
    owner_user_id: int,
) -> Tuple[bool, Optional[str]]:
    """
    Check all minimum requirements for setup completion.

    Requires:
    1. Active owner membership
    2. Workspace branding with at least a media_name
    3. A confirmed branding sample
    4. At least one Telegram destination with valid canonical integrity
    """
    member = get_workspace_member(workspace_id, owner_user_id)
    if not member or member.get("role") != "owner" or member.get("status") != "active":
        return False, "عضویت مالک فعال یافت نشد"

    branding = get_workspace_branding(workspace_id)
    if not branding or not (branding.get("media_name") or "").strip():
        return False, "نام رسانه تنظیم نشده است. ابتدا برندینگ را تنظیم کنید"

    setup_state = get_workspace_setup_state(workspace_id) or {}
    if setup_state.get("branding_sample_status") != "confirmed":
        return False, "نمونه پیام برندینگ هنوز تأیید نشده است"

    destinations = list_workspace_destinations(workspace_id, include_removed=False)
    if not has_required_telegram_destination(destinations):
        return False, "حداقل یک کانال تلگرام اضافه کنید"

    if not _telegram_destination_integrity_ready(destinations):
        return (
            False,
            "اتصال کانال تلگرام کامل نیست. کانال باید فعال، تأییدشده و به هویت رسانه متصل باشد",
        )

    return True, None


def complete_setup(
    workspace_id: int,
    owner_user_id: int,
) -> Tuple[bool, Optional[str]]:
    """
    Mark setup as completed if all requirements are satisfied.

    Returns (success, error_message).
    """
    if is_setup_completed(workspace_id):
        return True, None

    ok, reason = can_complete_setup(workspace_id, owner_user_id)
    if not ok:
        return False, reason

    upsert_workspace_setup_state(workspace_id, "completed", None)
    logger.info(f"Setup completed | workspace={workspace_id}")
    return True, None

