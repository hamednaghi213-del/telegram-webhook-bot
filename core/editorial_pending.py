import logging
import threading
import time
import uuid
from datetime import datetime

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    List,
    Optional,
)


logger = logging.getLogger(__name__)


def _persistence_enabled() -> bool:
    """B7 flag check, isolated for test patching."""
    try:
        from core.database import (
            persistent_editorial_pending_enabled,
        )

        return persistent_editorial_pending_enabled()
    except Exception:
        return False


def _persist_review(review) -> None:
    """Best-effort mirror of one review into Supabase (B7).

    Called with the store lock held (re-entrant RLock). Failures are
    logged and never raised into the editorial flow; the in-memory
    behaviour remains regression-free.
    """
    if not _persistence_enabled():
        return

    if not isinstance(review, PendingEditorialReview):
        return

    try:
        from core.database import (
            upsert_persistent_editorial_review,
        )

        payload = {
            "review_id": str(review.review_id),
            "user_id": int(review.user_id),
            "content_type": str(review.content_type),
            "original_text": str(review.original_text or ""),
            "current_summary": str(review.current_summary or ""),
            "regeneration_count": int(
                review.regeneration_count or 0
            ),
            "status": str(review.status),
            "metadata": dict(review.metadata or {}),
            "expires_at": (
                datetime.utcfromtimestamp(
                    float(review.updated_at)
                    + DEFAULT_PENDING_TTL_SECONDS
                ).isoformat()
            ),
        }

        upsert_persistent_editorial_review(payload)

    except Exception:
        logger.exception(
            "Persistent editorial review write failed "
            "(continuing in-memory) | review_id=%s",
            review.review_id,
        )


def _persist_review_deleted(review_id: str) -> None:
    """Best-effort delete of one persistent review row (B7)."""
    if not _persistence_enabled():
        return

    try:
        from core.database import (
            delete_persistent_editorial_review,
        )

        delete_persistent_editorial_review(
            review_id=str(review_id),
        )
    except Exception:
        logger.exception(
            "Persistent editorial review delete failed | "
            "review_id=%s",
            review_id,
        )


def rehydrate_editorial_reviews() -> int:
    """Restore pending editorial reviews from Supabase after restart (B7).

    Rebuilds the in-memory review objects exactly as creation would
    have produced them; per-user waiting flags are preserved via
    metadata so admin-instruction state survives the restart.
    """
    restored = 0

    try:
        from core.database import (
            list_unfinished_persistent_editorial_reviews,
        )

        if not _persistence_enabled():
            return 0

        rows = list_unfinished_persistent_editorial_reviews()

    except Exception:
        logger.exception("Editorial review rehydration read failed")
        return 0

    now = _now()

    for row in rows:
        try:
            review_id = str(row.get("review_id") or "").strip()

            if (
                not review_id
                or review_id in _pending_reviews
            ):
                continue

            review = PendingEditorialReview(
                review_id=review_id,
                user_id=int(row.get("user_id") or 0),
                content_type=str(row.get("content_type") or ""),
                original_text=str(row.get("original_text") or ""),
                current_summary=str(row.get("current_summary") or ""),
                regeneration_count=int(
                    row.get("regeneration_count") or 0
                ),
                created_at=(
                    float(row.get("created_at") or 0) or now
                ),
                updated_at=now,
                status=str(
                    row.get("status") or STATUS_PENDING
                ),
                metadata=dict(row.get("metadata") or {}),
            )

            _ensure_metadata(review)

            _pending_reviews[review_id] = review
            restored += 1

            logger.info(
                "♻️ Editorial review rehydrated | "
                "review_id=%s | user=%s",
                review_id,
                review.user_id,
            )

        except Exception:
            logger.exception(
                "Editorial review rehydration row failed | row=%s",
                row,
            )

    return restored


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
#
# این وضعیت برای زمانی است که ادمین روی دکمه:
#
# ✏️ اصلاح با دستور ادمین
#
# کلیک کرده و ربات منتظر پیام بعدی او است.
#
# اصل مهم:
#
# - Summary قبلی حذف نمی‌شود.
# - Original Text حذف نمی‌شود.
# - فقط یک Flag در Metadata ذخیره می‌شود.
# - برای هر کاربر در هر لحظه فقط یک Review
#   می‌تواند منتظر دستور ادمین باشد.
# =========================================================

ADMIN_INSTRUCTION_WAITING_KEY = (
    "awaiting_admin_instruction"
)

ADMIN_INSTRUCTION_REQUESTED_AT_KEY = (
    "admin_instruction_requested_at"
)

ADMIN_INSTRUCTION_LAST_TEXT_KEY = (
    "last_admin_instruction"
)

ADMIN_INSTRUCTION_LAST_APPLIED_AT_KEY = (
    "last_admin_instruction_applied_at"
)

ADMIN_INSTRUCTION_COUNT_KEY = (
    "admin_instruction_count"
)


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


def _ensure_metadata(
    review: PendingEditorialReview
) -> Dict[str, Any]:

    if not isinstance(
        review.metadata,
        dict
    ):

        review.metadata = {}

    return review.metadata


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

    # =====================================================
    # ADMIN INSTRUCTION DEFAULT STATE
    # =====================================================

    review_metadata.setdefault(
        ADMIN_INSTRUCTION_WAITING_KEY,
        False
    )

    review_metadata.setdefault(
        ADMIN_INSTRUCTION_COUNT_KEY,
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

        _persist_review(review)

    logger.info(
        f"📝 Pending editorial review created | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"type={content_type} | "
        f"regeneration_count={regeneration_count} | "
        f"awaiting_admin_instruction=False"
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

            metadata = (
                _ensure_metadata(
                    review
                )
            )

            metadata[
                ADMIN_INSTRUCTION_WAITING_KEY
            ] = False

            _persist_review(review)

            logger.info(
                f"⌛ Pending review expired | "
                f"review_id={review_id}"
            )

        return review


# =========================================================
# GET ALL USER REVIEWS
#
# فقط Reviewهای Pending کاربر را برمی‌گرداند.
#
# در معماری فعلی کاربرد اصلی برای پیدا کردن
# Review منتظر دستور ادمین است.
# =========================================================

def get_pending_reviews_for_user(
    user_id: int,
    ttl_seconds: int = (
        DEFAULT_PENDING_TTL_SECONDS
    )
) -> List[
    PendingEditorialReview
]:

    user_id = int(
        user_id
    )

    result: List[
        PendingEditorialReview
    ] = []

    with _store_lock:

        review_ids = list(
            _pending_reviews.keys()
        )

    for review_id in review_ids:

        review = get_pending_review(
            review_id=review_id,
            user_id=user_id,
            ttl_seconds=ttl_seconds
        )

        if review is None:
            continue

        if (
            review.status
            != STATUS_PENDING
        ):

            continue

        result.append(
            review
        )

    result.sort(
        key=lambda item: (
            item.updated_at
        ),
        reverse=True
    )

    return result


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

        review_metadata = (
            _ensure_metadata(
                review
            )
        )

        if metadata:

            review_metadata.update(
                metadata
            )

        review.updated_at = (
            _now()
        )

        _persist_review(review)

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
#
# وقتی ادمین دکمه:
#
# ✏️ اصلاح با دستور ادمین
#
# را می‌زند این تابع اجرا خواهد شد.
#
# سیاست:
#
# برای هر User فقط یک Review می‌تواند
# در حالت Waiting باشد.
#
# اگر Review دیگری منتظر باشد، Waiting آن
# خاموش می‌شود ولی خود Review حذف نمی‌شود.
# =========================================================

def set_admin_instruction_waiting(
    review_id: str,
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    review_id = str(
        review_id
        or ""
    ).strip()

    if not review_id:

        return None

    user_id = int(
        user_id
    )

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
            f"⚠️ Admin instruction waiting rejected | "
            f"review_id={review_id} | "
            f"status={review.status}"
        )

        return None

    now = _now()

    with _store_lock:

        # =================================================
        # CLEAR OTHER WAITING REVIEWS FOR SAME USER
        # =================================================

        for other_review in (
            _pending_reviews.values()
        ):

            if (
                other_review.user_id
                != user_id
            ):

                continue

            if (
                other_review.review_id
                == review_id
            ):

                continue

            if (
                other_review.status
                != STATUS_PENDING
            ):

                continue

            other_metadata = (
                _ensure_metadata(
                    other_review
                )
            )

            if other_metadata.get(
                ADMIN_INSTRUCTION_WAITING_KEY,
                False
            ):

                other_metadata[
                    ADMIN_INSTRUCTION_WAITING_KEY
                ] = False

                other_metadata.pop(
                    ADMIN_INSTRUCTION_REQUESTED_AT_KEY,
                    None
                )

                other_review.updated_at = (
                    now
                )

                _persist_review(other_review)

                logger.info(
                    f"🧹 Previous admin instruction "
                    f"waiting cleared | "
                    f"review_id="
                    f"{other_review.review_id} | "
                    f"user={user_id}"
                )

        # =================================================
        # ENABLE CURRENT REVIEW
        # =================================================

        metadata = (
            _ensure_metadata(
                review
            )
        )

        metadata[
            ADMIN_INSTRUCTION_WAITING_KEY
        ] = True

        metadata[
            ADMIN_INSTRUCTION_REQUESTED_AT_KEY
        ] = now

        review.updated_at = (
            now
        )

        _persist_review(review)

    logger.info(
        f"✏️ Pending review waiting for "
        f"admin instruction | "
        f"review_id={review_id} | "
        f"user={user_id}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# CLEAR WAITING
# =========================================================

def clear_admin_instruction_waiting(
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

        return review

    with _store_lock:

        metadata = (
            _ensure_metadata(
                review
            )
        )

        metadata[
            ADMIN_INSTRUCTION_WAITING_KEY
        ] = False

        metadata.pop(
            ADMIN_INSTRUCTION_REQUESTED_AT_KEY,
            None
        )

        review.updated_at = (
            _now()
        )

        _persist_review(review)

    logger.info(
        f"✅ Admin instruction waiting cleared | "
        f"review_id={review_id} | "
        f"user={user_id}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# IS WAITING?
# =========================================================

def is_waiting_for_admin_instruction(
    review: Optional[
        PendingEditorialReview
    ]
) -> bool:

    if review is None:

        return False

    if (
        review.status
        != STATUS_PENDING
    ):

        return False

    metadata = (
        review.metadata
        or {}
    )

    return bool(
        metadata.get(
            ADMIN_INSTRUCTION_WAITING_KEY,
            False
        )
    )


# =========================================================
# ADMIN INSTRUCTION
# FIND WAITING REVIEW FOR USER
#
# این تابع در webhook_handler استفاده خواهد شد.
#
# وقتی یک پیام Text جدید از ادمین می‌رسد:
#
# 1. ابتدا بررسی می‌کنیم آیا Review منتظر دستور دارد؟
# 2. اگر دارد، متن پیام News محسوب نمی‌شود.
# 3. آن متن به عنوان Admin Instruction پردازش می‌شود.
# =========================================================

def get_waiting_admin_instruction_review(
    user_id: int
) -> Optional[
    PendingEditorialReview
]:

    reviews = (
        get_pending_reviews_for_user(
            user_id=user_id
        )
    )

    for review in reviews:

        if is_waiting_for_admin_instruction(
            review
        ):

            return review

    return None


# =========================================================
# ADMIN INSTRUCTION
# RECORD SUCCESSFUL INSTRUCTION
#
# بعد از اینکه AI دستور ادمین را با موفقیت اعمال کرد:
#
# - متن دستور ثبت می‌شود.
# - Count افزایش می‌یابد.
# - Waiting خاموش می‌شود.
#
# Summary جدید جداگانه توسط update_pending_summary
# ذخیره خواهد شد.
# =========================================================

def record_admin_instruction_applied(
    review_id: str,
    user_id: int,
    instruction: str
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

    instruction = str(
        instruction
        or ""
    ).strip()

    now = _now()

    with _store_lock:

        metadata = (
            _ensure_metadata(
                review
            )
        )

        current_count = int(
            metadata.get(
                ADMIN_INSTRUCTION_COUNT_KEY,
                0
            )
            or 0
        )

        metadata[
            ADMIN_INSTRUCTION_COUNT_KEY
        ] = (
            current_count
            + 1
        )

        metadata[
            ADMIN_INSTRUCTION_LAST_TEXT_KEY
        ] = instruction

        metadata[
            ADMIN_INSTRUCTION_LAST_APPLIED_AT_KEY
        ] = now

        metadata[
            ADMIN_INSTRUCTION_WAITING_KEY
        ] = False

        metadata.pop(
            ADMIN_INSTRUCTION_REQUESTED_AT_KEY,
            None
        )

        review.updated_at = (
            now
        )

        _persist_review(review)

    logger.info(
        f"✅ Admin instruction recorded | "
        f"review_id={review_id} | "
        f"user={user_id} | "
        f"count="
        f"{review.metadata.get(ADMIN_INSTRUCTION_COUNT_KEY, 0)}"
    )

    return review


# =========================================================
# ADMIN INSTRUCTION
# GET COUNT
# =========================================================

def get_admin_instruction_count(
    review: Optional[
        PendingEditorialReview
    ]
) -> int:

    if review is None:

        return 0

    metadata = (
        review.metadata
        or {}
    )

    try:

        return int(
            metadata.get(
                ADMIN_INSTRUCTION_COUNT_KEY,
                0
            )
            or 0
        )

    except Exception:

        return 0


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

        metadata = (
            _ensure_metadata(
                review
            )
        )

        # =================================================
        # FINALIZED REVIEW MUST NEVER REMAIN WAITING
        # =================================================

        metadata[
            ADMIN_INSTRUCTION_WAITING_KEY
        ] = False

        metadata.pop(
            ADMIN_INSTRUCTION_REQUESTED_AT_KEY,
            None
        )

        review.updated_at = (
            _now()
        )

        _persist_review(review)

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

        _persist_review_deleted(review_id)

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
