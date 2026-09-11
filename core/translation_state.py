from __future__ import annotations

import logging
import uuid

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION STATE
# =========================================================
#
# EXISTING FILE — FULL REPLACEMENT
#
# Persistent Translation Workflow State.
#
# Previous implementation:
#
#     Python process memory
#
# New implementation:
#
#     translation_state.py
#             ↓
#     core.database
#             ↓
#     public.translation_reviews
#             ↓
#          Supabase
#
# Therefore translation review state now survives:
#
# - Render restart
# - deploy/redeploy
# - process replacement
# - multiple webhook workers
#
# Public function names are intentionally preserved so:
#
# - translation_controller.py
# - translation_telegram.py
# - webhook_handler.py
#
# do not need to know how state is stored.
#
# This module DOES NOT:
#
# - translate text
# - call Gemini
# - publish content
# - resolve destinations
# - apply branding
#
# =========================================================


# =========================================================
# STATES
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


ACTIVE_STATES = {
    STATE_WAITING_LANGUAGE,
    STATE_WAITING_CUSTOM_LANGUAGE,
    STATE_TRANSLATING,
    STATE_PREVIEW,
    STATE_WAITING_EDIT,
}


TERMINAL_STATES = {
    STATE_CONFIRMED,
    STATE_CANCELLED,
    STATE_FAILED,
}


ALL_STATES = (
    ACTIVE_STATES
    | TERMINAL_STATES
)


# =========================================================
# DATA MODEL
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

    edited_text: str = ""

    source_kind: str = "message"

    source_key: str = ""

    status: str = STATE_WAITING_LANGUAGE

    failure_reason: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    validation_errors: tuple = field(
        default_factory=tuple
    )

    validation_warnings: tuple = field(
        default_factory=tuple
    )

    translation_attempts: int = 0

    source_review_id: str = ""

    source_message_id: Optional[int] = None

    created_at: str = ""

    updated_at: str = ""

    expires_at: str = ""


# =========================================================
# DATABASE ACCESS
# =========================================================

def _database():
    """
    Lazy import avoids circular imports and keeps this module
    independent from database initialization at import time.
    """

    from core import database

    return database


# =========================================================
# NORMALIZATION
# =========================================================

def _normalize_metadata(
    value: Any,
) -> Dict[str, Any]:

    if not isinstance(
        value,
        dict,
    ):
        return {}

    return dict(
        value
    )


def _normalize_status(
    status: str,
) -> str:

    value = str(
        status
        or ""
    ).strip()

    if value not in ALL_STATES:

        raise ValueError(
            f"Invalid translation state: {value}"
        )

    return value


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return int(
            default
        )


def _safe_optional_int(
    value: Any,
) -> Optional[int]:

    if value is None:
        return None

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# =========================================================
# ROW → STATE
# =========================================================

def _state_from_row(
    row: Optional[
        Dict[str, Any]
    ],
) -> Optional[
    TranslationState
]:

    if not row:
        return None

    metadata = (
        _normalize_metadata(
            row.get(
                "metadata"
            )
        )
    )

    source_key = str(
        metadata.get(
            "source_key",
            "",
        )
        or ""
    )

    target_language_code = str(
        metadata.get(
            "target_language_code",
            "",
        )
        or ""
    )

    failure_reason = str(
        metadata.get(
            "failure_reason",
            "",
        )
        or ""
    )

    translated_text = str(
        row.get(
            "translated_text",
            "",
        )
        or ""
    )

    edited_text = str(
        row.get(
            "edited_text",
            "",
        )
        or ""
    )

    # Manual edit becomes the effective translation.
    #
    # This keeps the existing Controller contract:
    #
    #     state.translated_text
    #
    # always represents the content that will be confirmed.
    if edited_text:

        effective_translation = (
            edited_text
        )

    else:

        effective_translation = (
            translated_text
        )

    return TranslationState(
        review_id=str(
            row.get(
                "review_id",
                "",
            )
            or ""
        ),

        chat_id=_safe_int(
            row.get(
                "chat_id"
            )
        ),

        user_id=_safe_int(
            row.get(
                "user_id"
            )
        ),

        original_text=str(
            row.get(
                "original_text",
                "",
            )
            or ""
        ),

        source_language=str(
            row.get(
                "source_language",
                "auto",
            )
            or "auto"
        ),

        target_language=str(
            row.get(
                "target_language",
                "",
            )
            or ""
        ),

        target_language_code=(
            target_language_code
        ),

        translated_text=(
            effective_translation
        ),

        edited_text=(
            edited_text
        ),

        source_kind=str(
            row.get(
                "content_kind",
                "message",
            )
            or "message"
        ),

        source_key=(
            source_key
        ),

        status=str(
            row.get(
                "status",
                STATE_WAITING_LANGUAGE,
            )
            or STATE_WAITING_LANGUAGE
        ),

        failure_reason=(
            failure_reason
        ),

        metadata=metadata,

        validation_errors=tuple(
            row.get(
                "validation_errors"
            )
            or ()
        ),

        validation_warnings=tuple(
            row.get(
                "validation_warnings"
            )
            or ()
        ),

        translation_attempts=max(
            0,
            _safe_int(
                row.get(
                    "translation_attempts"
                ),
                0,
            ),
        ),

        source_review_id=str(
            row.get(
                "source_review_id",
                "",
            )
            or ""
        ),

        source_message_id=(
            _safe_optional_int(
                row.get(
                    "source_message_id"
                )
            )
        ),

        created_at=str(
            row.get(
                "created_at",
                "",
            )
            or ""
        ),

        updated_at=str(
            row.get(
                "updated_at",
                "",
            )
            or ""
        ),

        expires_at=str(
            row.get(
                "expires_at",
                "",
            )
            or ""
        ),
    )


# =========================================================
# EXPIRATION CHECK
# =========================================================

def translation_state_expired(
    state: Optional[
        TranslationState
    ],
) -> bool:

    if state is None:
        return True

    raw = str(
        state.expires_at
        or ""
    ).strip()

    if not raw:

        return False

    try:

        normalized = raw.replace(
            "Z",
            "+00:00",
        )

        expires_at = (
            datetime.fromisoformat(
                normalized
            )
        )

        if (
            expires_at.tzinfo
            is None
        ):

            expires_at = (
                expires_at.replace(
                    tzinfo=timezone.utc
                )
            )

        return (
            expires_at
            <= datetime.now(
                timezone.utc
            )
        )

    except Exception:

        # Database TTL cleanup remains authoritative.
        #
        # A malformed timestamp should not incorrectly delete a
        # workflow at this layer.
        return False


# =========================================================
# OWNERSHIP
# =========================================================

def translation_state_belongs_to(
    state: Optional[
        TranslationState
    ],
    *,
    chat_id: int,
    user_id: int,
) -> bool:

    if state is None:
        return False

    return (
        int(
            state.chat_id
        )
        == int(
            chat_id
        )
        and
        int(
            state.user_id
        )
        == int(
            user_id
        )
    )


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
    metadata: Optional[
        Dict[str, Any]
    ] = None,
    review_id: Optional[str] = None,
) -> TranslationState:
    """
    Create a new persistent Translation workflow.

    Only one active workflow is allowed per user/chat.
    database.py cancels an older active workflow before creating
    the new one.
    """

    text = str(
        original_text
        or ""
    )

    if not text.strip():

        raise ValueError(
            "Translation original_text is required"
        )

    resolved_review_id = str(
        review_id
        or uuid.uuid4()
    ).strip()

    if not resolved_review_id:

        raise ValueError(
            "Translation review_id is required"
        )

    normalized_metadata = (
        _normalize_metadata(
            metadata
        )
    )

    source_review_id = str(
        normalized_metadata.get(
            "source_review_id",
            "",
        )
        or ""
    ).strip()

    source_message_id = (
        _safe_optional_int(
            normalized_metadata.get(
                "source_message_id"
            )
        )
    )

    row = (
        _database()
        .create_persistent_translation_review(
            review_id=(
                resolved_review_id
            ),
            chat_id=int(
                chat_id
            ),
            user_id=int(
                user_id
            ),
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
                source_key
                or ""
            ),
            metadata=(
                normalized_metadata
            ),
            status=(
                STATE_WAITING_LANGUAGE
            ),
            source_review_id=(
                source_review_id
                or None
            ),
            source_message_id=(
                source_message_id
            ),
        )
    )

    state = (
        _state_from_row(
            row
        )
    )

    if state is None:

        raise RuntimeError(
            "Could not create persistent translation state"
        )

    logger.info(
        "💾 Translation state created | "
        "review_id=%s | chat_id=%s | user_id=%s",
        state.review_id,
        state.chat_id,
        state.user_id,
    )

    return state


# =========================================================
# GET BY REVIEW ID
# =========================================================

def get_translation_state(
    review_id: str,
) -> Optional[
    TranslationState
]:

    normalized_review_id = str(
        review_id
        or ""
    ).strip()

    if not normalized_review_id:
        return None

    row = (
        _database()
        .get_persistent_translation_review(
            normalized_review_id
        )
    )

    state = (
        _state_from_row(
            row
        )
    )

    if state is None:
        return None

    if translation_state_expired(
        state
    ):

        try:

            remove_translation_state(
                normalized_review_id
            )

        except Exception:

            logger.exception(
                "⚠️ Could not remove expired translation state | "
                "review_id=%s",
                normalized_review_id,
            )

        return None

    return state


# =========================================================
# GET ACTIVE
# =========================================================

def get_active_translation_state(
    *,
    chat_id: int,
    user_id: int,
) -> Optional[
    TranslationState
]:
    """
    Return active Translation workflow for one user/chat.

    Persistent storage is preferred.

    Some existing tests replace core.database with a lightweight
    fake module which predates persistent Translation state.
    Missing read support therefore means there is no persistent
    pending Translation workflow and must not break existing
    Editorial / External Review / publication paths.

    Translation mutations remain fail-closed.
    """

    database = _database()

    persistent_lookup = getattr(
        database,
        "get_active_persistent_translation_review",
        None,
    )

    if not callable(
        persistent_lookup
    ):

        return None

    try:

        row = persistent_lookup(
            chat_id=int(
                chat_id
            ),
            user_id=int(
                user_id
            ),
        )

    except Exception as exc:

        logger.debug(
            "Persistent translation active lookup unavailable | "
            "chat_id=%s | user_id=%s | error=%s",
            chat_id,
            user_id,
            exc,
        )

        return None

    state = (
        _state_from_row(
            row
        )
    )

    if state is None:
        return None

    if state.status not in ACTIVE_STATES:
        return None

    if translation_state_expired(
        state
    ):
        return None

    return state


# =========================================================
# GENERIC UPDATE
# =========================================================

def update_translation_state(
    review_id: str,
    *,
    status: Optional[str] = None,
    source_language: Optional[str] = None,
    target_language: Optional[str] = None,
    target_language_code: Optional[str] = None,
    translated_text: Optional[str] = None,
    edited_text: Optional[str] = None,
    source_kind: Optional[str] = None,
    source_key: Optional[str] = None,
    metadata: Optional[
        Dict[str, Any]
    ] = None,
    validation_errors: Optional[
        list
    ] = None,
    validation_warnings: Optional[
        list
    ] = None,
    translation_attempts: Optional[int] = None,
    source_review_id: Optional[str] = None,
    source_message_id: Optional[int] = None,
) -> Optional[
    TranslationState
]:

    normalized_review_id = str(
        review_id
        or ""
    ).strip()

    if not normalized_review_id:
        return None

    if status is not None:

        _normalize_status(
            status
        )

    row = (
        _database()
        .update_persistent_translation_review(
            normalized_review_id,
            status=status,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            target_language_code=(
                target_language_code
            ),
            translated_text=(
                translated_text
            ),
            edited_text=(
                edited_text
            ),
            source_kind=(
                source_kind
            ),
            source_key=(
                source_key
            ),
            metadata=(
                metadata
            ),
            validation_errors=(
                validation_errors
            ),
            validation_warnings=(
                validation_warnings
            ),
            translation_attempts=(
                translation_attempts
            ),
            source_review_id=(
                source_review_id
            ),
            source_message_id=(
                source_message_id
            ),
        )
    )

    return _state_from_row(
        row
    )


# =========================================================
# WAITING CUSTOM LANGUAGE
# =========================================================

def mark_waiting_custom_language(
    review_id: str,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status not in {
        STATE_WAITING_LANGUAGE,
        STATE_WAITING_CUSTOM_LANGUAGE,
    }:

        return None

    return update_translation_state(
        review_id,
        status=(
            STATE_WAITING_CUSTOM_LANGUAGE
        ),
    )


# =========================================================
# SET LANGUAGE / MARK TRANSLATING
# =========================================================

def set_translation_language(
    review_id: str,
    *,
    target_language: str,
    target_language_code: str = "",
    restart_preview: bool = False,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status not in {
        STATE_WAITING_LANGUAGE,
        STATE_WAITING_CUSTOM_LANGUAGE,
        STATE_TRANSLATING,
    } and not (restart_preview and state.status == STATE_PREVIEW):

        return None

    normalized_target = str(
        target_language
        or ""
    ).strip()

    if not normalized_target:
        return None

    return update_translation_state(
        review_id,
        status=STATE_TRANSLATING,
        target_language=(
            normalized_target
        ),
        target_language_code=(
            str(
                target_language_code
                or ""
            ).strip()
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
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status not in {
        STATE_TRANSLATING,
        STATE_PREVIEW,
        STATE_WAITING_EDIT,
    }:

        return None

    text = str(
        translated_text
        or ""
    ).strip()

    if not text:
        return None

    normalized_metadata = (
        _normalize_metadata(
            metadata
        )
    )

    attempts = normalized_metadata.get(
        "translation_attempts",
        normalized_metadata.get(
            "attempts"
        ),
    )

    validation_errors = (
        normalized_metadata.get(
            "translation_validation_errors",
            normalized_metadata.get(
                "validation_errors"
            ),
        )
    )

    validation_warnings = (
        normalized_metadata.get(
            "translation_validation_warnings",
            normalized_metadata.get(
                "validation_warnings"
            ),
        )
    )

    return update_translation_state(
        review_id,
        status=STATE_PREVIEW,
        translated_text=text,

        # New machine preview replaces any old manual edit.
        edited_text="",

        metadata=(
            normalized_metadata
        ),

        validation_errors=(
            list(
                validation_errors
                or []
            )
            if validation_errors
            is not None
            else None
        ),

        validation_warnings=(
            list(
                validation_warnings
                or []
            )
            if validation_warnings
            is not None
            else None
        ),

        translation_attempts=(
            max(
                0,
                _safe_int(
                    attempts,
                    0,
                ),
            )
            if attempts
            is not None
            else None
        ),
    )


# =========================================================
# WAITING EDIT
# =========================================================

def mark_waiting_translation_edit(
    review_id: str,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status != (
        STATE_PREVIEW
    ):

        return None

    if not state.translated_text.strip():

        return None

    return update_translation_state(
        review_id,
        status=(
            STATE_WAITING_EDIT
        ),
    )


# =========================================================
# APPLY EDIT
# =========================================================

def apply_translation_edit(
    review_id: str,
    *,
    translated_text: str,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status != (
        STATE_WAITING_EDIT
    ):

        return None

    text = str(
        translated_text
        or ""
    ).strip()

    if not text:
        return None

    metadata = {
        "translation_manually_edited":
            True,
    }

    return update_translation_state(
        review_id,
        status=STATE_PREVIEW,

        # Keep machine translation in translated_text DB column.
        #
        # edited_text becomes effective translated_text when the
        # row is reconstructed as TranslationState.
        edited_text=text,

        metadata=metadata,
    )


# =========================================================
# CONFIRM
# =========================================================

def confirm_translation_state(
    review_id: str,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status != (
        STATE_PREVIEW
    ):

        return None

    if not state.translated_text.strip():

        return None

    row = (
        _database()
        .mark_persistent_translation_review_confirmed(
            review_id
        )
    )

    return _state_from_row(
        row
    )


# =========================================================
# FAIL
# =========================================================

def mark_translation_failed(
    review_id: str,
    *,
    reason: str = "",
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status in {
        STATE_CONFIRMED,
        STATE_CANCELLED,
    }:

        return None

    failure_metadata = (
        _normalize_metadata(
            metadata
        )
    )

    if reason:

        failure_metadata[
            "failure_reason"
        ] = str(
            reason
        )

    row = (
        _database()
        .mark_persistent_translation_review_failed(
            review_id,
            reason=str(
                reason
                or ""
            ),
            metadata=(
                failure_metadata
            ),
        )
    )

    return _state_from_row(
        row
    )


# =========================================================
# CANCEL
# =========================================================

def cancel_translation_state(
    review_id: str,
) -> Optional[
    TranslationState
]:

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    if state.status == (
        STATE_CONFIRMED
    ):

        return None

    if state.status == (
        STATE_CANCELLED
    ):

        return state

    row = (
        _database()
        .mark_persistent_translation_review_cancelled(
            review_id
        )
    )

    return _state_from_row(
        row
    )


# =========================================================
# REMOVE
# =========================================================

def remove_translation_state(
    review_id: str,
) -> Optional[
    TranslationState
]:
    """
    Delete persistent Translation workflow.

    Return the previous state for backward compatibility with
    the existing Controller, which checks:

        removed is None
    """

    state = get_translation_state(
        review_id
    )

    if state is None:
        return None

    deleted = (
        _database()
        .delete_persistent_translation_review(
            review_id
        )
    )

    if not deleted:
        return None

    return state


# =========================================================
# CLEANUP
# =========================================================

def cleanup_expired_translation_states() -> int:

    try:

        return (
            _database()
            .cleanup_expired_persistent_translation_reviews()
        )

    except Exception:

        logger.exception(
            "❌ Persistent translation cleanup failed"
        )

        raise


# =========================================================
# ACTIVE CHECK
# =========================================================

def has_active_translation_state(
    *,
    chat_id: int,
    user_id: int,
) -> bool:

    return (
        get_active_translation_state(
            chat_id=chat_id,
            user_id=user_id,
        )
        is not None
    )


# =========================================================
# TERMINAL CHECK
# =========================================================

def translation_state_is_terminal(
    state: Optional[
        TranslationState
    ],
) -> bool:

    if state is None:
        return False

    return (
        state.status
        in TERMINAL_STATES
    )


# =========================================================
# COMPATIBILITY RESET
# =========================================================

def reset_translation_states() -> None:
    """
    Compatibility helper.

    The previous in-memory implementation could clear process
    state globally. Persistent Production state must never be
    globally deleted by an ordinary application helper.

    Therefore this function intentionally performs only expired
    state cleanup.

    This prevents tests/admin utilities from accidentally wiping
    active Production translation reviews.
    """

    cleanup_expired_translation_states()


# =========================================================
# DEBUG DESCRIPTION
# =========================================================

def describe_translation_state(
    state: Optional[
        TranslationState
    ],
) -> Dict[str, Any]:

    if state is None:

        return {
            "exists": False,
        }

    return {
        "exists":
            True,

        "review_id":
            state.review_id,

        "chat_id":
            state.chat_id,

        "user_id":
            state.user_id,

        "status":
            state.status,

        "source_language":
            state.source_language,

        "target_language":
            state.target_language,

        "target_language_code":
            state.target_language_code,

        "source_kind":
            state.source_kind,

        "source_key":
            state.source_key,

        "has_original_text":
            bool(
                state.original_text
            ),

        "has_translated_text":
            bool(
                state.translated_text
            ),

        "manually_edited":
            bool(
                state.edited_text
            ),

        "translation_attempts":
            state.translation_attempts,

        "failure_reason":
            state.failure_reason,

        "created_at":
            state.created_at,

        "updated_at":
            state.updated_at,

        "expires_at":
            state.expires_at,
    }
