"""Single publication orchestrator for Legacy and Workspace targets.

The module intentionally reuses the established formatter/entity/caption and
executor functions. It owns routing only; it contains no replacement content
algorithm.
"""

import logging
import os
import uuid
import inspect
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from core.content_model import (
    DeliveryResult,
    ExecutorResult,
    PreparedContent,
    PublicationTarget,
)
from core.publication_state import (
    DEFAULT_PUBLICATION_STATE_STORE,
    PublicationStateStore,
    delivery_state_has_success_proof,
)
from core.target_resolver import (
    canonical_target_identity,
    resolve_publication_targets,
)

logger = logging.getLogger(__name__)

_state_store: PublicationStateStore = DEFAULT_PUBLICATION_STATE_STORE

# Boot-unique lease owner identity for the persistent publication
# state store (B5). Distinct per process, so Supabase lease rows can
# attribute (and reclaim) claims per worker.
_LEASE_OWNER: str = (
    f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
)


def _get_runtime_state_store() -> PublicationStateStore:
    global _state_store

    if not isinstance(
        _state_store,
        type(DEFAULT_PUBLICATION_STATE_STORE),
    ):
        return _state_store

    try:
        from core import database
        from core.publication_state import (
            InMemoryPublicationStateStore,
            PersistentPublicationStateStore,
        )

        if (
            isinstance(
                _state_store,
                InMemoryPublicationStateStore,
            )
            and os.getenv(
                "ENABLE_PERSISTENT_PUBLICATION_STATE",
                "",
            ).strip().lower() == "true"
            and database.service_supabase is not None
        ):
            _state_store = PersistentPublicationStateStore(
                lease_owner=_LEASE_OWNER,
                lease_seconds=900,
            )

    except Exception:
        pass

    return _state_store


def _supports_return_result(sender) -> bool:
    try:
        return "return_result" in inspect.signature(sender).parameters
    except (TypeError, ValueError):
        return False


def reset_local_idempotency_state() -> None:
    """Test/support hook; production state lives for the single worker lifetime."""
    _state_store.reset()


def _claim(
    source_key: str,
    target: PublicationTarget,
) -> bool:
    if not source_key:
        return True

    state = _state_store.claim_destination(
        source_key,
        canonical_target_identity(target),
    )

    return state.status != "succeeded"


def _release(
    source_key: str,
    target: PublicationTarget,
) -> None:
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

        return (
            prepared.main_text,
            build_branding_for_user(chat_id),
        )

    destination_context = dict(
        target.destination or {}
    )

    if destination_context.get("_canonical_media"):
        from core.canonical_media import resolve_media_branding
        from core.publication_icons import (
            format_with_icons,
            format_with_profile,
            normalize_icons,
        )

        resolved = resolve_media_branding(
            dict(
                destination_context.get("media_identity")
                or {}
            ),
            dict(
                destination_context.get("destination_branding")
                or {}
            ),
        )

        parts = [
            value
            for value in (
                resolved.get("hashtag"),
                resolved.get("channel_tag"),
                (
                    resolved.get("custom_footer")
                    if resolved.get("footer_enabled")
                    else ""
                ),
            )
            if value
        ]

        branding = "\n".join(parts)

        profile = (
            resolved.get("publication_profile")
            or {}
        )

        if profile:
            content = format_with_profile(
                prepared.neutral_text
                or prepared.main_text,
                profile,
                True,
            )

        else:
            icons = normalize_icons(
                resolved.get("publication_icons")
                or []
            )

            if not resolved.get(
                "icons_enabled",
                False,
            ):
                icons = []

            content = format_with_icons(
                prepared.neutral_text
                or prepared.main_text,
                icons,
                bool(icons),
            )

        return (
            content,
            branding,
        )

    get_destination_branding = (
        destination_context.get(
            "_get_dest_branding_fn"
        )
    )

    get_workspace_branding = (
        destination_context.get(
            "_get_ws_branding_fn"
        )
    )

    if (
        not get_destination_branding
        or not get_workspace_branding
    ):
        from core.database import (
            get_destination_branding,
            get_workspace_branding,
        )

    from core.publication_icons import (
        format_with_icons,
        format_with_profile,
        normalize_icons,
    )
    from core.workspace_publisher import (
        compose_destination_branding,
    )

    workspace_id = int(
        target.workspace_id
    )

    branding = compose_destination_branding(
        int(target.destination_id),
        workspace_id,
        get_destination_branding,
        get_workspace_branding,
    )

    workspace_branding = (
        get_workspace_branding(
            workspace_id
        )
        or {}
    )

    profile = (
        workspace_branding.get(
            "publication_profile"
        )
        or {}
    )

    if profile:
        content = format_with_profile(
            prepared.neutral_text
            or prepared.main_text,
            profile,
            True,
        )

    else:
        icons = normalize_icons(
            workspace_branding.get(
                "publication_icons"
            )
            or []
        )

        if not workspace_branding.get(
            "icons_enabled",
            False,
        ):
            icons = []

        content = format_with_icons(
            prepared.neutral_text
            or prepared.main_text,
            icons,
            bool(icons),
        )

    return (
        content,
        branding,
    )

def _destination_translation_policy(
    target: PublicationTarget,
):
    """
    Build the shared translation policy from destination-level settings.

    Language is destination-specific and language-agnostic:
    fa, en, de, ru, ar, tr, zh, ja, or any other language
    identifier supported by the shared translation pipeline.

    Legacy targets and destinations with translation disabled
    keep the original PreparedContent unchanged.
    """
    if target.kind == "legacy":
        return None

    destination = dict(
        target.destination or {}
    )

    translation_enabled = bool(
        destination.get(
            "translation_enabled",
            False,
        )
    )

    target_language = str(
        destination.get(
            "target_language_code",
            "",
        )
        or ""
    ).strip()

    if (
        not translation_enabled
        or not target_language
    ):
        return None

    from core.translation_policy import (
        TRANSLATION_MODE_AUTO,
        TranslationPolicy,
        normalize_language,
    )

    target_language = normalize_language(
        target_language
    )

    if not target_language:
        return None

    return TranslationPolicy(
        destination_language=target_language,
        translation_mode=TRANSLATION_MODE_AUTO,
        fail_closed=True,
        enabled=True,
        metadata={
            "workspace_id": target.workspace_id,
            "destination_id": target.destination_id,
            "platform": target.platform,
        },
    )

def _translated_prepared_for_target(
    target: PublicationTarget,
    prepared: PreparedContent,
    translation_cache: Dict[
        str,
        PreparedContent,
    ],
) -> PreparedContent:
    """
    Return destination-language PreparedContent.

    Translation is performed once per target language and
    reused across destinations such as Telegram and Bale.
    """
    policy = _destination_translation_policy(
        target
    )

    if policy is None:
        return prepared

    target_language = str(
        policy.destination_language
        or ""
    ).strip()

    if not target_language:
        return prepared

    cached = translation_cache.get(
        target_language
    )

    if cached is not None:
        return cached

    from core.translation_prepared_content import (
        translate_prepared_content,
    )

    translated = translate_prepared_content(
        prepared=prepared,
        policy=policy,
        content_kind=(
            "media"
            if prepared.files
            else "text"
        ),
    )

    if (
        not translated.success
        or translated.blocked
    ):
        raise RuntimeError(
            "destination_translation_failed:"
            f"{target_language}:"
            f"{translated.reason}"
        )

    translated_prepared = replace(
        prepared,
        **translated.payload,
    )

    translation_cache[
        target_language
    ] = translated_prepared

    return translated_prepared

def _normalize_executor_result(
    outcome: Any,
) -> ExecutorResult:

    if isinstance(
        outcome,
        ExecutorResult,
    ):
        return outcome

    ok = _outcome_ok(outcome)
    message_id = _message_id_from_outcome(outcome)
    message_ids = _message_ids_from_outcome(outcome)

    status_code = None
    error_code = None
    error = None
    operation = None
    raw = outcome

    candidate = (
        outcome[2]
        if (
            isinstance(
                outcome,
                tuple,
            )
            and len(outcome) > 2
        )
        else outcome
    )

    if isinstance(
        candidate,
        dict,
    ):
        status_code = candidate.get("status_code")
        error_code = candidate.get("error_code")
        error = (
            candidate.get("error")
            or candidate.get("description")
        )
        operation = candidate.get("operation")

    if (
        isinstance(
            outcome,
            tuple,
        )
        and len(outcome) > 1
        and not ok
    ):
        error = str(
            outcome[1]
            or error
            or "executor failed"
        )

    return ExecutorResult(
        ok,
        message_id,
        message_ids,
        status_code,
        error,
        raw,
        error_code,
        operation,
    )


def _message_ids_from_outcome(
    outcome: Any,
) -> Tuple[int, ...]:

    if isinstance(
        outcome,
        ExecutorResult,
    ):
        return outcome.message_ids

    candidate = (
        outcome[2]
        if (
            isinstance(
                outcome,
                tuple,
            )
            and len(outcome) > 2
        )
        else outcome
    )

    values: Any = None

    if isinstance(
        candidate,
        dict,
    ):
        values = candidate.get(
            "message_ids"
        )

        if (
            values is None
            and isinstance(
                candidate.get("result"),
                list,
            )
        ):
            values = [
                item.get("message_id")
                for item in candidate["result"]
                if isinstance(
                    item,
                    dict,
                )
            ]

    normalized = tuple(
        int(value)
        for value in (
            values
            or ()
        )
        if (
            isinstance(
                value,
                int,
            )
            and not isinstance(
                value,
                bool,
            )
        )
    )

    if normalized:
        return normalized

    primary = _message_id_from_outcome(
        outcome
    )

    return (
        (primary,)
        if primary is not None
        else ()
    )


def _send_text_target(
    chat_id: int,
    api_url: str,
    target: PublicationTarget,
    plan: Dict[str, Any],
):

    messages = list(
        plan.get("messages")
        or []
    )

    modes = list(
        plan.get("message_parse_modes")
        or []
    )

    blockquotes = list(
        plan.get("blockquote_messages")
        or []
    )

    if target.platform == "telegram":

        if target.kind == "legacy":
            from core.webhook_handler import send_to_channel

            for index, message in enumerate(
                messages
            ):
                if message:
                    if _supports_return_result(
                        send_to_channel
                    ):
                        outcome = send_to_channel(
                            message,
                            parse_mode=(
                                modes[index]
                                if index < len(modes)
                                else None
                            ),
                            return_result=True,
                        )
                    else:
                        outcome = send_to_channel(
                            message,
                            parse_mode=(
                                modes[index]
                                if index < len(modes)
                                else None
                            ),
                        )

                    if not _outcome_ok(
                        outcome
                    ):
                        return _normalize_executor_result(
                            outcome
                        )

                    last_outcome = outcome

            for message in blockquotes:
                if message:
                    if _supports_return_result(
                        send_to_channel
                    ):
                        outcome = send_to_channel(
                            message,
                            parse_mode="HTML",
                            return_result=True,
                        )
                    else:
                        outcome = send_to_channel(
                            message,
                            parse_mode="HTML",
                        )

                    if not _outcome_ok(
                        outcome
                    ):
                        return _normalize_executor_result(
                            outcome
                        )

                    last_outcome = outcome

            return _normalize_executor_result(
                locals().get(
                    "last_outcome",
                    False,
                )
            )

        from core.workspace_publisher import (
            _send_text_to_destination,
        )

        last_outcome: Any = False

        for index, message in enumerate(
            messages
        ):
            if message:
                try:
                    outcome = _send_text_to_destination(
                        api_url,
                        target.external_id,
                        message,
                        parse_mode=(
                            modes[index]
                            if index < len(modes)
                            else None
                        ),
                    )

                except TypeError:
                    outcome = _send_text_to_destination(
                        api_url,
                        target.external_id,
                        message,
                    )

                if not _outcome_ok(
                    outcome
                ):
                    return outcome

                last_outcome = outcome

        for message in blockquotes:
            if message:
                outcome = _send_text_to_destination(
                    api_url,
                    target.external_id,
                    message,
                    parse_mode="HTML",
                )

                if not _outcome_ok(
                    outcome
                ):
                    return outcome

        return _normalize_executor_result(
            last_outcome
        )

    if target.kind == "legacy":
        from core.bale_forwarder import (
            send_to_bale_for_user,
        )

        outcomes = []

        for message in (
            messages
            + blockquotes
        ):
            if not message:
                continue

            if _supports_return_result(
                send_to_bale_for_user
            ):
                outcomes.append(
                    send_to_bale_for_user(
                        chat_id,
                        message,
                        return_result=True,
                    )
                )
            else:
                outcomes.append(
                    send_to_bale_for_user(
                        chat_id,
                        message,
                    )
                )

        return _normalize_executor_result(
            outcomes[-1]
            if (
                outcomes
                and all(
                    _outcome_ok(item)
                    for item in outcomes
                )
            )
            else False
        )

    token = os.getenv(
        "BALE_BOT_TOKEN",
        "",
    ).strip()

    if not token:
        return False

    from core.bale_forwarder import (
        send_text_to_bale,
    )

    outcomes = []

    for message in (
        messages
        + blockquotes
    ):
        if not message:
            continue

        if _supports_return_result(
            send_text_to_bale
        ):
            outcomes.append(
                send_text_to_bale(
                    target.external_id,
                    token,
                    message,
                    return_result=True,
                )
            )
        else:
            outcomes.append(
                send_text_to_bale(
                    target.external_id,
                    token,
                    message,
                )
            )

    return _normalize_executor_result(
        outcomes[-1]
        if (
            outcomes
            and all(
                _outcome_ok(item)
                for item in outcomes
            )
        )
        else False
    )


def _send_media_target(
    chat_id: int,
    api_url: str,
    target: PublicationTarget,
    files: List[Dict[str, Any]],
    plan: Dict[str, Any],
):

    media_presentation = str(
        plan.get(
            "_media_presentation",
            "",
        )
        or ""
    )

    if target.platform == "telegram":

        normalized_presentation = (
            media_presentation
            .strip()
            .lower()
        )

        from core.bale_media import is_bale_media_ref

        # Telegram Rich Message accepts reusable Telegram file IDs here.
        # Choose the normal media plan before attempting a Rich send when
        # Bale files need multipart upload; this avoids a failed Rich send
        # followed by an ambiguous retry that could duplicate delivery.
        requires_bale_upload = any(
            is_bale_media_ref(item.get("file_id")) for item in files
        )

        if not requires_bale_upload and normalized_presentation in (
            "slideshow",
            "collage",
        ):

            from core.telegram_rich_sender import (
                send_rich_media_to_channel,
            )

            outcome = send_rich_media_to_channel(
                files=files,
                presentation=(
                    normalized_presentation
                ),
                caption=(
                    plan.get(
                        "media_caption",
                        "",
                    )
                    or ""
                ),
                channel_id=(
                    None
                    if target.kind == "legacy"
                    else target.external_id
                ),
                api_url=(
                    None
                    if target.kind == "legacy"
                    else api_url
                ),
            )

            return _normalize_executor_result(
                outcome
            )

        from core.media_handler import (
            execute_telegram_plan,
        )

        outcome = execute_telegram_plan(
            files,
            plan,
            channel_id=(
                None
                if target.kind == "legacy"
                else target.external_id
            ),
            api_url=(
                None
                if target.kind == "legacy"
                else api_url
            ),
            return_result=True,
        )

        normalized = _normalize_executor_result(
            outcome
        )

        if (
            normalized.success
            and normalized.primary_message_id
            is None
        ):
            from core.media_handler import (
                get_last_media_message_id,
            )

            message_id = (
                get_last_media_message_id()
            )

            if message_id is not None:
                normalized = replace(
                    normalized,
                    primary_message_id=(
                        message_id
                    ),
                    message_ids=(
                        message_id,
                    ),
                )

        return normalized

    if target.kind == "legacy":
        from core.media_handler import (
            execute_bale_plan,
        )

        return _normalize_executor_result(
            execute_bale_plan(
                chat_id,
                files,
                plan,
                return_result=True,
            )
        )

    from core.bale_forwarder import (
        send_document_to_bale,
        send_media_group_to_bale,
        send_photo_to_bale,
        send_text_to_bale,
        send_typed_media_to_bale,
        send_video_to_bale,
    )

    token = os.getenv(
        "BALE_BOT_TOKEN",
        "",
    ).strip()

    if not token:
        return False

    caption = (
        plan.get(
            "media_caption",
            "",
        )
        or ""
    )

    if len(files) > 1:
        ok = send_media_group_to_bale(
            chat_id,
            files,
            caption,
            bale_channel=(
                target.external_id
            ),
            bale_token=token,
            return_result=True,
        )

    else:
        item = files[0]

        sender = {
            "photo":
                send_photo_to_bale,
            "video":
                send_video_to_bale,
            "document":
                send_document_to_bale,
        }.get(
            item.get("type")
        )

        ok = (
            send_typed_media_to_bale(
                target.external_id,
                token,
                caption,
                item.get("file_id"),
                item.get("type"),
                return_result=True,
            )
            if item.get("type") in ("audio", "voice", "animation")
            else sender(
                target.external_id,
                token,
                caption,
                item.get("file_id"),
                return_result=True,
            )
            if sender
            else False
        )

    if not _outcome_ok(
        ok
    ):
        return _normalize_executor_result(
            ok
        )

    for message in (
        list(
            plan.get(
                "followup_messages"
            )
            or []
        )
        + list(
            plan.get(
                "blockquote_messages"
            )
            or []
        )
    ):
        if (
            message
            and send_text_to_bale(
                target.external_id,
                token,
                message,
            )
            is False
        ):
            return False

    return _normalize_executor_result(
        ok
    )


def _message_id_from_outcome(
    outcome: Any,
) -> Optional[int]:

    if isinstance(
        outcome,
        ExecutorResult,
    ):
        return outcome.primary_message_id

    if isinstance(
        outcome,
        dict,
    ):
        value = outcome.get(
            "message_id"
        )

        if (
            value is None
            and isinstance(
                outcome.get("result"),
                dict,
            )
        ):
            value = (
                outcome["result"]
                .get("message_id")
            )

        return (
            int(value)
            if value is not None
            else None
        )

    if (
        isinstance(
            outcome,
            tuple,
        )
        and len(outcome) > 2
        and isinstance(
            outcome[2],
            dict,
        )
    ):
        return _message_id_from_outcome(
            outcome[2]
        )

    return None


def _chat_id_from_outcome(
    outcome: Any,
) -> Optional[str]:

    if isinstance(
        outcome,
        ExecutorResult,
    ):
        return _chat_id_from_outcome(
            outcome.raw_result
        )

    if (
        isinstance(
            outcome,
            tuple,
        )
        and len(outcome) > 2
    ):
        return _chat_id_from_outcome(
            outcome[2]
        )

    if isinstance(
        outcome,
        dict,
    ):
        result = (
            outcome.get("result")
            if isinstance(
                outcome.get("result"),
                dict,
            )
            else outcome
        )

        chat = (
            result.get("chat")
            if isinstance(
                result,
                dict,
            )
            else None
        )

        value = (
            chat.get("id")
            if isinstance(
                chat,
                dict,
            )
            else result.get(
                "chat_id"
            )
        )

        return (
            str(value)
            if value is not None
            else None
        )

    return None


def _outcome_ok(
    outcome: Any,
) -> bool:

    if isinstance(
        outcome,
        ExecutorResult,
    ):
        return outcome.success

    if isinstance(
        outcome,
        tuple,
    ):
        return bool(
            outcome[0]
        )

    if isinstance(
        outcome,
        dict,
    ):
        return bool(
            outcome.get(
                "ok",
                False,
            )
        )

    return bool(
        outcome
    )


def _targets_from_descriptor_identities(
    descriptor_targets: Any,
) -> Tuple[PublicationTarget, ...]:
    """Re-resolve B8 duplicate-override targets from persisted identities.

    Rebuilds PublicationTarget objects from the minimal identity tuple
    recorded in a duplicate override descriptor and re-applies the
    same physical-destination deduplication the live resolver uses.
    """
    rebuilt: List[PublicationTarget] = []

    for item in (
        descriptor_targets or ()
    ):
        if not isinstance(item, dict):
            continue

        platform = str(item.get("platform") or "").strip()

        if not platform:
            continue

        external_id = str(item.get("external_id") or "")
        workspace_id = item.get("workspace_id")
        destination_id = item.get("destination_id")

        if (
            item.get("kind") == "legacy"
            or workspace_id is None
        ):
            key = (
                f"legacy:{platform}:{external_id}"
            )

            kind = "legacy"

            destination: Dict[str, Any] = {}

        else:
            key = (
                f"workspace:{int(workspace_id)}:"
                f"destination:{destination_id}"
            )

            kind = "workspace"

            destination = {
                "id": destination_id,
                "workspace_id": workspace_id,
                "platform": platform,
                "external_id": external_id,
            }

        rebuilt.append(
            PublicationTarget(
                key=key,
                kind=kind,
                platform=platform,
                external_id=external_id,
                workspace_id=(
                    int(workspace_id)
                    if workspace_id is not None
                    else None
                ),
                destination_id=(
                    int(destination_id)
                    if destination_id is not None
                    else None
                ),
                destination=destination,
            )
        )

    # Re-apply physical-destination deduplication, mirroring the
    # resolver contract.
    deduplicated: Dict[str, PublicationTarget] = {}

    for target in rebuilt:
        identity = canonical_target_identity(target)

        deduplicated.setdefault(
            identity,
            target,
        )

    return tuple(deduplicated.values())


def _unique_media_identity_ids(
    targets: List[PublicationTarget],
) -> List[int]:
    """
    Return unique canonical Media Identity IDs represented
    by the publication targets.

    Telegram/Bale destinations belonging to the same media
    must produce one media identity only.
    """

    media_ids = set()

    for target in targets:
        destination_context = dict(
            target.destination
            or {}
        )

        if not destination_context.get(
            "_canonical_media"
        ):
            continue

        media_identity = dict(
            destination_context.get(
                "media_identity"
            )
            or {}
        )

        media_identity_id = (
            media_identity.get("id")
        )

        if media_identity_id is None:
            continue

        try:
            media_ids.add(
                int(
                    media_identity_id
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    return sorted(
        media_ids
    )


def _duplicate_decisions_for_targets(
    prepared: PreparedContent,
    targets: List[PublicationTarget],
) -> Dict[int, Any]:
    """
    Check Duplicate News Guard once per canonical Media Identity.

    Duplicate history is isolated by Media Identity, so Telegram/Bale
    destinations of the same media produce only one duplicate check.

    Any detector/database failure remains fail-open.
    """

    from core.duplicate_guard import (
        check_duplicate_against_history,
    )

    source_text = (
        prepared.neutral_text
        or prepared.main_text
        or ""
    ).strip()

    if not source_text:
        return {}

    decisions: Dict[int, Any] = {}

    for media_identity_id in (
        _unique_media_identity_ids(
            targets
        )
    ):
        try:
            decisions[
                media_identity_id
            ] = (
                check_duplicate_against_history(
                    media_identity_id=(
                        media_identity_id
                    ),
                    text=source_text,
                    source_key=(
                        prepared.publication_identity
                    ),
                )
            )
        except Exception:
            continue

    return decisions


def _duplicate_warning_payload(
    decisions: Dict[int, Any],
) -> Optional[Dict[str, Any]]:
    """
    Convert duplicate decisions into one Shared Engine warning payload.

    This function only formats the warning contract.
    It does not block or publish anything.
    """

    matches = []

    for (
        media_identity_id,
        decision,
    ) in decisions.items():

        if not getattr(
            decision,
            "duplicate",
            False,
        ):
            continue

        match = getattr(
            decision,
            "match",
            None,
        )

        matches.append(
            {
                "media_identity_id":
                    media_identity_id,

                "match_type":
                    getattr(
                        decision,
                        "match_type",
                        None,
                    ),

                "similarity":
                    float(
                        getattr(
                            decision,
                            "similarity",
                            0.0,
                        )
                        or 0.0
                    ),

                "publication_id":
                    (
                        getattr(
                            match,
                            "publication_id",
                            None,
                        )
                        if match is not None
                        else None
                    ),

                "actor_user_id":
                    (
                        getattr(
                            match,
                            "actor_user_id",
                            None,
                        )
                        if match is not None
                        else None
                    ),

                "published_at":
                    (
                        getattr(
                            match,
                            "published_at",
                            None,
                        )
                        if match is not None
                        else None
                    ),
            }
        )

    if not matches:
        return None

    return {
        "duplicate_warning":
            True,

        "matches":
            matches,
    }


def _shared_content_analysis(
    prepared: PreparedContent,
) -> PreparedContent:
    """Run AI-capable semantic analysis once, before target fan-out."""

    from core.caption_manager import (
        analyze_content,
    )

    source_text = (
        prepared.neutral_text
        or prepared.main_text
    )

    detached_texts = [
        str(
            block.get("text")
            or ""
        )
        for block in (
            *prepared.blockquote_blocks,
            *prepared.expandable_blocks,
        )
    ]

    publishable_text = "\n\n".join(
        item
        for item in (
            source_text,
            *detached_texts,
        )
        if item
    )

    threshold = (
        996
        if prepared.files
        else 4096
    )

    if len(
        publishable_text
    ) <= threshold:
        return prepared

    plan = analyze_content(
        output_kind="media" if prepared.files else "text",
        main_text=source_text,
        blockquote_blocks=list(
            prepared.blockquote_blocks
        ),
        expandable_blocks=list(
            prepared.expandable_blocks
        ),
        other_entities=list(
            prepared.other_entities
        ),
        branding="",
        editorial_finalized=(
            prepared.editorial_finalized
            and not prepared.require_single_message
        ),
    )

    if prepared.files:
        candidate = str(
            plan.telegram.get(
                "media_caption"
            )
            or ""
        ).strip()

        has_remainder = bool(
            plan.telegram.get(
                "followup_messages"
            )
            or plan.telegram.get(
                "blockquote_messages"
            )
        )

        semantic_summary = (
            plan.telegram.get(
                "_semantic_summary"
            )
        )

    else:
        messages = list(
            (
                plan.text.get(
                    "telegram"
                )
                or {}
            ).get(
                "messages"
            )
            or []
        )

        candidate = str(
            messages[0]
            if len(messages) == 1
            else ""
        ).strip()

        has_remainder = (
            len(messages) != 1
        )

        semantic_summary = None

    if (
        prepared.files
        and semantic_summary
        and candidate
        and not has_remainder
        and len(candidate)
        < len(publishable_text)
    ):
        summarized_main = str(
            semantic_summary.get(
                "main_text"
            )
            or ""
        ).strip()

        summarized_blockquotes = tuple(
            semantic_summary.get(
                "blockquote_blocks"
            )
            or ()
        )

        summarized_expandable = tuple(
            semantic_summary.get(
                "expandable_blocks"
            )
            or ()
        )

        return replace(
            prepared,
            main_text=(
                summarized_main
            ),
            neutral_text=(
                summarized_main
            ),
            blockquote_blocks=(
                summarized_blockquotes
            ),
            expandable_blocks=(
                summarized_expandable
            ),
            other_entities=(),
        )

    if (
        not prepared.files
        and candidate
        and not has_remainder
        and len(candidate)
        < len(publishable_text)
    ):
        return replace(
            prepared,
            main_text=candidate,
            neutral_text=candidate,
            blockquote_blocks=(),
            expandable_blocks=(),
            other_entities=(),
        )

    return prepared


def _part_plan(
    message: str,
    parse_mode: Optional[str] = None,
) -> Dict[str, Any]:

    return {
        "messages":
            [message],

        "message_parse_modes":
            [parse_mode],

        "blockquote_messages":
            [],
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
            primary_plan = dict(
                platform_plan
            )

            primary_plan[
                "followup_messages"
            ] = []

            primary_plan[
                "blockquote_messages"
            ] = []

            primary_plan[
                "_media_presentation"
            ] = (
                prepared.media_presentation
            )

            return _send_media_target(
                chat_id,
                api_url,
                target,
                list(
                    prepared.files
                ),
                primary_plan,
            )

        messages = list(
            platform_plan.get(
                "messages"
            )
            or []
        )

        modes = list(
            platform_plan.get(
                "message_parse_modes"
            )
            or []
        )

        if not messages:
            # No media and no text to send: there is nothing that can
            # produce a genuine Telegram transport success. Never
            # fabricate a "primary" success without an actual
            # sendMessage/sendPhoto/... call and a real message_id.
            return False

        return _send_text_target(
            chat_id,
            api_url,
            target,
            _part_plan(
                messages[0],
                (
                    modes[0]
                    if modes
                    else None
                ),
            ),
        )

    if part_kind == "followup":

        messages = (
            list(
                platform_plan.get(
                    "followup_messages"
                )
                or []
            )
            if prepared.files
            else list(
                platform_plan.get(
                    "messages"
                )
                or []
            )[1:]
        )

        modes = (
            []
            if prepared.files
            else list(
                platform_plan.get(
                    "message_parse_modes"
                )
                or []
            )[1:]
        )

        return _send_text_target(
            chat_id,
            api_url,
            target,
            _part_plan(
                messages[index],
                (
                    modes[index]
                    if index < len(modes)
                    else None
                ),
            ),
        )

    messages = list(
        platform_plan.get(
            "blockquote_messages"
        )
        or []
    )

    return _send_text_target(
        chat_id,
        api_url,
        target,
        _part_plan(
            messages[index],
            "HTML",
        ),
    )


def _delivery_parts(
    prepared: PreparedContent,
    platform_plan: Dict[str, Any],
):

    yield (
        "primary",
        "primary",
        0,
    )

    followups = (
        list(
            platform_plan.get(
                "followup_messages"
            )
            or []
        )
        if prepared.files
        else list(
            platform_plan.get(
                "messages"
            )
            or []
        )[1:]
    )

    for index in range(
        len(
            followups
        )
    ):
        yield (
            f"followup:{index}",
            "followup",
            index,
        )

    for index, _message in enumerate(
        platform_plan.get(
            "blockquote_messages"
        )
        or []
    ):
        yield (
            f"blockquote:{index}",
            "blockquote",
            index,
        )


def publish_prepared_content(
    chat_id: int,
    api_url: str,
    prepared: PreparedContent,
    targets: Optional[
        List[PublicationTarget]
    ] = None,
    state_store: Optional[
        PublicationStateStore
    ] = None,
    allow_duplicate: bool = False,
) -> Dict[str, Any]:
    """Publish immutable prepared content with resumable per-part deliveries."""

    store = (
        state_store
        or _get_runtime_state_store()
    )

    if targets is None:
        (
            targets,
            resolution_errors,
        ) = resolve_publication_targets(
            chat_id
        )
    else:
        resolution_errors = []

    unique_targets: Dict[
        str,
        PublicationTarget,
    ] = {}

    for target in targets:
        identity = (
            canonical_target_identity(
                target
            )
        )

        previous = (
            unique_targets.get(
                identity
            )
        )

        if (
            previous is None
            or (
                previous.kind
                == "legacy"
                and target.kind
                == "workspace"
            )
        ):
            unique_targets[
                identity
            ] = target

    targets = list(
        unique_targets.values()
    )

    # Keep Telegram publication latency isolated from Bale media upload
    # latency. Bale multipart uploads may legitimately take longer or retry,
    # so all Telegram destinations are executed first while preserving the
    # existing relative order within each platform group.
    targets = sorted(
        targets,
        key=lambda target: (
            0
            if target.platform == "telegram"
            else 1
        ),
    )

    if not allow_duplicate:
        duplicate_decisions = (
            _duplicate_decisions_for_targets(
                prepared,
                targets,
            )
        )

        duplicate_warning = (
            _duplicate_warning_payload(
                duplicate_decisions
            )
        )

        if duplicate_warning:
            try:
                from core.duplicate_pending import (
                    create_pending_duplicate,
                )

                duplicate_token = (
                    create_pending_duplicate(
                        chat_id=chat_id,
                        prepared=prepared,
                        targets=targets,
                    )
                )

            except Exception:
                logger.exception(
                    "Duplicate pending creation failed | source=%s",
                    prepared.publication_identity,
                )

                duplicate_token = None

            return {
                "ok": False,
                "results": [],
                "errors": [],
                "duplicate_token":
                    duplicate_token,
                **duplicate_warning,
            }

    analyzed = (
        _shared_content_analysis(
            prepared
        )
    )

    analyzed_primary_text = (
        analyzed.neutral_text
        or analyzed.main_text
        or ""
    )

    analyzed_threshold = (
        996
        if analyzed.files
        else 4096
    )

    # Feature Lock:
    # Only the primary article/news body is required to remain a single
    # semantically summarized message. Structured blockquote/expandable
    # content keeps its established independent follow-up/splitting contract.
    structured_followups_present = bool(
        analyzed.blockquote_blocks
        or analyzed.expandable_blocks
    )

    if (
        len(analyzed_primary_text) > analyzed_threshold
        and (
            prepared.require_single_message
            or not structured_followups_present
        )
    ):
        error_code = (
            "editorial_summary_unavailable"
            if prepared.require_single_message
            else "smart_summary_unavailable"
        )

        logger.error(
            "Single-message publication blocked | "
            "source=%s | editorial=%s | "
            "reason=%s",
            prepared.publication_identity,
            prepared.require_single_message,
            error_code,
        )

        return {
            "ok": False,
            "results": [],
            "errors": [
                error_code
            ],
        }

    source_key = (
        analyzed.publication_identity
    )

    # Reserve the exact analyzed news fingerprint before destination fan-out.
    #
    # The normal history check above is intentionally retained because it
    # handles already-published exact/near duplicates. This additional
    # database-backed reservation closes the race between two different
    # source updates that pass the history check before either publication
    # has had time to write duplicate_news_history.
    duplicate_claimed_media_ids: List[int] = []
    duplicate_claim_text = ""
    duplicate_claim_normalized_text = ""
    duplicate_claim_fingerprint = ""
    duplicate_claim_actor_user_id: Optional[int] = None

    if not allow_duplicate:
        try:
            from core import database
            from core.duplicate_guard import (
                duplicate_fingerprint,
                normalize_duplicate_text,
            )

            duplicate_claim_text = (
                analyzed.neutral_text
                or analyzed.main_text
                or ""
            ).strip()

            if duplicate_claim_text:
                user = database.get_user_by_telegram_id(
                    chat_id
                )

                duplicate_claim_actor_user_id = (
                    int(user["id"])
                    if (
                        user
                        and user.get("id")
                        is not None
                    )
                    else None
                )

                duplicate_claim_normalized_text = (
                    normalize_duplicate_text(
                        duplicate_claim_text
                    )
                )

                duplicate_claim_fingerprint = (
                    duplicate_fingerprint(
                        duplicate_claim_text
                    )
                )

                for media_identity_id in (
                    _unique_media_identity_ids(
                        targets
                    )
                ):
                    try:
                        claim_result = (
                            database.claim_duplicate_news_publication(
                                media_identity_id=(
                                    media_identity_id
                                ),
                                fingerprint=(
                                    duplicate_claim_fingerprint
                                ),
                                source_key=(
                                    source_key
                                ),
                                actor_user_id=(
                                    duplicate_claim_actor_user_id
                                ),
                            )
                        )

                    except Exception:
                        # Duplicate Guard has historically been fail-open on
                        # database errors. Preserve that contract: a transient
                        # claim failure must not stop normal publication.
                        logger.exception(
                            "Duplicate publication claim failed | "
                            "media_identity_id=%s | source=%s",
                            media_identity_id,
                            source_key,
                        )
                        continue

                    # No RPC row is treated as an unavailable claim service,
                    # preserving the existing fail-open database contract.
                    if not claim_result:
                        logger.warning(
                            "Duplicate publication claim returned no row | "
                            "media_identity_id=%s | source=%s",
                            media_identity_id,
                            source_key,
                        )
                        continue

                    if bool(
                        claim_result.get(
                            "claimed"
                        )
                    ):
                        duplicate_claimed_media_ids.append(
                            media_identity_id
                        )
                        continue

                    # Another source owns the live fingerprint reservation.
                    # Release any reservations this invocation already acquired
                    # for other Media Identities before returning the existing
                    # duplicate-warning contract.
                    for claimed_media_identity_id in (
                        duplicate_claimed_media_ids
                    ):
                        try:
                            database.release_duplicate_news_publication(
                                media_identity_id=(
                                    claimed_media_identity_id
                                ),
                                fingerprint=(
                                    duplicate_claim_fingerprint
                                ),
                                source_key=(
                                    source_key
                                ),
                            )
                        except Exception:
                            logger.exception(
                                "Duplicate publication claim release failed | "
                                "media_identity_id=%s | source=%s",
                                claimed_media_identity_id,
                                source_key,
                            )

                    duplicate_claimed_media_ids = []

                    try:
                        from core.duplicate_pending import (
                            create_pending_duplicate,
                        )

                        duplicate_token = (
                            create_pending_duplicate(
                                chat_id=chat_id,
                                prepared=prepared,
                                targets=targets,
                            )
                        )

                    except Exception:
                        logger.exception(
                            "Duplicate pending creation failed | source=%s",
                            source_key,
                        )
                        duplicate_token = None

                    return {
                        "ok": False,
                        "results": [],
                        "errors": [],
                        "duplicate_token":
                            duplicate_token,
                        "duplicate_warning":
                            True,
                        "matches": [
                            {
                                "media_identity_id":
                                    media_identity_id,
                                "match_type":
                                    "exact_in_flight",
                                "similarity":
                                    1.0,
                                "publication_id":
                                    None,
                                "actor_user_id":
                                    None,
                                "published_at":
                                    None,
                            }
                        ],
                    }

        except Exception:
            logger.exception(
                "Duplicate publication claim setup failed | source=%s",
                source_key,
            )

    store.claim_source(
        source_key
    )

    store.mark_source(
        source_key,
        "sending",
    )

    results: List[
        DeliveryResult
    ] = []

    failure_details: Dict[
        str,
        ExecutorResult,
    ] = {}

    plan_cache: Dict[
        Tuple[Any, ...],
        Any,
    ] = {}

    target_content_cache: Dict[
        Tuple[Any, ...],
        Tuple[str, str],
    ] = {}

    translation_cache: Dict[
    str,
    PreparedContent,
    ] = {}

    legacy_telegram_failed = False

    for target in targets:

        if (
            target.kind == "legacy"
            and target.platform == "bale"
            and legacy_telegram_failed
        ):
            results.append(
                DeliveryResult(
                    target.platform,
                    target.workspace_id,
                    target.destination_id,
                    target.external_id,
                    status="failed",
                    error=(
                        "legacy telegram prerequisite failed"
                    ),
                    idempotency_key=(
                        f"{source_key}:"
                        f"{canonical_target_identity(target)}"
                    ),
                )
            )

            continue

        identity = (
            canonical_target_identity(
                target
            )
        )

        state = (
            store.claim_destination(
                source_key,
                identity,
            )
        )

        if state.status == "succeeded":
            if not delivery_state_has_success_proof(
                state
            ):
                state.status = "failed"
                state.error = (
                    "delivery marked succeeded without transport proof"
                )
            else:
                results.append(
                    DeliveryResult(
                        target.platform,
                        target.workspace_id,
                        target.destination_id,
                        target.external_id,
                        status="succeeded",
                        attempt=state.attempt,
                        idempotency_key=(
                            f"{source_key}:{identity}"
                        ),
                        primary_message_id=(
                            state.message_ids.get(
                                "primary"
                            )
                        ),
                        message_ids=(
                            state.all_message_ids.get(
                                "primary",
                                (),
                            )
                        ),
                        followup_message_ids=tuple(
                            value
                            for key, value
                            in sorted(
                                state.message_ids.items()
                            )
                            if key.startswith(
                                "followup:"
                            )
                        ),
                        blockquote_message_ids=tuple(
                            value
                            for key, value
                            in sorted(
                                state.message_ids.items()
                            )
                            if key.startswith(
                                "blockquote:"
                            )
                        ),
                    )
                )

                continue

        if hasattr(
            store,
            "begin_persistent_attempt",
        ):
            state = (
                store.begin_persistent_attempt(
                    source_key=source_key,
                    target_identity=identity,
                    platform=target.platform,
                    destination_chat_id=(
                        target.external_id
                    ),
                    workspace_id=(
                        target.workspace_id
                    ),
                    destination_id=(
                        target.destination_id
                    ),
                )
            )
        else:
            state = (
                store.begin_attempt(
                    source_key,
                    identity,
                )
            )

        if (
            state is not None
            and state.status == "succeeded"
            and delivery_state_has_success_proof(
                state
            )
        ):
            results.append(
                DeliveryResult(
                    target.platform,
                    target.workspace_id,
                    target.destination_id,
                    target.external_id,
                    status="succeeded",
                    attempt=state.attempt,
                    idempotency_key=(
                        f"{source_key}:{identity}"
                    ),
                    primary_message_id=(
                        state.message_ids.get(
                            "primary"
                        )
                    ),
                    message_ids=(
                        state.all_message_ids.get(
                            "primary",
                            (),
                        )
                    ),
                    followup_message_ids=tuple(
                        value
                        for key, value
                        in sorted(
                            state.message_ids.items()
                        )
                        if key.startswith(
                            "followup:"
                        )
                    ),
                    blockquote_message_ids=tuple(
                        value
                        for key, value
                        in sorted(
                            state.message_ids.items()
                        )
                        if key.startswith(
                            "blockquote:"
                        )
                    ),
                )
            )

            continue

        if state is None:
            current = (
                store.get_delivery(
                    source_key,
                    identity,
                )
            )

            terminal = bool(
                current
                and current.status
                == "failed_terminal"
            )

            results.append(
                DeliveryResult(
                    target.platform,
                    target.workspace_id,
                    target.destination_id,
                    target.external_id,
                    status=(
                        "failed_terminal"
                        if terminal
                        else "sending"
                    ),
                    error=(
                        current.error
                        if terminal
                        else (
                            "delivery already claimed by "
                            "another in-process worker"
                        )
                    ),
                    attempt=(
                        current.attempt
                        if current
                        else 0
                    ),
                    idempotency_key=(
                        f"{source_key}:{identity}"
                    ),
                )
            )

            continue

        try:
            from core.caption_manager import (
                analyze_content,
                suppress_smart_summary,
            )

            target_prepared = (
                _translated_prepared_for_target(
                    target,
                    analyzed,
                    translation_cache,
                )
            )

            content_key = (
                target.kind,
                target.workspace_id,
                (
                    target.destination_id
                    if target.kind
                    != "legacy"
                    else None
                ),
            )

            cached_content = (
                target_content_cache.get(
                    content_key
                )
            )

            if cached_content is None:
                cached_content = (
                    _target_content_and_branding(
                        chat_id,
                        target,
                        target_prepared,
                    )
                )

                target_content_cache[
                    content_key
                ] = cached_content

            (
                main_text,
                branding,
            ) = cached_content

            plan_key = (
                main_text,
                branding,
                target_prepared.editorial_finalized,
                repr(
                    tuple(
                        dict(item)
                        for item in target_prepared.blockquote_blocks
                    )
                ),
                repr(
                    tuple(
                        dict(item)
                        for item in target_prepared.expandable_blocks
                    )
                ),
                repr(
                    tuple(
                        dict(item)
                        for item in target_prepared.other_entities
                    )
                ),
            )

            plan = (
                plan_cache.get(
                    plan_key
                )
            )

            if plan is None:
                with suppress_smart_summary():
                    plan = analyze_content(
                        output_kind="media" if target_prepared.files else "text",
                        main_text=main_text,
                        blockquote_blocks=list(
                            target_prepared.blockquote_blocks
                        ),
                        expandable_blocks=list(
                            target_prepared.expandable_blocks
                        ),
                        other_entities=list(
                            target_prepared.other_entities
                        ),
                        branding=branding,
                        editorial_finalized=(
                            target_prepared.editorial_finalized
                        ),
                    )

                plan_cache[
                    plan_key
                ] = plan

            platform_plan = (
                plan.telegram
                if (
                    target_prepared.files
                    and target.platform
                    == "telegram"
                )
                else (
                    plan.bale
                    if target_prepared.files
                    else plan.text[
                        target.platform
                    ]
                )
            )

            error = None
            part_name = None

            for (
                part_name,
                part_kind,
                index,
            ) in _delivery_parts(
                target_prepared,
                platform_plan,
            ):
                if store.part_completed(
                    source_key,
                    identity,
                    part_name,
                ):
                    continue

                outcome = (
                    _execute_delivery_part(
                        chat_id,
                        api_url,
                        target,
                        target_prepared,
                        platform_plan,
                        part_kind,
                        index,
                    )
                )

                if not _outcome_ok(
                    outcome
                ):
                    detail = (
                        _normalize_executor_result(
                            outcome
                        )
                    )

                    failure_details[
                        identity
                    ] = detail

                    error = (
                        detail.error
                        or f"{part_name} failed"
                    )

                    store.mark_failed(
                        source_key,
                        identity,
                        error,
                    )

                    if (
                        target.kind == "legacy"
                        and target.platform
                        == "telegram"
                    ):
                        legacy_telegram_failed = True

                    break

                store.part_succeeded(
                    source_key,
                    identity,
                    part_name,
                    _message_id_from_outcome(
                        outcome
                    ),
                    _message_ids_from_outcome(
                        outcome
                    ),
                    _chat_id_from_outcome(
                        outcome
                    ),
                )

            final = (
                store.get_delivery(
                    source_key,
                    identity,
                )
            )

            if (
                error is None
                and delivery_state_has_success_proof(
                    final
                )
            ):
                store.mark_succeeded(
                    source_key,
                    identity,
                )
            elif error is None:
                store.mark_failed(
                    source_key,
                    identity,
                    "delivery completed without transport confirmation",
                )

            final = (
                store.get_delivery(
                    source_key,
                    identity,
                )
            )

            detail = (
                failure_details.get(
                    identity
                )
            )

            results.append(
                DeliveryResult(
                    target.platform,
                    target.workspace_id,
                    target.destination_id,
                    final.message_chat_ids.get(
                        "primary",
                        target.external_id,
                    ),
                    primary_message_id=(
                        final.message_ids.get(
                            "primary"
                        )
                    ),
                    message_ids=(
                        final.all_message_ids.get(
                            "primary",
                            (),
                        )
                    ),
                    followup_message_ids=tuple(
                        value
                        for key, value
                        in sorted(
                            final.message_ids.items()
                        )
                        if key.startswith(
                            "followup:"
                        )
                    ),
                    blockquote_message_ids=tuple(
                        value
                        for key, value
                        in sorted(
                            final.message_ids.items()
                        )
                        if key.startswith(
                            "blockquote:"
                        )
                    ),
                    status=final.status,
                    error=final.error,
                    attempt=final.attempt,
                    idempotency_key=(
                        f"{source_key}:{identity}"
                    ),
                    status_code=(
                        detail.status_code
                        if detail
                        else None
                    ),
                    error_code=(
                        detail.error_code
                        if detail
                        else None
                    ),
                    failed_part=(
                        part_name
                        if detail
                        else None
                    ),
                    operation=(
                        detail.operation
                        if detail
                        else None
                    ),
                )
            )

        except Exception as exc:
            store.mark_failed(
                source_key,
                identity,
                str(exc),
            )

            if (
                target.kind == "legacy"
                and target.platform == "telegram"
            ):
                legacy_telegram_failed = True

            logger.exception(
                "Publication target failed | target=%s | %s",
                target.key,
                exc,
            )

            final = (
                store.get_delivery(
                    source_key,
                    identity,
                )
            )

            results.append(
                DeliveryResult(
                    target.platform,
                    target.workspace_id,
                    target.destination_id,
                    target.external_id,
                    status="failed",
                    error=str(exc),
                    attempt=(
                        final.attempt
                        if final
                        else 0
                    ),
                    idempotency_key=(
                        f"{source_key}:{identity}"
                    ),
                )
            )

    all_succeeded = bool(
        results
    ) and all(
        item.status
        == "succeeded"
        for item in results
    )

    any_succeeded = any(
        item.status
        == "succeeded"
        for item in results
    )

    all_terminal = bool(
        results
    ) and all(
        item.status
        == "failed_terminal"
        for item in results
    )

    source_status = (
        "succeeded"
        if all_succeeded
        else (
            "partial"
            if any_succeeded
            else (
                "failed_terminal"
                if all_terminal
                else "failed"
            )
        )
    )

    store.mark_source(
        source_key,
        source_status,
    )

    if hasattr(
        store,
        "begin_persistent_attempt",
    ):
        from core import database

        database.mark_persistent_publication_source(
            source_key=source_key,
            status=source_status,
        )

    if any_succeeded:
        try:
            from core import database
            from core.duplicate_guard import (
                duplicate_fingerprint,
                normalize_duplicate_text,
            )

            history_text = (
                analyzed.neutral_text
                or analyzed.main_text
                or ""
            ).strip()

            if history_text:
                user = database.get_user_by_telegram_id(
                    chat_id
                )

                actor_user_id = (
                    int(user["id"])
                    if (
                        user
                        and user.get("id")
                        is not None
                    )
                    else None
                )

                normalized_history_text = (
                    normalize_duplicate_text(
                        history_text
                    )
                )

                history_fingerprint = (
                    duplicate_fingerprint(
                        history_text
                    )
                )

                claimed_media_ids = set(
                    duplicate_claimed_media_ids
                )

                for media_identity_id in (
                    _unique_media_identity_ids(
                        targets
                    )
                ):
                    try:
                        if (
                            media_identity_id
                            in claimed_media_ids
                        ):
                            database.finalize_duplicate_news_publication(
                                media_identity_id=(
                                    media_identity_id
                                ),
                                fingerprint=(
                                    duplicate_claim_fingerprint
                                ),
                                source_key=(
                                    source_key
                                ),
                                actor_user_id=(
                                    duplicate_claim_actor_user_id
                                ),
                                content_text=(
                                    duplicate_claim_text
                                ),
                                normalized_text=(
                                    duplicate_claim_normalized_text
                                ),
                            )
                        else:
                            # allow_duplicate=True and fail-open claim errors
                            # continue to use the established durable history
                            # writer so successful publications are recorded.
                            database.record_duplicate_news_history(
                                media_identity_id=(
                                    media_identity_id
                                ),
                                actor_user_id=(
                                    actor_user_id
                                ),
                                source_key=(
                                    source_key
                                ),
                                content_text=(
                                    history_text
                                ),
                                normalized_text=(
                                    normalized_history_text
                                ),
                                fingerprint=(
                                    history_fingerprint
                                ),
                            )

                    except Exception:
                        logger.exception(
                            "Duplicate history finalize/write failed | "
                            "media_identity_id=%s | source=%s",
                            media_identity_id,
                            source_key,
                        )

        except Exception:
            logger.exception(
                "Duplicate history recording failed | source=%s",
                source_key,
            )

    elif duplicate_claimed_media_ids:
        # Nothing reached a destination, so this news must remain eligible
        # for a legitimate retry. Release only reservations owned by this
        # source; crash recovery is additionally bounded by the DB lease.
        try:
            from core import database

            for media_identity_id in (
                duplicate_claimed_media_ids
            ):
                try:
                    database.release_duplicate_news_publication(
                        media_identity_id=(
                            media_identity_id
                        ),
                        fingerprint=(
                            duplicate_claim_fingerprint
                        ),
                        source_key=(
                            source_key
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Duplicate publication claim release failed | "
                        "media_identity_id=%s | source=%s",
                        media_identity_id,
                        source_key,
                    )

        except Exception:
            logger.exception(
                "Duplicate publication claim cleanup failed | source=%s",
                source_key,
            )

    return {
        "ok":
            all_succeeded,

        "results":
            results,

        "errors":
            resolution_errors,
    }
