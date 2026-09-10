from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION → SHARED PUBLICATION BRIDGE
# =========================================================
#
# Confirmed Translation
#       ↓
# Rebuild publication payload
#       ↓
# Existing publish_prepared_text()
#       ↓
# PreparedContent
#       ↓
# Shared Publication Engine
#       ↓
# Telegram / Bale / Workspace destinations
#
# IMPORTANT:
#
# - No direct Telegram publication.
# - No direct Bale publication.
# - No duplicate Publication Engine.
# - No destination-specific publishing.
# - No new idempotency implementation.
# - No branding here.
#
# Existing Shared Publication Engine remains the only owner
# of final publication.
# =========================================================


PublishPreparedText = Callable[..., Any]


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationPublicationResult:
    success: bool

    published: bool

    review_id: str

    translated_text: str

    source_key: str

    publication_result: Any = None

    reason: str = ""

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# HELPERS
# =========================================================

def _state_value(
    state: Any,
    name: str,
    default: Any = None,
) -> Any:

    if state is None:
        return default

    if isinstance(
        state,
        dict,
    ):
        return state.get(
            name,
            default,
        )

    return getattr(
        state,
        name,
        default,
    )


def _safe_metadata(
    state: Any,
) -> Dict[str, Any]:

    value = _state_value(
        state,
        "metadata",
        {},
    )

    if not isinstance(
        value,
        dict,
    ):
        return {}

    return dict(
        value
    )


def _safe_dict_list(
    value: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return []

    result: List[
        Dict[str, Any]
    ] = []

    for item in value:

        if isinstance(
            item,
            dict,
        ):
            result.append(
                dict(
                    item
                )
            )

    return result


def _review_id(
    state: Any,
) -> str:

    return str(
        _state_value(
            state,
            "review_id",
            "",
        )
        or ""
    ).strip()


def _translated_text(
    state: Any,
) -> str:

    return str(
        _state_value(
            state,
            "translated_text",
            "",
        )
        or ""
    ).strip()


def _original_text(
    state: Any,
) -> str:

    return str(
        _state_value(
            state,
            "original_text",
            "",
        )
        or ""
    ).strip()


# =========================================================
# PUBLICATION IDENTITY
# =========================================================

def build_translation_publication_source_key(
    state: Any,
) -> str:
    """
    Build stable publication identity for one confirmed
    Translation Review.

    Critical semantics:

    SAME Translation review retry:
        SAME key

    New Translation review:
        NEW key

    This allows Shared Publication Engine idempotency to
    recover/retry safely without accidentally treating a new
    explicit translation publication as an old publication.
    """

    metadata = _safe_metadata(
        state
    )

    review_id = _review_id(
        state
    )

    original_source_key = str(
        metadata.get(
            "source_key",
            "",
        )
        or _state_value(
            state,
            "source_key",
            "",
        )
        or ""
    ).strip()

    if original_source_key:

        return (
            f"{original_source_key}"
            f":translation:{review_id}"
        )

    return (
        f"translation:{review_id}"
    )


# =========================================================
# SOURCE KIND
# =========================================================

def translation_source_kind(
    state: Any,
) -> str:

    value = str(
        _state_value(
            state,
            "source_kind",
            "",
        )
        or ""
    ).strip()

    return (
        value
        or "translation"
    )


# =========================================================
# TRANSLATED EDITORIAL DISPLAY
# =========================================================

def _editorial_translation_text(
    *,
    translated_text: str,
    metadata: Dict[str, Any],
) -> str:
    """
    Translation currently operates on the complete source
    text stored for review.

    Do NOT prepend the original-language title/author onto
    translated content here.

    If a future structured translation separately translates
    title / author / body, that belongs in the structured
    translation layer.
    """

    return translated_text


# =========================================================
# FILES
# =========================================================

def translation_publication_files(
    state: Any,
) -> List[Dict[str, Any]]:
    """
    Preserve original media.

    Translation changes language, not the associated photo,
    video, document or album members.
    """

    metadata = _safe_metadata(
        state
    )

    return _safe_dict_list(
        metadata.get(
            "files",
            [],
        )
    )


# =========================================================
# BLOCKQUOTES
# =========================================================

def translation_blockquote_blocks(
    state: Any,
) -> List[Dict[str, Any]]:

    metadata = _safe_metadata(
        state
    )

    translated = metadata.get(
        "translated_blockquote_blocks"
    )

    if translated is not None:

        return _safe_dict_list(
            translated
        )

    # IMPORTANT:
    #
    # Original-language detached blocks must not be appended
    # automatically to translated text.
    #
    # If they were not translated by the PreparedContent
    # translation adapter, fail-safe behavior is to omit them
    # instead of publishing mixed-language content.
    return []


def translation_expandable_blocks(
    state: Any,
) -> List[Dict[str, Any]]:

    metadata = _safe_metadata(
        state
    )

    translated = metadata.get(
        "translated_expandable_blocks"
    )

    if translated is not None:

        return _safe_dict_list(
            translated
        )

    return []


# =========================================================
# ENTITIES
# =========================================================

def translation_entities(
    state: Any,
) -> List[Dict[str, Any]]:
    """
    Never reuse original UTF-16 offsets after translation.

    Natural translation changes character positions.

    Future translated-entity remapping can store rebuilt
    entities in metadata under:

        translated_other_entities
    """

    metadata = _safe_metadata(
        state
    )

    translated = metadata.get(
        "translated_other_entities"
    )

    if translated is not None:

        return _safe_dict_list(
            translated
        )

    return []


# =========================================================
# MEDIA PRESENTATION
# =========================================================

def translation_media_presentation(
    state: Any,
) -> str:

    metadata = _safe_metadata(
        state
    )

    return str(
        metadata.get(
            "media_presentation",
            "",
        )
        or ""
    ).strip()


# =========================================================
# PUBLICATION PAYLOAD
# =========================================================

def build_translation_publication_payload(
    state: Any,
) -> Dict[str, Any]:
    """
    Build arguments compatible with the existing:

        publish_prepared_text(...)

    No publication happens here.
    """

    metadata = _safe_metadata(
        state
    )

    translated_text = _translated_text(
        state
    )

    source_kind = (
        translation_source_kind(
            state
        )
    )

    final_text = translated_text

    if source_kind == "editorial":

        final_text = (
            _editorial_translation_text(
                translated_text=(
                    translated_text
                ),
                metadata=metadata,
            )
        )

    return {
        "main_text":
            final_text,

        "neutral_text":
            final_text,

        "blockquote_blocks":
            translation_blockquote_blocks(
                state
            ),

        "expandable_blocks":
            translation_expandable_blocks(
                state
            ),

        "other_entities":
            translation_entities(
                state
            ),

        "files":
            translation_publication_files(
                state
            ),

        "media_presentation":
            translation_media_presentation(
                state
            ),

        "editorial_finalized":
            bool(
                metadata.get(
                    "editorial_finalized",
                    source_kind
                    == "editorial",
                )
            ),

        "require_single_message":
            bool(
                metadata.get(
                    "require_single_message",
                    source_kind
                    == "editorial",
                )
            ),

        "source_key":
            build_translation_publication_source_key(
                state
            ),
    }


# =========================================================
# VALIDATION
# =========================================================

def validate_translation_for_publication(
    state: Any,
) -> Optional[str]:
    """
    Return None when publication is safe.

    Otherwise return a compact failure reason.
    """

    if state is None:

        return (
            "translation_state_not_found"
        )

    review_id = _review_id(
        state
    )

    if not review_id:

        return (
            "translation_review_id_missing"
        )

    translated_text = (
        _translated_text(
            state
        )
    )

    if not translated_text:

        return (
            "translated_text_missing"
        )

    status = str(
        _state_value(
            state,
            "status",
            "",
        )
        or ""
    ).strip()

    # Avoid importing state constants here so this bridge
    # remains loosely coupled.
    if status != "confirmed":

        return (
            "translation_not_confirmed"
        )

    return None


# =========================================================
# PUBLICATION
# =========================================================

def publish_confirmed_translation(
    *,
    state: Any,
    publish_prepared_text: PublishPreparedText,
) -> TranslationPublicationResult:
    """
    Publish ONE explicitly confirmed translation through the
    existing Shared Publication Engine.

    `publish_prepared_text` is injected by webhook_handler to
    avoid circular imports and to guarantee reuse of the
    established publication path.
    """

    validation_error = (
        validate_translation_for_publication(
            state
        )
    )

    review_id = _review_id(
        state
    )

    translated_text = (
        _translated_text(
            state
        )
    )

    if validation_error:

        logger.warning(
            "⚠️ TRANSLATION-PUBLICATION-BLOCKED | "
            "review_id=%s | reason=%s",
            review_id or "-",
            validation_error,
        )

        return TranslationPublicationResult(
            success=False,
            published=False,
            review_id=review_id,
            translated_text=(
                translated_text
            ),
            source_key="",
            reason=(
                validation_error
            ),
        )

    payload = (
        build_translation_publication_payload(
            state
        )
    )

    chat_id = _state_value(
        state,
        "chat_id",
        None,
    )

    if chat_id is None:

        return TranslationPublicationResult(
            success=False,
            published=False,
            review_id=review_id,
            translated_text=(
                translated_text
            ),
            source_key=(
                payload.get(
                    "source_key",
                    "",
                )
            ),
            reason=(
                "translation_chat_id_missing"
            ),
        )

    try:

        chat_id = int(
            chat_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return TranslationPublicationResult(
            success=False,
            published=False,
            review_id=review_id,
            translated_text=(
                translated_text
            ),
            source_key=(
                payload.get(
                    "source_key",
                    "",
                )
            ),
            reason=(
                "translation_chat_id_invalid"
            ),
        )

    logger.info(
        "🌐 TRANSLATION-PUBLICATION-START | "
        "review_id=%s | "
        "source_kind=%s | "
        "target_language=%s | "
        "files=%s",
        review_id,
        translation_source_kind(
            state
        ),
        str(
            _state_value(
                state,
                "target_language",
                "",
            )
            or _state_value(
                state,
                "target_language_code",
                "",
            )
            or ""
        ),
        len(
            payload.get(
                "files",
                [],
            )
        ),
    )

    try:

        publication_result = (
            publish_prepared_text(
                chat_id=chat_id,

                main_text=(
                    payload[
                        "main_text"
                    ]
                ),

                neutral_text=(
                    payload[
                        "neutral_text"
                    ]
                ),

                blockquote_blocks=(
                    payload[
                        "blockquote_blocks"
                    ]
                ),

                expandable_blocks=(
                    payload[
                        "expandable_blocks"
                    ]
                ),

                other_entities=(
                    payload[
                        "other_entities"
                    ]
                ),

                editorial_finalized=(
                    payload[
                        "editorial_finalized"
                    ]
                ),

                source_key=(
                    payload[
                        "source_key"
                    ]
                ),

                files=(
                    payload[
                        "files"
                    ]
                ),

                media_presentation=(
                    payload[
                        "media_presentation"
                    ]
                ),

                require_single_message=(
                    payload[
                        "require_single_message"
                    ]
                ),

                return_result=True,
            )
        )

    except Exception as exc:

        logger.exception(
            "❌ TRANSLATION-PUBLICATION-ERROR | "
            "review_id=%s",
            review_id,
        )

        return TranslationPublicationResult(
            success=False,
            published=False,
            review_id=review_id,
            translated_text=(
                translated_text
            ),
            source_key=(
                payload[
                    "source_key"
                ]
            ),
            reason=(
                "translation_publication_exception:"
                f"{type(exc).__name__}"
            ),
        )

    # =====================================================
    # SHARED ENGINE RESULT
    # =====================================================

    if isinstance(
        publication_result,
        dict,
    ):

        published = bool(
            publication_result.get(
                "ok"
            )
        )

    else:

        published = bool(
            publication_result
        )

    if not published:

        logger.warning(
            "⚠️ TRANSLATION-PUBLICATION-FAILED | "
            "review_id=%s | source_key=%s",
            review_id,
            payload[
                "source_key"
            ],
        )

        return TranslationPublicationResult(
            success=False,
            published=False,
            review_id=review_id,
            translated_text=(
                translated_text
            ),
            source_key=(
                payload[
                    "source_key"
                ]
            ),
            publication_result=(
                publication_result
            ),
            reason=(
                "shared_publication_failed"
            ),
        )

    logger.info(
        "✅ TRANSLATION-PUBLISHED | "
        "review_id=%s | source_key=%s",
        review_id,
        payload[
            "source_key"
        ],
    )

    return TranslationPublicationResult(
        success=True,
        published=True,
        review_id=review_id,
        translated_text=(
            translated_text
        ),
        source_key=(
            payload[
                "source_key"
            ]
        ),
        publication_result=(
            publication_result
        ),
        metadata={
            "source_kind":
                translation_source_kind(
                    state
                ),

            "files_count":
                len(
                    payload.get(
                        "files",
                        [],
                    )
                ),

            "publication_identity":
                payload[
                    "source_key"
                ],
        },
    )


# =========================================================
# USER MESSAGE
# =========================================================

def translation_publication_message(
    result: TranslationPublicationResult,
) -> str:

    if result.published:

        return (
            "✅ نسخه ترجمه‌شده منتشر شد."
        )

    if (
        result.reason
        == "translation_not_confirmed"
    ):

        return (
            "❌ ترجمه هنوز تأیید نشده است."
        )

    if (
        result.reason
        == "translated_text_missing"
    ):

        return (
            "❌ متن ترجمه‌شده برای انتشار وجود ندارد."
        )

    return (
        "❌ انتشار نسخه ترجمه‌شده با خطا روبرو شد."
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translation_publication(
    result: TranslationPublicationResult,
) -> Dict[str, Any]:
    """
    Safe diagnostics.

    Translated content itself is not logged/returned here.
    """

    return {
        "success":
            result.success,

        "published":
            result.published,

        "review_id":
            result.review_id,

        "source_key":
            result.source_key,

        "reason":
            result.reason,

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }
