"""Single publication orchestrator for Legacy and Workspace targets.

The module intentionally reuses the established formatter/entity/caption and
executor functions.  It owns routing only; it contains no replacement content
algorithm.
"""

import logging
import os
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from core.content_model import DeliveryResult, PreparedContent, PublicationTarget
from core.publication_state import DEFAULT_PUBLICATION_STATE_STORE, PublicationStateStore
from core.target_resolver import canonical_target_identity, resolve_publication_targets

logger = logging.getLogger(__name__)

_state_store: PublicationStateStore = DEFAULT_PUBLICATION_STATE_STORE


def reset_local_idempotency_state() -> None:
    """Test/support hook; production state lives for the single worker lifetime."""
    _state_store.reset()


def _claim(source_key: str, target: PublicationTarget) -> bool:
    if not source_key:
        return True
    state = _state_store.claim_destination(source_key, canonical_target_identity(target))
    return state.status != "succeeded"


def _release(source_key: str, target: PublicationTarget) -> None:
    # Kept as a compatibility hook. Granular delivery state is never discarded:
    # successful parts must remain completed when a later part fails.
    return None


def _target_content_and_branding(
    chat_id: int,
    target: PublicationTarget,
    prepared: PreparedContent,
) -> tuple[str, str]:
    if target.kind == "legacy":
        from core.webhook_handler import build_branding_for_user
        return prepared.main_text, build_branding_for_user(chat_id)

    destination_context = dict(target.destination or {})
    get_destination_branding = destination_context.get("_get_dest_branding_fn")
    get_workspace_branding = destination_context.get("_get_ws_branding_fn")
    if not get_destination_branding or not get_workspace_branding:
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
        from core.workspace_publisher import _send_text_to_destination
        last_outcome: Any = True
        for index, message in enumerate(messages):
            if message:
                try:
                    outcome = _send_text_to_destination(
                        api_url, target.external_id, message,
                        parse_mode=modes[index] if index < len(modes) else None,
                    )
                except TypeError:
                    outcome = _send_text_to_destination(api_url, target.external_id, message)
                if not _outcome_ok(outcome):
                    return outcome
                last_outcome = outcome
        for message in blockquotes:
            if message:
                outcome = _send_text_to_destination(
                    api_url, target.external_id, message, parse_mode="HTML"
                )
                if not _outcome_ok(outcome):
                    return outcome
        return last_outcome

    if target.kind == "legacy":
        from core.bale_forwarder import send_to_bale_for_user
        outcomes = [send_to_bale_for_user(chat_id, message) for message in messages + blockquotes if message]
        return outcomes[-1] if outcomes and all(_outcome_ok(item) for item in outcomes) else False

    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        return False
    from core.bale_forwarder import send_text_to_bale
    outcomes = [send_text_to_bale(target.external_id, token, message) for message in messages + blockquotes if message]
    return outcomes[-1] if outcomes and all(_outcome_ok(item) for item in outcomes) else False


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
        if len(files) == 1:
            from core.workspace_publisher import _send_media_to_destination
            item = files[0]
            return _send_media_to_destination(
                api_url,
                target.external_id,
                item.get("file_id"),
                item.get("type"),
                plan.get("media_caption", "") or "",
            )
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


def _message_id_from_outcome(outcome: Any) -> Optional[int]:
    if isinstance(outcome, dict):
        value = outcome.get("message_id")
        if value is None and isinstance(outcome.get("result"), dict):
            value = outcome["result"].get("message_id")
        return int(value) if value is not None else None
    if isinstance(outcome, tuple) and len(outcome) > 2 and isinstance(outcome[2], dict):
        return _message_id_from_outcome(outcome[2])
    return None


def _chat_id_from_outcome(outcome: Any) -> Optional[str]:
    if isinstance(outcome, tuple) and len(outcome) > 2:
        return _chat_id_from_outcome(outcome[2])
    if isinstance(outcome, dict):
        result = outcome.get("result") if isinstance(outcome.get("result"), dict) else outcome
        chat = result.get("chat") if isinstance(result, dict) else None
        value = chat.get("id") if isinstance(chat, dict) else result.get("chat_id")
        return str(value) if value is not None else None
    return None


def _outcome_ok(outcome: Any) -> bool:
    if isinstance(outcome, tuple):
        return bool(outcome[0])
    if isinstance(outcome, dict):
        return bool(outcome.get("ok", True))
    return bool(outcome)


def _shared_content_analysis(prepared: PreparedContent) -> PreparedContent:
    """Run AI-capable semantic analysis once, before target fan-out."""
    from core.caption_manager import analyze_content

    source_text = prepared.neutral_text or prepared.main_text
    # The stable planner only invokes Smart Summary when platform capacity is
    # exceeded. Avoid a redundant planner pass for content that cannot trigger
    # AI, and for already-finalized editorial content.
    threshold = 996 if prepared.files else 4096
    if prepared.editorial_finalized or len(source_text) <= threshold:
        return prepared
    plan = analyze_content(
        main_text=source_text,
        blockquote_blocks=list(prepared.blockquote_blocks),
        expandable_blocks=list(prepared.expandable_blocks),
        other_entities=list(prepared.other_entities),
        branding="",
        editorial_finalized=prepared.editorial_finalized,
    )
    if prepared.files:
        candidate = str(plan.telegram.get("media_caption") or "").strip()
        has_remainder = bool(plan.telegram.get("followup_messages"))
    else:
        messages = list((plan.text.get("telegram") or {}).get("messages") or [])
        candidate = str(messages[0] if len(messages) == 1 else "").strip()
        has_remainder = len(messages) != 1
    if candidate and not has_remainder and len(candidate) < len(source_text):
        return replace(
            prepared,
            main_text=candidate,
            neutral_text=candidate,
            other_entities=(),
        )
    return prepared


def _part_plan(message: str, parse_mode: Optional[str] = None) -> Dict[str, Any]:
    return {
        "messages": [message],
        "message_parse_modes": [parse_mode],
        "blockquote_messages": [],
    }


def _execute_delivery_part(
    chat_id: int,
    api_url: str,
    target: PublicationTarget,
    prepared: PreparedContent,
    platform_plan: Dict[str, Any],
    part_kind: str,
    index: int = 0,
) -> Any:
    if part_kind == "primary":
        if prepared.files:
            primary_plan = dict(platform_plan)
            primary_plan["followup_messages"] = []
            primary_plan["blockquote_messages"] = []
            return _send_media_target(
                chat_id, api_url, target, list(prepared.files), primary_plan
            )
        messages = list(platform_plan.get("messages") or [])
        modes = list(platform_plan.get("message_parse_modes") or [])
        if not messages:
            return True
        return _send_text_target(
            chat_id,
            api_url,
            target,
            _part_plan(messages[0], modes[0] if modes else None),
        )

    if part_kind == "followup":
        messages = (
            list(platform_plan.get("followup_messages") or [])
            if prepared.files
            else list(platform_plan.get("messages") or [])[1:]
        )
        modes = [] if prepared.files else list(platform_plan.get("message_parse_modes") or [])[1:]
        return _send_text_target(
            chat_id, api_url, target,
            _part_plan(messages[index], modes[index] if index < len(modes) else None),
        )

    messages = list(platform_plan.get("blockquote_messages") or [])
    return _send_text_target(
        chat_id, api_url, target, _part_plan(messages[index], "HTML")
    )


def _delivery_parts(prepared: PreparedContent, platform_plan: Dict[str, Any]):
    yield "primary", "primary", 0
    followups = (
        list(platform_plan.get("followup_messages") or [])
        if prepared.files
        else list(platform_plan.get("messages") or [])[1:]
    )
    for index in range(len(followups)):
        yield f"followup:{index}", "followup", index
    for index, _message in enumerate(platform_plan.get("blockquote_messages") or []):
        yield f"blockquote:{index}", "blockquote", index


def publish_prepared_content(
    chat_id: int,
    api_url: str,
    prepared: PreparedContent,
    targets: Optional[List[PublicationTarget]] = None,
    state_store: Optional[PublicationStateStore] = None,
) -> Dict[str, Any]:
    """Publish immutable prepared content with resumable per-part deliveries."""
    store = state_store or _state_store
    if targets is None:
        targets, resolution_errors = resolve_publication_targets(chat_id)
    else:
        resolution_errors = []
    # Defensive dedup also protects explicit target lists passed by adapters.
    unique_targets: Dict[str, PublicationTarget] = {}
    for target in targets:
        identity = canonical_target_identity(target)
        previous = unique_targets.get(identity)
        if previous is None or (previous.kind == "legacy" and target.kind == "workspace"):
            unique_targets[identity] = target
    targets = list(unique_targets.values())

    analyzed = _shared_content_analysis(prepared)
    source_key = analyzed.source_key or f"ephemeral:{id(analyzed)}"
    store.claim_source(source_key)
    results: List[DeliveryResult] = []
    plan_cache: Dict[Tuple[Any, ...], Any] = {}
    target_content_cache: Dict[Tuple[Any, ...], Tuple[str, str]] = {}
    legacy_telegram_failed = False

    for target in targets:
        if target.kind == "legacy" and target.platform == "bale" and legacy_telegram_failed:
            results.append(DeliveryResult(
                target.platform, target.workspace_id, target.destination_id,
                target.external_id, status="failed",
                error="legacy telegram prerequisite failed",
                idempotency_key=f"{source_key}:{canonical_target_identity(target)}",
            ))
            continue
        identity = canonical_target_identity(target)
        state = store.claim_destination(source_key, identity)
        if state.status == "succeeded":
            results.append(DeliveryResult(
                target.platform, target.workspace_id, target.destination_id,
                target.external_id, status="succeeded", attempt=state.attempt,
                idempotency_key=f"{source_key}:{identity}",
                primary_message_id=state.message_ids.get("primary"),
                followup_message_ids=tuple(value for key, value in sorted(state.message_ids.items()) if key.startswith("followup:")),
                blockquote_message_ids=tuple(value for key, value in sorted(state.message_ids.items()) if key.startswith("blockquote:")),
            ))
            continue
        state = store.begin_attempt(source_key, identity)
        try:
            from core.caption_manager import analyze_content, suppress_smart_summary
            # A legacy Telegram+Bale pair shares the same semantic/branding
            # input.  Build it once so branding callbacks and caption planning
            # are not repeated merely because two platform executors exist.
            content_key = (
                target.kind,
                target.workspace_id,
                target.destination_id if target.kind != "legacy" else None,
            )
            cached_content = target_content_cache.get(content_key)
            if cached_content is None:
                cached_content = _target_content_and_branding(chat_id, target, analyzed)
                target_content_cache[content_key] = cached_content
            main_text, branding = cached_content
            plan_key = (
                main_text, branding, analyzed.editorial_finalized,
                repr(tuple(dict(item) for item in analyzed.blockquote_blocks)),
                repr(tuple(dict(item) for item in analyzed.expandable_blocks)),
                repr(tuple(dict(item) for item in analyzed.other_entities)),
            )
            plan = plan_cache.get(plan_key)
            if plan is None:
                with suppress_smart_summary():
                    plan = analyze_content(
                        main_text=main_text,
                        blockquote_blocks=list(analyzed.blockquote_blocks),
                        expandable_blocks=list(analyzed.expandable_blocks),
                        other_entities=list(analyzed.other_entities),
                        branding=branding,
                        editorial_finalized=analyzed.editorial_finalized,
                    )
                plan_cache[plan_key] = plan
            platform_plan = plan.telegram if analyzed.files and target.platform == "telegram" else (
                plan.bale if analyzed.files else plan.text[target.platform]
            )
            error = None
            for part_name, part_kind, index in _delivery_parts(analyzed, platform_plan):
                if store.part_completed(source_key, identity, part_name):
                    continue
                outcome = _execute_delivery_part(
                    chat_id, api_url, target, analyzed, platform_plan, part_kind, index
                )
                if not _outcome_ok(outcome):
                    error = f"{part_name} failed"
                    store.mark_failed(source_key, identity, error)
                    if target.kind == "legacy" and target.platform == "telegram":
                        legacy_telegram_failed = True
                    break
                store.part_succeeded(
                    source_key, identity, part_name, _message_id_from_outcome(outcome),
                    _chat_id_from_outcome(outcome),
                )
            if error is None:
                store.mark_succeeded(source_key, identity)
            final = store.get_delivery(source_key, identity)
            results.append(DeliveryResult(
                target.platform, target.workspace_id, target.destination_id,
                final.message_chat_ids.get("primary", target.external_id),
                primary_message_id=final.message_ids.get("primary"),
                followup_message_ids=tuple(value for key, value in sorted(final.message_ids.items()) if key.startswith("followup:")),
                blockquote_message_ids=tuple(value for key, value in sorted(final.message_ids.items()) if key.startswith("blockquote:")),
                status=final.status, error=final.error, attempt=final.attempt,
                idempotency_key=f"{source_key}:{identity}",
            ))
        except Exception as exc:
            store.mark_failed(source_key, identity, str(exc))
            if target.kind == "legacy" and target.platform == "telegram":
                legacy_telegram_failed = True
            logger.exception("Publication target failed | target=%s | %s", target.key, exc)
            final = store.get_delivery(source_key, identity)
            results.append(DeliveryResult(
                target.platform, target.workspace_id, target.destination_id,
                target.external_id, status="failed", error=str(exc),
                attempt=final.attempt if final else 0,
                idempotency_key=f"{source_key}:{identity}",
            ))
    return {
        "ok": bool(results) and all(item.status == "succeeded" for item in results),
        "results": results,
        "errors": resolution_errors,
    }
