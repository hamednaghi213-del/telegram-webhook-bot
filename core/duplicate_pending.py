"""Short-lived pending state for Duplicate News Guard overrides."""

from __future__ import annotations

import secrets
import time

from dataclasses import dataclass
from threading import RLock
from typing import Dict, List, Optional

from core.content_model import (
    PreparedContent,
    PublicationTarget,
)


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

        _pending.pop(
            str(token),
            None,
        )

        return pending
