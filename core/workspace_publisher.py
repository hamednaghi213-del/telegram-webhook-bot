"""
Phase 4B — Workspace Publication Path
Parallel to legacy tenant path. Used ONLY for workspace users (no legacy tenant).
"""
import logging
import os
import requests
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TELEGRAM_CAPTION_SAFE_LIMIT = 1000  # matches caption_manager.TELEGRAM_CAPTION_SAFE_LIMIT
TELEGRAM_CAPTION_HARD_LIMIT = 1024
BRANDING_SEPARATOR_COST = 2  # "\n\n"

# MVP publication roles that may publish
PUBLISH_ROLES = frozenset({"owner", "manager", "publisher"})
_LEGACY_PLACEHOLDER_LABELS = frozenset({"@channel", "channel"})

# In-process pending publication store (keyed by chat_id)
# Stores {"destinations": [...], "text": ..., "media_file_id": ...,
#         "media_type": ..., "selected": set()}
_PENDING: Dict[int, Dict] = {}


def build_destination_move_keyboard(
    target_workspace_id: int,
    candidates: List[Dict],
    selected_ids=None,
) -> list:
    """Build a compact, stateless multi-select keyboard for destination moves."""
    selected = {int(value) for value in (selected_ids or [])}
    keyboard = []
    for destination in candidates:
        destination_id = int(destination["id"])
        checked = destination_id in selected
        platform = "تلگرام" if destination.get("platform") == "telegram" else "بله"
        label = (
            f"{'✅' if checked else '⬜'} {destination.get('external_id')} — {platform}"
            f" — {destination.get('source_workspace_name')}"
        )
        keyboard.append([{
            "text": label[:60],
            "callback_data": (
                f"ws:move:pick:{int(target_workspace_id)}:{destination_id}:"
                f"{1 if checked else 0}"
            ),
        }])
    keyboard.append([{
        "text": "✅ انتقال انتخاب‌شده‌ها",
        "callback_data": f"ws:move:confirm:{int(target_workspace_id)}",
    }])
    keyboard.append([{
        "text": "⬅️ بازگشت",
        "callback_data": f"ws:manage:{int(target_workspace_id)}",
    }])
    return keyboard


def selected_destination_ids_from_callback(callback_query: Dict) -> set:
    keyboard = (((callback_query.get("message") or {}).get("reply_markup") or {}).get("inline_keyboard") or [])
    selected = set()
    for row in keyboard:
        for button in row:
            data = str(button.get("callback_data") or "")
            parts = data.split(":")
            if len(parts) == 6 and parts[:3] == ["ws", "move", "pick"] and parts[5] == "1":
                try:
                    selected.add(int(parts[4]))
                except (TypeError, ValueError):
                    pass
    return selected


def build_workspace_management_panel(workspace: Dict, destinations: List[Dict]):
    """Render destination state directly on the workspace management page."""
    workspace_id = int(workspace["id"])
    lines = [f"📁 {workspace.get('name') or workspace_id}", ""]
    keyboard = []
    for destination in sorted(destinations, key=lambda item: int(item.get("id", 0))):
        active = destination.get("status") == "active"
        platform = "تلگرام" if destination.get("platform") == "telegram" else "بله"
        label = f"{'✅' if active else '⬜'} {destination.get('external_id')} — {platform}"
        lines.append(label)
        keyboard.append([{
            "text": label[:60],
            "callback_data": f"ws:dest:toggle:{int(destination['id'])}",
        }])
    if not destinations:
        lines.append("هنوز کانالی در این گروه نیست.")
    lines.extend([
        "",
        "✏️ تغییر نام گروه",
        "➕ افزودن کانال",
        "📥 انتقال کانال موجود",
        "👥 مدیریت اعضا",
        "⚙️ تنظیمات رسانه",
    ])
    keyboard.extend([
        [{"text": "✏️ تغییر نام گروه", "callback_data": f"ws:rename:{workspace_id}"}],
        [{"text": "➕ افزودن کانال", "callback_data": f"ws:addchannel:{workspace_id}"}],
        [{"text": "📥 انتقال کانال موجود", "callback_data": f"ws:move:list:{workspace_id}"}],
        [{"text": "👥 مدیریت اعضا", "callback_data": f"ws:members:{workspace_id}"}],
        [{"text": "⚙️ تنظیمات رسانه", "callback_data": f"ws:settings:{workspace_id}"}],
        [{"text": "⬅️ بازگشت", "callback_data": "ws:back"}],
    ])
    return "\n".join(lines), keyboard


def resolve_legacy_media_label(tenant: Optional[Dict[str, Any]]) -> str:
    """Return a meaningful legacy-media label without exposing setup placeholders."""
    tenant = tenant or {}
    for key in ("telegram_channel", "channel_tag", "bale_channel"):
        value = str(tenant.get(key) or "").strip()
        if value and value.casefold() not in _LEGACY_PLACEHOLDER_LABELS:
            return value

    hashtag = str(tenant.get("hashtag") or "").strip().lstrip("#")
    if hashtag:
        return hashtag.replace("_", " ")
    return "رسانه قدیمی"


def _record_publication_message_link(**payload):
    from core.database import create_publication_message_link
    return create_publication_message_link(**payload)


def sync_edited_channel_post_to_bale(edited_post: Dict[str, Any]) -> bool:
    """Mirror a known Telegram destination edit to its paired Bale message."""
    chat_id = (edited_post.get("chat") or {}).get("id")
    message_id = edited_post.get("message_id")
    if chat_id is None or message_id is None:
        return False

    from core.database import get_publication_message_link
    link = get_publication_message_link(chat_id, message_id)
    if not link:
        logger.info(
            f"Edited Telegram post has no Bale link | chat={chat_id} | message={message_id}"
        )
        return False

    is_caption = link.get("content_kind") == "caption"
    edited_text = (
        edited_post.get("caption") if is_caption else edited_post.get("text")
    )
    if edited_text is None:
        logger.warning(
            f"Edited post content kind mismatch | chat={chat_id} | message={message_id}"
        )
        return False

    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        logger.error("BALE_BOT_TOKEN is not configured for edit sync")
        return False

    from core.bale_forwarder import edit_bale_message
    ok = edit_bale_message(
        link["bale_chat_id"],
        token,
        link["bale_message_id"],
        edited_text,
        is_caption=is_caption,
    )
    if ok:
        logger.info(
            f"Telegram edit mirrored to Bale | tg={chat_id}/{message_id} | "
            f"bale={link['bale_chat_id']}/{link['bale_message_id']}"
        )
    return ok


# =========================================================
# DESTINATION BRANDING COMPOSITION
# =========================================================

def compose_destination_branding(
    destination_id: int,
    workspace_id: int,
    get_dest_branding_fn,
    get_ws_branding_fn,
) -> str:
    """
    Build the final branding string for a single destination.
    Falls back to workspace branding when destination-level branding is absent.
    Destination A and B produce completely independent outputs.
    """
    dest_branding = get_dest_branding_fn(destination_id) or {}

    hashtag = (dest_branding.get("hashtag") or "").strip()
    channel_tag = (dest_branding.get("channel_tag") or "").strip()
    custom_footer = (dest_branding.get("custom_footer") or "").strip()
    footer_enabled = bool(dest_branding.get("footer_enabled", False))

    # Workspace fallback only when destination has no hashtag AND no channel_tag
    if not hashtag and not channel_tag:
        ws_branding = get_ws_branding_fn(workspace_id) or {}
        hashtag = (ws_branding.get("hashtag") or "").strip()
        channel_tag = (ws_branding.get("channel_tag") or "").strip()

    parts = []
    if hashtag:
        parts.append(hashtag)
    if channel_tag:
        parts.append(channel_tag)
    if footer_enabled and custom_footer:
        parts.append(custom_footer)

    return "\n".join(parts)


# =========================================================
# PER-DESTINATION CAPTION BUDGET
# =========================================================

def compute_caption_budget(branding_str: str) -> int:
    """
    Available content characters for a destination given its branding.
    Budget = TELEGRAM_CAPTION_SAFE_LIMIT - len(branding) - separator cost.
    """
    branding_len = len(branding_str or "")
    separator_cost = BRANDING_SEPARATOR_COST if branding_str else 0
    return max(0, TELEGRAM_CAPTION_SAFE_LIMIT - branding_len - separator_cost)


# =========================================================
# CAPTION CONSTRUCTION
# =========================================================

def build_final_caption(content_text: str, branding_str: str) -> str:
    """
    Concatenate content and branding. Enforces absolute Telegram caption limit.
    Does NOT blindly truncate content — caller must provide already-budgeted content.
    """
    content_text = (content_text or "").strip()
    branding_str = (branding_str or "").strip()

    if content_text and branding_str:
        result = f"{content_text}\n\n{branding_str}"
    elif content_text:
        result = content_text
    else:
        result = branding_str

    # Final deterministic safety guard — never exceed the hard Telegram limit
    if len(result) > TELEGRAM_CAPTION_HARD_LIMIT:
        result = result[:TELEGRAM_CAPTION_HARD_LIMIT]

    return result


def fit_content_to_budget(
    content_text: str,
    budget: int,
    is_editorial_finalized: bool = False,
) -> str:
    """
    Return content that fits within *budget* characters.
    If editorial_finalized, does NOT re-summarize — just validates.
    Otherwise uses smart summarizer if available.
    Does NOT blindly truncate.
    """
    if not content_text:
        return ""

    if len(content_text) <= budget:
        return content_text

    if is_editorial_finalized:
        # Do not re-summarize finalized content; return as-is (will exceed, caller handles)
        return content_text

    # Try smart summarizer
    try:
        from core.smart_summarizer import summarize_text_safely
        outcome = summarize_text_safely(content_text, budget)
        shortened = getattr(outcome, "summary_text", outcome)
        if isinstance(shortened, str) and shortened and len(shortened) <= budget:
            return shortened
    except Exception as e:
        logger.warning(f"Smart summarizer error: {e}")

    # No safe summarization available — return original
    return content_text


# =========================================================
# PERMISSION CHECK
# =========================================================

def check_publish_permission(
    workspace_id: int,
    user_db_id: int,
    get_member_fn,
) -> Tuple[bool, Optional[str]]:
    """
    Returns (allowed, error_message).
    Owner/manager/publisher may publish. Writer may not.
    Member must be status=active.
    """
    member = get_member_fn(workspace_id, user_db_id)
    if not member:
        return False, "شما عضو این رسانه نیستید"
    if member.get("status") != "active":
        return False, "عضویت شما در این رسانه فعال نیست"
    if member.get("role") not in PUBLISH_ROLES:
        return False, "شما مجاز به انتشار نیستید"
    return True, None


# =========================================================
# WORKSPACE RESOLUTION
# =========================================================

def resolve_workspace_for_user(
    telegram_user_id: int,
    get_user_fn,
    list_workspaces_fn,
    get_active_preference_fn=None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Resolve the current workspace for a telegram user.
    Returns (workspace_row, error_message).
    If user belongs to exactly one workspace, it is returned automatically.
    If multiple, return error asking user to choose (not implemented yet).
    """
    user = get_user_fn(telegram_user_id)
    if not user:
        return None, None  # Not a workspace user at all

    workspaces = list_workspaces_fn(user["id"])
    if not workspaces:
        return None, None  # No workspaces

    if len(workspaces) == 1:
        return workspaces[0], None

    if get_active_preference_fn:
        preference = get_active_preference_fn(user["id"]) or {}
        active_workspace_id = preference.get("active_workspace_id")
        for workspace in workspaces:
            if workspace.get("id") == active_workspace_id:
                return workspace, None

    # Multiple workspaces — cannot safely determine which one
    return None, "شما عضو چند رسانه هستید. لطفاً رسانه مورد نظر را انتخاب کنید."


def resolve_workspaces_for_user(
    telegram_user_id: int,
    get_user_fn,
    list_workspaces_fn,
    get_active_preference_fn=None,
    list_selected_ids_fn=None,
) -> Tuple[List[Dict], Optional[str]]:
    """
    Resolve workspaces selected explicitly for publication.

    Publication selection and active management context are intentionally
    separate concepts:

    - selected workspace IDs control publication targets
    - active_workspace_id controls management/setup context only

    When an explicit publication-selection provider is available, an active
    workspace must never be restored implicitly after the user unchecked it.
    """
    user = get_user_fn(telegram_user_id)
    if not user:
        return [], None

    workspaces = list_workspaces_fn(user["id"])
    if not workspaces:
        return [], None

    # The publication path supplies list_selected_ids_fn. In that path the
    # checkmarks are authoritative, even when there is only one workspace.
    if list_selected_ids_fn is not None:
        selected_ids = set(list_selected_ids_fn(user["id"]) or [])

        selected = [
            workspace
            for workspace in workspaces
            if workspace.get("id") in selected_ids
        ]

        if selected:
            return selected, None

        return [], (
            "هیچ رسانه‌ای برای انتشار انتخاب نشده است. "
            "لطفاً از /workspaces حداقل یک رسانه را انتخاب کنید."
        )

    # Backward-compatible behavior for older/internal callers that do not
    # provide an explicit publication-selection function.
    if len(workspaces) == 1:
        return workspaces, None

    if get_active_preference_fn:
        preference = get_active_preference_fn(user["id"]) or {}
        if preference.get("context_type") != "legacy":
            active_workspace_id = preference.get("active_workspace_id")
            selected = [
                workspace
                for workspace in workspaces
                if workspace.get("id") == active_workspace_id
            ]
            if selected:
                return selected, None

    return [], "شما عضو چند رسانه هستید. لطفاً حداقل یک رسانه را انتخاب کنید."


def prepare_workspace_display_rows(
    workspaces: List[Dict],
    list_verified_active_destinations_fn,
    get_workspace_branding_fn,
) -> List[Dict]:
    """
    Prepare visible workspace identity consistently.

    Used whenever the /workspaces keyboard is rebuilt, including callbacks.

    Label priority:
    1. workspace_branding.media_name
    2. verified Telegram destination
    3. verified Bale destination
    4. workspace.name
    5. generic workspace ID
    """
    display_workspaces = []

    for workspace in workspaces:
        display_workspace = dict(workspace)

        destinations = (
            list_verified_active_destinations_fn(
                workspace["id"]
            )
            or []
        )

        destinations = sorted(
            destinations,
            key=lambda item: (
                not bool(item.get("is_default")),
                item.get("platform") != "telegram",
                item.get("id") or 0,
            ),
        )

        primary = next(
            (
                item
                for item in destinations
                if item.get("platform") == "telegram"
            ),
            None,
        ) or next(
            (
                item
                for item in destinations
                if item.get("platform") == "bale"
            ),
            None,
        )

        branding = (
            get_workspace_branding_fn(
                workspace["id"]
            )
            or {}
        )

        media_name = (
            branding.get("media_name")
            or ""
        ).strip()

        display_workspace["display_label"] = (
            media_name
            or (primary or {}).get("external_id")
            or workspace.get("name")
            or f"رسانه {workspace['id']}"
        )

        display_workspace["display_platforms"] = sorted({
            str(item.get("platform") or "")
            for item in destinations
            if item.get("platform")
        })
        display_workspace["destination_count"] = len(destinations)

        display_workspaces.append(
            display_workspace
        )

    return display_workspaces


def build_workspace_keyboard(
    workspaces: List[Dict],
    active_workspace_id: Optional[int],
    selected_workspace_ids: Optional[List[int]] = None,
    include_legacy: bool = False,
    legacy_active: bool = False,
    legacy_label: Optional[str] = None,
) -> List[List[Dict]]:
    """Build an inline keyboard for simultaneous workspace selection."""
    keyboard = []
    selected_ids = set(selected_workspace_ids or [])

    # Explicit [] means the user has no workspace selected for publication.
    # Only callers that omit selected_workspace_ids entirely may use the
    # historical active-workspace fallback.
    if (
        selected_workspace_ids is None
        and active_workspace_id is not None
        and not legacy_active
    ):
        selected_ids.add(active_workspace_id)

    if include_legacy:
        legacy_marker = "✅" if legacy_active else "▫️"
        keyboard.append([{
            "text": f"{legacy_marker} {legacy_label or 'رسانه قدیمی'}",
            "callback_data": "ws:legacy",
        }])

    for workspace in workspaces:
        marker = "✅" if workspace.get("id") in selected_ids else "▫️"

        display_label = (
            workspace.get("display_label")
            or workspace.get("name")
            or workspace["id"]
        )

        destination_count = int(workspace.get("destination_count") or 0)
        keyboard.append([
            {
                "text": f"{marker} {display_label} — {destination_count} کانال",
                "callback_data": f"ws:toggle:{workspace['id']}",
            },
            {
                "text": "⚙️",
                "callback_data": f"ws:manage:{workspace['id']}",
            },
        ])

    return keyboard


# =========================================================
# LOW-LEVEL SEND
# =========================================================

def _send_media_to_destination(
    api_url: str,
    channel_id: str,
    file_id: str,
    media_type: str,
    caption: str,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Send a single media item to a Telegram channel. Returns (ok, error)."""
    endpoint_map = {
        "photo": "sendPhoto",
        "video": "sendVideo",
        "document": "sendDocument",
        "voice": "sendVoice",
        "audio": "sendAudio",
    }
    endpoint = endpoint_map.get(media_type)
    if not endpoint:
        return False, f"نوع رسانه پشتیبانی نمی‌شود: {media_type}", None

    payload: Dict[str, Any] = {
        "chat_id": channel_id,
        media_type: file_id,
    }
    if caption:
        payload["caption"] = caption

    try:
        r = requests.post(f"{api_url}/{endpoint}", json=payload, timeout=30)
        data = r.json() or {}
        if r.status_code == 200 and data.get("ok"):
            return True, "", data.get("result") or {}
        err = _extract_error(r)
        return False, err, {
            "status_code": r.status_code,
            "error_code": data.get("error_code"),
            "error": err,
            "operation": endpoint,
        }
    except Exception as e:
        return False, str(e), None


def _send_text_to_destination(
    api_url: str,
    channel_id: str,
    text: str,
    parse_mode: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Send a text message to a Telegram channel. Returns (ok, error)."""
    payload: Dict[str, Any] = {"chat_id": channel_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = requests.post(f"{api_url}/sendMessage", json=payload, timeout=30)
        data = r.json() or {}
        if r.status_code == 200 and data.get("ok"):
            return True, "", data.get("result") or {}
        err = _extract_error(r)
        return False, err, {
            "status_code": r.status_code,
            "error_code": data.get("error_code"),
            "error": err,
            "operation": "sendMessage",
        }
    except Exception as e:
        return False, str(e), None


def _extract_error(response) -> str:
    """Best-effort extraction of a Telegram error description."""
    try:
        data = response.json() or {}
        description = data.get("description")
        if description:
            return str(description)
    except Exception:
        pass
    try:
        return str(response.text)[:200]
    except Exception:
        return "unknown error"


# =========================================================
# MULTI-DESTINATION PUBLICATION
# =========================================================

def publish_to_destinations(
    api_url: str,
    destinations: List[Dict],
    content_text: str,
    media_file_id: Optional[str],
    media_type: Optional[str],
    get_dest_branding_fn,
    get_ws_branding_fn,
    is_editorial_finalized: bool = False,
    record_message_link_fn=None,
    source_key: str = "",
) -> Dict[str, Any]:
    """
    Publish content to a list of destinations.

    Processes source content once (fit_content_to_budget is per-destination).
    Failure of one destination does NOT prevent others.

    Returns {"success": int, "failure": int, "errors": List[str]}.
    """
    # Backward-compatible adapter: legacy callbacks still call this public
    # function, but all processing and sending is owned by the shared engine.
    import hashlib
    import uuid
    from core.content_model import PreparedContent, PublicationTarget
    from core.publication_engine import publish_prepared_content

    targets = [
        PublicationTarget(
            key=f"workspace:{dest['workspace_id']}:destination:{dest['id']}",
            kind="workspace",
            platform=str(dest.get("platform") or "telegram"),
            external_id=str(dest.get("external_id") or ""),
            workspace_id=int(dest["workspace_id"]),
            destination_id=int(dest["id"]),
            destination={
                **dict(dest),
                "_get_dest_branding_fn": get_dest_branding_fn,
                "_get_ws_branding_fn": get_ws_branding_fn,
            },
        )
        for dest in destinations
    ]

    source_material = "|".join([
        content_text or "",
        media_file_id or "",
        media_type or "",
        ",".join(str(dest.get("id")) for dest in destinations),
    ])

    source_key = source_key or (
        "wp:legacy-callback:" + hashlib.sha256(
            (source_material + str(uuid.uuid4())).encode("utf-8")
        ).hexdigest()
    )

    files = (
        [{"type": media_type, "file_id": media_file_id}]
        if media_file_id and media_type
        else []
    )

    shared = publish_prepared_content(
        0,
        api_url,
        PreparedContent(
            main_text=content_text or "",
            neutral_text=content_text or "",
            files=files,
            editorial_finalized=is_editorial_finalized,
            source_key=source_key,
        ),
        targets=targets,
    )

    deliveries = list(shared.get("results") or [])
    successful = [
        item
        for item in deliveries
        if item.status == "succeeded"
    ]
    failed = [
        item
        for item in deliveries
        if item.status != "succeeded"
    ]

    # Preserve the old Telegram↔Bale edit-link behavior only when an actual
    # pair and both primary IDs are available. Never collapse multiple pairs.
    if record_message_link_fn:
        by_workspace: Dict[int, List[Any]] = {}

        for item in successful:
            if item.workspace_id is not None:
                by_workspace.setdefault(
                    item.workspace_id,
                    [],
                ).append(item)

        for workspace_id, items in by_workspace.items():
            telegram = next(
                (
                    item
                    for item in items
                    if item.platform == "telegram"
                ),
                None,
            )

            bale = next(
                (
                    item
                    for item in items
                    if item.platform == "bale"
                ),
                None,
            )

            if (
                telegram
                and bale
                and telegram.primary_message_id
                and bale.primary_message_id
            ):
                record_message_link_fn(
                    workspace_id=workspace_id,
                    telegram_destination_id=telegram.destination_id,
                    telegram_chat_id=telegram.destination_chat_id,
                    telegram_message_id=telegram.primary_message_id,
                    bale_destination_id=bale.destination_id,
                    bale_chat_id=bale.destination_chat_id,
                    bale_message_id=bale.primary_message_id,
                    content_kind="caption" if files else "text",
                )

    return {
        "success": len(successful),
        "failure": len(failed),
        "errors": [
            item.destination_chat_id
            for item in failed
        ],
    }


def format_publish_result(result: Dict[str, Any]) -> str:
    """Format publish result as Persian summary message."""
    success = result.get("success", 0)
    failure = result.get("failure", 0)

    if failure == 0:
        return f"✅ انتشار انجام شد\nموفق: {success}\nناموفق: ۰"

    lines = [
        f"موفق: {success}",
        f"❌ ناموفق: {failure}",
    ]

    errors = result.get("errors") or []

    if errors:
        lines.append(
            "کانال‌های ناموفق: "
            + "، ".join(str(e) for e in errors)
        )

    return "\n".join(lines)


# =========================================================
# PENDING PUBLICATION STATE (in-process, for selection UX)
# =========================================================

def store_pending(
    chat_id: int,
    destinations: List[Dict],
    content_text: str,
    media_file_id: Optional[str],
    media_type: Optional[str],
    source_key: str = "",
) -> None:
    """Store pending publication content for destination selection."""
    _PENDING[chat_id] = {
        "destinations": destinations,
        "text": content_text,
        "media_file_id": media_file_id,
        "media_type": media_type,
        "source_key": source_key,
        "selected": set(
            d["id"]
            for d in destinations
        ),
    }


def get_pending(chat_id: int) -> Optional[Dict]:
    """Retrieve pending publication state."""
    return _PENDING.get(chat_id)


def clear_pending(chat_id: int) -> None:
    """Clear pending publication state."""
    _PENDING.pop(chat_id, None)


def toggle_destination_selection(
    chat_id: int,
    dest_id: int,
) -> bool:
    """Toggle a destination in/out of the selection. Returns new state."""
    pending = _PENDING.get(chat_id)

    if not pending:
        return False

    selected = pending["selected"]

    if dest_id in selected:
        selected.discard(dest_id)
        return False

    selected.add(dest_id)
    return True


def build_selection_keyboard(
    destinations: List[Dict],
    selected_ids: set,
) -> List[List[Dict]]:
    """Build inline keyboard for destination selection."""
    rows = []

    for dest in destinations:
        d_id = dest["id"]
        name = (
            dest.get("name")
            or dest.get("external_id", "")
        )
        check = (
            "✅"
            if d_id in selected_ids
            else "☑️"
        )

        rows.append([{
            "text": f"{check} {name}",
            "callback_data": f"wp:toggle:{d_id}",
        }])

    rows.append([
        {
            "text": "📤 انتشار",
            "callback_data": "wp:confirm",
        },
        {
            "text": "❌ لغو",
            "callback_data": "wp:cancel",
        },
    ])

    return rows


# =========================================================
# WEBHOOK ENTRY POINTS
# =========================================================

def _try_workspace_publication(
    chat_id: int,
    msg: Dict,
    req_id: str,
    api_url: str,
) -> bool:
    """
    Attempt workspace publication for a non-legacy user.
    Returns True if this message was handled (even on failure), False if not applicable.
    """
    try:
        from core.database import (
            get_user_by_telegram_id,
            list_user_workspace_memberships,
            list_verified_active_destinations,
            get_workspace_setup_state,
            get_destination_branding,
            get_workspace_branding,
            get_workspace_member,
            get_active_workspace_preference,
            list_selected_workspace_ids,
        )

        user = get_user_by_telegram_id(chat_id)

        if not user:
            return False

        workspaces = list_user_workspace_memberships(
            user["id"]
        )

        if not workspaces:
            return False

        selected_workspaces, workspace_error = (
            resolve_workspaces_for_user(
                chat_id,
                lambda _telegram_id: user,
                lambda _user_id: workspaces,
                get_active_workspace_preference,
                list_selected_workspace_ids,
            )
        )

        if not selected_workspaces:
            _ws_send_message(
                api_url,
                chat_id,
                workspace_error
                or "رسانه فعالی یافت نشد.",
            )
            return True

        destinations = []

        for workspace in selected_workspaces:
            workspace_id = workspace["id"]

            setup_state = get_workspace_setup_state(
                workspace_id
            )

            if (
                not setup_state
                or setup_state.get("step") != "completed"
            ):
                _ws_send_message(
                    api_url,
                    chat_id,
                    (
                        "❌ راه‌اندازی رسانه "
                        f"«{workspace.get('name')}» کامل نیست."
                    ),
                )
                return True

            allowed, err = check_publish_permission(
                workspace_id,
                user["id"],
                get_workspace_member,
            )

            if not allowed:
                _ws_send_message(
                    api_url,
                    chat_id,
                    f"❌ {workspace.get('name')}: {err}",
                )
                return True

            destinations.extend(
                list_verified_active_destinations(
                    workspace_id
                )
            )

        destinations = list({
            dest["id"]: dest
            for dest in destinations
        }.values())

        if not destinations:
            _ws_send_message(
                api_url,
                chat_id,
                (
                    "❌ هیچ کانال تأیید شده‌ای موجود نیست. "
                    "ابتدا کانال را تأیید کنید."
                ),
            )
            return True

        # Extract content from message
        media_type = None
        media_file_id = None

        content_text = (
            msg.get("caption")
            or msg.get("text")
            or ""
        ).strip()

        # Simple media extraction
        for mtype in (
            "photo",
            "video",
            "document",
            "voice",
            "audio",
        ):
            if mtype in msg:
                media_type = mtype

                if mtype == "photo":
                    photos = msg["photo"] or []
                    media_file_id = (
                        photos[-1]["file_id"]
                        if photos
                        else None
                    )
                else:
                    media_file_id = (
                        msg[mtype] or {}
                    ).get("file_id")

                break

        if not content_text and not media_file_id:
            return False

        platforms = {
            destination.get("platform")
            for destination in destinations
        }

        paired_destinations = (
            len(destinations) == 2
            and platforms == {"telegram", "bale"}
        )

        # One Telegram+Bale pair publishes together without another prompt.
        if (
            len(selected_workspaces) > 1
            or len(destinations) == 1
            or paired_destinations
        ):
            result = publish_to_destinations(
                api_url,
                destinations,
                content_text,
                media_file_id,
                media_type,
                get_destination_branding,
                get_workspace_branding,
                record_message_link_fn=(
                    _record_publication_message_link
                ),
                source_key=(
                    f"telegram:{chat_id}:message:"
                    f"{msg.get('message_id')}"
                ),
            )

            _ws_send_message(
                api_url,
                chat_id,
                format_publish_result(result),
            )
            return True

        # Multiple destinations: store pending and show selection
        store_pending(
            chat_id,
            destinations,
            content_text,
            media_file_id,
            media_type,
            source_key=(
                f"telegram:{chat_id}:message:"
                f"{msg.get('message_id')}"
            ),
        )

        pending = get_pending(chat_id)

        keyboard = build_selection_keyboard(
            destinations,
            pending["selected"],
        )

        _ws_send_message_with_keyboard(
            api_url,
            chat_id,
            "📢 انتخاب کانال انتشار:",
            keyboard,
        )

        return True

    except Exception as e:
        logger.exception(
            f"[{req_id}] _try_workspace_publication error: {e}"
        )
        return False


def _handle_workspace_callback(
    callback_query: Dict,
    req_id: str,
    api_url: str,
) -> None:
    """Handle wp: callback queries for destination selection."""
    from core.database import (
        get_user_by_telegram_id,
        get_destination_branding,
        get_workspace_branding,
        set_active_legacy_context,
        set_active_workspace,
        set_legacy_workspace_selected,
        get_active_workspace_preference,
        list_selected_workspace_ids,
        select_workspace,
        deselect_workspace,
        list_user_workspace_memberships,
        get_workspace_setup_state,
    )

    get_tenant = getattr(
        __import__(
            "core.database",
            fromlist=["get_tenant"],
        ),
        "get_tenant",
        lambda _chat_id: None,
    )
    callback_data = (
        callback_query.get("data", "")
        or ""
    )

    callback_id = (
        callback_query.get("id", "")
        or ""
    )

    from_user = (
        callback_query.get("from", {})
        or {}
    )

    chat_id = from_user.get("id")

    if chat_id is None:
        return

    parts = callback_data.split(":")

    if len(parts) < 2:
        return

    if callback_data == "ws:legacy":
        try:
            user = get_user_by_telegram_id(
                chat_id
            )

            if not user:
                raise ValueError(
                    "user not found"
                )

            legacy_tenant = get_tenant(chat_id)

            if not legacy_tenant:
                raise ValueError(
                    "legacy tenant not found"
                )

            preference = (
                get_active_workspace_preference(
                    user["id"]
                )
                or {}
            )

            selected_ids = set(
                list_selected_workspace_ids(
                    user["id"]
                )
            )

            legacy_selected = bool(
                preference.get("legacy_selected")
                if "legacy_selected" in preference
                else (
                    preference.get("context_type")
                    == "legacy"
                )
            )

            if (
                legacy_selected
                and preference.get("context_type")
                == "legacy"
            ):
                if not selected_ids:
                    _ws_answer_callback(
                        api_url,
                        callback_id,
                        "حداقل یک رسانه باید انتخاب بماند",
                    )
                    return

                set_legacy_workspace_selected(
                    user["id"],
                    False,
                )

                text = (
                    "رسانه قدیمی از انتشار هم‌زمان حذف شد"
                )

            else:
                set_active_legacy_context(
                    user["id"]
                )

                text = (
                    "رسانه قدیمی برای مدیریت فعال شد"
                    if legacy_selected
                    else (
                        "رسانه قدیمی به انتشار "
                        "هم‌زمان اضافه شد"
                    )
                )

        except (TypeError, ValueError):
            _ws_answer_callback(
                api_url,
                callback_id,
                "رسانه قدیمی معتبر نیست",
            )
            return

        _ws_answer_callback(
            api_url,
            callback_id,
            text,
        )

        preference = (
            get_active_workspace_preference(
                user["id"]
            )
            or {}
        )

        workspaces = (
            list_user_workspace_memberships(
                user["id"]
            )
        )

        display_workspaces = (
            prepare_workspace_display_rows(
    workspaces,
        getattr(
    __import__(
        "core.database",
        fromlist=["list_verified_active_destinations"],
    ),
    "list_verified_active_destinations",
    lambda _workspace_id: [],
),
                get_workspace_branding,
            )
        )

        legacy_label = (
            (legacy_tenant or {}).get(
                "telegram_channel"
            )
            or (legacy_tenant or {}).get(
                "bale_channel"
            )
            or "رسانه قدیمی"
        )

        keyboard = build_workspace_keyboard(
            display_workspaces,
            preference.get(
                "active_workspace_id"
            ),
            selected_workspace_ids=(
                list_selected_workspace_ids(
                    user["id"]
                )
            ),
            include_legacy=True,
            legacy_active=bool(
                preference.get(
                    "legacy_selected"
                )
            ),
            legacy_label=legacy_label,
        )

        _ws_edit_message_keyboard(
            api_url,
            callback_query,
            keyboard,
        )

        _ws_send_message(
            api_url,
            chat_id,
            f"✅ {text}.",
        )

    elif (
        callback_data.startswith("ws:manage:")
        and len(parts) >= 3
    ):
        try:
            from core.database import get_workspace_member, list_workspace_destinations
            from core.workspace_destinations import can_manage_destinations
            workspace_id = int(parts[2])
            user = get_user_by_telegram_id(chat_id)
            member = get_workspace_member(workspace_id, (user or {}).get("id"))
            workspace = next(
                (
                    item for item in list_user_workspace_memberships(user["id"])
                    if item.get("id") == workspace_id
                ),
                None,
            ) if user else None
            allowed, _reason = can_manage_destinations((member or {}).get("role"))
            if not user or not workspace or not member or member.get("status") != "active" or not allowed:
                raise ValueError("workspace access denied")
            destinations = list_workspace_destinations(workspace_id)
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "گروه رسانه‌ای معتبر نیست")
            return

        _ws_answer_callback(api_url, callback_id, "مدیریت گروه")
        panel_text, panel_keyboard = build_workspace_management_panel(workspace, destinations)
        _ws_send_message_with_keyboard(api_url, chat_id, panel_text, panel_keyboard)

    elif callback_data.startswith("ws:dest:toggle:") and len(parts) == 4:
        from core import database as database_module
        from core.workspace_destinations import can_manage_destinations
        try:
            destination_id = int(parts[3])
            user = get_user_by_telegram_id(chat_id)
            destination = database_module.get_publication_destination(destination_id)
            workspace_id = int((destination or {})["workspace_id"])
            workspace = database_module.get_workspace(workspace_id)
            member = database_module.get_workspace_member(workspace_id, (user or {})["id"])
            allowed, _reason = can_manage_destinations((member or {}).get("role"))
            if (
                not user or not destination or destination.get("status") == "removed"
                or not workspace or workspace.get("status") != "active"
                or not member or member.get("status") != "active" or not allowed
            ):
                raise ValueError("اجازه مدیریت این کانال را ندارید.")
            new_status = "inactive" if destination.get("status") == "active" else "active"
            database_module.update_publication_destination_status(destination_id, new_status)
            fresh = database_module.list_workspace_destinations(workspace_id)
            panel_text, panel_keyboard = build_workspace_management_panel(workspace, fresh)
            _ws_answer_callback(api_url, callback_id, "وضعیت کانال به‌روزرسانی شد")
            _ws_edit_message_text(api_url, callback_query, panel_text, panel_keyboard)
        except (KeyError, TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "کانال معتبر یا قابل مدیریت نیست")

    elif callback_data.startswith("ws:move:") and len(parts) >= 4:
        from core import database as database_module
        from core.workspace_destination_moves import list_move_candidates, move_destinations
        try:
            action = parts[2]
            target_workspace_id = int(parts[3])
            user = get_user_by_telegram_id(chat_id)
            if not user:
                raise ValueError("کاربر یافت نشد.")
            _target, candidates = list_move_candidates(
                database_module, user["id"], target_workspace_id,
            )
            if action == "list":
                _ws_answer_callback(api_url, callback_id, "انتخاب کانال")
                if not candidates:
                    _ws_send_message(api_url, chat_id, "کانال قابل انتقالی یافت نشد.")
                    return
                _ws_send_message_with_keyboard(
                    api_url,
                    chat_id,
                    "کانال‌هایی را که می‌خواهید به این گروه منتقل شوند انتخاب کنید:",
                    build_destination_move_keyboard(target_workspace_id, candidates),
                )
                return
            selected = selected_destination_ids_from_callback(callback_query)
            if action == "pick" and len(parts) == 6:
                destination_id = int(parts[4])
                candidate_ids = {int(row["id"]) for row in candidates}
                if destination_id not in candidate_ids:
                    raise ValueError("کانال انتخاب‌شده قابل انتقال نیست.")
                if destination_id in selected:
                    selected.remove(destination_id)
                else:
                    selected.add(destination_id)
                _ws_answer_callback(api_url, callback_id, "انتخاب به‌روزرسانی شد")
                _ws_edit_message_keyboard(
                    api_url,
                    callback_query,
                    build_destination_move_keyboard(target_workspace_id, candidates, selected),
                )
                return
            if action == "confirm":
                moved = move_destinations(
                    database_module, user["id"], target_workspace_id, selected,
                )
                _ws_answer_callback(api_url, callback_id, "انتقال انجام شد")
                _ws_send_message(
                    api_url,
                    chat_id,
                    f"✅ {len(moved)} کانال با موفقیت منتقل شد.",
                )
                return
            raise ValueError("عملیات انتقال نامعتبر است.")
        except (TypeError, ValueError) as exc:
            _ws_answer_callback(api_url, callback_id, str(exc)[:180])

    elif callback_data.startswith("ws:rename:") and len(parts) >= 3:
        try:
            workspace_id = int(parts[2])
            from core.command_handler import begin_workspace_rename
            _ws_answer_callback(api_url, callback_id, "نام جدید را ارسال کنید")
            begin_workspace_rename(chat_id, workspace_id)
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "گروه رسانه‌ای معتبر نیست")

    elif callback_data.startswith(("ws:addchannel:", "ws:members:", "ws:settings:")) and len(parts) >= 3:
        try:
            from core.database import get_workspace_member
            from core.workspace_destinations import can_manage_destinations
            workspace_id = int(parts[2])
            user = get_user_by_telegram_id(chat_id)
            member = get_workspace_member(workspace_id, (user or {}).get("id"))
            allowed, reason = can_manage_destinations((member or {}).get("role"))
            if not user or not member or member.get("status") != "active" or not allowed:
                raise ValueError(reason or "workspace access denied")
            set_active_workspace(user["id"], workspace_id)
            action = parts[1]
            message = {
                "addchannel": "شناسه کانال را با /addchannel @mychannel اضافه کنید.",
                "members": "برای مدیریت اعضا /members را بفرستید.",
                "settings": "برای تنظیمات رسانه /settings را بفرستید.",
            }[action]
            _ws_answer_callback(api_url, callback_id, "گروه برای مدیریت فعال شد")
            _ws_send_message(api_url, chat_id, message)
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "گروه رسانه‌ای معتبر نیست")

    elif callback_data == "ws:back":
        _ws_answer_callback(api_url, callback_id, "بازگشت")
        from core.command_handler import handle_workspaces
        handle_workspaces(chat_id)

    elif (
        callback_data.startswith(
            "ws:select:"
        )
        and len(parts) >= 3
    ):
        try:
            workspace_id = int(parts[2])

            user = (
                get_user_by_telegram_id(
                    chat_id
                )
            )

            if not user:
                raise ValueError(
                    "user not found"
                )

            select_workspace(
                user["id"],
                workspace_id,
            )

        except (TypeError, ValueError):
            _ws_answer_callback(
                api_url,
                callback_id,
                "انتخاب رسانه معتبر نیست",
            )
            return

        _ws_answer_callback(
            api_url,
            callback_id,
            "رسانه فعال تغییر کرد",
        )

        _ws_send_message(
            api_url,
            chat_id,
            (
                "✅ رسانه فعال با موفقیت "
                "تغییر کرد."
            ),
        )

    elif (
        callback_data.startswith(
            "ws:toggle:"
        )
        and len(parts) >= 3
    ):
        resume_incomplete_setup = False

        try:
            workspace_id = int(parts[2])

            user = (
                get_user_by_telegram_id(
                    chat_id
                )
            )

            if not user:
                raise ValueError(
                    "user not found"
                )

            selected_ids = set(
                list_selected_workspace_ids(
                    user["id"]
                )
            )

            preference = (
                get_active_workspace_preference(
                    user["id"]
                )
                or {}
            )

            legacy_selected = bool(
                preference.get(
                    "legacy_selected"
                )
                if "legacy_selected" in preference
                else (
                    preference.get(
                        "context_type"
                    )
                    == "legacy"
                )
            )

            setup_state = (
                get_workspace_setup_state(
                    workspace_id
                )
                or {}
            )

            setup_incomplete = (
                setup_state.get("step")
                != "completed"
            )

            if workspace_id in selected_ids:
                if not (
                    preference.get(
                        "context_type"
                    )
                    == "workspace"
                    and preference.get(
                        "active_workspace_id"
                    )
                    == workspace_id
                ):
                    set_active_workspace(
                        user["id"],
                        workspace_id,
                    )

                    text = (
                        "رسانه برای مدیریت و تکمیل "
                        "راه‌اندازی فعال شد"
                    )

                    resume_incomplete_setup = (
                        setup_incomplete
                    )

                elif setup_incomplete:
                    text = (
                        "راه‌اندازی رسانه از مرحله "
                        "ذخیره‌شده ادامه پیدا می‌کند"
                    )

                    resume_incomplete_setup = True

                elif (
                    len(selected_ids) == 1
                    and not legacy_selected
                ):
                    _ws_answer_callback(
                        api_url,
                        callback_id,
                        (
                            "حداقل یک رسانه باید "
                            "انتخاب بماند"
                        ),
                    )
                    return

                else:
                    deselect_workspace(
                        user["id"],
                        workspace_id,
                    )

                    text = (
                        "رسانه از انتشار "
                        "هم‌زمان حذف شد"
                    )

            else:
                select_workspace(
                    user["id"],
                    workspace_id,
                )

                text = (
                    "رسانه به انتشار "
                    "هم‌زمان اضافه شد"
                )

                resume_incomplete_setup = (
                    setup_incomplete
                )

        except (TypeError, ValueError):
            _ws_answer_callback(
                api_url,
                callback_id,
                "انتخاب رسانه معتبر نیست",
            )
            return

        _ws_answer_callback(
            api_url,
            callback_id,
            text,
        )

        selected_ids = (
            list_selected_workspace_ids(
                user["id"]
            )
        )

        workspaces = (
            list_user_workspace_memberships(
                user["id"]
            )
        )

        preference = (
            get_active_workspace_preference(
                user["id"]
            )
            or {}
        )

        legacy_tenant = get_tenant(chat_id)

        display_workspaces = (
            prepare_workspace_display_rows(
                workspaces,
        getattr(
    __import__(
        "core.database",
        fromlist=["list_verified_active_destinations"],
    ),
    "list_verified_active_destinations",
    lambda _workspace_id: [],
),
                get_workspace_branding,
            )
        )

        legacy_label = (
            (legacy_tenant or {}).get(
                "telegram_channel"
            )
            or (legacy_tenant or {}).get(
                "bale_channel"
            )
            or "رسانه قدیمی"
        )

        keyboard = build_workspace_keyboard(
            display_workspaces,
            preference.get(
                "active_workspace_id"
            ),
            selected_workspace_ids=(
                selected_ids
            ),
            include_legacy=bool(
                legacy_tenant
            ),
            legacy_active=bool(
                preference.get(
                    "legacy_selected"
                )
                if "legacy_selected"
                in preference
                else (
                    preference.get(
                        "context_type"
                    )
                    == "legacy"
                )
            ),
            legacy_label=legacy_label,
        )

        _ws_edit_message_keyboard(
            api_url,
            callback_query,
            keyboard,
        )

        _ws_send_message(
            api_url,
            chat_id,
            f"✅ {text}.",
        )

        if resume_incomplete_setup:
            from core.command_handler import (
                handle_setup
            )

            handle_setup(chat_id)

    elif (
        len(parts) >= 3
        and parts[1] == "toggle"
    ):
        try:
            dest_id = int(parts[2])

        except ValueError:
            return

        new_state = (
            toggle_destination_selection(
                chat_id,
                dest_id,
            )
        )

        pending = get_pending(chat_id)

        if not pending:
            _ws_answer_callback(
                api_url,
                callback_id,
                "جلسه منقضی شده است",
            )
            return

        keyboard = (
            build_selection_keyboard(
                pending["destinations"],
                pending["selected"],
            )
        )

        _ws_edit_message_keyboard(
            api_url,
            callback_query,
            keyboard,
        )

        check = (
            "✅"
            if new_state
            else "☑️"
        )

        _ws_answer_callback(
            api_url,
            callback_id,
            f"{check} انتخاب به‌روز شد",
        )

    elif parts[1] == "confirm":
        pending = get_pending(chat_id)

        if not pending:
            _ws_answer_callback(
                api_url,
                callback_id,
                "جلسه منقضی شده است",
            )
            return

        selected_ids = pending["selected"]

        if not selected_ids:
            _ws_answer_callback(
                api_url,
                callback_id,
                "حداقل یک کانال انتخاب کنید",
            )
            return

        selected_dests = [
            d
            for d in pending["destinations"]
            if d["id"] in selected_ids
        ]

        clear_pending(chat_id)

        _ws_answer_callback(
            api_url,
            callback_id,
            "در حال انتشار...",
        )

        result = publish_to_destinations(
            api_url,
            selected_dests,
            pending["text"],
            pending["media_file_id"],
            pending["media_type"],
            get_destination_branding,
            get_workspace_branding,
            record_message_link_fn=(
                _record_publication_message_link
            ),
            source_key=pending.get(
                "source_key",
                "",
            ),
        )

        _ws_send_message(
            api_url,
            chat_id,
            format_publish_result(result),
        )

    elif parts[1] == "cancel":
        clear_pending(chat_id)

        _ws_answer_callback(
            api_url,
            callback_id,
            "لغو شد",
        )

        _ws_send_message(
            api_url,
            chat_id,
            "❌ انتشار لغو شد.",
        )


def _ws_send_message(
    api_url: str,
    chat_id: int,
    text: str,
) -> None:
    try:
        requests.post(
            f"{api_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
            },
            timeout=10,
        )

    except Exception as e:
        logger.warning(
            f"_ws_send_message failed: {e}"
        )


def _ws_send_message_with_keyboard(
    api_url: str,
    chat_id: int,
    text: str,
    keyboard: list,
) -> None:
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {
                "inline_keyboard": keyboard
            },
        }

        requests.post(
            f"{api_url}/sendMessage",
            json=payload,
            timeout=10,
        )

    except Exception as e:
        logger.warning(
            "_ws_send_message_with_keyboard "
            f"failed: {e}"
        )


def _ws_answer_callback(
    api_url: str,
    callback_id: str,
    text: str,
) -> None:
    try:
        requests.post(
            f"{api_url}/answerCallbackQuery",
            json={
                "callback_query_id": callback_id,
                "text": text,
            },
            timeout=10,
        )

    except Exception as e:
        logger.warning(
            f"_ws_answer_callback failed: {e}"
        )


def _ws_edit_message_keyboard(
    api_url: str,
    callback_query: Dict,
    keyboard: list,
) -> None:
    try:
        msg = (
            callback_query.get(
                "message",
                {},
            )
            or {}
        )

        chat_id = (
            msg.get("chat", {})
            or {}
        ).get("id")

        message_id = msg.get(
            "message_id"
        )

        if chat_id and message_id:
            requests.post(
                f"{api_url}/editMessageReplyMarkup",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": {
                        "inline_keyboard": keyboard
                    },
                },
                timeout=10,
            )

    except Exception as e:
        logger.warning(
            "_ws_edit_message_keyboard "
            f"failed: {e}"
        )


def _ws_edit_message_text(
    api_url: str,
    callback_query: Dict,
    text: str,
    keyboard: list,
) -> None:
    """Refresh one management page after a server-authorized state change."""
    try:
        msg = callback_query.get("message", {}) or {}
        chat_id = (msg.get("chat", {}) or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id and message_id:
            requests.post(
                f"{api_url}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "reply_markup": {"inline_keyboard": keyboard},
                },
                timeout=10,
            )
    except Exception as e:
        logger.warning(f"_ws_edit_message_text failed: {e}")
