from __future__ import annotations

import logging
import threading
import time
import uuid

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION STATE
# =========================================================
#
# NEW FILE
#
# مسئول نگهداری وضعیت موقت Translation Review.
#
# Flow:
#
# Content
#   ↓
# 🌐 Translate
#   ↓
# TranslationState created
#   ↓
# Language selected
#   ↓
# Translation generated
#   ↓
# Preview stored
#   ↓
# Confirm / Edit / Cancel
#
# نکته:
# این Store فعلاً in-process است تا Controller بدون تغییر
# Database ساخته و تست شود.
#
# در مرحله اتصال نهایی، persistence آن به storage موجود
# پروژه متصل خواهد شد.
#
# =========================================================


STATE_WAITING_LANGUAGE = "waiting_language"

STATE_WAITING_CUSTOM_LANGUAGE = (
    "waiting_custom_language"
)

STATE_TRANSLATING = "translating"

STATE_PREVIEW = "preview"

STATE_WAITING_EDIT = "waiting_edit"

STATE_CONFIRMED = "confirmed"

STATE_CANCELLED = "cancelled"

STATE_FAILED = "failed"


DEFAULT_STATE_TTL_SECONDS = 1800

MIN_STATE_TTL_SECONDS = 60

MAX_STATE_TTL_SECONDS = 86400


# =========================================================
# MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationState:
    review_id: str

    chat_id: int

    user_id: int

    original_text: str

    source_language: str = "auto"

    target_language: str = ""

    target_language_code: str = ""

    translated_text: str = ""

    status: str = STATE_WAITING_LANGUAGE

    source_kind: str = "message"

    source_key: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    created_at: float = field(
        default_factory=time.time
    )

    updated_at: float = field(
        default_factory=time.time
    )

    expires_at: float = 0.0


# =========================================================
# STORE
# =========================================================

_STATE_LOCK = threading.RLock()

_STATES: Dict[
    str,
    TranslationState
] = {}

_ACTIVE_BY_USER_CHAT: Dict[
    str,
    str
] = {}


# =========================================================
# HELPERS
# =========================================================

def _user_chat_key(
    chat_id: int,
    user_id: int,
) -> str:
    return (
        f"{int(chat_id)}:"
        f"{int(user_id)}"
    )


def _normalize_ttl(
    ttl_seconds: Optional[int]
) -> int:
    if ttl_seconds is None:
        return DEFAULT_STATE_TTL_SECONDS

    try:
        ttl = int(
            ttl_seconds
        )

    except (
        TypeError,
        ValueError,
    ):
        ttl = DEFAULT_STATE_TTL_SECONDS

    return max(
        MIN_STATE_TTL_SECONDS,
        min(
            ttl,
            MAX_STATE_TTL_SECONDS,
        ),
    )


def _is_expired(
    state: TranslationState,
    now: Optional[float] = None,
) -> bool:
    if now is None:
        now = time.time()

    if not state.expires_at:
        return False

    return now >= state.expires_at


def _remove_locked(
    review_id: str
) -> Optional[TranslationState]:
    state = _STATES.pop(
        review_id,
        None,
    )

    if state is None:
        return None

    active_key = _user_chat_key(
        state.chat_id,
        state.user_id,
    )

    if (
        _ACTIVE_BY_USER_CHAT.get(
            active_key
        )
        == review_id
    ):
        _ACTIVE_BY_USER_CHAT.pop(
            active_key,
            None,
        )

    return state


# =========================================================
# CLEANUP
# =========================================================

def cleanup_expired_translation_states(
    now: Optional[float] = None,
) -> int:
    if now is None:
        now = time.time()

    removed = 0

    with _STATE_LOCK:
        expired_ids = [
            review_id
            for review_id, state
            in _STATES.items()
            if _is_expired(
                state,
                now,
            )
        ]

        for review_id in expired_ids:
            if _remove_locked(
                review_id
            ):
                removed += 1

    if removed:
        logger.info(
            "🧹 Translation state cleanup | removed=%s",
            removed,
        )

    return removed


# =========================================================
# CREATE
# =========================================================

def create_translation_state(
    *,
    chat_id: int,
    user_id: int,
    original_text: str,
    source_language: str = "auto",
    source_kind: str = "message",
    source_key: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    ttl_seconds: Optional[int] = None,
) -> TranslationState:
    cleanup_expired_translation_states()

    text = str(
        original_text or ""
    )

    if not text.strip():
        raise ValueError(
            "translation original_text is empty"
        )

    ttl = _normalize_ttl(
        ttl_seconds
    )

    now = time.time()

    review_id = uuid.uuid4().hex

    state = TranslationState(
        review_id=review_id,
        chat_id=int(chat_id),
        user_id=int(user_id),
        original_text=text,
        source_language=(
            str(
                source_language
                or "auto"
            ).strip()
            or "auto"
        ),
        source_kind=(
            str(
                source_kind
                or "message"
            ).strip()
            or "message"
        ),
        source_key=str(
            source_key or ""
        ).strip(),
        metadata=dict(
            metadata or {}
        ),
        created_at=now,
        updated_at=now,
        expires_at=(
            now + ttl
        ),
    )

    active_key = _user_chat_key(
        chat_id,
        user_id,
    )

    with _STATE_LOCK:
        previous_review_id = (
            _ACTIVE_BY_USER_CHAT.get(
                active_key
            )
        )

        if previous_review_id:
            _remove_locked(
                previous_review_id
            )

        _STATES[
            review_id
        ] = state

        _ACTIVE_BY_USER_CHAT[
            active_key
        ] = review_id

    logger.info(
        "🌐 Translation state created | "
        "review_id=%s | chat_id=%s | user_id=%s | "
        "source_kind=%s",
        review_id,
        chat_id,
        user_id,
        state.source_kind,
    )

    return state


# =========================================================
# GET
# =========================================================

def get_translation_state(
    review_id: str
) -> Optional[TranslationState]:
    cleanup_expired_translation_states()

    with _STATE_LOCK:
        return _STATES.get(
            str(
                review_id or ""
            )
        )


def get_active_translation_state(
    *,
    chat_id: int,
    user_id: int,
) -> Optional[TranslationState]:
    cleanup_expired_translation_states()

    active_key = _user_chat_key(
        chat_id,
        user_id,
    )

    with _STATE_LOCK:
        review_id = (
            _ACTIVE_BY_USER_CHAT.get(
                active_key
            )
        )

        if not review_id:
            return None

        return _STATES.get(
            review_id
        )


# =========================================================
# AUTHORIZATION
# =========================================================

def translation_state_belongs_to(
    state: TranslationState,
    *,
    chat_id: int,
    user_id: int,
) -> bool:
    return (
        state.chat_id
        == int(chat_id)
        and state.user_id
        == int(user_id)
    )


# =========================================================
# UPDATE
# =========================================================

def update_translation_state(
    review_id: str,
    **changes: Any,
) -> Optional[TranslationState]:
    cleanup_expired_translation_states()

    review_id = str(
        review_id or ""
    )

    if not review_id:
        return None

    protected_fields = {
        "review_id",
        "chat_id",
        "user_id",
        "created_at",
    }

    safe_changes = {
        key: value
        for key, value
        in changes.items()
        if key not in protected_fields
    }

    safe_changes[
        "updated_at"
    ] = time.time()

    with _STATE_LOCK:
        current = _STATES.get(
            review_id
        )

        if current is None:
            return None

        try:
            updated = replace(
                current,
                **safe_changes,
            )

        except TypeError:
            logger.exception(
                "❌ Invalid TranslationState update | "
                "review_id=%s | fields=%s",
                review_id,
                list(
                    safe_changes.keys()
                ),
            )

            return None

        _STATES[
            review_id
        ] = updated

        return updated


# =========================================================
# LANGUAGE SELECTION
# =========================================================

def set_translation_language(
    review_id: str,
    *,
    target_language: str,
    target_language_code: str = "",
) -> Optional[TranslationState]:
    language = str(
        target_language or ""
    ).strip()

    if not language:
        return None

    return update_translation_state(
        review_id,
        target_language=language,
        target_language_code=str(
            target_language_code or ""
        ).strip(),
        status=STATE_TRANSLATING,
    )


# =========================================================
# CUSTOM LANGUAGE WAIT
# =========================================================

def mark_waiting_custom_language(
    review_id: str
) -> Optional[TranslationState]:
    return update_translation_state(
        review_id,
        status=(
            STATE_WAITING_CUSTOM_LANGUAGE
        ),
    )


# =========================================================
# PREVIEW
# =========================================================

def set_translation_preview(
    review_id: str,
    *,
    translated_text: str,
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Optional[TranslationState]:
    text = str(
        translated_text or ""
    ).strip()

    if not text:
        return mark_translation_failed(
            review_id,
            reason="empty_translation",
        )

    current = get_translation_state(
        review_id
    )

    if current is None:
        return None

    merged_metadata = dict(
        current.metadata
    )

    if metadata:
        merged_metadata.update(
            metadata
        )

    return update_translation_state(
        review_id,
        translated_text=text,
        metadata=merged_metadata,
        status=STATE_PREVIEW,
    )


# =========================================================
# EDIT
# =========================================================

def mark_waiting_translation_edit(
    review_id: str
) -> Optional[TranslationState]:
    return update_translation_state(
        review_id,
        status=STATE_WAITING_EDIT,
    )


def apply_translation_edit(
    review_id: str,
    *,
    translated_text: str,
) -> Optional[TranslationState]:
    text = str(
        translated_text or ""
    ).strip()

    if not text:
        return None

    return update_translation_state(
        review_id,
        translated_text=text,
        status=STATE_PREVIEW,
    )


# =========================================================
# CONFIRM
# =========================================================

def confirm_translation_state(
    review_id: str
) -> Optional[TranslationState]:
    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if (
        state.status
        != STATE_PREVIEW
    ):
        logger.warning(
            "⚠️ Translation confirm rejected | "
            "review_id=%s | status=%s",
            review_id,
            state.status,
        )

        return None

    if not state.translated_text.strip():
        return None

    return update_translation_state(
        review_id,
        status=STATE_CONFIRMED,
    )


# =========================================================
# FAILURE
# =========================================================

def mark_translation_failed(
    review_id: str,
    *,
    reason: str,
) -> Optional[TranslationState]:
    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    metadata = dict(
        state.metadata
    )

    metadata[
        "translation_error"
    ] = str(
        reason or "unknown"
    )

    return update_translation_state(
        review_id,
        status=STATE_FAILED,
        metadata=metadata,
    )


# =========================================================
# CANCEL
# =========================================================

def cancel_translation_state(
    review_id: str
) -> Optional[TranslationState]:
    state = update_translation_state(
        review_id,
        status=STATE_CANCELLED,
    )

    if state is None:
        return None

    active_key = _user_chat_key(
        state.chat_id,
        state.user_id,
    )

    with _STATE_LOCK:
        if (
            _ACTIVE_BY_USER_CHAT.get(
                active_key
            )
            == review_id
        ):
            _ACTIVE_BY_USER_CHAT.pop(
                active_key,
                None,
            )

    logger.info(
        "❌ Translation state cancelled | "
        "review_id=%s",
        review_id,
    )

    return state


# =========================================================
# REMOVE
# =========================================================

def remove_translation_state(
    review_id: str
) -> Optional[TranslationState]:
    with _STATE_LOCK:
        return _remove_locked(
            str(
                review_id or ""
            )
        )


# =========================================================
# STATUS HELPERS
# =========================================================

def translation_waiting_for_text_input(
    state: Optional[TranslationState]
) -> bool:
    if state is None:
        return False

    return state.status in {
        STATE_WAITING_CUSTOM_LANGUAGE,
        STATE_WAITING_EDIT,
    }


def translation_ready_for_publish(
    state: Optional[TranslationState]
) -> bool:
    if state is None:
        return False

    return (
        state.status
        == STATE_CONFIRMED
        and bool(
            state.translated_text.strip()
        )
    )


# =========================================================
# DEBUG / TEST
# =========================================================

def translation_state_count() -> int:
    cleanup_expired_translation_states()

    with _STATE_LOCK:
        return len(
            _STATES
        )


def clear_translation_states() -> None:
    """
    فقط برای تست.
    """

    with _STATE_LOCK:
        _STATES.clear()
        _ACTIVE_BY_USER_CHAT.clear()
