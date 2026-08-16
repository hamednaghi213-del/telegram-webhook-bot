import logging
import threading
import time
import uuid

from dataclasses import dataclass
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


# =========================================================
# PENDING REVIEW POLICY
# =========================================================

DEFAULT_PENDING_TTL_SECONDS = 60 * 60 * 6

STATUS_PENDING = "pending"
STATUS_PUBLISHED_SUMMARY = "published_summary"
STATUS_PUBLISHED_ORIGINAL = "published_original"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"


# =========================================================
# ADMIN INSTRUCTION POLICY
# =========================================================

ADMIN_INSTRUCTION_IDLE = "idle"
ADMIN_INSTRUCTION_WAITING = "waiting"
ADMIN_INSTRUCTION_PROCESSING = "processing"


# =========================================================
# REVIEW OBJECT
# =========================================================

@dataclass
class PendingEditorialReview:

    review_id: str

    user_id: int

    content_type: str

    original_text: str

    current_summary: str

    regeneration_count: int

    created_at: float

    updated_at: float

    status: str

    metadata: Dict[str, Any]


# =========================================================
# IN-MEMORY STORE
# =========================================================

_pending_reviews: Dict[
    str,
    PendingEditorialReview
] = {}

_store_lock = threading.RLock()


# =========================================================
# HELPERS
# =========================================================

def _now() -> float:

    return time.time()


def _new_review_id() -> str:

    return uuid.uuid4().hex[:16]


def _is_expired(
    review: PendingEditorialReview,
    ttl_seconds: int = (
        DEFAULT_PENDING_TTL_SECONDS
    )
) -> bool:

    if ttl_seconds <= 0:
        return False

    age = (
        _now()
        - review.updated_at
    )

    return (
        age > ttl_seconds
    )


def _ensure_admin_instruction_metadata(
    review: PendingEditorialReview
) -> None:

    if review.metadata is None:

        review.metadata = {}

    review.metadata.setdefault(
        "admin_instruction_state",
        ADMIN_INSTRUCTION_IDLE
    )

    review.metadata.setdefault(
        "admin_instruction",
        ""
    )

    review.metadata.setdefault(
        "admin_instruction_requested_at",
        None
    )

    review.metadata.setdefault(
        "admin_instruction_received_at",
        None
    )

    review.metadata.setdefault(
        "admin_instruction_completed_at",
        None
    )

    review.metadata.setdefault(
        "admin_instruction_attempt_count",
        0
    )


# =========================================================
# CREATE REVIEW
# =========================================================

def create_pending_review(
    user_id: int,
    content_type: str,
    original_text: str,
    current_summary: str,
    regeneration_count: int = 0,
    metadata: Optional[
        Dict[str, Any]
    ] = None
) -> PendingEditorialReview:

    review_id = (
        _new_review_id()
    )

    now = _now()

    review_metadata = dict(
        metadata
        or {}
    )

    review_metadata.setdefault(
        "admin_instruction_state",
        ADMIN_INSTRUCTION_IDLE
    )

    review_metadata.setdefault(
        "admin_instruction",
        ""
    )

    review_metadata.setdefault(
        "admin_instruction_requested_at",
        None
    )

    review_metadata.setdefault(
        "admin_instruction_received_at",
        None
    )

    review_metadata.setdefault(
        "admin_instruction_completed_at",
        None
    )

    review_metadata.setdefault(
        "admin_instruction_attempt_count",
        0
    )

    review = (
        PendingEditorialReview(
            review_id=review_id,
            user_id=int(
                user_id
            ),
            content_type=str(
                content_type
            ),
            original_text=str(
                original_text
                or ""
            ),
            current_summary=str(
                current_summary
                or ""
            ),
            regeneration_count=int(
                regeneration_count
                or 0
            ),
            created_at=now,
            updated_at=now,
            status=STATUS_PENDING,
            metadata=review_metadata
        )
    )

    with _store_lock:

        _pending_reviews[
            review_id
        ] = review

    logger.info(
        f"📝 Pending editorial review created | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"type={content_type} | "
        f"regeneration_count={regeneration_count} | "
        f"admin_instruction_state="
        f"{ADMIN_INSTRUCTION_IDLE}"
    )

    return review


# =========================================================
# GET REVIEW
# =========================================================

def get_pending_review(
    review_id: str,
    user_id: Optional[int] = None,
    ttl_seconds: int = (
        DEFAULT_PENDING_TTL_SECONDS
    )
) -> Optional[
    PendingEditorialReview
]:

    review_id = str(
        review_id
        or ""
    ).strip()

    if not review_id:

        return None

    with _store_lock:

        review = (
            _pending_reviews.get(
                review_id
            )
        )

        if review is None:
            return None

        if (
            user_id is not None
            and review.user_id
            != int(user_id)
        ):

            logger.warning(
                f"⚠️ Pending review user mismatch | "
                f"review_id={review_id} | "
                f"expected={review.user_id} | "
                f"received={user_id}"
            )

            return None

        if (
            review.status
            != STATUS_PENDING
        ):

            return review

        if _is_expired(
            review,
            ttl_seconds
        ):

            review.status = (
                STATUS_EXPIRED
            )

            review.updated_at = (
                _now()
            )

            logger.info(
                f"⌛ Pending review expired | "
                f"review_id={review_id}"
            )

            return review

        _ensure_admin_instruction_metadata(
            review
        )

        return review


# =========================================================
# UPDATE SUMMARY
# =========================================================

def update_pending_summary(
    review_id: str,
    user_id: int,
    new_summary: str,
    regeneration_count: int,
    metadata: Optional[
        Dict[str, Any]
    ] = None
) -> Optional[
    PendingEditorialReview
]:

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:

        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        logger.warning(
            f"⚠️ Pending review update rejected | "
            f"review_id={review_id} | "
            f"status={review.status}"
        )

        return None

    with _store_lock:

        review.current_summary = (
            str(
                new_summary
                or ""
            )
        )

        review.regeneration_count = (
            int(
                regeneration_count
                or 0
            )
        )

        if metadata:

            review.metadata.update(
                metadata
            )

        _ensure_admin_instruction_metadata(
            review
        )

        review.updated_at = (
            _now()
        )

    logger.info(
        f"🔄 Pending review summary updated | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"regeneration_count="
        f"{review.regeneration_count}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# START WAITING
# =========================================================

def start_waiting_for_admin_instruction(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:

        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        logger.warning(
            f"⚠️ Admin instruction wait rejected | "
            f"review_id={review_id} | "
            f"status={review.status}"
        )

        return None

    with _store_lock:

        _ensure_admin_instruction_metadata(
            review
        )

        review.metadata[
            "admin_instruction_state"
        ] = (
            ADMIN_INSTRUCTION_WAITING
        )

        review.metadata[
            "admin_instruction"
        ] = ""

        review.metadata[
            "admin_instruction_requested_at"
        ] = _now()

        review.metadata[
            "admin_instruction_received_at"
        ] = None

        review.metadata[
            "admin_instruction_completed_at"
        ] = None

        review.updated_at = (
            _now()
        )

    logger.info(
        f"✏️ Pending review waiting for "
        f"admin instruction | "
        f"review_id={review_id} | "
        f"user={user_id}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# SAVE RECEIVED INSTRUCTION
# =========================================================

def save_admin_instruction(
    review_id: str,
    user_id: int,
    instruction: str
) -> Optional[
    PendingEditorialReview
]:

    instruction = str(
        instruction
        or ""
    ).strip()

    if not instruction:

        return None

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:

        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        return None

    _ensure_admin_instruction_metadata(
        review
    )

    if (
        review.metadata.get(
            "admin_instruction_state"
        )
        != ADMIN_INSTRUCTION_WAITING
    ):

        logger.warning(
            f"⚠️ Admin instruction ignored | "
            f"review_id={review_id} | "
            f"state="
            f"{review.metadata.get('admin_instruction_state')}"
        )

        return None

    with _store_lock:

        review.metadata[
            "admin_instruction"
        ] = instruction

        review.metadata[
            "admin_instruction_state"
        ] = (
            ADMIN_INSTRUCTION_PROCESSING
        )

        review.metadata[
            "admin_instruction_received_at"
        ] = _now()

        current_count = int(
            review.metadata.get(
                "admin_instruction_attempt_count",
                0
            )
            or 0
        )

        review.metadata[
            "admin_instruction_attempt_count"
        ] = (
            current_count
            + 1
        )

        review.updated_at = (
            _now()
        )

    logger.info(
        f"✏️ Admin instruction received | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"length={len(instruction)} | "
        f"attempt="
        f"{review.metadata.get('admin_instruction_attempt_count')}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# COMPLETE
# =========================================================

def complete_admin_instruction(
    review_id: str,
    user_id: int,
    success: bool
) -> Optional[
    PendingEditorialReview
]:

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:

        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        return None

    with _store_lock:

        _ensure_admin_instruction_metadata(
            review
        )

        review.metadata[
            "admin_instruction_state"
        ] = (
            ADMIN_INSTRUCTION_IDLE
        )

        review.metadata[
            "admin_instruction_completed_at"
        ] = _now()

        review.metadata[
            "admin_instruction_success"
        ] = bool(
            success
        )

        review.updated_at = (
            _now()
        )

    logger.info(
        f"✏️ Admin instruction completed | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"success={bool(success)}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# CANCEL WAITING
# =========================================================

def cancel_admin_instruction_wait(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:

        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        return None

    with _store_lock:

        _ensure_admin_instruction_metadata(
            review
        )

        review.metadata[
            "admin_instruction_state"
        ] = (
            ADMIN_INSTRUCTION_IDLE
        )

        review.metadata[
            "admin_instruction"
        ] = ""

        review.metadata[
            "admin_instruction_requested_at"
        ] = None

        review.metadata[
            "admin_instruction_received_at"
        ] = None

        review.metadata[
            "admin_instruction_completed_at"
        ] = _now()

        review.updated_at = (
            _now()
        )

    logger.info(
        f"↩️ Admin instruction wait cancelled | "
        f"review_id={review_id} | "
        f"user={user_id}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# CHECK WAITING FOR USER
# =========================================================

def get_waiting_admin_instruction_review(
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    user_id = int(
        user_id
    )

    with _store_lock:

        candidates = [
            review
            for review in _pending_reviews.values()
            if (
                review.user_id
                == user_id
                and review.status
                == STATUS_PENDING
            )
        ]

        candidates.sort(
            key=lambda item: (
                item.updated_at
            ),
            reverse=True
        )

        for review in candidates:

            if _is_expired(
                review
            ):

                review.status = (
                    STATUS_EXPIRED
                )

                review.updated_at = (
                    _now()
                )

                continue

            _ensure_admin_instruction_metadata(
                review
            )

            if (
                review.metadata.get(
                    "admin_instruction_state"
                )
                == ADMIN_INSTRUCTION_WAITING
            ):

                return review

    return None


# =========================================================
# ADMIN INSTRUCTION
# STATE HELPER
# =========================================================

def admin_instruction_state(
    review: Optional[
        PendingEditorialReview
    ]
) -> str:

    if review is None:

        return (
            ADMIN_INSTRUCTION_IDLE
        )

    _ensure_admin_instruction_metadata(
        review
    )

    return str(
        review.metadata.get(
            "admin_instruction_state",
            ADMIN_INSTRUCTION_IDLE
        )
        or ADMIN_INSTRUCTION_IDLE
    )


# =========================================================
# MARK PUBLISHED SUMMARY
# =========================================================

def mark_summary_published(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    return _mark_status(
        review_id=review_id,
        user_id=user_id,
        status=(
            STATUS_PUBLISHED_SUMMARY
        )
    )


# =========================================================
# MARK PUBLISHED ORIGINAL
# =========================================================

def mark_original_published(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    return _mark_status(
        review_id=review_id,
        user_id=user_id,
        status=(
            STATUS_PUBLISHED_ORIGINAL
        )
    )


# =========================================================
# CANCEL REVIEW
# =========================================================

def cancel_pending_review(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    return _mark_status(
        review_id=review_id,
        user_id=user_id,
        status=STATUS_CANCELLED
    )


# =========================================================
# INTERNAL STATUS UPDATE
# =========================================================

def _mark_status(
    review_id: str,
    user_id: int,
    status: str
) -> Optional[
    PendingEditorialReview
]:

    review = get_pending_review(
        review_id=review_id,
        user_id=user_id
    )

    if review is None:
        return None

    if (
        review.status
        != STATUS_PENDING
    ):

        logger.warning(
            f"⚠️ Pending review already finalized | "
            f"review_id={review_id} | "
            f"status={review.status}"
        )

        return review

    with _store_lock:

        review.status = status

        _ensure_admin_instruction_metadata(
            review
        )

        review.metadata[
            "admin_instruction_state"
        ] = (
            ADMIN_INSTRUCTION_IDLE
        )

        review.updated_at = (
            _now()
        )

    logger.info(
        f"✅ Pending review status changed | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"status={status}"
    )

    return review


# =========================================================
# DELETE REVIEW
# =========================================================

def delete_pending_review(
    review_id: str,
    user_id: Optional[int] = None
) -> bool:

    review_id = str(
        review_id
        or ""
    ).strip()

    if not review_id:
        return False

    with _store_lock:

        review = (
            _pending_reviews.get(
                review_id
            )
        )

        if review is None:
            return False

        if (
            user_id is not None
            and review.user_id
            != int(user_id)
        ):

            return False

        del _pending_reviews[
            review_id
        ]

    logger.info(
        f"🗑️ Pending review deleted | "
        f"review_id={review_id}"
    )

    return True


# =========================================================
# CLEANUP EXPIRED
# =========================================================

def cleanup_expired_reviews(
    ttl_seconds: int = (
        DEFAULT_PENDING_TTL_SECONDS
    )
) -> int:

    removed = 0

    with _store_lock:

        review_ids = list(
            _pending_reviews.keys()
        )

        for review_id in review_ids:

            review = (
                _pending_reviews.get(
                    review_id
                )
            )

            if review is None:
                continue

            if (
                review.status
                != STATUS_PENDING
            ):

                continue

            if not _is_expired(
                review,
                ttl_seconds
            ):

                continue

            del _pending_reviews[
                review_id
            ]

            removed += 1

    if removed:

        logger.info(
            f"🧹 Expired pending reviews cleaned | "
            f"count={removed}"
        )

    return removed


# =========================================================
# COUNT
# =========================================================

def pending_review_count() -> int:

    with _store_lock:

        return len(
            _pending_reviews
        )


# =========================================================
# CLEAR STORE
#
# فقط برای تست.
# =========================================================

def clear_pending_reviews() -> None:

    with _store_lock:

        _pending_reviews.clear()
