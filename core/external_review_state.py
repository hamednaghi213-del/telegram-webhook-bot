"""In-process pending review state for external content ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import time
from typing import (
    Dict,
    Optional,
    Tuple,
)

from core.external_content_model import (
    NormalizedExternalContent,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalReviewStateError(
    RuntimeError
):
    """Base error for external review state."""


class ExternalReviewNotFound(
    ExternalReviewStateError
):
    """Raised when no active pending review exists."""


class ExternalReviewExpired(
    ExternalReviewStateError
):
    """Raised when a pending review has expired."""


class ExternalReviewConflict(
    ExternalReviewStateError
):
    """Raised when an active review would be overwritten."""


# =========================================================
# MODEL
# =========================================================


@dataclass(frozen=True)
class PendingExternalReview:
    """
    One external-content review waiting for user action.

    This state is intentionally platform-neutral. chat_id identifies the
    current interaction channel but the normalized content itself contains
    no Telegram/Bale-specific publication identity.
    """

    review_id: str
    chat_id: int
    content: NormalizedExternalContent
    created_at: float
    expires_at: float

    @property
    def expired(
        self,
    ) -> bool:
        return (
            time()
            >= self.expires_at
        )


# =========================================================
# STORE
# =========================================================


class ExternalReviewStateStore:
    """
    Thread-safe in-process pending-review store.

    This is deliberately isolated behind a small interface so durable
    persistence can replace it later without changing external ingestion
    or Shared Publication Engine contracts.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 1800,
    ) -> None:
        ttl = int(
            ttl_seconds
        )

        if ttl <= 0:
            raise ValueError(
                "ttl_seconds must be > 0"
            )

        self.ttl_seconds = ttl

        self._lock = RLock()

        self._by_chat: Dict[
            int,
            PendingExternalReview,
        ] = {}

        self._by_id: Dict[
            str,
            PendingExternalReview,
        ] = {}

    # -----------------------------------------------------
    # INTERNAL
    # -----------------------------------------------------

    def _remove(
        self,
        pending: PendingExternalReview,
    ) -> None:
        current_chat = (
            self._by_chat.get(
                pending.chat_id
            )
        )

        if (
            current_chat is pending
            or (
                current_chat is not None
                and current_chat.review_id
                == pending.review_id
            )
        ):
            self._by_chat.pop(
                pending.chat_id,
                None,
            )

        current_id = (
            self._by_id.get(
                pending.review_id
            )
        )

        if (
            current_id is pending
            or (
                current_id is not None
                and current_id.chat_id
                == pending.chat_id
            )
        ):
            self._by_id.pop(
                pending.review_id,
                None,
            )

    def _purge_if_expired(
        self,
        pending: Optional[
            PendingExternalReview
        ],
    ) -> Optional[
        PendingExternalReview
    ]:
        if pending is None:
            return None

        if not pending.expired:
            return pending

        self._remove(
            pending
        )

        return None

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    def create(
        self,
        *,
        review_id: str,
        chat_id: int,
        content: NormalizedExternalContent,
        replace_existing: bool = False,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            raise ValueError(
                "review_id is required"
            )

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise TypeError(
                "content must be NormalizedExternalContent"
            )

        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            existing_chat = (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

            existing_id = (
                self._purge_if_expired(
                    self._by_id.get(
                        normalized_review_id
                    )
                )
            )

            if (
                existing_id is not None
                and existing_id.chat_id
                != normalized_chat_id
            ):
                raise ExternalReviewConflict(
                    "review_id already belongs to another chat"
                )

            if (
                existing_chat is not None
                and existing_chat.review_id
                != normalized_review_id
            ):
                if not replace_existing:
                    raise ExternalReviewConflict(
                        "chat already has an active external review"
                    )

                self._remove(
                    existing_chat
                )

            if existing_id is not None:
                if not replace_existing:
                    raise ExternalReviewConflict(
                        "review_id already exists"
                    )

                self._remove(
                    existing_id
                )

            now = time()

            pending = (
                PendingExternalReview(
                    review_id=(
                        normalized_review_id
                    ),
                    chat_id=(
                        normalized_chat_id
                    ),
                    content=content,
                    created_at=now,
                    expires_at=(
                        now
                        + self.ttl_seconds
                    ),
                )
            )

            self._by_chat[
                normalized_chat_id
            ] = pending

            self._by_id[
                normalized_review_id
            ] = pending

            return pending

    # -----------------------------------------------------
    # READ
    # -----------------------------------------------------

    def get_for_chat(
        self,
        chat_id: int,
    ) -> Optional[
        PendingExternalReview
    ]:
        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            return (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

    def get_by_id(
        self,
        review_id: str,
    ) -> Optional[
        PendingExternalReview
    ]:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        if not normalized_review_id:
            return None

        with self._lock:
            return (
                self._purge_if_expired(
                    self._by_id.get(
                        normalized_review_id
                    )
                )
            )

    def require(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        normalized_review_id = str(
            review_id
            or ""
        ).strip()

        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            pending = (
                self._by_id.get(
                    normalized_review_id
                )
            )

            if pending is None:
                raise ExternalReviewNotFound(
                    "external review not found"
                )

            if pending.expired:
                self._remove(
                    pending
                )

                raise ExternalReviewExpired(
                    "external review expired"
                )

            if (
                pending.chat_id
                != normalized_chat_id
            ):
                raise ExternalReviewNotFound(
                    "external review does not belong to this chat"
                )

            return pending

    # -----------------------------------------------------
    # COMPLETE / CANCEL
    # -----------------------------------------------------

    def pop(
        self,
        *,
        review_id: str,
        chat_id: int,
    ) -> PendingExternalReview:
        with self._lock:
            pending = self.require(
                review_id=review_id,
                chat_id=chat_id,
            )

            self._remove(
                pending
            )

            return pending

    def cancel_for_chat(
        self,
        chat_id: int,
    ) -> bool:
        normalized_chat_id = int(
            chat_id
        )

        with self._lock:
            pending = (
                self._purge_if_expired(
                    self._by_chat.get(
                        normalized_chat_id
                    )
                )
            )

            if pending is None:
                return False

            self._remove(
                pending
            )

            return True

    # -----------------------------------------------------
    # MAINTENANCE
    # -----------------------------------------------------

    def cleanup_expired(
        self,
    ) -> int:
        with self._lock:
            expired = tuple(
                pending
                for pending
                in self._by_id.values()
                if pending.expired
            )

            for pending in expired:
                self._remove(
                    pending
                )

            return len(
                expired
            )

    def reset(
        self,
    ) -> None:
        with self._lock:
            self._by_chat.clear()
            self._by_id.clear()

    def __len__(
        self,
    ) -> int:
        with self._lock:
            self.cleanup_expired()

            return len(
                self._by_id
            )

    def active_review_ids(
        self,
    ) -> Tuple[str, ...]:
        with self._lock:
            self.cleanup_expired()

            return tuple(
                sorted(
                    self._by_id.keys()
                )
            )


DEFAULT_EXTERNAL_REVIEW_STATE_STORE = (
    ExternalReviewStateStore()
)
