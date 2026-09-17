"""Short-lived pending state for Duplicate News Guard overrides.

Two storage tiers:

- In-memory tier (historical behaviour): the original
  PendingDuplicatePublication, including the frozen PreparedContent,
  is retained in-process for fast consumption within one worker.
- Persistent tier (B8, flag-gated): a reconstructable *descriptor*
  (never the opaque PreparedContent object) is mirrored to Supabase
  and consumed atomically via the consume_duplicate_override RPC
  (schema/028), so an override survives restart/deploy and can never
  be consumed twice across workers.

The consume path is the same for both tiers: in-memory first, then
the atomic RPC. A token that was consumed by either tier is dead.
"""

from __future__ import annotations

import logging
import secrets
import time

from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List, Optional

from core.content_model import (
    PreparedContent,
    PublicationTarget,
)


logger = logging.getLogger(__name__)


PENDING_DUPLICATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class PendingDuplicatePublication:
    token: str
    chat_id: int
    prepared: PreparedContent
    targets: tuple[PublicationTarget, ...]
    created_at: float


_lock = RLock()

_pending: Dict[
    str,
    PendingDuplicatePublication,
] = {}


def _persistence_enabled() -> bool:
    """B8 flag check, isolated for test patching."""
    try:
        from core.database import (
            persistent_duplicate_override_enabled,
        )

        return persistent_duplicate_override_enabled()
    except Exception:
        return False


def _descriptor_from_pending(
    pending: PendingDuplicatePublication,
) -> Dict[str, Any]:
    """
    Build the reconstructable descriptor persisted for B8.

    This intentionally excludes the opaque PreparedContent object.
    On consume, the application re-prepares content from
    main_text/neutral_text plus entity blocks, and re-resolves
    targets from workspace/destination identities.
    """
    return {
        "main_text": str(pending.prepared.main_text or ""),
        "neutral_text": str(pending.prepared.neutral_text or ""),
        "blockquote_blocks": [
            dict(item)
            for item in (pending.prepared.blockquote_blocks or ())
        ],
        "expandable_blocks": [
            dict(item)
            for item in (pending.prepared.expandable_blocks or ())
        ],
        "other_entities": [
            dict(item)
            for item in (pending.prepared.other_entities or ())
        ],
        "files": [
            dict(item)
            for item in (pending.prepared.files or ())
        ],
        "editorial_finalized": bool(
            pending.prepared.editorial_finalized
        ),
        "source_key": str(pending.prepared.source_key or ""),
        "targets": [
            {
                "key": str(target.key or ""),
                "kind": str(target.kind or ""),
                "platform": str(target.platform or ""),
                "external_id": str(target.external_id or ""),
                "workspace_id": (
                    int(target.workspace_id)
                    if target.workspace_id is not None
                    else None
                ),
                "destination_id": (
                    int(target.destination_id)
                    if target.destination_id is not None
                    else None
                ),
            }
            for target in (pending.targets or ())
        ],
    }


def _persist_override(
    token: str,
    chat_id: int,
    descriptor: Dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Best-effort mirror of one override token (B8). Fail-closed is
    NOT required here: the in-memory token remains authoritative for
    the current worker; the persistent row is a recovery + cross-worker
    safety net."""
    try:
        from core.database import (
            create_persistent_duplicate_override,
        )

        create_persistent_duplicate_override(
            token=token,
            chat_id=int(chat_id),
            descriptor=descriptor,
            ttl_seconds=ttl_seconds,
        )
    except Exception:
        logger.exception(
            "Persistent duplicate override write failed "
            "(continuing in-memory) | chat=%s",
            chat_id,
        )


def _cleanup_expired() -> None:
    now = time.time()

    expired = [
        token
        for token, item in _pending.items()
        if (
            now - item.created_at
            > PENDING_DUPLICATE_TTL_SECONDS
        )
    ]

    for token in expired:
        _pending.pop(token, None)


def create_pending_duplicate(
    *,
    chat_id: int,
    prepared: PreparedContent,
    targets: List[PublicationTarget],
) -> str:
    """
    Preserve one blocked duplicate publication long enough
    for an explicit user override.
    """
    token = secrets.token_urlsafe(12)

    pending = PendingDuplicatePublication(
        token=token,
        chat_id=int(chat_id),
        prepared=prepared,
        targets=tuple(targets),
        created_at=time.time(),
    )

    with _lock:
        _cleanup_expired()
        _pending[token] = pending

    if _persistence_enabled():
        _persist_override(
            token=token,
            chat_id=int(chat_id),
            descriptor=_descriptor_from_pending(pending),
            ttl_seconds=PENDING_DUPLICATE_TTL_SECONDS,
        )

    return token


def get_pending_duplicate(
    *,
    token: str,
    chat_id: int,
) -> Optional[PendingDuplicatePublication]:
    """
    Read a pending override without consuming it.
    Ownership is restricted to the originating chat/user.
    """
    with _lock:
        _cleanup_expired()

        pending = _pending.get(
            str(token)
        )

        if pending is None:
            return None

        if pending.chat_id != int(chat_id):
            return None

        return pending


def consume_pending_duplicate(
    *,
    token: str,
    chat_id: int,
) -> Optional[PendingDuplicatePublication]:
    """
    Atomically consume a pending override.

    A token cannot be reused after a successful consume.

    Consumption order:

    1. In-memory (fast path, current worker).
    2. Persistent RPC (B8) — the DB-side DELETE ... RETURNING is the
       cross-worker atomicity guarantee; the losing worker receives
       None.
    """
    token = str(token)

    with _lock:
        _cleanup_expired()

        pending = _pending.get(token)

        if pending is not None:
            if pending.chat_id != int(chat_id):
                return None

            _pending.pop(token, None)

            if _persistence_enabled():
                # Invalidate the persistent mirror so another worker
                # cannot consume the same override afterwards.
                try:
                    from core.database import (
                        consume_persistent_duplicate_override,
                    )

                    consume_persistent_duplicate_override(
                        token=token,
                        chat_id=int(chat_id),
                    )
                except Exception:
                    logger.exception(
                        "Persistent duplicate override mirror "
                        "invalidation failed | chat=%s",
                        chat_id,
                    )

            return pending

    if _persistence_enabled():
        try:
            from core.database import (
                consume_persistent_duplicate_override,
            )

            descriptor = consume_persistent_duplicate_override(
                token=token,
                chat_id=int(chat_id),
            )

        except Exception:
            # Fail closed: a persistence error must not look like a
            # consumable token.
            logger.exception(
                "Persistent duplicate override consume failed | "
                "chat=%s",
                chat_id,
            )
            return None

        if descriptor is None:
            return None

        return _pending_from_descriptor(
            token=token,
            chat_id=int(chat_id),
            descriptor=descriptor,
        )

    return None


def _pending_from_descriptor(
    *,
    token: str,
    chat_id: int,
    descriptor: Dict[str, Any],
) -> Optional[PendingDuplicatePublication]:
    """
    Reconstruct a PendingDuplicatePublication from the persisted
    descriptor by re-preparing content and re-resolving targets.
    """
    try:
        from core.content_model import (
            PreparedContent as _PreparedContent,
        )
        from core.publication_engine import (
            _targets_from_descriptor_identities,
        )

        prepared = _PreparedContent(
            main_text=str(descriptor.get("main_text") or ""),
            neutral_text=str(descriptor.get("neutral_text") or ""),
            blockquote_blocks=list(
                descriptor.get("blockquote_blocks") or []
            ),
            expandable_blocks=list(
                descriptor.get("expandable_blocks") or []
            ),
            other_entities=list(
                descriptor.get("other_entities") or []
            ),
            files=list(descriptor.get("files") or []),
            editorial_finalized=bool(
                descriptor.get("editorial_finalized")
            ),
            source_key=str(descriptor.get("source_key") or ""),
        )

        targets = _targets_from_descriptor_identities(
            descriptor.get("targets") or []
        )

        if not targets:
            logger.error(
                "Duplicate override descriptor resolved to no "
                "targets | chat=%s",
                chat_id,
            )
            return None

        return PendingDuplicatePublication(
            token=token,
            chat_id=int(chat_id),
            prepared=prepared,
            targets=tuple(targets),
            created_at=time.time(),
        )

    except Exception:
        logger.exception(
            "Duplicate override reconstruction failed | chat=%s",
            chat_id,
        )
        return None
