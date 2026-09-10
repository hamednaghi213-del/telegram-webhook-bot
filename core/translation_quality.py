from __future__ import annotations

import json
import logging
import re

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# MULTILINGUAL TRANSLATION QUALITY CHECK
# =========================================================
#
# Purpose:
#
# Validate translated content from ANY source language
# to ANY target language.
#
# Example:
#
# Arabic  -> Persian
# Persian -> English
# Russian -> Arabic
# Turkish -> French
# Chinese -> German
#
# This module is NOT English-specific.
#
# Responsibilities:
#
# 1. Deterministic structural validation
# 2. Protected information validation
# 3. Optional semantic / linguistic quality review
#
# Quality dimensions:
#
# - grammatical correctness
# - natural sentence structure
# - appropriate word choice
# - natural target-language fluency
# - newsroom/media suitability
# - factual fidelity
# - preservation of certainty/modality
# - preservation of names, numbers, dates, URLs
# - no invented information
# - no omitted material
#
# IMPORTANT:
#
# - This module does NOT publish content.
# - This module does NOT modify Translation Policy.
# - This module does NOT change Workspace/Legacy behavior.
# - This module does NOT write to the database.
# - This module does NOT automatically rewrite translations.
#
# If semantic quality cannot be verified safely, the result
# is conservative instead of silently declaring success.
# =========================================================


# =========================================================
# TYPES
# =========================================================

QualityProvider = Callable[..., str]


# =========================================================
# STATUS
# =========================================================

QUALITY_PASS = "pass"
QUALITY_WARNING = "warning"
QUALITY_FAIL = "fail"
QUALITY_UNVERIFIED = "unverified"


# =========================================================
# SEVERITY
# =========================================================

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


# =========================================================
# ISSUE CODES
# =========================================================

ISSUE_EMPTY_SOURCE = "empty_source"
ISSUE_EMPTY_TRANSLATION = "empty_translation"

ISSUE_IDENTICAL_TEXT = "identical_text"

ISSUE_NUMBER_CHANGED = "number_changed"
ISSUE_URL_CHANGED = "url_changed"
ISSUE_MENTION_CHANGED = "mention_changed"
ISSUE_HASHTAG_CHANGED = "hashtag_changed"

ISSUE_STRUCTURE_COLLAPSED = "structure_collapsed"

ISSUE_GRAMMAR = "grammar"
ISSUE_WORD_CHOICE = "word_choice"
ISSUE_UNNATURAL_LANGUAGE = "unnatural_language"
ISSUE_STYLE = "style"

ISSUE_FACT_CHANGED = "fact_changed"
ISSUE_FACT_ADDED = "fact_added"
ISSUE_FACT_OMITTED = "fact_omitted"
ISSUE_NAME_CHANGED = "name_changed"
ISSUE_DATE_CHANGED = "date_changed"
ISSUE_QUOTE_CHANGED = "quote_changed"
ISSUE_ATTRIBUTION_CHANGED = "attribution_changed"
ISSUE_CERTAINTY_CHANGED = "certainty_changed"

ISSUE_WRONG_TARGET_LANGUAGE = "wrong_target_language"

ISSUE_PROVIDER_UNAVAILABLE = "provider_unavailable"
ISSUE_PROVIDER_FAILED = "provider_failed"
ISSUE_PROVIDER_INVALID_RESPONSE = "provider_invalid_response"


# =========================================================
# MODE
# =========================================================

QUALITY_MODE_DETERMINISTIC = "deterministic"
QUALITY_MODE_SEMANTIC = "semantic"


# =========================================================
# MODELS
# =========================================================

@dataclass(frozen=True)
class TranslationQualityIssue:
    code: str
    severity: str
    message: str
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class TranslationQualityResult:
    passed: bool

    status: str

    score: Optional[float]

    source_language: str
    target_language: str

    issues: Tuple[
        TranslationQualityIssue,
        ...
    ] = ()

    warnings: Tuple[str, ...] = ()

    grammar_ok: Optional[bool] = None
    fluency_ok: Optional[bool] = None
    word_choice_ok: Optional[bool] = None
    style_ok: Optional[bool] = None

    factual_fidelity_ok: Optional[bool] = None
    certainty_preserved: Optional[bool] = None
    attribution_preserved: Optional[bool] = None
    target_language_ok: Optional[bool] = None

    checked_by: Tuple[str, ...] = ()

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# REGEX
# =========================================================

_URL_RE = re.compile(
    r"https?://[^\s<>\]\[(){}]+",
    flags=re.IGNORECASE,
)

_MENTION_RE = re.compile(
    r"(?<![\w@])@[A-Za-z0-9_]{2,}"
)

_HASHTAG_RE = re.compile(
    r"(?<![\w#])#[^\s#]+"
)

_NUMBER_RE = re.compile(
    r"""
    (?<!\w)
    [+\-]?
    (?:
        [0-9۰-۹٠-٩]+
        (?:
            [.,٫٬:/\-]
            [0-9۰-۹٠-٩]+
        )*
    )
    (?!\w)
    """,
    flags=re.VERBOSE,
)

_WHITESPACE_RE = re.compile(
    r"[ \t]+"
)


# =========================================================
# NORMALIZATION
# =========================================================

_DIGIT_TRANSLATION = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",

        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",

        "٫": ".",
        "٬": ",",
    }
)


def _normalize_text(
    text: Optional[str],
) -> str:

    value = str(
        text
        or ""
    )

    value = value.replace(
        "\r\n",
        "\n"
    )

    value = value.replace(
        "\r",
        "\n"
    )

    value = _WHITESPACE_RE.sub(
        " ",
        value
    )

    return value.strip()


def _normalize_number(
    value: str,
) -> str:

    normalized = str(
        value
        or ""
    ).translate(
        _DIGIT_TRANSLATION
    )

    normalized = normalized.replace(
        ",",
        ""
    )

    return normalized.strip()


def _normalized_language(
    language: Optional[str],
) -> str:

    return (
        str(
            language
            or "auto"
        )
        .strip()
        .lower()
        .replace(
            "_",
            "-"
        )
    )


# =========================================================
# EXTRACTION
# =========================================================

def _extract_urls(
    text: str,
) -> Tuple[str, ...]:

    return tuple(
        _URL_RE.findall(
            text
        )
    )


def _extract_mentions(
    text: str,
) -> Tuple[str, ...]:

    return tuple(
        _MENTION_RE.findall(
            text
        )
    )


def _extract_hashtags(
    text: str,
) -> Tuple[str, ...]:

    return tuple(
        _HASHTAG_RE.findall(
            text
        )
    )


def _extract_numbers(
    text: str,
) -> Tuple[str, ...]:

    return tuple(
        _normalize_number(
            item
        )
        for item
        in _NUMBER_RE.findall(
            text
        )
    )


# =========================================================
# ISSUE HELPERS
# =========================================================

def _issue(
    code: str,
    severity: str,
    message: str,
    **metadata: Any,
) -> TranslationQualityIssue:

    return TranslationQualityIssue(
        code=code,
        severity=severity,
        message=message,
        metadata=dict(
            metadata
        ),
    )


def _has_error(
    issues: List[
        TranslationQualityIssue
    ],
) -> bool:

    return any(
        item.severity
        == SEVERITY_ERROR
        for item in issues
    )


# =========================================================
# STRUCTURE
# =========================================================

def _paragraph_count(
    text: str,
) -> int:

    return len(
        [
            part
            for part
            in re.split(
                r"\n\s*\n",
                text,
            )
            if part.strip()
        ]
    )


def _structure_collapsed(
    source: str,
    translated: str,
) -> bool:

    source_paragraphs = (
        _paragraph_count(
            source
        )
    )

    translated_paragraphs = (
        _paragraph_count(
            translated
        )
    )

    if source_paragraphs < 3:
        return False

    if translated_paragraphs == 1:
        return True

    if (
        source_paragraphs >= 5
        and translated_paragraphs
        < max(
            2,
            source_paragraphs // 3,
        )
    ):
        return True

    return False


# =========================================================
# DETERMINISTIC CHECK
# =========================================================

def deterministic_quality_check(
    *,
    source_text: str,
    translated_text: str,
    source_language: str = "auto",
    target_language: str,
) -> TranslationQualityResult:
    """
    Fast deterministic validation.

    This does not attempt to decide grammatical correctness
    across all human languages.

    It verifies objective invariants that can be checked
    safely without an LLM/provider.
    """

    source = _normalize_text(
        source_text
    )

    translated = _normalize_text(
        translated_text
    )

    source_language = (
        _normalized_language(
            source_language
        )
    )

    target_language = (
        _normalized_language(
            target_language
        )
    )

    issues: List[
        TranslationQualityIssue
    ] = []

    warnings: List[str] = []

    # =====================================================
    # EMPTY
    # =====================================================

    if not source:

        issues.append(
            _issue(
                ISSUE_EMPTY_SOURCE,
                SEVERITY_ERROR,
                "Source text is empty.",
            )
        )

    if not translated:

        issues.append(
            _issue(
                ISSUE_EMPTY_TRANSLATION,
                SEVERITY_ERROR,
                "Translated text is empty.",
            )
        )

    if _has_error(
        issues
    ):

        return TranslationQualityResult(
            passed=False,
            status=QUALITY_FAIL,
            score=0.0,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            issues=tuple(
                issues
            ),
            warnings=tuple(
                warnings
            ),
            checked_by=(
                QUALITY_MODE_DETERMINISTIC,
            ),
        )

    # =====================================================
    # IDENTICAL TEXT
    # =====================================================

    if (
        source_language
        not in {
            "auto",
            "unknown",
            "mixed",
        }
        and target_language
        not in {
            "auto",
            "source",
            "unknown",
        }
        and source_language
        != target_language
        and source == translated
    ):

        issues.append(
            _issue(
                ISSUE_IDENTICAL_TEXT,
                SEVERITY_ERROR,
                (
                    "Translation is identical to source "
                    "despite different source and target "
                    "languages."
                ),
            )
        )

    # =====================================================
    # NUMBERS
    # =====================================================

    source_numbers = (
        _extract_numbers(
            source
        )
    )

    translated_numbers = (
        _extract_numbers(
            translated
        )
    )

    if (
        sorted(
            source_numbers
        )
        != sorted(
            translated_numbers
        )
    ):

        issues.append(
            _issue(
                ISSUE_NUMBER_CHANGED,
                SEVERITY_ERROR,
                (
                    "One or more numeric values were added, "
                    "removed or changed."
                ),
                source_numbers=list(
                    source_numbers
                ),
                translated_numbers=list(
                    translated_numbers
                ),
            )
        )

    # =====================================================
    # URL
    # =====================================================

    source_urls = (
        _extract_urls(
            source
        )
    )

    translated_urls = (
        _extract_urls(
            translated
        )
    )

    if (
        sorted(
            source_urls
        )
        != sorted(
            translated_urls
        )
    ):

        issues.append(
            _issue(
                ISSUE_URL_CHANGED,
                SEVERITY_ERROR,
                (
                    "One or more URLs were added, removed "
                    "or changed."
                ),
                source_urls=list(
                    source_urls
                ),
                translated_urls=list(
                    translated_urls
                ),
            )
        )

    # =====================================================
    # MENTION
    # =====================================================

    source_mentions = (
        _extract_mentions(
            source
        )
    )

    translated_mentions = (
        _extract_mentions(
            translated
        )
    )

    if (
        sorted(
            source_mentions
        )
        != sorted(
            translated_mentions
        )
    ):

        issues.append(
            _issue(
                ISSUE_MENTION_CHANGED,
                SEVERITY_ERROR,
                (
                    "One or more mentions were added, "
                    "removed or changed."
                ),
                source_mentions=list(
                    source_mentions
                ),
                translated_mentions=list(
                    translated_mentions
                ),
            )
        )

    # =====================================================
    # HASHTAG
    # =====================================================

    source_hashtags = (
        _extract_hashtags(
            source
        )
    )

    translated_hashtags = (
        _extract_hashtags(
            translated
        )
    )

    if (
        sorted(
            source_hashtags
        )
        != sorted(
            translated_hashtags
        )
    ):

        issues.append(
            _issue(
                ISSUE_HASHTAG_CHANGED,
                SEVERITY_ERROR,
                (
                    "One or more hashtags were added, "
                    "removed or changed."
                ),
                source_hashtags=list(
                    source_hashtags
                ),
                translated_hashtags=list(
                    translated_hashtags
                ),
            )
        )

    # =====================================================
    # STRUCTURE
    # =====================================================

    if _structure_collapsed(
        source,
        translated,
    ):

        issues.append(
            _issue(
                ISSUE_STRUCTURE_COLLAPSED,
                SEVERITY_WARNING,
                (
                    "Translation appears to have collapsed "
                    "the source paragraph structure."
                ),
            )
        )

        warnings.append(
            "Paragraph structure may not have been preserved."
        )

    # =====================================================
    # RESULT
    # =====================================================

    failed = _has_error(
        issues
    )

    warning_present = any(
        item.severity
        == SEVERITY_WARNING
        for item in issues
    )

    if failed:
        status = QUALITY_FAIL
        score = 0.0

    elif warning_present:
        status = QUALITY_WARNING
        score = 0.85

    else:
        status = QUALITY_PASS
        score = 1.0

    return TranslationQualityResult(
        passed=not failed,
        status=status,
        score=score,
        source_language=source_language,
        target_language=target_language,
        issues=tuple(
            issues
        ),
        warnings=tuple(
            warnings
        ),
        checked_by=(
            QUALITY_MODE_DETERMINISTIC,
        ),
        metadata={
            "source_length":
                len(
                    source
                ),

            "translated_length":
                len(
                    translated
                ),

            "source_paragraphs":
                _paragraph_count(
                    source
                ),

            "translated_paragraphs":
                _paragraph_count(
                    translated
                ),
        },
    )


# =========================================================
# SEMANTIC QUALITY PROMPT
# =========================================================

def build_quality_instruction(
    *,
    source_language: str,
    target_language: str,
) -> str:
    """
    Build a language-agnostic newsroom quality instruction.

    The reviewer must evaluate according to the grammar,
    idiom and conventions of TARGET_LANGUAGE rather than
    applying English-specific rules.
    """

    source_language = (
        _normalized_language(
            source_language
        )
    )

    target_language = (
        _normalized_language(
            target_language
        )
    )

    return f"""
You are a multilingual translation quality reviewer.

SOURCE LANGUAGE:
{source_language}

TARGET LANGUAGE:
{target_language}

Evaluate the translation according to the natural grammar,
syntax, vocabulary, idiom and professional media/newsroom
writing conventions of the TARGET LANGUAGE.

Do NOT evaluate the translation using English-specific rules
unless the target language itself is English.

The translated text must be natural for a fluent native
speaker of the target language while remaining faithful to
the source.

Check all of the following:

1. GRAMMAR
The translation must be grammatically correct according to
the target language.

2. NATURAL SENTENCE STRUCTURE
Sentence order and syntax may differ from the source when
necessary for natural target-language writing.
Literal word-for-word translation is NOT required.

3. WORD CHOICE
Vocabulary must be natural, precise and contextually
appropriate in the target language.

4. MEDIA STYLE
For news/editorial content, the language should read like
professional media prose in the target language, without
changing the source meaning.

5. FACTUAL FIDELITY
No fact may be invented, removed, exaggerated, weakened or
changed.

6. NAMES
People, organizations and geographic names must remain
correct. Transliteration may follow normal conventions of
the target language.

7. NUMBERS AND DATES
Numbers, quantities, percentages, dates and times must retain
their original meaning.

8. ATTRIBUTION
Who said, claimed, reported, denied, confirmed or predicted
something must remain unchanged.

9. CERTAINTY AND MODALITY
Meaning such as:
possible / probable / alleged / expected / may / might /
will / confirmed / denied
must remain at the same level of certainty.

10. QUOTATIONS
Quoted claims must preserve meaning and speaker attribution.

11. COMPLETENESS
Important source information must not disappear.

12. NO INVENTION
The translation must contain no unsupported information.

13. TARGET LANGUAGE
The output must actually be written in the requested target
language, except names, quotations, URLs, hashtags or terms
that appropriately remain unchanged.

Return ONLY a JSON object.

Required JSON schema:

{{
  "passed": true,
  "score": 0.0,
  "grammar_ok": true,
  "fluency_ok": true,
  "word_choice_ok": true,
  "style_ok": true,
  "factual_fidelity_ok": true,
  "certainty_preserved": true,
  "attribution_preserved": true,
  "target_language_ok": true,
  "issues": [
    {{
      "code": "issue_code",
      "severity": "error",
      "message": "brief explanation"
    }}
  ]
}}

score must be between 0 and 1.

passed must be false if there is a factual change,
fabrication, omission of important information, wrong
attribution, changed certainty, wrong target language, or a
serious grammatical problem.

Do not rewrite the translation.
Do not return an improved version.
Do not summarize either text.
""".strip()


# =========================================================
# PROVIDER CALL
# =========================================================

def _call_quality_provider(
    provider: QualityProvider,
    *,
    source_text: str,
    translated_text: str,
    source_language: str,
    target_language: str,
    instruction: str,
) -> str:
    """
    Support several provider adapter signatures without
    coupling this module to one LLM implementation.
    """

    combined_text = (
        "SOURCE TEXT:\n"
        "<<<SOURCE>>>\n"
        f"{source_text}\n"
        "<<<END SOURCE>>>\n\n"
        "TRANSLATED TEXT:\n"
        "<<<TRANSLATION>>>\n"
        f"{translated_text}\n"
        "<<<END TRANSLATION>>>"
    )

    attempts = (
        lambda: provider(
            text=combined_text,
            instruction=instruction,
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
        ),

        lambda: provider(
            combined_text,
            instruction,
            source_language,
            target_language,
        ),

        lambda: provider(
            text=combined_text,
            instruction=instruction,
        ),

        lambda: provider(
            combined_text,
            instruction,
        ),
    )

    last_type_error: Optional[
        TypeError
    ] = None

    for attempt in attempts:

        try:
            value = attempt()

            return str(
                value
                or ""
            ).strip()

        except TypeError as exc:
            last_type_error = exc
            continue

    if last_type_error:
        raise last_type_error

    raise RuntimeError(
        "Quality provider could not be called."
    )


# =========================================================
# JSON PARSING
# =========================================================

def _strip_json_fence(
    value: str,
) -> str:

    text = str(
        value
        or ""
    ).strip()

    if text.startswith(
        "```"
    ):

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    return text.strip()


def _parse_provider_response(
    raw: str,
) -> Dict[str, Any]:

    cleaned = _strip_json_fence(
        raw
    )

    if not cleaned:
        raise ValueError(
            "Empty quality provider response."
        )

    try:
        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        start = cleaned.find(
            "{"
        )

        end = cleaned.rfind(
            "}"
        )

        if (
            start < 0
            or end < 0
            or end <= start
        ):
            raise ValueError(
                "Quality provider response is not valid JSON."
            )

        parsed = json.loads(
            cleaned[
                start:end + 1
            ]
        )

    if not isinstance(
        parsed,
        dict,
    ):
        raise ValueError(
            "Quality provider response must be an object."
        )

    return parsed


# =========================================================
# COERCION
# =========================================================

def _bool_or_none(
    value: Any,
) -> Optional[bool]:

    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):

        lowered = (
            value
            .strip()
            .lower()
        )

        if lowered in {
            "true",
            "yes",
            "1",
        }:
            return True

        if lowered in {
            "false",
            "no",
            "0",
        }:
            return False

    return None


def _score_or_none(
    value: Any,
) -> Optional[float]:

    try:
        score = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return max(
        0.0,
        min(
            1.0,
            score,
        ),
    )


# =========================================================
# PROVIDER ISSUES
# =========================================================

def _provider_issues(
    value: Any,
) -> List[
    TranslationQualityIssue
]:

    if not isinstance(
        value,
        list,
    ):
        return []

    result: List[
        TranslationQualityIssue
    ] = []

    for item in value:

        if not isinstance(
            item,
            dict,
        ):
            continue

        code = str(
            item.get(
                "code",
                ""
            )
            or "semantic_quality_issue"
        ).strip()

        severity = str(
            item.get(
                "severity",
                SEVERITY_ERROR
            )
            or SEVERITY_ERROR
        ).strip().lower()

        if severity not in {
            SEVERITY_INFO,
            SEVERITY_WARNING,
            SEVERITY_ERROR,
        }:
            severity = SEVERITY_ERROR

        message = str(
            item.get(
                "message",
                ""
            )
            or code
        ).strip()

        result.append(
            _issue(
                code,
                severity,
                message,
            )
        )

    return result


# =========================================================
# SEMANTIC CHECK
# =========================================================

def semantic_quality_check(
    *,
    source_text: str,
    translated_text: str,
    target_language: str,
    provider: Optional[
        QualityProvider
    ],
    source_language: str = "auto",
) -> TranslationQualityResult:
    """
    Run multilingual semantic and linguistic validation.

    This does NOT rewrite the translation.
    """

    deterministic = (
        deterministic_quality_check(
            source_text=source_text,
            translated_text=(
                translated_text
            ),
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
        )
    )

    if not deterministic.passed:

        return deterministic

    if provider is None:

        issue = _issue(
            ISSUE_PROVIDER_UNAVAILABLE,
            SEVERITY_WARNING,
            (
                "Semantic translation quality provider "
                "is not configured."
            ),
        )

        return TranslationQualityResult(
            passed=(
                deterministic.passed
            ),
            status=QUALITY_UNVERIFIED,
            score=(
                deterministic.score
            ),
            source_language=(
                deterministic
                .source_language
            ),
            target_language=(
                deterministic
                .target_language
            ),
            issues=(
                *deterministic.issues,
                issue,
            ),
            warnings=(
                *deterministic.warnings,
                (
                    "Semantic language quality could not "
                    "be verified."
                ),
            ),
            checked_by=(
                *deterministic.checked_by,
            ),
            metadata={
                **(
                    deterministic.metadata
                    or {}
                ),
                "semantic_verified":
                    False,
            },
        )

    instruction = (
        build_quality_instruction(
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
        )
    )

    try:

        raw = _call_quality_provider(
            provider,
            source_text=source_text,
            translated_text=(
                translated_text
            ),
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
            instruction=instruction,
        )

        parsed = (
            _parse_provider_response(
                raw
            )
        )

    except Exception as exc:

        logger.exception(
            "Translation semantic quality check failed."
        )

        issue = _issue(
            ISSUE_PROVIDER_FAILED,
            SEVERITY_ERROR,
            (
                "Semantic translation quality validation "
                "failed."
            ),
            error_type=(
                type(exc).__name__
            ),
        )

        return TranslationQualityResult(
            passed=False,
            status=QUALITY_FAIL,
            score=0.0,
            source_language=(
                deterministic
                .source_language
            ),
            target_language=(
                deterministic
                .target_language
            ),
            issues=(
                *deterministic.issues,
                issue,
            ),
            warnings=(
                deterministic.warnings
            ),
            checked_by=(
                *deterministic.checked_by,
                QUALITY_MODE_SEMANTIC,
            ),
            metadata={
                **(
                    deterministic.metadata
                    or {}
                ),
                "semantic_verified":
                    False,
            },
        )

    provider_passed = (
        _bool_or_none(
            parsed.get(
                "passed"
            )
        )
    )

    score = _score_or_none(
        parsed.get(
            "score"
        )
    )

    grammar_ok = _bool_or_none(
        parsed.get(
            "grammar_ok"
        )
    )

    fluency_ok = _bool_or_none(
        parsed.get(
            "fluency_ok"
        )
    )

    word_choice_ok = (
        _bool_or_none(
            parsed.get(
                "word_choice_ok"
            )
        )
    )

    style_ok = _bool_or_none(
        parsed.get(
            "style_ok"
        )
    )

    factual_fidelity_ok = (
        _bool_or_none(
            parsed.get(
                "factual_fidelity_ok"
            )
        )
    )

    certainty_preserved = (
        _bool_or_none(
            parsed.get(
                "certainty_preserved"
            )
        )
    )

    attribution_preserved = (
        _bool_or_none(
            parsed.get(
                "attribution_preserved"
            )
        )
    )

    target_language_ok = (
        _bool_or_none(
            parsed.get(
                "target_language_ok"
            )
        )
    )

    semantic_issues = (
        _provider_issues(
            parsed.get(
                "issues"
            )
        )
    )

    issues = [
        *deterministic.issues,
        *semantic_issues,
    ]

    # =====================================================
    # REQUIRED FIELDS
    # =====================================================

    required_flags = {
        "passed":
            provider_passed,

        "grammar_ok":
            grammar_ok,

        "fluency_ok":
            fluency_ok,

        "word_choice_ok":
            word_choice_ok,

        "style_ok":
            style_ok,

        "factual_fidelity_ok":
            factual_fidelity_ok,

        "certainty_preserved":
            certainty_preserved,

        "attribution_preserved":
            attribution_preserved,

        "target_language_ok":
            target_language_ok,
    }

    missing_flags = [
        key
        for key, value
        in required_flags.items()
        if value is None
    ]

    if missing_flags:

        issues.append(
            _issue(
                ISSUE_PROVIDER_INVALID_RESPONSE,
                SEVERITY_ERROR,
                (
                    "Quality provider response omitted "
                    "required validation fields."
                ),
                missing_fields=(
                    missing_flags
                ),
            )
        )

    # =====================================================
    # FAIL-CLOSED QUALITY RULES
    # =====================================================

    critical_values = (
        grammar_ok,
        factual_fidelity_ok,
        certainty_preserved,
        attribution_preserved,
        target_language_ok,
    )

    critical_failure = any(
        value is False
        for value in critical_values
    )

    linguistic_failure = (
        fluency_ok is False
        or word_choice_ok is False
    )

    explicit_error = _has_error(
        issues
    )

    passed = bool(
        provider_passed is True
        and not critical_failure
        and not linguistic_failure
        and not explicit_error
    )

    if score is None:

        if passed:
            score = 1.0
        else:
            score = 0.0

    if passed:
        status = QUALITY_PASS

    elif (
        not explicit_error
        and not critical_failure
        and not linguistic_failure
    ):
        status = QUALITY_WARNING

    else:
        status = QUALITY_FAIL

    return TranslationQualityResult(
        passed=passed,
        status=status,
        score=score,
        source_language=(
            deterministic
            .source_language
        ),
        target_language=(
            deterministic
            .target_language
        ),
        issues=tuple(
            issues
        ),
        warnings=(
            deterministic
            .warnings
        ),
        grammar_ok=grammar_ok,
        fluency_ok=fluency_ok,
        word_choice_ok=(
            word_choice_ok
        ),
        style_ok=style_ok,
        factual_fidelity_ok=(
            factual_fidelity_ok
        ),
        certainty_preserved=(
            certainty_preserved
        ),
        attribution_preserved=(
            attribution_preserved
        ),
        target_language_ok=(
            target_language_ok
        ),
        checked_by=(
            *deterministic.checked_by,
            QUALITY_MODE_SEMANTIC,
        ),
        metadata={
            **(
                deterministic.metadata
                or {}
            ),
            "semantic_verified":
                True,
        },
    )


# =========================================================
# SHARED QUALITY CHECK
# =========================================================

def check_translation_quality(
    *,
    source_text: str,
    translated_text: str,
    target_language: str,
    source_language: str = "auto",
    provider: Optional[
        QualityProvider
    ] = None,
    semantic_check: bool = True,
) -> TranslationQualityResult:
    """
    Main public API.

    semantic_check=False:
        deterministic validation only

    semantic_check=True:
        deterministic + multilingual semantic review
    """

    if not semantic_check:

        return deterministic_quality_check(
            source_text=source_text,
            translated_text=(
                translated_text
            ),
            source_language=(
                source_language
            ),
            target_language=(
                target_language
            ),
        )

    return semantic_quality_check(
        source_text=source_text,
        translated_text=(
            translated_text
        ),
        source_language=(
            source_language
        ),
        target_language=(
            target_language
        ),
        provider=provider,
    )


# =========================================================
# RETRY DECISION
# =========================================================

_RETRYABLE_ISSUES = {
    ISSUE_GRAMMAR,
    ISSUE_WORD_CHOICE,
    ISSUE_UNNATURAL_LANGUAGE,
    ISSUE_STYLE,

    ISSUE_FACT_CHANGED,
    ISSUE_FACT_ADDED,
    ISSUE_FACT_OMITTED,
    ISSUE_NAME_CHANGED,
    ISSUE_DATE_CHANGED,
    ISSUE_QUOTE_CHANGED,
    ISSUE_ATTRIBUTION_CHANGED,
    ISSUE_CERTAINTY_CHANGED,

    ISSUE_WRONG_TARGET_LANGUAGE,
}


def translation_quality_should_retry(
    result: TranslationQualityResult,
) -> bool:
    """
    Decide whether generating a fresh translation may safely
    fix the quality problem.

    Provider/infrastructure failures are intentionally not
    classified here as translation-quality retries.
    """

    if result.passed:
        return False

    codes = {
        item.code
        for item in result.issues
    }

    if codes.intersection(
        _RETRYABLE_ISSUES
    ):
        return True

    if (
        result.grammar_ok is False
        or result.fluency_ok is False
        or result.word_choice_ok is False
        or result.style_ok is False
        or result.factual_fidelity_ok is False
        or result.certainty_preserved is False
        or result.attribution_preserved is False
        or result.target_language_ok is False
    ):
        return True

    return False


# =========================================================
# RETRY INSTRUCTION
# =========================================================

def build_translation_retry_instruction(
    *,
    result: TranslationQualityResult,
    target_language: str,
) -> str:
    """
    Build a compact instruction for Translation Service when
    a candidate fails the quality check.

    The original source text must still be used for the next
    translation attempt.
    """

    target_language = (
        _normalized_language(
            target_language
        )
    )

    issue_codes = [
        item.code
        for item in result.issues
        if item.severity
        in {
            SEVERITY_ERROR,
            SEVERITY_WARNING,
        }
    ]

    issue_text = (
        ", ".join(
            issue_codes
        )
        if issue_codes
        else "general_language_quality"
    )

    return (
        "Generate a fresh translation from the ORIGINAL "
        "source text. "
        f"Target language: {target_language}. "
        "Correct the previous quality problems: "
        f"{issue_text}. "
        "Use natural grammar, sentence structure and "
        "vocabulary of the target language. "
        "Do not translate word-for-word when that produces "
        "unnatural language. "
        "Preserve every fact, person, organization, place, "
        "number, date, quotation, attribution and degree of "
        "certainty exactly in meaning. "
        "Do not add, remove, summarize, expand or rewrite "
        "the underlying information."
    )


# =========================================================
# RESULT HELPERS
# =========================================================

def quality_has_issue(
    result: TranslationQualityResult,
    code: str,
) -> bool:

    return any(
        item.code == code
        for item in result.issues
    )


def quality_error_codes(
    result: TranslationQualityResult,
) -> Tuple[str, ...]:

    return tuple(
        item.code
        for item in result.issues
        if item.severity
        == SEVERITY_ERROR
    )


def quality_warning_codes(
    result: TranslationQualityResult,
) -> Tuple[str, ...]:

    return tuple(
        item.code
        for item in result.issues
        if item.severity
        == SEVERITY_WARNING
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def describe_translation_quality(
    result: TranslationQualityResult,
) -> Dict[str, Any]:
    """
    Safe diagnostics.

    Source and translated content are intentionally excluded.
    """

    return {
        "passed":
            result.passed,

        "status":
            result.status,

        "score":
            result.score,

        "source_language":
            result.source_language,

        "target_language":
            result.target_language,

        "grammar_ok":
            result.grammar_ok,

        "fluency_ok":
            result.fluency_ok,

        "word_choice_ok":
            result.word_choice_ok,

        "style_ok":
            result.style_ok,

        "factual_fidelity_ok":
            result.factual_fidelity_ok,

        "certainty_preserved":
            result.certainty_preserved,

        "attribution_preserved":
            result.attribution_preserved,

        "target_language_ok":
            result.target_language_ok,

        "checked_by":
            list(
                result.checked_by
            ),

        "issues": [
            {
                "code":
                    item.code,

                "severity":
                    item.severity,

                "message":
                    item.message,

                "metadata":
                    dict(
                        item.metadata
                        or {}
                    ),
            }
            for item in result.issues
        ],

        "warnings":
            list(
                result.warnings
            ),

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }
