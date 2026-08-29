"""
Phase 4A — Workspace Setup Coordinator
========================================
Implements the one-time guided setup wizard for a new workspace.

Flow (owner perspective):
  /start  →  detect incomplete setup  →  /setup
  Step 1: register publication channel(s)  (/addchannel @id)
  Step 2: configure workspace branding     (/setbranding name hashtag tag)
  Step 3: confirm a branding sample
  Step 4: add member (optional)            (/addmember TELEGRAM_ID role)
  Step 5: finish                           (/finishsetup)

State machine (persisted in workspace_setup_state table):
  not_started  →  in_progress (step=setup_channel)
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
    create_publication_destination,
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
    update_workspace_name,
    update_workspace_branding_sample,
    upsert_workspace_setup_state,
)

logger = logging.getLogger(__name__)

# Ordered setup steps; member step is optional.
SETUP_STEPS: List[str] = [
    "setup_channel",
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

    Safety:
    - Duplicate external_id is detected and rejected.
    - Destination stored with status='inactive' (NOT ready for publication).
    - A destination_verification record is created with verified=False.
    - Phase 4B will handle actual Telegram admin verification via the API.
    """
    existing = list_workspace_destinations(workspace_id, include_removed=False)
    for dest in existing:
        if (
            dest.get("platform") == "telegram"
            and dest.get("external_id") == str(external_id).strip()
        ):
            logger.info(
                "Duplicate channel registration blocked | "
                f"workspace={workspace_id} external_id={external_id}"
            )
            return dest, True

    dest = create_publication_destination(
        workspace_id=workspace_id,
        platform="telegram",
        destination_type="channel",
        name=(name or external_id).strip(),
        external_id=str(external_id).strip(),
        status="inactive",   # NOT active until verified (Phase 4B)
        is_default=False,
    )
    if dest:
        upsert_destination_verification(
            dest["id"],
            verified=False,
            verification_note="pending_admin_verification",
        )
        logger.info(
            "Channel registered (unverified) | "
            f"workspace={workspace_id} dest_id={dest['id']} "
            f"external_id={external_id}"
        )
    return dest, False


def register_bale_destination(
    workspace_id: int,
    external_id: str,
    name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Register an optional Bale destination using the central Bale bot."""
    external_id = str(external_id).strip()
    existing = list_workspace_destinations(workspace_id, include_removed=False)
    for destination in existing:
        if (
            destination.get("platform") == "bale"
            and destination.get("external_id") == external_id
        ):
            return destination, True
    destination = create_publication_destination(
        workspace_id=workspace_id,
        platform="bale",
        destination_type="channel",
        name=(name or external_id).strip(),
        external_id=external_id,
        status="inactive",
        is_default=False,
    )
    if destination:
        upsert_destination_verification(
            destination["id"],
            verified=False,
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
    update_workspace_name(workspace_id, media_name)
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
    4. At least one registered destination
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
