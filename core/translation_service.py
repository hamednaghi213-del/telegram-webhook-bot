from __future__ import annotations

import logging
import re
import time
from core.translation_provider import TranslationProviderError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION SERVICE
# =========================================================
#
# هدف:
# ایجاد موتور عمومی ترجمه برای Shared Publication Engine.
#
# این فایل:
# - مستقل از Telegram / Bale است.
# - مستقل از Workspace / Legacy است.
# - هیچ پیام خارجی ارسال نمی‌کند.
# - هیچ Branding اضافه نمی‌کند.
# - متن را خلاصه یا بازنویسی نمی‌کند.
# - فقط ترجمه وفادارانه تولید و اعتبارسنجی می‌کند.
#
# مسیر آینده:
#
# PreparedContent
#       ↓
# Translation Service
#       ↓
# Translated PreparedContent
#       ↓
# Destination Branding / FormatProfile
#       ↓
# PublicationPlan
#       ↓
# Telegram / Bale
#
# =========================================================


# =========================================================
# CONSTANTS
# =========================================================

LANGUAGE_AUTO = "auto"

DEFAULT_TRANSLATION_RETRIES = 2

MAX_TRANSLATION_RETRIES = 3

MIN_TRANSLATABLE_LENGTH = 1

MAX_PROVIDER_LANGUAGE_NAME_LENGTH = 80


# =========================================================
# VALIDATION ERRORS
# =========================================================

ERROR_EMPTY_SOURCE = "empty_source"
ERROR_EMPTY_TRANSLATION = "empty_translation"

ERROR_NUMBERS_CHANGED = "numbers_changed"

ERROR_URLS_CHANGED = "urls_changed"

ERROR_MENTIONS_CHANGED = "mentions_changed"

ERROR_HASHTAGS_CHANGED = "hashtags_changed"

ERROR_CERTAINTY_LOST = "certainty_markers_lost"

ERROR_PLACEHOLDER_LOST = "protected_placeholder_lost"

ERROR_PROVIDER = "provider_error"

ERROR_INVALID_LANGUAGE = "invalid_language"

ERROR_SAME_LANGUAGE = "source_and_target_language_same"


# =========================================================
# CERTAINTY / ATTRIBUTION MARKERS
# =========================================================
#
# ترجمه ممکن است خود کلمات را تغییر دهد؛ بنابراین این لیست
# فقط برای تشخیص وجود «معنای احتیاط / ادعا / انتساب» در متن
# مبدأ استفاده می‌شود.
#
# Validator الزام نمی‌کند همان کلمه فارسی در ترجمه باقی بماند.
# برای زبان‌های مختلف، Provider موظف است مفهوم را حفظ کند.
#
# در مرحله Validation ماشینی، Placeholder مخصوص Semantic
# Constraint استفاده می‌کنیم.
#
# =========================================================

PERSIAN_CERTAINTY_MARKERS: Tuple[str, ...] = (
    "احتمال",
    "احتمالاً",
    "ممکن است",
    "ممکن",
    "شاید",
    "گمان",
    "ادعا",
    "مدعی",
    "گفته می‌شود",
    "گزارش شده",
    "گزارش شده است",
    "به گفته",
    "بر اساس گزارش",
    "براساس گزارش",
    "تأیید نشده",
    "تایید نشده",
    "تکذیب",
    "رد کرد",
    "اعلام کرد",
    "گفت",
)

ENGLISH_CERTAINTY_MARKERS: Tuple[str, ...] = (
    "reportedly",
    "report says",
    "according to",
    "alleged",
    "allegedly",
    "claims",
    "claimed",
    "may",
    "might",
    "could",
    "possibly",
    "probably",
    "likely",
    "unlikely",
    "unconfirmed",
    "confirmed",
    "denied",
    "denies",
)


# =========================================================
# PROTECTED TOKEN PATTERNS
# =========================================================

URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    flags=re.IGNORECASE,
)

MENTION_PATTERN = re.compile(
    r"(?<!\w)@[A-Za-z0-9_]+"
)

HASHTAG_PATTERN = re.compile(
    r"(?<!\w)#[^\s#]+"
)

NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w])
    [+\-]?
    [0-9۰-۹٠-٩]+
    (?:
        [.,٫٬:/-]
        [0-9۰-۹٠-٩]+
    )*
    (?:\s*[%٪])?
    (?![\w])
    """,
    flags=re.VERBOSE,
)


# =========================================================
# DATA MODELS
# =========================================================

@dataclass(frozen=True)
class TranslationRequest:
    text: str

    target_language: str

    source_language: str = LANGUAGE_AUTO

    preserve_numbers: bool = True

    preserve_urls: bool = True

    preserve_mentions: bool = True

    preserve_hashtags: bool = True

    preserve_structure: bool = True

    preserve_certainty: bool = True

    preserve_attribution: bool = True

    preserve_names: bool = True

    preserve_dates: bool = True

    preserve_quotes: bool = True

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class TranslationValidation:
    valid: bool

    errors: Tuple[str, ...] = ()

    warnings: Tuple[str, ...] = ()

    original_numbers: Tuple[str, ...] = ()

    translated_numbers: Tuple[str, ...] = ()

    original_urls: Tuple[str, ...] = ()

    translated_urls: Tuple[str, ...] = ()

    original_mentions: Tuple[str, ...] = ()

    translated_mentions: Tuple[str, ...] = ()

    original_hashtags: Tuple[str, ...] = ()

    translated_hashtags: Tuple[str, ...] = ()

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class TranslationResult:
    success: bool

    original_text: str

    translated_text: str

    source_language: str

    target_language: str

    detected_source_language: Optional[str]

    validation_passed: bool

    reason: str

    attempts: int

    validation: TranslationValidation

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# PROVIDER TYPE
# =========================================================
#
# Provider signature:
#
# provider(
#     text=<protected text>,
#     instruction=<translation instruction>,
#     source_language=<source/auto>,
#     target_language=<target>
# ) -> str
#
# برای سازگاری با Providerهای ساده‌تر، تابع داخلی
# _call_provider چند signature متداول را پشتیبانی می‌کند.
#
# =========================================================

TranslationProvider = Callable[..., str]


# =========================================================
# BASIC HELPERS
# =========================================================

def normalize_language_name(
    value: Optional[str]
) -> str:
    if value is None:
        return ""

    value = str(
        value
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value[
        :MAX_PROVIDER_LANGUAGE_NAME_LENGTH
    ]


def normalize_text(
    value: Optional[str]
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _ordered_unique(
    values: Iterable[str]
) -> List[str]:
    result: List[str] = []

    seen: Set[str] = set()

    for value in values:
        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    return result


def extract_numbers(
    text: str
) -> List[str]:
    return _ordered_unique(
        NUMBER_PATTERN.findall(
            text or ""
        )
    )


def extract_urls(
    text: str
) -> List[str]:
    return _ordered_unique(
        URL_PATTERN.findall(
            text or ""
        )
    )


def extract_mentions(
    text: str
) -> List[str]:
    return _ordered_unique(
        MENTION_PATTERN.findall(
            text or ""
        )
    )


def extract_hashtags(
    text: str
) -> List[str]:
    return _ordered_unique(
        HASHTAG_PATTERN.findall(
            text or ""
        )
    )


def contains_certainty_language(
    text: str
) -> bool:
    normalized = (
        text or ""
    ).casefold()

    markers = (
        PERSIAN_CERTAINTY_MARKERS
        + ENGLISH_CERTAINTY_MARKERS
    )

    return any(
        marker.casefold()
        in normalized
        for marker in markers
    )


# =========================================================
# PROTECTED PLACEHOLDERS
# =========================================================

@dataclass
class ProtectedText:
    text: str

    replacements: Dict[str, str]


def _protect_matches(
    text: str,
    pattern: re.Pattern,
    prefix: str,
    replacements: Dict[str, str]
) -> str:
    counter = 0

    def replacement(
        match: re.Match
    ) -> str:
        nonlocal counter

        token = (
            f"⟦D24_{prefix}_{counter}⟧"
        )

        counter += 1

        replacements[
            token
        ] = match.group(
            0
        )

        return token

    return pattern.sub(
        replacement,
        text
    )


def protect_translation_tokens(
    text: str,
    *,
    preserve_numbers: bool = True,
    preserve_urls: bool = True,
    preserve_mentions: bool = True,
    preserve_hashtags: bool = True,
) -> ProtectedText:
    replacements: Dict[
        str,
        str
    ] = {}

    protected = text

    # ترتیب مهم است.
    # ابتدا URL تا # یا @ داخل URL اشتباه پردازش نشوند.

    if preserve_urls:
        protected = (
            _protect_matches(
                protected,
                URL_PATTERN,
                "URL",
                replacements
            )
        )

    if preserve_mentions:
        protected = (
            _protect_matches(
                protected,
                MENTION_PATTERN,
                "MENTION",
                replacements
            )
        )

    if preserve_hashtags:
        protected = (
            _protect_matches(
                protected,
                HASHTAG_PATTERN,
                "HASHTAG",
                replacements
            )
        )

    if preserve_numbers:
        protected = (
            _protect_matches(
                protected,
                NUMBER_PATTERN,
                "NUMBER",
                replacements
            )
        )

    return ProtectedText(
        text=protected,
        replacements=replacements
    )


def restore_translation_tokens(
    translated_text: str,
    replacements: Dict[str, str]
) -> Tuple[
    str,
    List[str]
]:
    restored = (
        translated_text or ""
    )

    missing: List[str] = []

    for token, original in (
        replacements.items()
    ):
        if token not in restored:
            missing.append(
                token
            )

            continue

        restored = restored.replace(
            token,
            original
        )

    return (
        restored,
        missing
    )


# =========================================================
# STRUCTURE ANALYSIS
# =========================================================

def count_nonempty_lines(
    text: str
) -> int:
    return sum(
        1
        for line
        in (
            text or ""
        ).splitlines()
        if line.strip()
    )


def count_paragraphs(
    text: str
) -> int:
    text = (
        text or ""
    ).strip()

    if not text:
        return 0

    paragraphs = re.split(
        r"\n\s*\n",
        text
    )

    return sum(
        1
        for paragraph
        in paragraphs
        if paragraph.strip()
    )


# =========================================================
# TRANSLATION INSTRUCTION
# =========================================================

def build_translation_instruction(
    request: TranslationRequest,
    *,
    retry_errors: Optional[
        Sequence[str]
    ] = None
) -> str:
    source_language = (
        normalize_language_name(
            request.source_language
        )
        or LANGUAGE_AUTO
    )

    target_language = (
        normalize_language_name(
            request.target_language
        )
    )

    instructions: List[str] = [
        "You are translating professional news and editorial content.",
        (
            f"Translate the content into {target_language}."
        ),
        (
            "Detect the source language automatically."
            if (
                source_language.casefold()
                == LANGUAGE_AUTO
            )
            else (
                f"The source language is {source_language}."
            )
        ),
        (
            "Return only the translated content. "
            "Do not add explanations, notes, labels or commentary."
        ),
        (
            "Translate faithfully. "
            "Do not summarize, shorten, expand, rewrite, analyze "
            "or change the editorial meaning."
        ),
        (
            "Do not invent, remove or alter facts."
        ),
    ]

    if request.preserve_names:
        instructions.append(
            "Preserve names of people, organizations and places accurately."
        )

    if request.preserve_numbers:
        instructions.append(
            "Preserve all numbers exactly as represented by protected placeholders."
        )

    if request.preserve_dates:
        instructions.append(
            "Preserve dates and time references accurately."
        )

    if request.preserve_urls:
        instructions.append(
            "Do not modify protected URLs."
        )

    if request.preserve_mentions:
        instructions.append(
            "Do not modify protected @mentions."
        )

    if request.preserve_hashtags:
        instructions.append(
            "Do not modify protected hashtags."
        )

    if request.preserve_quotes:
        instructions.append(
            (
                "Preserve quotation meaning and speaker attribution. "
                "Do not turn reported speech into a factual assertion."
            )
        )

    if request.preserve_certainty:
        instructions.append(
            (
                "Preserve the exact level of certainty and uncertainty. "
                "Possibility must remain possibility, allegations must remain "
                "allegations, and unconfirmed information must not become confirmed."
            )
        )

    if request.preserve_attribution:
        instructions.append(
            (
                "Preserve attribution to speakers, officials, agencies, "
                "media outlets and other sources."
            )
        )

    if request.preserve_structure:
        instructions.append(
            (
                "Preserve the content structure as closely as practical: "
                "headline, paragraphs, line breaks, lists and quoted sections."
            )
        )

    instructions.append(
        (
            "Tokens formatted like ⟦D24_...⟧ are protected placeholders. "
            "Copy every such token exactly once and do not translate, alter, "
            "split or delete it."
        )
    )

    if retry_errors:
        retry_error_set = set(
            retry_errors
        )

        instructions.append(
            (
                "The previous translation failed validation. "
                "Correct the following constraints while translating again."
            )
        )

        if (
            ERROR_PLACEHOLDER_LOST
            in retry_error_set
        ):
            instructions.append(
                (
                    "At least one protected placeholder was lost. "
                    "Every ⟦D24_...⟧ token must appear exactly once."
                )
            )

        if (
            ERROR_NUMBERS_CHANGED
            in retry_error_set
        ):
            instructions.append(
                "Preserve every number exactly."
            )

        if (
            ERROR_URLS_CHANGED
            in retry_error_set
        ):
            instructions.append(
                "Preserve every URL exactly."
            )

        if (
            ERROR_MENTIONS_CHANGED
            in retry_error_set
        ):
            instructions.append(
                "Preserve every @mention exactly."
            )

        if (
            ERROR_HASHTAGS_CHANGED
            in retry_error_set
        ):
            instructions.append(
                "Preserve every hashtag exactly."
            )

        if (
            ERROR_CERTAINTY_LOST
            in retry_error_set
        ):
            instructions.append(
                (
                    "The previous result altered or lost uncertainty, "
                    "claim, denial, confirmation or attribution semantics. "
                    "Preserve those semantics explicitly."
                )
            )

    return "\n".join(
        f"- {item}"
        for item
        in instructions
    )


# =========================================================
# PROVIDER CALL
# =========================================================

def _call_provider(
    provider: TranslationProvider,
    *,
    text: str,
    instruction: str,
    source_language: str,
    target_language: str,
) -> str:
    """
    چند Signature متداول را پشتیبانی می‌کند تا این سرویس
    به Provider مشخصی قفل نشود.
    """

    # Preferred keyword API

    try:
        return provider(
            text=text,
            instruction=instruction,
            source_language=source_language,
            target_language=target_language,
        )

    except TypeError:
        pass

    # Existing AI-style:
    # provider(text, instruction, target)

    try:
        return provider(
            text,
            instruction,
            target_language,
        )

    except TypeError:
        pass

    # Simpler:
    # provider(text, instruction)

    try:
        return provider(
            text,
            instruction,
        )

    except TypeError:
        pass

    # Minimal:
    # provider(text)

    return provider(
        text
    )


# =========================================================
# VALIDATION
# =========================================================

def validate_translation(
    original_text: str,
    translated_text: str,
    request: TranslationRequest,
    *,
    missing_placeholders: Optional[
        Sequence[str]
    ] = None
) -> TranslationValidation:
    errors: List[str] = []

    warnings: List[str] = []

    original = (
        normalize_text(
            original_text
        )
    )

    translated = (
        normalize_text(
            translated_text
        )
    )

    if not original:
        errors.append(
            ERROR_EMPTY_SOURCE
        )

    if not translated:
        errors.append(
            ERROR_EMPTY_TRANSLATION
        )

    if missing_placeholders:
        errors.append(
            ERROR_PLACEHOLDER_LOST
        )

    original_numbers = tuple(
        extract_numbers(
            original
        )
    )

    translated_numbers = tuple(
        extract_numbers(
            translated
        )
    )

    if (
        request.preserve_numbers
        and set(
            original_numbers
        )
        != set(
            translated_numbers
        )
    ):
        errors.append(
            ERROR_NUMBERS_CHANGED
        )

    original_urls = tuple(
        extract_urls(
            original
        )
    )

    translated_urls = tuple(
        extract_urls(
            translated
        )
    )

    if (
        request.preserve_urls
        and set(
            original_urls
        )
        != set(
            translated_urls
        )
    ):
        errors.append(
            ERROR_URLS_CHANGED
        )

    original_mentions = tuple(
        extract_mentions(
            original
        )
    )

    translated_mentions = tuple(
        extract_mentions(
            translated
        )
    )

    if (
        request.preserve_mentions
        and set(
            original_mentions
        )
        != set(
            translated_mentions
        )
    ):
        errors.append(
            ERROR_MENTIONS_CHANGED
        )

    original_hashtags = tuple(
        extract_hashtags(
            original
        )
    )

    translated_hashtags = tuple(
        extract_hashtags(
            translated
        )
    )

    if (
        request.preserve_hashtags
        and set(
            original_hashtags
        )
        != set(
            translated_hashtags
        )
    ):
        errors.append(
            ERROR_HASHTAGS_CHANGED
        )

    original_nonempty_lines = (
        count_nonempty_lines(
            original
        )
    )

    translated_nonempty_lines = (
        count_nonempty_lines(
            translated
        )
    )

    original_paragraphs = (
        count_paragraphs(
            original
        )
    )

    translated_paragraphs = (
        count_paragraphs(
            translated
        )
    )

    if request.preserve_structure:
        if (
            original_paragraphs > 1
            and translated_paragraphs == 1
        ):
            warnings.append(
                "paragraph_structure_collapsed"
            )

        if (
            original_nonempty_lines >= 3
            and translated_nonempty_lines == 1
        ):
            warnings.append(
                "line_structure_collapsed"
            )

    if (
        request.preserve_certainty
        and contains_certainty_language(
            original
        )
    ):
        # تشخیص دقیق بین‌زبانی فقط با Regex قابل اعتماد نیست.
        # بنابراین اینجا Fail خودکار نمی‌کنیم.
        #
        # Provider instruction این قید را enforce می‌کند و
        # در مرحله آینده می‌توان Semantic Validator مبتنی بر AI
        # به همین Service متصل کرد.
        warnings.append(
            "certainty_semantics_require_semantic_validation"
        )

    return TranslationValidation(
        valid=(
            len(
                errors
            )
            == 0
        ),
        errors=tuple(
            _ordered_unique(
                errors
            )
        ),
        warnings=tuple(
            _ordered_unique(
                warnings
            )
        ),
        original_numbers=(
            original_numbers
        ),
        translated_numbers=(
            translated_numbers
        ),
        original_urls=(
            original_urls
        ),
        translated_urls=(
            translated_urls
        ),
        original_mentions=(
            original_mentions
        ),
        translated_mentions=(
            translated_mentions
        ),
        original_hashtags=(
            original_hashtags
        ),
        translated_hashtags=(
            translated_hashtags
        ),
        metadata={
            "original_nonempty_lines": (
                original_nonempty_lines
            ),
            "translated_nonempty_lines": (
                translated_nonempty_lines
            ),
            "original_paragraphs": (
                original_paragraphs
            ),
            "translated_paragraphs": (
                translated_paragraphs
            ),
            "missing_placeholders": list(
                missing_placeholders
                or []
            ),
        }
    )


# =========================================================
# TRANSLATE
# =========================================================

def translate_text_safely(
    request: TranslationRequest,
    provider: Optional[
        TranslationProvider
    ],
    *,
    max_retries: int = (
        DEFAULT_TRANSLATION_RETRIES
    ),
) -> TranslationResult:
    """
    موتور عمومی ترجمه.

    رفتار:
    - متن اصلی را تغییر نمی‌دهد.
    - URL / Mention / Hashtag / Number را محافظت می‌کند.
    - AI فقط متن غیرمحافظت‌شده را ترجمه می‌کند.
    - خروجی دوباره Validate می‌شود.
    - در شکست Validation، Retry محدود انجام می‌شود.
    - هیچ Fail-open وجود ندارد.
    """

    original_text = (
        request.text
        if request.text is not None
        else ""
    )

    normalized_original = (
        normalize_text(
            original_text
        )
    )

    source_language = (
        normalize_language_name(
            request.source_language
        )
        or LANGUAGE_AUTO
    )

    target_language = (
        normalize_language_name(
            request.target_language
        )
    )

    empty_validation = (
        TranslationValidation(
            valid=False,
            errors=(),
            warnings=(),
        )
    )

    # =====================================================
    # SOURCE VALIDATION
    # =====================================================

    if (
        len(
            normalized_original
        )
        < MIN_TRANSLATABLE_LENGTH
    ):
        validation = (
            TranslationValidation(
                valid=False,
                errors=(
                    ERROR_EMPTY_SOURCE,
                )
            )
        )

        return TranslationResult(
            success=False,
            original_text=original_text,
            translated_text=original_text,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            detected_source_language=None,
            validation_passed=False,
            reason=ERROR_EMPTY_SOURCE,
            attempts=0,
            validation=validation,
        )

    if not target_language:
        validation = (
            TranslationValidation(
                valid=False,
                errors=(
                    ERROR_INVALID_LANGUAGE,
                )
            )
        )

        return TranslationResult(
            success=False,
            original_text=original_text,
            translated_text=original_text,
            source_language=(
                source_language
            ),
            target_language="",
            detected_source_language=None,
            validation_passed=False,
            reason=ERROR_INVALID_LANGUAGE,
            attempts=0,
            validation=validation,
        )

    if (
        source_language.casefold()
        != LANGUAGE_AUTO
        and source_language.casefold()
        == target_language.casefold()
    ):
        validation = (
            TranslationValidation(
                valid=False,
                errors=(
                    ERROR_SAME_LANGUAGE,
                )
            )
        )

        return TranslationResult(
            success=False,
            original_text=original_text,
            translated_text=original_text,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            detected_source_language=(
                source_language
            ),
            validation_passed=False,
            reason=ERROR_SAME_LANGUAGE,
            attempts=0,
            validation=validation,
        )

    if provider is None:
        return TranslationResult(
            success=False,
            original_text=original_text,
            translated_text=original_text,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            detected_source_language=None,
            validation_passed=False,
            reason="translation_provider_not_configured",
            attempts=0,
            validation=empty_validation,
        )

    # =====================================================
    # PROTECT TOKENS
    # =====================================================

    protected = (
        protect_translation_tokens(
            original_text,
            preserve_numbers=(
                request.preserve_numbers
            ),
            preserve_urls=(
                request.preserve_urls
            ),
            preserve_mentions=(
                request.preserve_mentions
            ),
            preserve_hashtags=(
                request.preserve_hashtags
            ),
        )
    )

    # =====================================================
    # RETRY LIMIT
    # =====================================================

    try:
        resolved_retries = int(
            max_retries
        )

    except (
        TypeError,
        ValueError,
    ):
        resolved_retries = (
            DEFAULT_TRANSLATION_RETRIES
        )

    resolved_retries = max(
        0,
        min(
            resolved_retries,
            MAX_TRANSLATION_RETRIES
        )
    )

    total_attempts = (
        1
        + resolved_retries
    )

    previous_errors: Tuple[
        str,
        ...
    ] = ()

    last_validation = (
        empty_validation
    )

    last_candidate = ""
    provider_wait = 0.0

    # =====================================================
    # PROVIDER ATTEMPTS
    # =====================================================

    for attempt_index in range(
        1,
        total_attempts + 1
    ):
        instruction = (
            build_translation_instruction(
                request,
                retry_errors=(
                    previous_errors
                    if attempt_index > 1
                    else None
                )
            )
        )

        logger.info(
            "🌐 Translation attempt | "
            "attempt=%s/%s | "
            "source=%s | "
            "target=%s | "
            "input_length=%s",
            attempt_index,
            total_attempts,
            source_language,
            target_language,
            len(
                original_text
            ),
        )

        try:
            provider_output = (
                _call_provider(
                    provider,
                    text=protected.text,
                    instruction=instruction,
                    source_language=(
                        source_language
                    ),
                    target_language=(
                        target_language
                    ),
                )
            )

        except Exception as exc:
            failure = exc if isinstance(exc, TranslationProviderError) else TranslationProviderError("unknown")
            delay = failure.retry_after_seconds
            if delay is None:
                delay = 2 ** (attempt_index - 1)
            delay = max(0.25, delay)
            can_retry = (failure.retryable and attempt_index < total_attempts
                         and provider_wait + delay <= 3.0)
            metadata = failure.as_metadata()
            metadata["deferred"] = failure.retryable or failure.category in {"rate_limited", "quota_unavailable"}
            logger.warning(
                "TRANSLATION-PROVIDER | provider=%s model=%s status=%s category=%s "
                "retryable=%s retry_after_seconds=%s attempt=%s stopped=%s",
                failure.provider, failure.model, failure.http_status, failure.category,
                failure.retryable, failure.retry_after_seconds, attempt_index, not can_retry,
            )
            if can_retry:
                time.sleep(delay)
                provider_wait += delay
                continue
            return TranslationResult(
                success=False, original_text=original_text, translated_text="",
                source_language=source_language, target_language=target_language,
                detected_source_language=None, validation_passed=False,
                reason=failure.reason, attempts=attempt_index, validation=last_validation,
                metadata={"provider_failure": metadata},
            )

        provider_output = (
            normalize_text(
                provider_output
            )
        )

        restored_text, missing_tokens = (
            restore_translation_tokens(
                provider_output,
                protected.replacements
            )
        )

        restored_text = (
            normalize_text(
                restored_text
            )
        )

        validation = (
            validate_translation(
                original_text=(
                    original_text
                ),
                translated_text=(
                    restored_text
                ),
                request=request,
                missing_placeholders=(
                    missing_tokens
                ),
            )
        )

        last_validation = (
            validation
        )

        last_candidate = (
            restored_text
        )

        if validation.valid:
            logger.info(
                "✅ Translation accepted | "
                "attempt=%s/%s | "
                "source=%s | "
                "target=%s | "
                "input_length=%s | "
                "output_length=%s | "
                "warnings=%s",
                attempt_index,
                total_attempts,
                source_language,
                target_language,
                len(
                    original_text
                ),
                len(
                    restored_text
                ),
                list(
                    validation.warnings
                ),
            )

            return TranslationResult(
                success=True,
                original_text=(
                    original_text
                ),
                translated_text=(
                    restored_text
                ),
                source_language=(
                    source_language
                ),
                target_language=(
                    target_language
                ),
                detected_source_language=(
                    None
                    if (
                        source_language.casefold()
                        == LANGUAGE_AUTO
                    )
                    else source_language
                ),
                validation_passed=True,
                reason="translation_accepted",
                attempts=attempt_index,
                validation=validation,
                metadata={
                    "protected_token_count": (
                        len(
                            protected.replacements
                        )
                    ),
                    "retry_used": (
                        attempt_index > 1
                    ),
                }
            )

        previous_errors = (
            validation.errors
        )

        logger.warning(
            "⚠️ Translation rejected | "
            "attempt=%s/%s | "
            "source=%s | "
            "target=%s | "
            "errors=%s | "
            "warnings=%s",
            attempt_index,
            total_attempts,
            source_language,
            target_language,
            list(
                validation.errors
            ),
            list(
                validation.warnings
            ),
        )

    # =====================================================
    # FAIL CLOSED
    # =====================================================

    logger.error(
        "❌ Translation failed after validation retries | "
        "source=%s | "
        "target=%s | "
        "attempts=%s | "
        "errors=%s",
        source_language,
        target_language,
        total_attempts,
        list(
            last_validation.errors
        ),
    )

    return TranslationResult(
        success=False,
        original_text=(
            original_text
        ),
        translated_text=(
            original_text
        ),
        source_language=(
            source_language
        ),
        target_language=(
            target_language
        ),
        detected_source_language=None,
        validation_passed=False,
        reason="translation_validation_failed",
        attempts=total_attempts,
        validation=(
            last_validation
        ),
        metadata={
            "candidate_translation": (
                last_candidate
            ),
            "protected_token_count": (
                len(
                    protected.replacements
                )
            ),
        }
    )


# =========================================================
# SIMPLE CONVENIENCE API
# =========================================================

def translate_text(
    text: str,
    target_language: str,
    provider: TranslationProvider,
    *,
    source_language: str = LANGUAGE_AUTO,
    max_retries: int = DEFAULT_TRANSLATION_RETRIES,
) -> TranslationResult:
    request = TranslationRequest(
        text=text,
        source_language=(
            source_language
        ),
        target_language=(
            target_language
        ),
    )

    return translate_text_safely(
        request=request,
        provider=provider,
        max_retries=max_retries,
    )


# =========================================================
# MULTI-FIELD TRANSLATION
# =========================================================

def translate_content_fields(
    fields: Dict[
        str,
        Optional[str]
    ],
    target_language: str,
    provider: TranslationProvider,
    *,
    source_language: str = LANGUAGE_AUTO,
    max_retries: int = DEFAULT_TRANSLATION_RETRIES,
) -> Dict[
    str,
    TranslationResult
]:
    """
    برای مرحله اتصال به PreparedContent.

    مثال:
        {
            "headline": "...",
            "body": "...",
            "author": "...",
        }

    هر Field مستقل Validate می‌شود.

    در مرحله اتصال واقعی به PreparedContent می‌توانیم تصمیم
    بگیریم کدام Field قابل ترجمه است و کدام Field باید
    بدون تغییر حفظ شود.
    """

    results: Dict[
        str,
        TranslationResult
    ] = {}

    for field_name, value in (
        fields.items()
    ):
        text = (
            ""
            if value is None
            else str(
                value
            )
        )

        if not text.strip():
            continue

        results[
            field_name
        ] = translate_text(
            text=text,
            target_language=(
                target_language
            ),
            source_language=(
                source_language
            ),
            provider=provider,
            max_retries=max_retries,
        )

    return results


# =========================================================
# ALL FIELDS SUCCESS?
# =========================================================

def all_translations_succeeded(
    results: Dict[
        str,
        TranslationResult
    ]
) -> bool:
    if not results:
        return False

    return all(
        result.success
        and result.validation_passed
        for result
        in results.values()
    )
