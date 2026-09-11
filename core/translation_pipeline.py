from __future__ import annotations

import inspect
import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# =========================================================
# PIPELINE STATUS
# =========================================================

PIPELINE_PASSTHROUGH = "passthrough"

PIPELINE_TRANSLATED = "translated"

PIPELINE_REVIEW_REQUIRED = "review_required"

PIPELINE_BLOCKED = "blocked"

PIPELINE_FAILED = "failed"


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class TranslationPipelineResult:
    success: bool

    status: str

    original_text: str

    output_text: str

    source_language: str = "auto"

    target_language: str = ""

    detection: Any = None

    provider_detection: Any = None

    decision: Any = None

    translation_result: Any = None

    quality_result: Any = None

    requires_review: bool = False

    blocked: bool = False

    reason: str = ""

    attempts: int = 0

    warnings: List[str] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# GENERIC HELPERS
# =========================================================

def _value(
    obj: Any,
    name: str,
    default: Any = None,
) -> Any:

    if obj is None:
        return default

    if isinstance(
        obj,
        dict,
    ):
        return obj.get(
            name,
            default,
        )

    return getattr(
        obj,
        name,
        default,
    )


def _bool_value(
    obj: Any,
    name: str,
    default: bool = False,
) -> bool:

    return bool(
        _value(
            obj,
            name,
            default,
        )
    )


def _string_value(
    obj: Any,
    name: str,
    default: str = "",
) -> str:

    return str(
        _value(
            obj,
            name,
            default,
        )
        or ""
    ).strip()


def _normalize_language(
    value: Any,
    default: str = "auto",
) -> str:

    text = str(
        value
        or ""
    ).strip().lower()

    if not text:

        return default

    text = text.replace(
        "_",
        "-",
    )

    aliases = {
        "persian": "fa",
        "farsi": "fa",
        "فارسی": "fa",

        "english": "en",

        "arabic": "ar",

        "turkish": "tr",

        "russian": "ru",

        "french": "fr",

        "german": "de",

        "spanish": "es",

        "italian": "it",

        "portuguese": "pt",

        "chinese": "zh",

        "japanese": "ja",

        "korean": "ko",

        "hindi": "hi",

        "urdu": "ur",
    }

    if text in aliases:

        return aliases[
            text
        ]

    if text in {
        "auto",
        "unknown",
        "und",
        "uncertain",
    }:

        return "auto"

    base = (
        text
        .split(
            "-",
            1,
        )[0]
        .strip()
    )

    if (
        2 <= len(base) <= 3
        and base.isalpha()
    ):

        return base

    return default


def _normalize_retry_count(
    value: Any,
) -> int:

    try:

        retries = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        retries = 1

    return max(
        0,
        min(
            retries,
            2,
        ),
    )


def _call_supported(
    func: Any,
    **kwargs: Any,
) -> Any:
    """
    Call a project function using only parameters accepted
    by its current signature.

    This prevents accidental coupling between Translation
    modules while they are being integrated incrementally.
    """

    try:

        signature = (
            inspect.signature(
                func
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        return func(
            **kwargs
        )

    parameters = (
        signature.parameters
    )

    has_var_kwargs = any(
        parameter.kind
        == inspect.Parameter.VAR_KEYWORD
        for parameter
        in parameters.values()
    )

    if has_var_kwargs:

        return func(
            **kwargs
        )

    supported = {
        key: value
        for key, value
        in kwargs.items()
        if key in parameters
    }

    return func(
        **supported
    )


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def _detect_language(
    text: str,
) -> Any:

    from core.language_detector import (
        detect_language,
    )

    return detect_language(
        text
    )


def _deterministic_language(
    result: Any,
) -> str:

    # Prefer the detector's own helper when available.
    try:

        from core.language_detector import (
            get_translation_source_language,
        )

        language = (
            get_translation_source_language(
                result
            )
        )

        normalized = (
            _normalize_language(
                language
            )
        )

        if normalized != "auto":

            return normalized

    except Exception:

        pass

    language = (
        _normalize_language(
            _value(
                result,
                "language",
                "auto",
            )
        )
    )

    reliable = bool(
        _value(
            result,
            "reliable",
            False,
        )
    )

    if (
        reliable
        and language != "auto"
    ):

        return language

    return "auto"


def _provider_language_detection(
    text: str,
) -> Any:
    """
    Provider detection is used ONLY when deterministic
    detection cannot confidently determine a language.
    """

    try:

        from core.language_detection_provider import (
            detect_language_with_provider_fallback,
        )

    except Exception as exc:

        logger.warning(
            "⚠️ LANGUAGE-DETECTION-FALLBACK unavailable | %s",
            exc,
        )

        return None

    try:

        return (
            detect_language_with_provider_fallback(
                text
            )
        )

    except Exception as exc:

        logger.exception(
            "❌ LANGUAGE-DETECTION-FALLBACK failed | %s",
            exc,
        )

        return None


def detect_pipeline_source_language(
    text: str,
) -> Dict[str, Any]:
    """
    Deterministic detector first.

    Gemini/provider is called only when the deterministic
    detector is uncertain.

    Failure never guesses.
    """

    deterministic = (
        _detect_language(
            text
        )
    )

    language = (
        _deterministic_language(
            deterministic
        )
    )

    if language != "auto":

        return {
            "language":
                language,

            "detection":
                deterministic,

            "provider_detection":
                None,

            "detected_by":
                "deterministic",
        }

    provider_result = (
        _provider_language_detection(
            text
        )
    )

    provider_language = (
        _normalize_language(
            _value(
                provider_result,
                "language",
                "auto",
            )
        )
    )

    provider_success = bool(
        _value(
            provider_result,
            "success",
            False,
        )
    )

    if (
        provider_success
        and provider_language != "auto"
    ):

        return {
            "language":
                provider_language,

            "detection":
                deterministic,

            "provider_detection":
                provider_result,

            "detected_by":
                "provider",
        }

    return {
        "language":
            "auto",

        "detection":
            deterministic,

        "provider_detection":
            provider_result,

        "detected_by":
            "unknown",
    }


# =========================================================
# POLICY
# =========================================================

def _decide_translation(
    *,
    policy: Any,
    source_language: str,
    content_kind: str,
    manual_override: bool,
    manual_target_language: str,
) -> Any:

    from core.translation_policy import (
        decide_translation,
    )

    return _call_supported(
        decide_translation,

        policy=policy,

        source_language=(
            source_language
        ),

        content_kind=(
            content_kind
        ),

        manual_override=(
            manual_override
        ),

        target_language=(
            manual_target_language
        ),

        manual_target_language=(
            manual_target_language
        ),
    )


def _decision_action(
    decision: Any,
) -> str:

    return str(
        _value(
            decision,
            "action",
            "",
        )
        or ""
    ).strip().lower()


def _decision_target_language(
    *,
    decision: Any,
    policy: Any,
    manual_target_language: str,
) -> str:

    if manual_target_language:

        return (
            _normalize_language(
                manual_target_language,
                default="",
            )
        )

    value = (
        _string_value(
            decision,
            "target_language",
            "",
        )
    )

    if value:

        return (
            _normalize_language(
                value,
                default="",
            )
        )

    return (
        _normalize_language(
            _value(
                policy,
                "destination_language",
                "",
            ),
            default="",
        )
    )


def _decision_requires_review(
    decision: Any,
) -> bool:

    if _bool_value(
        decision,
        "requires_review",
        False,
    ):

        return True

    action = (
        _decision_action(
            decision
        )
    )

    return action in {
        "translate_and_review",
        "manual_translate",
        "review",
    }


# =========================================================
# TRANSLATION PROVIDER
# =========================================================

def _default_translation_provider() -> Any:

    try:

        from core.translation_provider import (
            get_default_translation_provider,
        )

        return (
            get_default_translation_provider()
        )

    except Exception as exc:

        logger.warning(
            "⚠️ TRANSLATION-PROVIDER unavailable | %s",
            exc,
        )

        return None


# =========================================================
# TRANSLATION
# =========================================================

def _translate(
    *,
    text: str,
    source_language: str,
    target_language: str,
    provider: Any,
    extra_instruction: str = "",
) -> Any:

    from core.translation_service import (
        translate_text,
    )

    return _call_supported(
        translate_text,

        text=text,

        source_language=(
            source_language
        ),

        target_language=(
            target_language
        ),

        provider=provider,

        extra_instruction=(
            extra_instruction
        ),
    )


def _translation_success(
    result: Any,
) -> bool:

    return bool(
        _value(
            result,
            "success",
            False,
        )
    )


def _translation_text(
    result: Any,
) -> str:

    for field_name in (
        "translated_text",
        "output_text",
        "text",
    ):

        value = (
            _string_value(
                result,
                field_name,
                "",
            )
        )

        if value:

            return value

    return ""


def _translation_reason(
    result: Any,
) -> str:

    for field_name in (
        "reason",
        "error",
        "message",
    ):

        value = (
            _string_value(
                result,
                field_name,
                "",
            )
        )

        if value:

            return value

    return ""


# =========================================================
# QUALITY
# =========================================================

def _quality_check(
    *,
    source_text: str,
    translated_text: str,
    source_language: str,
    target_language: str,
    semantic_quality: bool,
    editorial_instruction: str = "",
) -> Any:

    try:

        from core.translation_quality import (
            check_translation_quality,
        )

    except Exception as exc:

        logger.warning(
            "⚠️ TRANSLATION-QUALITY unavailable | %s",
            exc,
        )

        return None

    quality_provider = None

    if semantic_quality:

        try:

            from core.translation_quality_provider import (
                get_default_translation_quality_provider,
            )

            quality_provider = (
                get_default_translation_quality_provider()
            )

        except Exception as exc:

            logger.warning(
                "⚠️ TRANSLATION-QUALITY-PROVIDER "
                "unavailable | %s",
                exc,
            )

    if quality_provider is not None and editorial_instruction:
        base_quality_provider = quality_provider

        def quality_provider(**kwargs):
            kwargs["instruction"] = (
                str(kwargs.get("instruction", ""))
                + "\n\n" + editorial_instruction
            )
            return _call_supported(base_quality_provider, **kwargs)

    try:

        return _call_supported(
            check_translation_quality,

            source_text=(
                source_text
            ),

            original_text=(
                source_text
            ),

            translated_text=(
                translated_text
            ),

            translation=(
                translated_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            provider=(
                quality_provider
            ),

            quality_provider=(
                quality_provider
            ),

            semantic_check=(
                semantic_quality
            ),

            semantic_quality=(
                semantic_quality
            ),
        )

    except Exception as exc:

        logger.exception(
            "❌ TRANSLATION-QUALITY-CHECK failed | %s",
            exc,
        )

        return None


def _quality_status(
    result: Any,
) -> str:

    return str(
        _value(
            result,
            "status",
            "",
        )
        or ""
    ).strip().lower()


def _quality_passed(
    result: Any,
) -> bool:

    return bool(
        _value(
            result,
            "passed",
            False,
        )
    )


def _quality_semantically_verified(
    result: Any,
) -> bool:
    """
    Distinguish:
        deterministic checks passed

    from:
        semantic / linguistic quality actually verified.

    If semantic quality is required, an unverified result
    must NOT silently become an automatic publication.
    """

    if result is None:

        return False

    status = (
        _quality_status(
            result
        )
    )

    if status in {
        "unverified",
        "quality_unverified",
        "semantic_unverified",
        "provider_unavailable",
        "provider_failed",
    }:

        return False

    explicit = _value(
        result,
        "semantic_verified",
        None,
    )

    if explicit is not None:

        return bool(
            explicit
        )

    provider_used = _value(
        result,
        "provider_used",
        None,
    )

    if provider_used is not None:

        return bool(
            provider_used
        )

    metadata = _value(
        result,
        "metadata",
        {},
    )

    if isinstance(
        metadata,
        dict,
    ):

        if (
            "semantic_verified"
            in metadata
        ):

            return bool(
                metadata[
                    "semantic_verified"
                ]
            )

        if (
            metadata.get(
                "provider"
            )
            and status not in {
                "unverified",
                "failed",
            }
        ):

            return True

    # Some implementations report only a verified status.
    if status in {
        "passed",
        "verified",
        "quality_passed",
        "semantic_passed",
        "ok",
        "success",
    }:

        return True

    return False


def _quality_should_retry(
    result: Any,
) -> bool:

    try:

        import core.translation_quality as quality_module

        helper = getattr(
            quality_module,
            "translation_quality_should_retry",
            None,
        )

        if helper is None:

            helper = getattr(
                quality_module,
                "should_retry_translation_quality",
                None,
            )

        if helper is not None:

            return bool(
                _call_supported(
                    helper,
                    result=result,
                    quality_result=result,
                )
            )

    except Exception:

        pass

    if result is None:

        return False

    return not _quality_passed(
        result
    )


def _quality_retry_instruction(
    *,
    result: Any,
    target_language: str,
) -> str:

    try:

        import core.translation_quality as quality_module

        helper = getattr(
            quality_module,
            "build_translation_retry_instruction",
            None,
        )

        if helper is None:

            helper = getattr(
                quality_module,
                "build_quality_retry_instruction",
                None,
            )

        if helper is not None:

            value = (
                _call_supported(
                    helper,

                    result=result,

                    quality_result=result,

                    target_language=(
                        target_language
                    ),
                )
            )

            return str(
                value
                or ""
            ).strip()

    except Exception:

        pass

    return (
        "Translate again from the original source. "
        "Correct any grammar, fluency, terminology, factual "
        "fidelity, certainty, attribution, number, date, "
        "name, URL or completeness problems detected in the "
        "previous candidate. Do not summarize, expand, omit "
        "or invent information."
    )


# =========================================================
# FAILURE POLICY
# =========================================================

def _translation_failure_decision(
    *,
    policy: Any,
    decision: Any,
    source_language: str,
    target_language: str,
    reason: str,
) -> Any:

    try:

        from core.translation_policy import (
            decide_translation_failure,
        )

    except Exception:

        return None

    try:

        return _call_supported(
            decide_translation_failure,

            policy=policy,

            decision=decision,

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            reason=reason,
        )

    except Exception as exc:

        logger.exception(
            "❌ TRANSLATION-FAILURE-POLICY failed | %s",
            exc,
        )

        return None


def _failure_is_blocked(
    failure_decision: Any,
    policy: Any,
) -> bool:

    action = str(
        _value(
            failure_decision,
            "action",
            "",
        )
        or ""
    ).lower()

    if action == "block":

        return True

    fail_closed = bool(
        _value(
            policy,
            "fail_closed",
            True,
        )
    )

    return fail_closed


# =========================================================
# FAILURE RESULT
# =========================================================

def _failure_result(
    *,
    original_text: str,
    source_language: str,
    target_language: str,
    detection: Any,
    provider_detection: Any,
    decision: Any,
    policy: Any,
    translation_result: Any = None,
    quality_result: Any = None,
    reason: str,
    attempts: int,
    warnings: Optional[List[str]] = None,
) -> TranslationPipelineResult:

    failure_decision = (
        _translation_failure_decision(
            policy=policy,
            decision=decision,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            reason=reason,
        )
    )

    blocked = (
        _failure_is_blocked(
            failure_decision,
            policy,
        )
    )

    return TranslationPipelineResult(
        success=False,

        status=(
            PIPELINE_BLOCKED
            if blocked
            else PIPELINE_FAILED
        ),

        original_text=(
            original_text
        ),

        output_text=(
            original_text
        ),

        source_language=(
            source_language
        ),

        target_language=(
            target_language
        ),

        detection=detection,

        provider_detection=(
            provider_detection
        ),

        decision=decision,

        translation_result=(
            translation_result
        ),

        quality_result=(
            quality_result
        ),

        requires_review=False,

        blocked=blocked,

        reason=reason,

        attempts=attempts,

        warnings=list(
            warnings
            or []
        ),

        metadata={
            "failure_decision":
                failure_decision,
        },
    )


# =========================================================
# MAIN PIPELINE
# =========================================================

def run_translation_pipeline(
    *,
    text: str,
    policy: Any,
    content_kind: str = "text",
    manual_override: bool = False,
    manual_target_language: str = "",
    semantic_quality: bool = True,
    quality_retries: int = 1,
    editorial_policy: Any = None,
) -> TranslationPipelineResult:
    """
    Shared multilingual Translation Pipeline.

    Flow:

        Source text
            ↓
        deterministic language detection
            ↓
        AI detection fallback if uncertain
            ↓
        TranslationPolicy decision
            ↓
        Translation Service
            ↓
        explicit editorial terminology policy
            ↓
        deterministic validation
            ↓
        semantic/linguistic quality validation
            ↓
        bounded retry from ORIGINAL source
            ↓
        translated / review_required / blocked

    This function NEVER publishes.
    """

    original_text = str(
        text
        or ""
    ).strip()

    warnings: List[str] = []

    # =====================================================
    # EMPTY
    # =====================================================

    if not original_text:

        return TranslationPipelineResult(
            success=True,

            status=(
                PIPELINE_PASSTHROUGH
            ),

            original_text="",

            output_text="",

            source_language="auto",

            target_language="",

            requires_review=False,

            blocked=False,

            reason="empty_text",

            attempts=0,
        )

    # =====================================================
    # LANGUAGE DETECTION
    # =====================================================

    detection_bundle = (
        detect_pipeline_source_language(
            original_text
        )
    )

    source_language = (
        detection_bundle[
            "language"
        ]
    )

    detection = (
        detection_bundle[
            "detection"
        ]
    )

    provider_detection = (
        detection_bundle[
            "provider_detection"
        ]
    )

    detected_by = (
        detection_bundle[
            "detected_by"
        ]
    )

    if source_language == "auto":

        warnings.append(
            "source_language_uncertain"
        )

    # =====================================================
    # POLICY
    # =====================================================

    try:

        decision = (
            _decide_translation(
                policy=policy,

                source_language=(
                    source_language
                ),

                content_kind=(
                    content_kind
                ),

                manual_override=(
                    manual_override
                ),

                manual_target_language=(
                    manual_target_language
                ),
            )
        )

    except Exception as exc:

        logger.exception(
            "❌ TRANSLATION-POLICY failed | %s",
            exc,
        )

        return TranslationPipelineResult(
            success=False,

            status=PIPELINE_BLOCKED,

            original_text=(
                original_text
            ),

            output_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            blocked=True,

            reason=(
                "translation_policy_failed"
            ),

            warnings=warnings,

            metadata={
                "detected_by":
                    detected_by,
            },
        )

    action = (
        _decision_action(
            decision
        )
    )

    target_language = (
        _decision_target_language(
            decision=decision,
            policy=policy,
            manual_target_language=(
                manual_target_language
            ),
        )
    )

    requires_review = (
        _decision_requires_review(
            decision
        )
    )

    # =====================================================
    # PASSTHROUGH
    # =====================================================

    if action in {
        "",
        "passthrough",
        "disabled",
        "none",
    }:

        return TranslationPipelineResult(
            success=True,

            status=(
                PIPELINE_PASSTHROUGH
            ),

            original_text=(
                original_text
            ),

            output_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            requires_review=False,

            blocked=False,

            reason=(
                _string_value(
                    decision,
                    "reason",
                    "translation_not_required",
                )
            ),

            attempts=0,

            warnings=warnings,

            metadata={
                "detected_by":
                    detected_by,

                "translation_applied":
                    False,
            },
        )

    # =====================================================
    # POLICY BLOCK
    # =====================================================

    if action == "block":

        return TranslationPipelineResult(
            success=False,

            status=PIPELINE_BLOCKED,

            original_text=(
                original_text
            ),

            output_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            requires_review=False,

            blocked=True,

            reason=(
                _string_value(
                    decision,
                    "reason",
                    "translation_policy_blocked",
                )
            ),

            attempts=0,

            warnings=warnings,

            metadata={
                "detected_by":
                    detected_by,
            },
        )

    # =====================================================
    # TARGET LANGUAGE
    # =====================================================

    if (
        not target_language
        or target_language == "auto"
    ):

        return _failure_result(
            original_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            policy=policy,

            reason=(
                "translation_target_language_missing"
            ),

            attempts=0,

            warnings=warnings,
        )

    # =====================================================
    # SAME LANGUAGE SAFETY
    # =====================================================

    if (
        source_language != "auto"
        and source_language
        == target_language
        and not manual_override
    ):

        return TranslationPipelineResult(
            success=True,

            status=(
                PIPELINE_PASSTHROUGH
            ),

            original_text=(
                original_text
            ),

            output_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            requires_review=False,

            blocked=False,

            reason=(
                "source_matches_target"
            ),

            attempts=0,

            warnings=warnings,

            metadata={
                "detected_by":
                    detected_by,

                "translation_applied":
                    False,
            },
        )

    # =====================================================
    # PROVIDER
    # =====================================================

    provider = (
        _default_translation_provider()
    )

    if provider is None:

        return _failure_result(
            original_text=(
                original_text
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            policy=policy,

            reason=(
                "translation_provider_unavailable"
            ),

            attempts=0,

            warnings=warnings,
        )

    # =====================================================
    # TRANSLATE + QUALITY + BOUNDED RETRY
    # =====================================================

    retry_limit = (
        _normalize_retry_count(
            quality_retries
        )
    )

    total_attempt_limit = (
        1
        + retry_limit
    )

    translation_result = None

    quality_result = None

    candidate = ""

    retry_instruction = ""

    attempts = 0

    for attempt_index in range(
        total_attempt_limit
    ):

        attempts = (
            attempt_index
            + 1
        )

        try:

            translation_result = (
                _translate(
                    text=(
                        original_text
                    ),

                    source_language=(
                        source_language
                    ),

                    target_language=(
                        target_language
                    ),

                    provider=provider,

                    extra_instruction=(
                        retry_instruction
                    ),
                )
            )

        except Exception as exc:

            logger.exception(
                "❌ TRANSLATION attempt failed | "
                "attempt=%s | %s",
                attempts,
                exc,
            )

            translation_result = None

        if not _translation_success(
            translation_result
        ):

            reason = (
                _translation_reason(
                    translation_result
                )
                or "translation_generation_failed"
            )

            if (
                attempt_index
                < retry_limit
            ):

                retry_instruction = (
                    "Translate again from the ORIGINAL "
                    "source text. Preserve every fact, name, "
                    "number, date, URL, attribution and degree "
                    "of certainty. Do not summarize, omit, "
                    "expand or invent information."
                )

                continue

            return _failure_result(
                original_text=(
                    original_text
                ),

                source_language=(
                    source_language
                ),

                target_language=(
                    target_language
                ),

                detection=detection,

                provider_detection=(
                    provider_detection
                ),

                decision=decision,

                policy=policy,

                translation_result=(
                    translation_result
                ),

                reason=reason,

                attempts=attempts,

                warnings=warnings,
            )

        candidate = (
            _translation_text(
                translation_result
            )
        )

        if not candidate:

            if (
                attempt_index
                < retry_limit
            ):

                retry_instruction = (
                    "Previous translation returned no usable "
                    "text. Translate the ORIGINAL source "
                    "completely and return only the translated "
                    "content."
                )

                continue

            return _failure_result(
                original_text=(
                    original_text
                ),

                source_language=(
                    source_language
                ),

                target_language=(
                    target_language
                ),

                detection=detection,

                provider_detection=(
                    provider_detection
                ),

                decision=decision,

                policy=policy,

                translation_result=(
                    translation_result
                ),

                reason=(
                    "translation_output_empty"
                ),

                attempts=attempts,

                warnings=warnings,
            )

        # =================================================
        # EDITORIAL HOUSE STYLE (before quality, never after human edits)
        # =================================================
        try:
            from core.translation_editorial_policy import (
                PERSIAN_NEWSROOM_POLICY,
                apply_editorial_translation_policy,
            )
            editorial_result = apply_editorial_translation_policy(
                source_text=original_text,
                translated_text=candidate,
                target_language=target_language,
                policy=(editorial_policy if editorial_policy is not None else PERSIAN_NEWSROOM_POLICY),
            )
            if editorial_result.blocked or not editorial_result.output_text.strip():
                raise ValueError(editorial_result.reason or "editorial_policy_blocked")
        except Exception:
            logger.exception("EDITORIAL-TRANSLATION-POLICY failed")
            return TranslationPipelineResult(
                success=False, status=PIPELINE_BLOCKED, blocked=True, output_text="",
                original_text=original_text, source_language=source_language,
                target_language=target_language, detection=detection,
                provider_detection=provider_detection, decision=decision,
                translation_result=translation_result,
                reason="editorial_policy_failed", attempts=attempts, warnings=warnings,
            )

        candidate = editorial_result.output_text

        # =================================================
        # QUALITY
        # =================================================

        quality_result = (
            _quality_check(
                source_text=(
                    original_text
                ),

                translated_text=(
                    candidate
                ),

                source_language=(
                    source_language
                ),

                target_language=(
                    target_language
                ),

                semantic_quality=(
                    semantic_quality
                ),
                editorial_instruction=editorial_result.quality_instruction,
            )
        )

        # Semantic quality explicitly requested but no
        # quality result exists:
        if (
            semantic_quality
            and quality_result is None
        ):

            warnings.append(
                "semantic_quality_unavailable"
            )

            if (
                attempt_index
                < retry_limit
            ):

                retry_instruction = (
                    "Translate again carefully from the "
                    "ORIGINAL source. Produce natural, "
                    "grammatically correct newsroom-quality "
                    f"{target_language} while preserving all "
                    "facts and certainty."
                )

                continue

            return _failure_result(
                original_text=(
                    original_text
                ),

                source_language=(
                    source_language
                ),

                target_language=(
                    target_language
                ),

                detection=detection,

                provider_detection=(
                    provider_detection
                ),

                decision=decision,

                policy=policy,

                translation_result=(
                    translation_result
                ),

                quality_result=(
                    quality_result
                ),

                reason=(
                    "semantic_quality_unavailable"
                ),

                attempts=attempts,

                warnings=warnings,
            )

        if quality_result is not None:

            quality_passed = (
                _quality_passed(
                    quality_result
                )
            )

            if (
                semantic_quality
                and not _quality_semantically_verified(
                    quality_result
                )
            ):

                quality_passed = False

                if (
                    "semantic_quality_unverified"
                    not in warnings
                ):

                    warnings.append(
                        "semantic_quality_unverified"
                    )

            if not quality_passed:

                if (
                    attempt_index
                    < retry_limit
                    and _quality_should_retry(
                        quality_result
                    )
                ):

                    retry_instruction = (
                        _quality_retry_instruction(
                            result=(
                                quality_result
                            ),

                            target_language=(
                                target_language
                            ),
                        )
                    )

                    continue

                return _failure_result(
                    original_text=(
                        original_text
                    ),

                    source_language=(
                        source_language
                    ),

                    target_language=(
                        target_language
                    ),

                    detection=detection,

                    provider_detection=(
                        provider_detection
                    ),

                    decision=decision,

                    policy=policy,

                    translation_result=(
                        translation_result
                    ),

                    quality_result=(
                        quality_result
                    ),

                    reason=(
                        "translation_quality_failed"
                    ),

                    attempts=attempts,

                    warnings=warnings,
                )

        # =================================================
        # SUCCESS
        # =================================================

        requires_review = requires_review or editorial_result.requires_review
        if editorial_result.requires_review:
            warnings.append("editorial_policy_review_required")

        final_status = (
            PIPELINE_REVIEW_REQUIRED
            if requires_review
            else PIPELINE_TRANSLATED
        )

        logger.info(
            "✅ TRANSLATION-PIPELINE | "
            "source=%s | target=%s | "
            "detected_by=%s | "
            "status=%s | attempts=%s | "
            "review=%s",
            source_language,
            target_language,
            detected_by,
            final_status,
            attempts,
            requires_review,
        )

        return TranslationPipelineResult(
            success=True,

            status=(
                final_status
            ),

            original_text=(
                original_text
            ),

            output_text=(
                candidate
            ),

            source_language=(
                source_language
            ),

            target_language=(
                target_language
            ),

            detection=detection,

            provider_detection=(
                provider_detection
            ),

            decision=decision,

            translation_result=(
                translation_result
            ),

            quality_result=(
                quality_result
            ),

            requires_review=(
                requires_review
            ),

            blocked=False,

            reason=(
                editorial_result.reason or "translation_ready"
            ),

            attempts=attempts,

            warnings=warnings,

            metadata={
                "detected_by":
                    detected_by,

                "translation_applied":
                    True,

                "manual_override":
                    manual_override,

                "semantic_quality":
                    semantic_quality,
                "editorial_policy": {
                    "status": editorial_result.status,
                    "matched_rules": list(editorial_result.matched_rules),
                    "normalized_rules": list(editorial_result.normalized_rules),
                    "reason": editorial_result.reason,
                },
            },
        )

    # Defensive fallback.
    return _failure_result(
        original_text=(
            original_text
        ),

        source_language=(
            source_language
        ),

        target_language=(
            target_language
        ),

        detection=detection,

        provider_detection=(
            provider_detection
        ),

        decision=decision,

        policy=policy,

        translation_result=(
            translation_result
        ),

        quality_result=(
            quality_result
        ),

        reason=(
            "translation_pipeline_exhausted"
        ),

        attempts=attempts,

        warnings=warnings,
    )


# =========================================================
# MANUAL TRANSLATION
# =========================================================

def run_manual_translation_pipeline(
    *,
    text: str,
    policy: Any,
    target_language: str,
    content_kind: str = "text",
    semantic_quality: bool = True,
    quality_retries: int = 1,
    editorial_policy: Any = None,
) -> TranslationPipelineResult:
    """
    Manual 🌐 Translation always uses explicit target
    language and enters the review path.
    """

    result = (
        run_translation_pipeline(
            text=text,

            policy=policy,

            content_kind=(
                content_kind
            ),

            manual_override=True,

            manual_target_language=(
                target_language
            ),

            semantic_quality=(
                semantic_quality
            ),

            quality_retries=(
                quality_retries
            ),
            editorial_policy=editorial_policy,
        )
    )

    if (
        result.success
        and result.status
        == PIPELINE_TRANSLATED
    ):

        return TranslationPipelineResult(
            success=(
                result.success
            ),

            status=(
                PIPELINE_REVIEW_REQUIRED
            ),

            original_text=(
                result.original_text
            ),

            output_text=(
                result.output_text
            ),

            source_language=(
                result.source_language
            ),

            target_language=(
                result.target_language
            ),

            detection=(
                result.detection
            ),

            provider_detection=(
                result.provider_detection
            ),

            decision=(
                result.decision
            ),

            translation_result=(
                result.translation_result
            ),

            quality_result=(
                result.quality_result
            ),

            requires_review=True,

            blocked=False,

            reason=(
                result.reason
            ),

            attempts=(
                result.attempts
            ),

            warnings=list(
                result.warnings
            ),

            metadata=dict(
                result.metadata
            ),
        )

    return result


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translation_pipeline_result(
    result: TranslationPipelineResult,
) -> Dict[str, Any]:
    """
    Safe diagnostics.

    Source/translated message bodies are intentionally not
    included.
    """

    quality_score = None

    if result.quality_result is not None:

        quality_score = _value(
            result.quality_result,
            "score",
            None,
        )

    provider_confidence = None

    if (
        result.provider_detection
        is not None
    ):

        provider_confidence = (
            _value(
                result.provider_detection,
                "confidence",
                None,
            )
        )

    return {
        "success":
            result.success,

        "status":
            result.status,

        "source_language":
            result.source_language,

        "target_language":
            result.target_language,

        "requires_review":
            result.requires_review,

        "blocked":
            result.blocked,

        "reason":
            result.reason,

        "attempts":
            result.attempts,

        "warnings":
            list(
                result.warnings
            ),

        "quality_score":
            quality_score,

        "provider_detection_confidence":
            provider_confidence,

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }
