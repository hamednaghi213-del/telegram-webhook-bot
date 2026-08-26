"""Single publication orchestrator for Legacy and Workspace targets.

The module intentionally reuses the established formatter/entity/caption and
executor functions.  It owns routing only; it contains no replacement content
algorithm.
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from core.content_model import PreparedContent, PublicationTarget
from core.target_resolver import resolve_publication_targets

logger = logging.getLogger(__name__)

_idempotency_lock = threading.RLock()
_published_keys = set()


def reset_local_idempotency_state() -> None:
    """Test/support hook; production state lives for the single worker lifetime."""
    with _idempotency_lock:
        _published_keys.clear()


def _claim(source_key: str, target: PublicationTarget) -> bool:
    if not source_key:
        return True
    key = (source_key, target.platform, target.external_id.strip().lower())
    with _idempotency_lock:
        if key in _published_keys:
            return False
        _published_keys.add(key)
    return True


def _release(source_key: str, target: PublicationTarget) -> None:
    if not source_key:
        return
    key = (source_key, target.platform, target.external_id.strip().lower())
    with _idempotency_lock:
        _published_keys.discard(key)


def _target_content_and_branding(
    chat_id: int,
    target: PublicationTarget,
    prepared: PreparedContent,
) -> tuple[str, str]:
    if target.kind == "legacy":
        from core.webhook_handler import build_branding_for_user
        return prepared.main_text, build_branding_for_user(chat_id)

    from core.database import get_destination_branding, get_workspace_branding
    from core.publication_icons import format_with_icons, format_with_profile, normalize_icons
    from core.workspace_publisher import compose_destination_branding

    workspace_id = int(target.workspace_id)
    branding = compose_destination_branding(
        int(target.destination_id),
        workspace_id,
        get_destination_branding,
        get_workspace_branding,
    )
    workspace_branding = get_workspace_branding(workspace_id) or {}
    profile = workspace_branding.get("publication_profile") or {}
    if profile:
        content = format_with_profile(prepared.neutral_text or prepared.main_text, profile, True)
    else:
        icons = normalize_icons(workspace_branding.get("publication_icons") or [])
        if not workspace_branding.get("icons_enabled", False):
            icons = []
        content = format_with_icons(prepared.neutral_text or prepared.main_text, icons, bool(icons))
    return content, branding


def _send_text_target(
    chat_id: int,
    api_url: str,
    target: PublicationTarget,
    plan: Dict[str, Any],
) -> bool:
    messages = list(plan.get("messages") or [])
    modes = list(plan.get("message_parse_modes") or [])
    blockquotes = list(plan.get("blockquote_messages") or [])
    if target.platform == "telegram":
        if target.kind == "legacy":
            from core.webhook_handler import send_to_channel
            for index, message in enumerate(messages):
                if message and not send_to_channel(
                    message,
                    parse_mode=modes[index] if index < len(modes) else None,
                ):
                    return False
            for message in blockquotes:
                if message and not send_to_channel(message, parse_mode="HTML"):
                    return False
            return True
        from core.media_handler import send_text_to_channel
        for index, message in enumerate(messages):
            if message and not send_text_to_channel(
                message,
                parse_mode=modes[index] if index < len(modes) else None,
                channel_id=target.external_id,
                api_url=api_url,
            ):
                return False
        for message in blockquotes:
            if message and not send_text_to_channel(
                message,
                parse_mode="HTML",
                channel_id=target.external_id,
                api_url=api_url,
            ):
                return False
        return True

    if target.kind == "legacy":
        from core.bale_forwarder import send_to_bale_for_user
        return all(send_to_bale_for_user(chat_id, message) is not False for message in messages + blockquotes if message)

    from core.bale_forwarder import send_text_to_bale
    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        return False
    return all(send_text_to_bale(target.external_id, token, message) is not False for message in messages + blockquotes if message)


def _send_media_target(
    chat_id: int,
    api_url: str,
    target: PublicationTarget,
    files: List[Dict[str, Any]],
    plan: Dict[str, Any],
) -> bool:
    if target.platform == "telegram":
        from core.media_handler import execute_telegram_plan
        if target.kind == "legacy":
            return execute_telegram_plan(files, plan)
        return execute_telegram_plan(
            files,
            plan,
            channel_id=target.external_id,
            api_url=api_url,
        )

    if target.kind == "legacy":
        from core.media_handler import execute_bale_plan
        return execute_bale_plan(chat_id, files, plan)

    from core.bale_forwarder import (
        send_document_to_bale,
        send_media_group_to_bale,
        send_photo_to_bale,
        send_text_to_bale,
        send_video_to_bale,
    )
    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        return False
    caption = plan.get("media_caption", "") or ""
    if len(files) > 1:
        ok = send_media_group_to_bale(
            chat_id,
            files,
            caption,
            bale_channel=target.external_id,
            bale_token=token,
        )
    else:
        item = files[0]
        sender = {
            "photo": send_photo_to_bale,
            "video": send_video_to_bale,
            "document": send_document_to_bale,
            "voice": send_document_to_bale,
            "audio": send_document_to_bale,
        }.get(item.get("type"))
        ok = bool(sender and sender(target.external_id, token, caption, item.get("file_id")))
    if not ok:
        return False
    for message in list(plan.get("followup_messages") or []) + list(plan.get("blockquote_messages") or []):
        if message and send_text_to_bale(target.external_id, token, message) is False:
            return False
    return True


def publish_prepared_content(
    chat_id: int,
    api_url: str,
    prepared: PreparedContent,
    targets: Optional[List[PublicationTarget]] = None,
) -> Dict[str, Any]:
    """Build one destination-specific PublicationPlan per resolved target."""
    if targets is None:
        targets, resolution_errors = resolve_publication_targets(chat_id)
    else:
        resolution_errors = []
    results: List[Dict[str, Any]] = []
    legacy_plan = None
    legacy_telegram_failed = False
    for target in targets:
        if target.kind == "legacy" and target.platform == "bale" and legacy_telegram_failed:
            results.append({"target": target.key, "ok": False, "skipped": True})
            continue
        if not _claim(prepared.source_key, target):
            results.append({"target": target.key, "ok": True, "duplicate": True})
            continue
        try:
            from core.caption_manager import analyze_content
            if target.kind == "legacy" and legacy_plan is not None:
                plan = legacy_plan
            else:
                main_text, branding = _target_content_and_branding(chat_id, target, prepared)
                plan = analyze_content(
                    main_text=main_text,
                    blockquote_blocks=prepared.blockquote_blocks,
                    expandable_blocks=prepared.expandable_blocks,
                    other_entities=prepared.other_entities,
                    branding=branding,
                    editorial_finalized=prepared.editorial_finalized,
                )
                if target.kind == "legacy":
                    legacy_plan = plan
            if prepared.files:
                platform_plan = plan.telegram if target.platform == "telegram" else plan.bale
                ok = _send_media_target(chat_id, api_url, target, prepared.files, platform_plan)
            else:
                platform_plan = plan.text[target.platform]
                ok = _send_text_target(chat_id, api_url, target, platform_plan)
            if not ok:
                _release(prepared.source_key, target)
                if target.kind == "legacy" and target.platform == "telegram":
                    legacy_telegram_failed = True
            results.append({"target": target.key, "ok": bool(ok), "duplicate": False})
        except Exception as exc:
            _release(prepared.source_key, target)
            logger.exception("Publication target failed | target=%s | %s", target.key, exc)
            results.append({"target": target.key, "ok": False, "error": str(exc)})
    blocking_results = [
        item for item, target in zip(results, targets)
        if not (target.kind == "legacy" and target.platform == "bale")
    ]
    return {
        "ok": bool(results) and all(item.get("ok") for item in blocking_results),
        "results": results,
        "errors": resolution_errors,
    }
