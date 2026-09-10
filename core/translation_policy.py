from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION POLICY
# =========================================================
#
# Shared decision layer for multilingual publication.
#
# Responsibilities:
#
# Source Language
#       ↓
# Workspace / Destination Language Policy
#       ↓
# Translation Decision
#       ↓
# Translation Service
#       ↓
# Optional Review
#       ↓
# Shared Publication Engine
#
# IMPORTANT:
#
# - This module does NOT translate content.
# - This module does NOT publish content.
# - This module does NOT send Telegram/Bale messages.
# - This module does NOT modify onboarding.
# - This module does NOT write to the database.
#
# It only decides whether translation is required and
# whether the translated result requires review.
#
# Existing Legacy / Workspace publication behavior remains
# unchanged unless a translation policy explicitly enables
# translation.
# =========================================================


# =========================================================
# LANGUAGE SPECIAL VALUES
# =========================================================

LANGUAGE_AUTO = "auto"

# Keep the incoming/source language.
LANGUAGE_SOURCE = "source"

# No destination language requirement.
LANGUAGE_NONE = ""


# =========================================================
# TRANSLATION MODES
# =========================================================

TRANSLATION_MODE_DISABLED = "disabled"

# Translate automatically when source != destination.
TRANSLATION_MODE_AUTO = "auto"

# Translate when needed, but require explicit review before
# publication.
TRANSLATION_MODE_REVIEW = "review"


VALID_TRANSLATION_MODES = {
    TRANSLATION_MODE_DISABLED,
    TRANSLATION_MODE_AUTO,
    TRANSLATION_MODE_REVIEW,
}


# =========================================================
# CONTENT KINDS
# =========================================================

CONTENT_KIND_TEXT = "text"
CONTENT_KIND_NEWS = "news"
CONTENT_KIND_MEDIA = "media"
CONTENT_KIND_ALBUM = "album"
CONTENT_KIND_DOCUMENT = "document"
CONTENT_KIND_EXTERNAL_REVIEW = "external_review"
CONTENT_KIND_OPINION_NOTE = "opinion_note"
CONTENT_KIND_NEWS_ANALYSIS = "news_analysis"
CONTENT_KIND_EDITORIAL = "editorial"
CONTENT_KIND_UNKNOWN = "unknown"


EDITORIAL_CONTENT_KINDS = {
    CONTENT_KIND_OPINION_NOTE,
    CONTENT_KIND_NEWS_ANALYSIS,
    CONTENT_KIND_EDITORIAL,
}


# =========================================================
# DECISION ACTIONS
# =========================================================

ACTION_PASSTHROUGH = "passthrough"
ACTION_TRANSLATE = "translate"
ACTION_TRANSLATE_AND_REVIEW = "translate_and_review"
ACTION_MANUAL_TRANSLATE = "manual_translate"
ACTION_BLOCK = "block"


# =========================================================
# REASONS
# =========================================================

REASON_TRANSLATION_DISABLED = "translation_disabled"
REASON_DESTINATION_LANGUAGE_UNSET = "destination_language_unset"
REASON_KEEP_SOURCE_LANGUAGE = "keep_source_language"
REASON_SOURCE_LANGUAGE_UNKNOWN = "source_language_unknown"
REASON_SAME_LANGUAGE = "same_language"
REASON_DIFFERENT_LANGUAGE = "different_language"
REASON_REVIEW_REQUIRED = "review_required"
REASON_MANUAL_OVERRIDE = "manual_override"
REASON_TRANSLATION_FAILED = "translation_failed"
REASON_INVALID_POLICY = "invalid_policy"


# =========================================================
# POLICY MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationPolicy:
    """
    Language policy for one publication context.

    This object can later be built from:

    - Workspace settings
    - Destination settings
    - Legacy defaults
    - User onboarding preferences

    Destination-level settings can override Workspace-level
    settings before this object reaches the decision engine.
    """

    destination_language: str = LANGUAGE_SOURCE

    # Language used for previews shown to the administrator.
    #
    # This is intentionally independent from destination
    # language.
    #
    # Example:
    #
    # source: Arabic
    # review: Persian
    # destination: English
    #
    review_language: str = LANGUAGE_SOURCE

    translation_mode: str = TRANSLATION_MODE_DISABLED

    # Editorial / note / analysis can require review even
    # when normal news uses automatic translation.
    review_editorial_translation: bool = True

    # External web articles may optionally require review.
    review_external_translation: bool = False

    # Normal text/news/media translation review.
    review_normal_translation: bool = False

    # Fail closed when a destination explicitly requires a
    # particular language and translation fails.
    #
    # This prevents Persian text from accidentally being
    # published to an English-only destination, etc.
    fail_closed: bool = True

    enabled: bool = True

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# DECISION MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationDecision:
    should_translate: bool

    requires_review: bool

    allow_original_on_failure: bool

    action: str

    reason: str

    source_language: str

    target_language: str

    review_language: str

    content_kind: str

    manual_override: bool = False

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# NORMALIZATION
# =========================================================

_LANGUAGE_ALIASES = {
    "persian": "fa",
    "farsi": "fa",
    "فارسی": "fa",
    "fa-ir": "fa",

    "english": "en",
    "انگلیسی": "en",
    "en-us": "en",
    "en-gb": "en",

    "arabic": "ar",
    "عربی": "ar",

    "turkish": "tr",
    "ترکی": "tr",

    "russian": "ru",
    "روسی": "ru",

    "french": "fr",
    "فرانسوی": "fr",

    "german": "de",
    "آلمانی": "de",

    "spanish": "es",
    "اسپانیایی": "es",

    "chinese": "zh",
    "چینی": "zh",

    "italian": "it",
    "ایتالیایی": "it",

    "portuguese": "pt",
    "پرتغالی": "pt",

    "japanese": "ja",
    "ژاپنی": "ja",

    "korean": "ko",
    "کره‌ای": "ko",
    "کره ای": "ko",

    "hindi": "hi",
    "هندی": "hi",

    "urdu": "ur",
    "اردو": "ur",

    "azerbaijani": "az",
    "آذری": "az",

    "hebrew": "he",
    "عبری": "he",

    "auto": LANGUAGE_AUTO,
    "خودکار": LANGUAGE_AUTO,

    "source": LANGUAGE_SOURCE,
    "original": LANGUAGE_SOURCE,
    "same": LANGUAGE_SOURCE,
    "همان زبان ورودی": LANGUAGE_SOURCE,
    "زبان ورودی": LANGUAGE_SOURCE,
}


def normalize_language(
    language: Optional[str],
) -> str:
    """
    Normalize a language identifier without limiting the
    engine to a fixed language registry.

    Unknown language codes/names are preserved so the
    translation engine remains language-agnostic.
    """

    value = str(
        language
        or ""
    ).strip()

    if not value:
        return ""

    lowered = value.lower()

    alias = _LANGUAGE_ALIASES.get(
        lowered
    )

    if alias:
        return alias

    alias = _LANGUAGE_ALIASES.get(
        value
    )

    if alias:
        return alias

    # Normalize common locale format:
    #
    # EN_us -> en-us
    #
    normalized = (
        lowered
        .replace("_", "-")
        .strip()
    )

    return normalized


def normalize_content_kind(
    content_kind: Optional[str],
) -> str:

    value = str(
        content_kind
        or ""
    ).strip().lower()

    if not value:
        return CONTENT_KIND_UNKNOWN

    aliases = {
        "normal": CONTENT_KIND_TEXT,
        "normal_text": CONTENT_KIND_TEXT,
        "message": CONTENT_KIND_TEXT,

        "photo": CONTENT_KIND_MEDIA,
        "video": CONTENT_KIND_MEDIA,
        "audio": CONTENT_KIND_MEDIA,
        "voice": CONTENT_KIND_MEDIA,

        "media_group": CONTENT_KIND_ALBUM,

        "file": CONTENT_KIND_DOCUMENT,

        "web": CONTENT_KIND_EXTERNAL_REVIEW,
        "web_article": CONTENT_KIND_EXTERNAL_REVIEW,
        "external": CONTENT_KIND_EXTERNAL_REVIEW,

        "note": CONTENT_KIND_OPINION_NOTE,
        "یادداشت": CONTENT_KIND_OPINION_NOTE,

        "analysis": CONTENT_KIND_NEWS_ANALYSIS,
        "تحلیل": CONTENT_KIND_NEWS_ANALYSIS,
    }

    return aliases.get(
        value,
        value
    )


def normalize_translation_mode(
    mode: Optional[str],
) -> str:

    value = str(
        mode
        or ""
    ).strip().lower()

    aliases = {
        "off": TRANSLATION_MODE_DISABLED,
        "none": TRANSLATION_MODE_DISABLED,
        "false": TRANSLATION_MODE_DISABLED,

        "automatic": TRANSLATION_MODE_AUTO,
        "enabled": TRANSLATION_MODE_AUTO,
        "on": TRANSLATION_MODE_AUTO,
        "true": TRANSLATION_MODE_AUTO,

        "approval": TRANSLATION_MODE_REVIEW,
        "confirm": TRANSLATION_MODE_REVIEW,
        "preview": TRANSLATION_MODE_REVIEW,
    }

    value = aliases.get(
        value,
        value
    )

    if value not in VALID_TRANSLATION_MODES:
        return TRANSLATION_MODE_DISABLED

    return value


# =========================================================
# LANGUAGE COMPARISON
# =========================================================

def _base_language(
    language: str,
) -> str:
    """
    Convert locale-like identifiers to their base language.

    en-US -> en
    fa-IR -> fa

    This prevents unnecessary translation between locale
    variants unless a future policy explicitly needs locale
    transformation.
    """

    normalized = normalize_language(
        language
    )

    if not normalized:
        return ""

    if normalized in {
        LANGUAGE_AUTO,
        LANGUAGE_SOURCE,
    }:
        return normalized

    return normalized.split(
        "-",
        1
    )[0]


def languages_match(
    source_language: Optional[str],
    target_language: Optional[str],
) -> bool:

    source = _base_language(
        normalize_language(
            source_language
        )
    )

    target = _base_language(
        normalize_language(
            target_language
        )
    )

    if not source or not target:
        return False

    if source in {
        LANGUAGE_AUTO,
        LANGUAGE_SOURCE,
    }:
        return False

    if target in {
        LANGUAGE_AUTO,
        LANGUAGE_SOURCE,
    }:
        return False

    return source == target


# =========================================================
# REVIEW POLICY
# =========================================================

def translation_requires_review(
    policy: TranslationPolicy,
    content_kind: Optional[str],
) -> bool:

    mode = normalize_translation_mode(
        policy.translation_mode
    )

    if mode == TRANSLATION_MODE_REVIEW:
        return True

    kind = normalize_content_kind(
        content_kind
    )

    if kind in EDITORIAL_CONTENT_KINDS:
        return bool(
            policy.review_editorial_translation
        )

    if (
        kind
        == CONTENT_KIND_EXTERNAL_REVIEW
    ):
        return bool(
            policy.review_external_translation
        )

    return bool(
        policy.review_normal_translation
    )


# =========================================================
# CORE DECISION ENGINE
# =========================================================

def decide_translation(
    *,
    source_language: Optional[str],
    policy: TranslationPolicy,
    content_kind: Optional[str] = None,
    manual_override: bool = False,
    manual_target_language: Optional[str] = None,
) -> TranslationDecision:
    """
    Decide whether translation is required.

    This function has no side effects.

    manual_override=True represents an explicit user action
    such as pressing:

        🌐 ترجمه

    Manual translation remains available even when automatic
    translation is disabled.
    """

    source = normalize_language(
        source_language
    )

    kind = normalize_content_kind(
        content_kind
    )

    destination = normalize_language(
        manual_target_language
        if manual_override
        and manual_target_language
        else policy.destination_language
    )

    review_language = normalize_language(
        policy.review_language
    )

    mode = normalize_translation_mode(
        policy.translation_mode
    )

    # =====================================================
    # MANUAL OVERRIDE
    # =====================================================

    if manual_override:

        if not destination:
            destination = LANGUAGE_AUTO

        if destination == LANGUAGE_SOURCE:
            destination = LANGUAGE_AUTO

        return TranslationDecision(
            should_translate=True,
            requires_review=True,
            allow_original_on_failure=True,
            action=ACTION_MANUAL_TRANSLATE,
            reason=REASON_MANUAL_OVERRIDE,
            source_language=(
                source
                or LANGUAGE_AUTO
            ),
            target_language=destination,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
            manual_override=True,
            metadata={
                "translation_mode":
                    mode,
            },
        )

    # =====================================================
    # POLICY DISABLED
    # =====================================================

    if not policy.enabled:

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_TRANSLATION_DISABLED,
            source_language=(
                source
                or LANGUAGE_AUTO
            ),
            target_language=destination,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
        )

    if mode == TRANSLATION_MODE_DISABLED:

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_TRANSLATION_DISABLED,
            source_language=(
                source
                or LANGUAGE_AUTO
            ),
            target_language=destination,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
        )

    # =====================================================
    # NO DESTINATION LANGUAGE
    # =====================================================

    if not destination:

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_DESTINATION_LANGUAGE_UNSET,
            source_language=(
                source
                or LANGUAGE_AUTO
            ),
            target_language="",
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
        )

    # =====================================================
    # KEEP SOURCE LANGUAGE
    # =====================================================

    if destination == LANGUAGE_SOURCE:

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_KEEP_SOURCE_LANGUAGE,
            source_language=(
                source
                or LANGUAGE_AUTO
            ),
            target_language=LANGUAGE_SOURCE,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
        )

    # =====================================================
    # UNKNOWN SOURCE LANGUAGE
    # =====================================================
    #
    # Detection can happen in the Translation Service or
    # dedicated language detector.
    #
    # We still request translation because the destination
    # has an explicit language requirement.
    # =====================================================

    if (
        not source
        or source == LANGUAGE_AUTO
    ):

        requires_review = (
            translation_requires_review(
                policy,
                kind,
            )
        )

        return TranslationDecision(
            should_translate=True,
            requires_review=(
                requires_review
            ),
            allow_original_on_failure=(
                not policy.fail_closed
            ),
            action=(
                ACTION_TRANSLATE_AND_REVIEW
                if requires_review
                else ACTION_TRANSLATE
            ),
            reason=REASON_SOURCE_LANGUAGE_UNKNOWN,
            source_language=LANGUAGE_AUTO,
            target_language=destination,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
            metadata={
                "translation_mode":
                    mode,
                "language_detection_required":
                    True,
            },
        )

    # =====================================================
    # SAME LANGUAGE
    # =====================================================

    if languages_match(
        source,
        destination,
    ):

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_SAME_LANGUAGE,
            source_language=source,
            target_language=destination,
            review_language=(
                review_language
                or LANGUAGE_SOURCE
            ),
            content_kind=kind,
        )

    # =====================================================
    # DIFFERENT LANGUAGE
    # =====================================================

    requires_review = (
        translation_requires_review(
            policy,
            kind,
        )
    )

    return TranslationDecision(
        should_translate=True,
        requires_review=requires_review,
        allow_original_on_failure=(
            not policy.fail_closed
        ),
        action=(
            ACTION_TRANSLATE_AND_REVIEW
            if requires_review
            else ACTION_TRANSLATE
        ),
        reason=(
            REASON_REVIEW_REQUIRED
            if requires_review
            else REASON_DIFFERENT_LANGUAGE
        ),
        source_language=source,
        target_language=destination,
        review_language=(
            review_language
            or LANGUAGE_SOURCE
        ),
        content_kind=kind,
        metadata={
            "translation_mode":
                mode,
        },
    )


# =========================================================
# TRANSLATION FAILURE DECISION
# =========================================================

def decide_translation_failure(
    decision: TranslationDecision,
) -> TranslationDecision:
    """
    Convert a successful translation decision into its
    failure outcome.

    Explicit-language destinations fail closed by default.

    Example:

        Persian source
        ↓
        English-only destination
        ↓
        translation fails
        ↓
        BLOCK

    We must NOT silently publish Persian content into the
    English destination.
    """

    if decision.allow_original_on_failure:

        return TranslationDecision(
            should_translate=False,
            requires_review=False,
            allow_original_on_failure=True,
            action=ACTION_PASSTHROUGH,
            reason=REASON_TRANSLATION_FAILED,
            source_language=(
                decision.source_language
            ),
            target_language=(
                decision.target_language
            ),
            review_language=(
                decision.review_language
            ),
            content_kind=(
                decision.content_kind
            ),
            manual_override=(
                decision.manual_override
            ),
            metadata={
                **(
                    decision.metadata
                    or {}
                ),
                "translation_failed": True,
                "fallback_to_original": True,
            },
        )

    return TranslationDecision(
        should_translate=False,
        requires_review=False,
        allow_original_on_failure=False,
        action=ACTION_BLOCK,
        reason=REASON_TRANSLATION_FAILED,
        source_language=(
            decision.source_language
        ),
        target_language=(
            decision.target_language
        ),
        review_language=(
            decision.review_language
        ),
        content_kind=(
            decision.content_kind
        ),
        manual_override=(
            decision.manual_override
        ),
        metadata={
            **(
                decision.metadata
                or {}
            ),
            "translation_failed": True,
            "fallback_to_original": False,
        },
    )


# =========================================================
# REVIEW LANGUAGE DECISION
# =========================================================

def should_translate_for_review(
    *,
    source_language: Optional[str],
    review_language: Optional[str],
) -> bool:
    """
    Decide whether content should be translated only for the
    administrator's review surface.

    This is separate from publication translation.

    Example:

        source      = Arabic
        review      = Persian
        destination = English

    The administrator can review Persian while the final
    destination receives English.
    """

    source = normalize_language(
        source_language
    )

    review = normalize_language(
        review_language
    )

    if not review:
        return False

    if review == LANGUAGE_SOURCE:
        return False

    if (
        not source
        or source == LANGUAGE_AUTO
    ):
        return True

    return not languages_match(
        source,
        review,
    )


# =========================================================
# DEFAULT POLICIES
# =========================================================

def build_legacy_default_policy() -> TranslationPolicy:
    """
    Backward-compatible default.

    Existing users keep current publication behavior.
    Translation is NOT automatically enabled.
    """

    return TranslationPolicy(
        destination_language=(
            LANGUAGE_SOURCE
        ),
        review_language=(
            LANGUAGE_SOURCE
        ),
        translation_mode=(
            TRANSLATION_MODE_DISABLED
        ),
        review_editorial_translation=True,
        review_external_translation=False,
        review_normal_translation=False,
        fail_closed=True,
        enabled=True,
        metadata={
            "policy_source":
                "legacy_default",
        },
    )


def build_multilingual_policy(
    *,
    destination_language: str,
    review_language: str = LANGUAGE_SOURCE,
    automatic: bool = True,
    require_review: bool = False,
    review_editorial_translation: bool = True,
    review_external_translation: bool = False,
    review_normal_translation: bool = False,
    fail_closed: bool = True,
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> TranslationPolicy:
    """
    Convenience builder for Workspace/Destination settings.

    This does not persist anything.
    """

    if require_review:
        mode = TRANSLATION_MODE_REVIEW

    elif automatic:
        mode = TRANSLATION_MODE_AUTO

    else:
        mode = TRANSLATION_MODE_DISABLED

    return TranslationPolicy(
        destination_language=(
            normalize_language(
                destination_language
            )
            or LANGUAGE_SOURCE
        ),
        review_language=(
            normalize_language(
                review_language
            )
            or LANGUAGE_SOURCE
        ),
        translation_mode=mode,
        review_editorial_translation=(
            review_editorial_translation
        ),
        review_external_translation=(
            review_external_translation
        ),
        review_normal_translation=(
            review_normal_translation
        ),
        fail_closed=fail_closed,
        enabled=True,
        metadata=dict(
            metadata
            or {}
        ),
    )


# =========================================================
# POLICY OVERRIDE
# =========================================================

def merge_translation_policy(
    base: TranslationPolicy,
    *,
    destination_language: Optional[str] = None,
    review_language: Optional[str] = None,
    translation_mode: Optional[str] = None,
    review_editorial_translation: Optional[
        bool
    ] = None,
    review_external_translation: Optional[
        bool
    ] = None,
    review_normal_translation: Optional[
        bool
    ] = None,
    fail_closed: Optional[bool] = None,
    enabled: Optional[bool] = None,
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> TranslationPolicy:
    """
    Apply Workspace/Destination overrides without mutating
    the base policy.

    Intended hierarchy:

        Legacy/default
            ↓
        Workspace policy
            ↓
        Destination override
    """

    merged_metadata = {
        **(
            base.metadata
            or {}
        ),
        **(
            metadata
            or {}
        ),
    }

    return TranslationPolicy(
        destination_language=(
            normalize_language(
                destination_language
            )
            if destination_language
            is not None
            else base.destination_language
        ),
        review_language=(
            normalize_language(
                review_language
            )
            if review_language
            is not None
            else base.review_language
        ),
        translation_mode=(
            normalize_translation_mode(
                translation_mode
            )
            if translation_mode
            is not None
            else base.translation_mode
        ),
        review_editorial_translation=(
            bool(
                review_editorial_translation
            )
            if review_editorial_translation
            is not None
            else (
                base
                .review_editorial_translation
            )
        ),
        review_external_translation=(
            bool(
                review_external_translation
            )
            if review_external_translation
            is not None
            else (
                base
                .review_external_translation
            )
        ),
        review_normal_translation=(
            bool(
                review_normal_translation
            )
            if review_normal_translation
            is not None
            else (
                base
                .review_normal_translation
            )
        ),
        fail_closed=(
            bool(
                fail_closed
            )
            if fail_closed
            is not None
            else base.fail_closed
        ),
        enabled=(
            bool(
                enabled
            )
            if enabled
            is not None
            else base.enabled
        ),
        metadata=merged_metadata,
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translation_decision(
    decision: TranslationDecision,
) -> Dict[str, Any]:
    """
    Safe diagnostic representation.

    No content text is included.
    """

    return {
        "should_translate":
            decision.should_translate,

        "requires_review":
            decision.requires_review,

        "allow_original_on_failure":
            decision.allow_original_on_failure,

        "action":
            decision.action,

        "reason":
            decision.reason,

        "source_language":
            decision.source_language,

        "target_language":
            decision.target_language,

        "review_language":
            decision.review_language,

        "content_kind":
            decision.content_kind,

        "manual_override":
            decision.manual_override,

        "metadata":
            dict(
                decision.metadata
                or {}
            ),
    }
