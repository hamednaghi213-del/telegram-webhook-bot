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

# In-process pending publication store (keyed by chat_id)
# Stores {"destinations": [...], "text": ..., "media_file_id": ...,
#         "media_type": ..., "selected": set()}
_PENDING: Dict[int, Dict] = {}


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
    """Resolve every workspace selected for simultaneous publication."""
    user = get_user_fn(telegram_user_id)
    if not user:
        return [], None
    workspaces = list_workspaces_fn(user["id"])
    if not workspaces:
        return [], None
    if len(workspaces) == 1:
        return workspaces, None
    selected_ids = set(
        list_selected_ids_fn(user["id"]) or []
    ) if list_selected_ids_fn else set()
    if not selected_ids and get_active_preference_fn:
        preference = get_active_preference_fn(user["id"]) or {}
        if preference.get("context_type") != "legacy":
            selected_ids.add(preference.get("active_workspace_id"))
    selected = [ws for ws in workspaces if ws.get("id") in selected_ids]
    if selected:
        return selected, None
    return [], "شما عضو چند رسانه هستید. لطفاً حداقل یک رسانه را انتخاب کنید."


def build_workspace_keyboard(
    workspaces: List[Dict],
    active_workspace_id: Optional[int],
    selected_workspace_ids: Optional[List[int]] = None,
    include_legacy: bool = False,
    legacy_active: bool = False,
) -> List[List[Dict]]:
    """Build an inline keyboard for simultaneous workspace selection."""
    keyboard = []
    selected_ids = set(selected_workspace_ids or [])
    if not selected_ids and active_workspace_id is not None and not legacy_active:
        selected_ids.add(active_workspace_id)
    if include_legacy:
        legacy_marker = "✅" if legacy_active else "▫️"
        keyboard.append([{
            "text": f"{legacy_marker} رسانه قدیمی",
            "callback_data": "ws:legacy",
        }])
    for workspace in workspaces:
        marker = (
            "✅"
            if not legacy_active and workspace.get("id") in selected_ids
            else "▫️"
        )
        role = workspace.get("membership_role") or workspace.get("member_role") or "member"
        keyboard.append([{
            "text": f"{marker} {workspace.get('name') or workspace['id']} ({role})",
            "callback_data": f"ws:toggle:{workspace['id']}",
        }])
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
        return False, err, None
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
        return False, err, None
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
) -> Dict[str, Any]:
    """
    Publish content to a list of destinations.

    Processes source content once (fit_content_to_budget is per-destination).
    Failure of one destination does NOT prevent others.

    Returns {"success": int, "failure": int, "errors": List[str]}.
    """
    success = 0
    failure = 0
    errors: List[str] = []
    sent_messages: Dict[str, Dict[str, Any]] = {}

    for dest in destinations:
        dest_id = dest["id"]
        workspace_id = dest["workspace_id"]
        channel_id = dest["external_id"]
        dest_name = dest.get("name") or channel_id

        try:
            branding = compose_destination_branding(
                dest_id, workspace_id, get_dest_branding_fn, get_ws_branding_fn
            )
            workspace_branding = get_ws_branding_fn(workspace_id) or {}
            from core.publication_icons import (
                format_with_icons,
                format_with_profile,
                normalize_icons,
            )
            selected_icons = normalize_icons(
                workspace_branding.get("publication_icons") or []
            ) if workspace_branding.get("icons_enabled", False) else []
            publication_profile = workspace_branding.get("publication_profile") or {}
            if publication_profile:
                content = format_with_profile(
                    content_text or "", publication_profile, True
                )
            else:
                content = format_with_icons(
                    content_text or "",
                    selected_icons,
                    bool(selected_icons),
                )
            content = fit_content_to_budget(
                content,
                compute_caption_budget(branding),
                is_editorial_finalized,
            )
            caption = build_final_caption(content, branding)

            if dest.get("platform") == "bale":
                token = os.getenv("BALE_BOT_TOKEN", "").strip()
                if not token:
                    ok, err = False, "BALE_BOT_TOKEN is not configured"
                else:
                    from core.bale_forwarder import (
                        send_document_to_bale,
                        send_photo_to_bale,
                        send_text_to_bale,
                        send_video_to_bale,
                    )
                    if media_file_id and media_type == "photo":
                        sender = send_photo_to_bale
                    elif media_file_id and media_type == "video":
                        sender = send_video_to_bale
                    elif media_file_id:
                        sender = send_document_to_bale
                    else:
                        sender = send_text_to_bale
                    try:
                        if media_file_id:
                            bale_result = sender(
                                channel_id, token, caption, media_file_id,
                                return_result=True,
                            )
                        else:
                            bale_result = sender(
                                channel_id, token, caption, return_result=True
                            )
                    except TypeError:
                        # Backward compatibility for injected/older senders.
                        if media_file_id:
                            bale_result = sender(channel_id, token, caption, media_file_id)
                        else:
                            bale_result = sender(channel_id, token, caption)
                    if isinstance(bale_result, bool):
                        bale_result = {"ok": bale_result, "message_id": None}
                    ok = bool(bale_result.get("ok"))
                    if ok:
                        sent_messages["bale"] = {
                            "destination_id": dest_id,
                            "chat_id": channel_id,
                            "message_id": bale_result.get("message_id"),
                        }
                    err = None if ok else "Bale publish failed"
            elif media_file_id and media_type:
                telegram_outcome = _send_media_to_destination(
                    api_url, channel_id, media_file_id, media_type, caption
                )
                ok, err = telegram_outcome[:2]
                telegram_result = telegram_outcome[2] if len(telegram_outcome) > 2 else {}
            else:
                telegram_outcome = _send_text_to_destination(
                    api_url, channel_id, caption
                )
                ok, err = telegram_outcome[:2]
                telegram_result = telegram_outcome[2] if len(telegram_outcome) > 2 else {}

            if ok and dest.get("platform") == "telegram":
                telegram_result = telegram_result or {}
                sent_messages["telegram"] = {
                    "destination_id": dest_id,
                    "chat_id": (telegram_result.get("chat") or {}).get("id", channel_id),
                    "message_id": telegram_result.get("message_id"),
                }

            if ok:
                success += 1
                logger.info(f"Published to {channel_id} ✓")
            else:
                failure += 1
                logger.warning(f"Failed to publish to {channel_id}: {err}")
                errors.append(dest_name)

        except Exception as e:
            logger.exception(f"Exception publishing to dest {dest_id}: {e}")
            failure += 1
            errors.append(dest_name)

    telegram_sent = sent_messages.get("telegram") or {}
    bale_sent = sent_messages.get("bale") or {}
    if (
        record_message_link_fn
        and telegram_sent.get("message_id") is not None
        and bale_sent.get("message_id") is not None
    ):
        try:
            record_message_link_fn(
                workspace_id=destinations[0]["workspace_id"],
                telegram_destination_id=telegram_sent["destination_id"],
                telegram_chat_id=str(telegram_sent["chat_id"]),
                telegram_message_id=int(telegram_sent["message_id"]),
                bale_destination_id=bale_sent["destination_id"],
                bale_chat_id=str(bale_sent["chat_id"]),
                bale_message_id=int(bale_sent["message_id"]),
                content_kind="caption" if media_file_id else "text",
            )
        except Exception as e:
            logger.exception(f"Failed to record Telegram/Bale message link: {e}")

    return {"success": success, "failure": failure, "errors": errors}


def format_publish_result(result: Dict[str, Any]) -> str:
    """Format publish result as Persian summary message."""
    success = result.get("success", 0)
    failure = result.get("failure", 0)

    if failure == 0:
        return f"✅ انتشار انجام شد\nموفق: {success}\nناموفق: ۰"

    lines = [f"موفق: {success}", f"❌ ناموفق: {failure}"]
    errors = result.get("errors") or []
    if errors:
        lines.append("کانال‌های ناموفق: " + "، ".join(str(e) for e in errors))
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
) -> None:
    """Store pending publication content for destination selection."""
    _PENDING[chat_id] = {
        "destinations": destinations,
        "text": content_text,
        "media_file_id": media_file_id,
        "media_type": media_type,
        "selected": set(d["id"] for d in destinations),  # default: all selected
    }


def get_pending(chat_id: int) -> Optional[Dict]:
    """Retrieve pending publication state."""
    return _PENDING.get(chat_id)


def clear_pending(chat_id: int) -> None:
    """Clear pending publication state."""
    _PENDING.pop(chat_id, None)


def toggle_destination_selection(chat_id: int, dest_id: int) -> bool:
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
        name = dest.get("name") or dest.get("external_id", "")
        check = "✅" if d_id in selected_ids else "☑️"
        rows.append([{
            "text": f"{check} {name}",
            "callback_data": f"wp:toggle:{d_id}",
        }])
    # Confirm row
    rows.append([
        {"text": "📤 انتشار", "callback_data": "wp:confirm"},
        {"text": "❌ لغو", "callback_data": "wp:cancel"},
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

        workspaces = list_user_workspace_memberships(user["id"])
        if not workspaces:
            return False

        selected_workspaces, workspace_error = resolve_workspaces_for_user(
            chat_id,
            lambda _telegram_id: user,
            lambda _user_id: workspaces,
            get_active_workspace_preference,
            list_selected_workspace_ids,
        )
        if not selected_workspaces:
            _ws_send_message(
                api_url,
                chat_id,
                workspace_error or "رسانه فعالی یافت نشد.",
            )
            return True
        destinations = []
        for workspace in selected_workspaces:
            workspace_id = workspace["id"]
            setup_state = get_workspace_setup_state(workspace_id)
            if not setup_state or setup_state.get("step") != "completed":
                _ws_send_message(
                    api_url, chat_id,
                    f"❌ راه‌اندازی رسانه «{workspace.get('name')}» کامل نیست.",
                )
                return True
            allowed, err = check_publish_permission(
                workspace_id, user["id"], get_workspace_member
            )
            if not allowed:
                _ws_send_message(api_url, chat_id, f"❌ {workspace.get('name')}: {err}")
                return True
            destinations.extend(list_verified_active_destinations(workspace_id))
        destinations = list({dest["id"]: dest for dest in destinations}.values())
        if not destinations:
            _ws_send_message(
                api_url,
                chat_id,
                "❌ هیچ کانال تأیید شده‌ای موجود نیست. ابتدا کانال را تأیید کنید.",
            )
            return True

        # Extract content from message
        media_type = None
        media_file_id = None
        content_text = (msg.get("caption") or msg.get("text") or "").strip()

        # Simple media extraction
        for mtype in ("photo", "video", "document", "voice", "audio"):
            if mtype in msg:
                media_type = mtype
                if mtype == "photo":
                    photos = msg["photo"] or []
                    media_file_id = photos[-1]["file_id"] if photos else None
                else:
                    media_file_id = (msg[mtype] or {}).get("file_id")
                break

        if not content_text and not media_file_id:
            return False  # No publishable content

        platforms = {destination.get("platform") for destination in destinations}
        paired_destinations = (
            len(destinations) == 2 and platforms == {"telegram", "bale"}
        )

        # One Telegram+Bale pair publishes together without another prompt.
        if len(selected_workspaces) > 1 or len(destinations) == 1 or paired_destinations:
            result = publish_to_destinations(
                api_url, destinations, content_text, media_file_id, media_type,
                get_destination_branding, get_workspace_branding,
                record_message_link_fn=_record_publication_message_link,
            )
            _ws_send_message(api_url, chat_id, format_publish_result(result))
            return True

        # Multiple destinations: store pending and show selection
        store_pending(chat_id, destinations, content_text, media_file_id, media_type)
        pending = get_pending(chat_id)
        keyboard = build_selection_keyboard(destinations, pending["selected"])
        _ws_send_message_with_keyboard(
            api_url, chat_id,
            "📢 انتخاب کانال انتشار:",
            keyboard,
        )
        return True

    except Exception as e:
        logger.exception(f"[{req_id}] _try_workspace_publication error: {e}")
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
        list_selected_workspace_ids,
        select_workspace,
        deselect_workspace,
        list_user_workspace_memberships,
    )

    callback_data = callback_query.get("data", "") or ""
    callback_id = callback_query.get("id", "")
    from_user = callback_query.get("from", {}) or {}
    chat_id = from_user.get("id")
    if chat_id is None:
        return

    parts = callback_data.split(":")
    if len(parts) < 2:
        return

    if callback_data == "ws:legacy":
        try:
            user = get_user_by_telegram_id(chat_id)
            if not user:
                raise ValueError("user not found")
            from core.database import get_tenant
            if not get_tenant(chat_id):
                raise ValueError("legacy tenant not found")
            set_active_legacy_context(user["id"])
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "رسانه قدیمی معتبر نیست")
            return
        _ws_answer_callback(api_url, callback_id, "رسانه قدیمی فعال شد")
        _ws_send_message(api_url, chat_id, "✅ رسانه قدیمی شما فعال شد.")

    elif callback_data.startswith("ws:select:") and len(parts) >= 3:
        try:
            workspace_id = int(parts[2])
            user = get_user_by_telegram_id(chat_id)
            if not user:
                raise ValueError("user not found")
            select_workspace(user["id"], workspace_id)
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "انتخاب رسانه معتبر نیست")
            return
        _ws_answer_callback(api_url, callback_id, "رسانه فعال تغییر کرد")
        _ws_send_message(api_url, chat_id, "✅ رسانه فعال با موفقیت تغییر کرد.")

    elif callback_data.startswith("ws:toggle:") and len(parts) >= 3:
        try:
            workspace_id = int(parts[2])
            user = get_user_by_telegram_id(chat_id)
            if not user:
                raise ValueError("user not found")
            selected_ids = set(list_selected_workspace_ids(user["id"]))
            if workspace_id in selected_ids:
                if len(selected_ids) == 1:
                    _ws_answer_callback(
                        api_url, callback_id, "حداقل یک رسانه باید انتخاب بماند"
                    )
                    return
                deselect_workspace(user["id"], workspace_id)
                text = "رسانه از انتشار هم‌زمان حذف شد"
            else:
                select_workspace(user["id"], workspace_id)
                text = "رسانه به انتشار هم‌زمان اضافه شد"
        except (TypeError, ValueError):
            _ws_answer_callback(api_url, callback_id, "انتخاب رسانه معتبر نیست")
            return
        _ws_answer_callback(api_url, callback_id, text)
        selected_ids = list_selected_workspace_ids(user["id"])
        workspaces = list_user_workspace_memberships(user["id"])
        from core.database import get_tenant
        keyboard = build_workspace_keyboard(
            workspaces,
            workspace_id,
            selected_workspace_ids=selected_ids,
            include_legacy=bool(get_tenant(chat_id)),
        )
        _ws_edit_message_keyboard(api_url, callback_query, keyboard)
        _ws_send_message(api_url, chat_id, f"✅ {text}.")

    elif len(parts) >= 3 and parts[1] == "toggle":
        try:
            dest_id = int(parts[2])
        except ValueError:
            return
        new_state = toggle_destination_selection(chat_id, dest_id)
        pending = get_pending(chat_id)
        if not pending:
            _ws_answer_callback(api_url, callback_id, "جلسه منقضی شده است")
            return
        # Update keyboard
        keyboard = build_selection_keyboard(
            pending["destinations"], pending["selected"]
        )
        _ws_edit_message_keyboard(api_url, callback_query, keyboard)
        check = "✅" if new_state else "☑️"
        _ws_answer_callback(api_url, callback_id, f"{check} انتخاب به‌روز شد")

    elif parts[1] == "confirm":
        pending = get_pending(chat_id)
        if not pending:
            _ws_answer_callback(api_url, callback_id, "جلسه منقضی شده است")
            return
        selected_ids = pending["selected"]
        if not selected_ids:
            _ws_answer_callback(api_url, callback_id, "حداقل یک کانال انتخاب کنید")
            return
        selected_dests = [
            d for d in pending["destinations"] if d["id"] in selected_ids
        ]
        clear_pending(chat_id)
        _ws_answer_callback(api_url, callback_id, "در حال انتشار...")
        result = publish_to_destinations(
            api_url,
            selected_dests,
            pending["text"],
            pending["media_file_id"],
            pending["media_type"],
            get_destination_branding,
            get_workspace_branding,
            record_message_link_fn=_record_publication_message_link,
        )
        _ws_send_message(api_url, chat_id, format_publish_result(result))

    elif parts[1] == "cancel":
        clear_pending(chat_id)
        _ws_answer_callback(api_url, callback_id, "لغو شد")
        _ws_send_message(api_url, chat_id, "❌ انتشار لغو شد.")


def _ws_send_message(api_url: str, chat_id: int, text: str) -> None:
    try:
        requests.post(
            f"{api_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"_ws_send_message failed: {e}")


def _ws_send_message_with_keyboard(
    api_url: str, chat_id: int, text: str, keyboard: list
) -> None:
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"inline_keyboard": keyboard},
        }
        requests.post(f"{api_url}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"_ws_send_message_with_keyboard failed: {e}")


def _ws_answer_callback(api_url: str, callback_id: str, text: str) -> None:
    try:
        requests.post(
            f"{api_url}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"_ws_answer_callback failed: {e}")


def _ws_edit_message_keyboard(
    api_url: str, callback_query: Dict, keyboard: list
) -> None:
    try:
        msg = callback_query.get("message", {}) or {}
        chat_id = (msg.get("chat", {}) or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id and message_id:
            requests.post(
                f"{api_url}/editMessageReplyMarkup",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": {"inline_keyboard": keyboard},
                },
                timeout=10,
            )
    except Exception as e:
        logger.warning(f"_ws_edit_message_keyboard failed: {e}")
