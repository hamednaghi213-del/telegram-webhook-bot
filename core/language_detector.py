from __future__ import annotations

import logging
import re
import unicodedata

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# LANGUAGE DETECTOR
# =========================================================
#
# Shared lightweight language detection layer.
#
# Responsibilities:
#
# Incoming Content
#       ↓
# Language Detection
#       ↓
# Translation Policy
#       ↓
# Translation Service
#
# IMPORTANT:
#
# - This module does NOT translate content.
# - This module does NOT publish content.
# - This module does NOT modify Workspace/Legacy settings.
# - This module does NOT write to the database.
# - This module does NOT call Telegram/Bale.
#
# The detector is deliberately language-agnostic.
#
# It uses deterministic Unicode/script analysis first.
# When exact language cannot be identified safely from script
# alone, it returns a conservative result instead of guessing.
#
# A model/provider based detector can later be added behind
# the same API without changing callers.
# =========================================================


# =========================================================
# LANGUAGE CONSTANTS
# =========================================================

LANGUAGE_AUTO = "auto"
LANGUAGE_UNKNOWN = "unknown"
LANGUAGE_MIXED = "mixed"


# =========================================================
# SCRIPT CONSTANTS
# =========================================================

SCRIPT_ARABIC = "arabic"
SCRIPT_LATIN = "latin"
SCRIPT_CYRILLIC = "cyrillic"
SCRIPT_HAN = "han"
SCRIPT_HIRAGANA = "hiragana"
SCRIPT_KATAKANA = "katakana"
SCRIPT_HANGUL = "hangul"
SCRIPT_DEVANAGARI = "devanagari"
SCRIPT_HEBREW = "hebrew"
SCRIPT_GREEK = "greek"
SCRIPT_THAI = "thai"
SCRIPT_GEORGIAN = "georgian"
SCRIPT_ARMENIAN = "armenian"
SCRIPT_UNKNOWN = "unknown"


# =========================================================
# CONFIDENCE LEVELS
# =========================================================

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class LanguageDetectionResult:
    language: str

    confidence: float

    confidence_level: str

    script: str

    reliable: bool

    is_mixed: bool = False

    alternatives: Tuple[str, ...] = ()

    detected_by: str = "unicode"

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# TEXT CLEANUP
# =========================================================

_URL_RE = re.compile(
    r"https?://\S+|www\.\S+",
    flags=re.IGNORECASE,
)

_MENTION_RE = re.compile(
    r"(?<!\w)@[A-Za-z0-9_]{2,}",
)

_HASHTAG_RE = re.compile(
    r"(?<!\w)#[^\s#]+",
)

_NUMBER_RE = re.compile(
    r"[0-9۰-۹٠-٩]+(?:[.,٫٬:/\-][0-9۰-۹٠-٩]+)*"
)

_WHITESPACE_RE = re.compile(
    r"\s+"
)


def _clean_text_for_detection(
    text: Optional[str],
) -> str:
    """
    Remove content that should not influence language
    detection significantly.

    URLs, mentions, hashtags and standalone numeric material
    are ignored for primary language identification.
    """

    value = str(
        text
        or ""
    )

    if not value.strip():
        return ""

    value = _URL_RE.sub(
        " ",
        value,
    )

    value = _MENTION_RE.sub(
        " ",
        value,
    )

    value = _HASHTAG_RE.sub(
        " ",
        value,
    )

    value = _NUMBER_RE.sub(
        " ",
        value,
    )

    value = _WHITESPACE_RE.sub(
        " ",
        value,
    )

    return value.strip()


# =========================================================
# UNICODE SCRIPT DETECTION
# =========================================================

def _char_script(
    char: str,
) -> Optional[str]:

    if not char:
        return None

    code = ord(char)

    # Arabic / Persian / Urdu etc.
    if (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0x08A0 <= code <= 0x08FF
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    ):
        return SCRIPT_ARABIC

    # Latin
    if (
        0x0041 <= code <= 0x005A
        or 0x0061 <= code <= 0x007A
        or 0x00C0 <= code <= 0x024F
        or 0x1E00 <= code <= 0x1EFF
    ):
        return SCRIPT_LATIN

    # Cyrillic
    if (
        0x0400 <= code <= 0x052F
        or 0x2DE0 <= code <= 0x2DFF
        or 0xA640 <= code <= 0xA69F
    ):
        return SCRIPT_CYRILLIC

    # Han / Chinese ideographs
    if (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
    ):
        return SCRIPT_HAN

    # Japanese
    if 0x3040 <= code <= 0x309F:
        return SCRIPT_HIRAGANA

    if 0x30A0 <= code <= 0x30FF:
        return SCRIPT_KATAKANA

    # Korean
    if (
        0x1100 <= code <= 0x11FF
        or 0x3130 <= code <= 0x318F
        or 0xAC00 <= code <= 0xD7AF
    ):
        return SCRIPT_HANGUL

    # Hindi / Devanagari family
    if 0x0900 <= code <= 0x097F:
        return SCRIPT_DEVANAGARI

    # Hebrew
    if 0x0590 <= code <= 0x05FF:
        return SCRIPT_HEBREW

    # Greek
    if (
        0x0370 <= code <= 0x03FF
        or 0x1F00 <= code <= 0x1FFF
    ):
        return SCRIPT_GREEK

    # Thai
    if 0x0E00 <= code <= 0x0E7F:
        return SCRIPT_THAI

    # Georgian
    if (
        0x10A0 <= code <= 0x10FF
        or 0x2D00 <= code <= 0x2D2F
    ):
        return SCRIPT_GEORGIAN

    # Armenian
    if 0x0530 <= code <= 0x058F:
        return SCRIPT_ARMENIAN

    return None


def _script_counts(
    text: str,
) -> Dict[str, int]:

    counts: Dict[str, int] = {}

    for char in text:

        if (
            char.isspace()
            or char.isdigit()
        ):
            continue

        category = unicodedata.category(
            char
        )

        if not category.startswith(
            ("L", "M")
        ):
            continue

        script = _char_script(
            char
        )

        if not script:
            continue

        counts[script] = (
            counts.get(
                script,
                0
            )
            + 1
        )

    return counts


def _dominant_script(
    counts: Dict[str, int],
) -> Tuple[
    str,
    float,
    bool,
]:
    """
    Return:
        script
        dominance ratio
        mixed
    """

    if not counts:
        return (
            SCRIPT_UNKNOWN,
            0.0,
            False,
        )

    total = sum(
        counts.values()
    )

    ranked = sorted(
        counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    script, amount = ranked[0]

    ratio = (
        amount / total
        if total
        else 0.0
    )

    meaningful_scripts = [
        value
        for value
        in counts.values()
        if (
            value / total
            >= 0.15
        )
    ]

    mixed = (
        len(
            meaningful_scripts
        )
        > 1
    )

    return (
        script,
        ratio,
        mixed,
    )


# =========================================================
# ARABIC-SCRIPT LANGUAGE DETECTION
# =========================================================

# Characters strongly associated with Persian.
_PERSIAN_SPECIFIC = set(
    "پچژگ"
)

# Urdu-specific / highly indicative letters.
_URDU_SPECIFIC = set(
    "ٹڈڑںھہےۓ"
)

# Arabic-specific characters / forms that are strong
# indicators when they occur repeatedly.
_ARABIC_INDICATIVE = set(
    "ةثذظضصط"
)

# Persian common words.
_PERSIAN_WORDS = {
    "است",
    "این",
    "آن",
    "که",
    "را",
    "برای",
    "با",
    "از",
    "به",
    "در",
    "یک",
    "می",
    "شود",
    "کرد",
    "گفت",
    "خواهد",
    "اما",
    "نیز",
    "بر",
    "خود",
    "کشور",
    "دولت",
    "خبر",
    "گزارش",
}

# Arabic common words.
_ARABIC_WORDS = {
    "في",
    "من",
    "إلى",
    "على",
    "أن",
    "إن",
    "هذا",
    "هذه",
    "التي",
    "الذي",
    "كان",
    "كانت",
    "مع",
    "عن",
    "بعد",
    "قبل",
    "وقد",
    "قال",
    "وقال",
    "هناك",
    "بين",
    "دولة",
    "الحكومة",
}

# Urdu common words.
_URDU_WORDS = {
    "ہے",
    "ہیں",
    "اور",
    "میں",
    "سے",
    "کے",
    "کی",
    "کو",
    "یہ",
    "وہ",
    "پر",
    "نے",
    "تھا",
    "تھی",
    "کہ",
    "ایک",
}


def _words(
    text: str,
) -> List[str]:

    return [
        word.strip(
            ".,!?؟،؛:()[]{}«»\"'"
        )
        for word in text.split()
        if word.strip()
    ]


def _detect_arabic_script_language(
    text: str,
) -> LanguageDetectionResult:

    words = _words(
        text
    )

    word_set = set(
        words
    )

    persian_chars = sum(
        1
        for char in text
        if char in _PERSIAN_SPECIFIC
    )

    urdu_chars = sum(
        1
        for char in text
        if char in _URDU_SPECIFIC
    )

    arabic_chars = sum(
        1
        for char in text
        if char in _ARABIC_INDICATIVE
    )

    persian_words = sum(
        1
        for word in word_set
        if word in _PERSIAN_WORDS
    )

    arabic_words = sum(
        1
        for word in word_set
        if word in _ARABIC_WORDS
    )

    urdu_words = sum(
        1
        for word in word_set
        if word in _URDU_WORDS
    )

    persian_score = (
        persian_chars * 3
        + persian_words * 2
    )

    arabic_score = (
        arabic_chars
        + arabic_words * 2
    )

    urdu_score = (
        urdu_chars * 3
        + urdu_words * 2
    )

    scores = {
        "fa": persian_score,
        "ar": arabic_score,
        "ur": urdu_score,
    }

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    best_language, best_score = (
        ranked[0]
    )

    second_score = ranked[1][1]

    # Strong language evidence.
    if (
        best_score >= 4
        and best_score
        >= second_score + 2
    ):
        confidence = min(
            0.98,
            0.72
            + min(
                best_score,
                20
            )
            * 0.012
        )

        return LanguageDetectionResult(
            language=best_language,
            confidence=confidence,
            confidence_level=(
                CONFIDENCE_HIGH
                if confidence >= 0.85
                else CONFIDENCE_MEDIUM
            ),
            script=SCRIPT_ARABIC,
            reliable=True,
            alternatives=tuple(
                language
                for language, score
                in ranked[1:]
                if score > 0
            ),
            metadata={
                "language_scores":
                    scores,
            },
        )

    # Persian-specific characters are very useful in short
    # Persian texts.
    if persian_chars >= 2:

        return LanguageDetectionResult(
            language="fa",
            confidence=0.84,
            confidence_level=(
                CONFIDENCE_MEDIUM
            ),
            script=SCRIPT_ARABIC,
            reliable=True,
            alternatives=(
                "ar",
                "ur",
            ),
            metadata={
                "language_scores":
                    scores,
            },
        )

    if urdu_chars >= 2:

        return LanguageDetectionResult(
            language="ur",
            confidence=0.84,
            confidence_level=(
                CONFIDENCE_MEDIUM
            ),
            script=SCRIPT_ARABIC,
            reliable=True,
            alternatives=(
                "fa",
                "ar",
            ),
            metadata={
                "language_scores":
                    scores,
            },
        )

    # Arabic script alone is not enough to distinguish
    # Arabic/Persian/Urdu safely.
    return LanguageDetectionResult(
        language=LANGUAGE_UNKNOWN,
        confidence=0.45,
        confidence_level=CONFIDENCE_LOW,
        script=SCRIPT_ARABIC,
        reliable=False,
        alternatives=(
            "fa",
            "ar",
            "ur",
        ),
        metadata={
            "language_scores":
                scores,
            "reason":
                "ambiguous_arabic_script",
        },
    )


# =========================================================
# CYRILLIC DETECTION
# =========================================================

_UKRAINIAN_SPECIFIC = set(
    "іїєґІЇЄҐ"
)

_RUSSIAN_SPECIFIC = set(
    "ыэъёЫЭЪЁ"
)


def _detect_cyrillic_language(
    text: str,
) -> LanguageDetectionResult:

    ukrainian_count = sum(
        1
        for char in text
        if char in _UKRAINIAN_SPECIFIC
    )

    russian_count = sum(
        1
        for char in text
        if char in _RUSSIAN_SPECIFIC
    )

    if ukrainian_count >= 2:

        return LanguageDetectionResult(
            language="uk",
            confidence=0.90,
            confidence_level=CONFIDENCE_HIGH,
            script=SCRIPT_CYRILLIC,
            reliable=True,
            alternatives=("ru",),
            metadata={
                "ukrainian_specific":
                    ukrainian_count,
                "russian_specific":
                    russian_count,
            },
        )

    if russian_count >= 2:

        return LanguageDetectionResult(
            language="ru",
            confidence=0.88,
            confidence_level=CONFIDENCE_HIGH,
            script=SCRIPT_CYRILLIC,
            reliable=True,
            alternatives=("uk",),
            metadata={
                "ukrainian_specific":
                    ukrainian_count,
                "russian_specific":
                    russian_count,
            },
        )

    return LanguageDetectionResult(
        language=LANGUAGE_UNKNOWN,
        confidence=0.50,
        confidence_level=CONFIDENCE_LOW,
        script=SCRIPT_CYRILLIC,
        reliable=False,
        alternatives=(
            "ru",
            "uk",
        ),
        metadata={
            "reason":
                "ambiguous_cyrillic_script",
        },
    )


# =========================================================
# LATIN-SCRIPT DETECTION
# =========================================================
#
# Latin script is shared by many languages.
# We intentionally avoid pretending that script detection
# alone can reliably distinguish English/French/German/etc.
#
# Small high-signal word/character indicators are used only
# when evidence is meaningful.
# =========================================================

_LATIN_LANGUAGE_WORDS = {
    "en": {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "for",
        "was",
        "were",
        "will",
        "said",
        "have",
        "has",
        "government",
        "president",
    },

    "fr": {
        "le",
        "la",
        "les",
        "des",
        "une",
        "dans",
        "avec",
        "pour",
        "que",
        "qui",
        "est",
        "sont",
        "sur",
        "gouvernement",
    },

    "de": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "mit",
        "für",
        "von",
        "auf",
        "nicht",
        "eine",
        "einer",
        "regierung",
    },

    "es": {
        "el",
        "la",
        "los",
        "las",
        "una",
        "que",
        "con",
        "para",
        "por",
        "del",
        "está",
        "gobierno",
    },

    "it": {
        "il",
        "lo",
        "la",
        "gli",
        "una",
        "che",
        "con",
        "per",
        "del",
        "della",
        "governo",
    },

    "pt": {
        "o",
        "a",
        "os",
        "as",
        "uma",
        "que",
        "com",
        "para",
        "por",
        "do",
        "da",
        "governo",
    },

    "tr": {
        "ve",
        "bir",
        "bu",
        "ile",
        "için",
        "olan",
        "olarak",
        "de",
        "da",
        "hükümet",
    },

    "id": {
        "dan",
        "yang",
        "ini",
        "itu",
        "dengan",
        "untuk",
        "dari",
        "pada",
        "pemerintah",
    },

    "ms": {
        "dan",
        "yang",
        "ini",
        "itu",
        "dengan",
        "untuk",
        "dari",
        "pada",
        "kerajaan",
    },
}


def _detect_latin_language(
    text: str,
) -> LanguageDetectionResult:

    words = [
        word.lower()
        for word in _words(
            text
        )
    ]

    scores: Dict[str, int] = {}

    for language, markers in (
        _LATIN_LANGUAGE_WORDS.items()
    ):

        score = sum(
            1
            for word in words
            if word in markers
        )

        scores[language] = score

    # Character-specific boosts.
    lowered = text.lower()

    if any(
        char in lowered
        for char in "ğışçöü"
    ):
        scores["tr"] += 3

    if any(
        char in lowered
        for char in "ñ¿¡"
    ):
        scores["es"] += 2

    if any(
        char in lowered
        for char in "ßäöü"
    ):
        scores["de"] += 2

    if any(
        char in lowered
        for char in "àâçéèêëîïôûùüÿœ"
    ):
        scores["fr"] += 1

    if any(
        char in lowered
        for char in "ãõ"
    ):
        scores["pt"] += 2

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    best_language, best_score = (
        ranked[0]
    )

    second_score = ranked[1][1]

    if (
        best_score >= 3
        and best_score
        >= second_score + 2
    ):

        confidence = min(
            0.95,
            0.68
            + min(
                best_score,
                15
            )
            * 0.02
        )

        return LanguageDetectionResult(
            language=best_language,
            confidence=confidence,
            confidence_level=(
                CONFIDENCE_HIGH
                if confidence >= 0.85
                else CONFIDENCE_MEDIUM
            ),
            script=SCRIPT_LATIN,
            reliable=True,
            alternatives=tuple(
                language
                for language, score
                in ranked[1:4]
                if score > 0
            ),
            metadata={
                "language_scores":
                    scores,
            },
        )

    return LanguageDetectionResult(
        language=LANGUAGE_UNKNOWN,
        confidence=0.40,
        confidence_level=CONFIDENCE_LOW,
        script=SCRIPT_LATIN,
        reliable=False,
        alternatives=tuple(
            language
            for language, _
            in ranked[:5]
        ),
        metadata={
            "language_scores":
                scores,
            "reason":
                "ambiguous_latin_script",
        },
    )


# =========================================================
# SCRIPT-BASED DIRECT LANGUAGES
# =========================================================

def _direct_script_language(
    script: str,
    text: str,
) -> Optional[
    LanguageDetectionResult
]:

    if script == SCRIPT_HANGUL:

        return LanguageDetectionResult(
            language="ko",
            confidence=0.98,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    if script == SCRIPT_DEVANAGARI:

        # Hindi is the default shortcut here, but the script
        # is shared by multiple languages. Therefore medium
        # rather than absolute confidence.
        return LanguageDetectionResult(
            language="hi",
            confidence=0.80,
            confidence_level=CONFIDENCE_MEDIUM,
            script=script,
            reliable=True,
            alternatives=(),
            metadata={
                "script_family":
                    "devanagari",
            },
        )

    if script == SCRIPT_HEBREW:

        return LanguageDetectionResult(
            language="he",
            confidence=0.96,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    if script == SCRIPT_GREEK:

        return LanguageDetectionResult(
            language="el",
            confidence=0.96,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    if script == SCRIPT_THAI:

        return LanguageDetectionResult(
            language="th",
            confidence=0.96,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    if script == SCRIPT_GEORGIAN:

        return LanguageDetectionResult(
            language="ka",
            confidence=0.96,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    if script == SCRIPT_ARMENIAN:

        return LanguageDetectionResult(
            language="hy",
            confidence=0.96,
            confidence_level=CONFIDENCE_HIGH,
            script=script,
            reliable=True,
        )

    return None


# =========================================================
# CJK DETECTION
# =========================================================

def _detect_cjk_language(
    text: str,
    counts: Dict[str, int],
) -> LanguageDetectionResult:

    han = counts.get(
        SCRIPT_HAN,
        0
    )

    hiragana = counts.get(
        SCRIPT_HIRAGANA,
        0
    )

    katakana = counts.get(
        SCRIPT_KATAKANA,
        0
    )

    hangul = counts.get(
        SCRIPT_HANGUL,
        0
    )

    if hangul > 0:

        return LanguageDetectionResult(
            language="ko",
            confidence=0.98,
            confidence_level=CONFIDENCE_HIGH,
            script=SCRIPT_HANGUL,
            reliable=True,
            metadata={
                "han":
                    han,
                "hangul":
                    hangul,
            },
        )

    if (
        hiragana > 0
        or katakana > 0
    ):

        return LanguageDetectionResult(
            language="ja",
            confidence=0.98,
            confidence_level=CONFIDENCE_HIGH,
            script=(
                SCRIPT_HIRAGANA
                if hiragana >= katakana
                else SCRIPT_KATAKANA
            ),
            reliable=True,
            metadata={
                "han":
                    han,
                "hiragana":
                    hiragana,
                "katakana":
                    katakana,
            },
        )

    if han > 0:

        return LanguageDetectionResult(
            language="zh",
            confidence=0.88,
            confidence_level=CONFIDENCE_HIGH,
            script=SCRIPT_HAN,
            reliable=True,
            alternatives=(),
            metadata={
                "han":
                    han,
            },
        )

    return LanguageDetectionResult(
        language=LANGUAGE_UNKNOWN,
        confidence=0.0,
        confidence_level=CONFIDENCE_UNKNOWN,
        script=SCRIPT_UNKNOWN,
        reliable=False,
    )


# =========================================================
# PRIMARY DETECTOR
# =========================================================

def detect_language(
    text: Optional[str],
) -> LanguageDetectionResult:
    """
    Detect source language conservatively.

    The result should be passed to translation_policy.py.

    If exact language is ambiguous, language="unknown" is
    returned and the Translation Service can use
    source_language="auto".
    """

    cleaned = _clean_text_for_detection(
        text
    )

    if not cleaned:

        return LanguageDetectionResult(
            language=LANGUAGE_UNKNOWN,
            confidence=0.0,
            confidence_level=CONFIDENCE_UNKNOWN,
            script=SCRIPT_UNKNOWN,
            reliable=False,
            metadata={
                "reason":
                    "empty_or_nonlinguistic_text",
            },
        )

    counts = _script_counts(
        cleaned
    )

    dominant_script, dominance, mixed = (
        _dominant_script(
            counts
        )
    )

    # =====================================================
    # CJK
    # =====================================================

    if any(
        counts.get(
            script,
            0
        )
        > 0
        for script in (
            SCRIPT_HAN,
            SCRIPT_HIRAGANA,
            SCRIPT_KATAKANA,
            SCRIPT_HANGUL,
        )
    ):

        result = _detect_cjk_language(
            cleaned,
            counts,
        )

        return _with_common_metadata(
            result,
            counts=counts,
            dominance=dominance,
            mixed=mixed,
        )

    # =====================================================
    # MIXED SCRIPT
    # =====================================================

    if (
        mixed
        and dominance < 0.70
    ):

        return LanguageDetectionResult(
            language=LANGUAGE_MIXED,
            confidence=dominance,
            confidence_level=CONFIDENCE_LOW,
            script=dominant_script,
            reliable=False,
            is_mixed=True,
            metadata={
                "script_counts":
                    counts,
                "dominance":
                    dominance,
                "reason":
                    "multiple_meaningful_scripts",
            },
        )

    # =====================================================
    # ARABIC SCRIPT
    # =====================================================

    if (
        dominant_script
        == SCRIPT_ARABIC
    ):

        result = (
            _detect_arabic_script_language(
                cleaned
            )
        )

        return _with_common_metadata(
            result,
            counts=counts,
            dominance=dominance,
            mixed=mixed,
        )

    # =====================================================
    # LATIN SCRIPT
    # =====================================================

    if (
        dominant_script
        == SCRIPT_LATIN
    ):

        result = (
            _detect_latin_language(
                cleaned
            )
        )

        return _with_common_metadata(
            result,
            counts=counts,
            dominance=dominance,
            mixed=mixed,
        )

    # =====================================================
    # CYRILLIC
    # =====================================================

    if (
        dominant_script
        == SCRIPT_CYRILLIC
    ):

        result = (
            _detect_cyrillic_language(
                cleaned
            )
        )

        return _with_common_metadata(
            result,
            counts=counts,
            dominance=dominance,
            mixed=mixed,
        )

    # =====================================================
    # DIRECT SCRIPT MAPPINGS
    # =====================================================

    direct = _direct_script_language(
        dominant_script,
        cleaned,
    )

    if direct:

        return _with_common_metadata(
            direct,
            counts=counts,
            dominance=dominance,
            mixed=mixed,
        )

    # =====================================================
    # UNKNOWN
    # =====================================================

    return LanguageDetectionResult(
        language=LANGUAGE_UNKNOWN,
        confidence=dominance,
        confidence_level=CONFIDENCE_UNKNOWN,
        script=dominant_script,
        reliable=False,
        is_mixed=mixed,
        metadata={
            "script_counts":
                counts,
            "dominance":
                dominance,
            "reason":
                "language_not_identified",
        },
    )


# =========================================================
# RESULT METADATA
# =========================================================

def _with_common_metadata(
    result: LanguageDetectionResult,
    *,
    counts: Dict[str, int],
    dominance: float,
    mixed: bool,
) -> LanguageDetectionResult:

    metadata = {
        **(
            result.metadata
            or {}
        ),
        "script_counts":
            dict(
                counts
            ),
        "dominance":
            dominance,
    }

    return LanguageDetectionResult(
        language=result.language,
        confidence=result.confidence,
        confidence_level=(
            result.confidence_level
        ),
        script=result.script,
        reliable=result.reliable,
        is_mixed=mixed,
        alternatives=(
            result.alternatives
        ),
        detected_by=(
            result.detected_by
        ),
        metadata=metadata,
    )


# =========================================================
# SAFE SOURCE LANGUAGE
# =========================================================

def get_translation_source_language(
    result: LanguageDetectionResult,
) -> str:
    """
    Return the language value safe to pass into the
    Translation Service.

    Reliable detection:
        fa / en / ar / ...

    Ambiguous detection:
        auto
    """

    if (
        result.reliable
        and result.language
        not in {
            LANGUAGE_UNKNOWN,
            LANGUAGE_MIXED,
            LANGUAGE_AUTO,
        }
    ):
        return result.language

    return LANGUAGE_AUTO


# =========================================================
# POLICY HELPER
# =========================================================

def detection_requires_provider(
    result: LanguageDetectionResult,
) -> bool:
    """
    Whether deterministic detection is insufficient and a
    future provider/model language detector may improve the
    result.
    """

    return not bool(
        result.reliable
    )


# =========================================================
# CONTENT-FIELD DETECTION
# =========================================================

def detect_content_language(
    *,
    main_text: Optional[str] = None,
    caption: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
) -> LanguageDetectionResult:
    """
    Detect the language of a structured content object.

    Body/main_text receives the greatest practical weight by
    simply forming the largest portion of the combined text.

    This works for:
    - normal text
    - media captions
    - albums
    - External Review articles
    - notes
    - analysis
    """

    parts: List[str] = []

    if title:
        parts.append(
            str(
                title
            )
        )

    if main_text:
        parts.append(
            str(
                main_text
            )
        )

    if body:
        parts.append(
            str(
                body
            )
        )

    if caption:
        parts.append(
            str(
                caption
            )
        )

    combined = "\n\n".join(
        part.strip()
        for part in parts
        if part.strip()
    )

    return detect_language(
        combined
    )


# =========================================================
# MULTI-FIELD DIAGNOSTICS
# =========================================================

def describe_language_detection(
    result: LanguageDetectionResult,
) -> Dict[str, Any]:
    """
    Safe diagnostic representation.

    No source content is returned.
    """

    return {
        "language":
            result.language,

        "confidence":
            result.confidence,

        "confidence_level":
            result.confidence_level,

        "script":
            result.script,

        "reliable":
            result.reliable,

        "is_mixed":
            result.is_mixed,

        "alternatives":
            list(
                result.alternatives
            ),

        "detected_by":
            result.detected_by,

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }


# =========================================================
# CONVENIENCE
# =========================================================

def detect_language_code(
    text: Optional[str],
) -> str:
    """
    Convenience API.

    Returns a reliable language code when possible.
    Otherwise returns "auto".
    """

    return get_translation_source_language(
        detect_language(
            text
        )
    )
