from __future__ import annotations

import logging
import re
import unicodedata

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# SHARED MULTILINGUAL LANGUAGE DETECTOR
# =========================================================
#
# EXISTING FILE — FULL REPLACEMENT
#
# This module is intentionally:
#
# - deterministic
# - lightweight
# - provider-free
# - publication-free
# - database-free
#
# It performs fast local language detection where the evidence
# is strong enough.
#
# IMPORTANT:
#
# A script is NOT automatically a language.
#
# Examples:
#
# - Devanagari != Hindi
# - Arabic script != Arabic
# - Cyrillic != Russian
# - Latin != English
#
# Shared / ambiguous scripts return an uncertain result so the
# shared Translation Pipeline can invoke:
#
#     language_detection_provider.py
#
# This prevents false confidence and supports arbitrary source
# languages more safely.
#
# =========================================================


# =========================================================
# CONSTANTS
# =========================================================

LANGUAGE_AUTO = "auto"
LANGUAGE_UNKNOWN = "auto"

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class LanguageDetectionResult:
    language: str = LANGUAGE_AUTO

    confidence: float = 0.0

    confidence_level: str = CONFIDENCE_LOW

    script: str = ""

    reliable: bool = False

    is_mixed: bool = False

    alternatives: Tuple[str, ...] = field(
        default_factory=tuple
    )

    detected_by: str = "deterministic"

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


# =========================================================
# BASIC PATTERNS
# =========================================================

URL_RE = re.compile(
    r"https?://[^\s]+|www\.[^\s]+",
    re.IGNORECASE,
)

MENTION_RE = re.compile(
    r"(?<!\w)@[A-Za-z0-9_]{2,}"
)

HASHTAG_RE = re.compile(
    r"(?<!\w)#[^\s#]+"
)

NUMBER_RE = re.compile(
    r"[0-9۰-۹٠-٩]+(?:[.,٫٬:/\-][0-9۰-۹٠-٩]+)*"
)

WHITESPACE_RE = re.compile(
    r"\s+"
)


# =========================================================
# SCRIPT RANGES
# =========================================================

SCRIPT_RANGES: Dict[str, Tuple[Tuple[int, int], ...]] = {
    "arabic": (
        (0x0600, 0x06FF),
        (0x0750, 0x077F),
        (0x08A0, 0x08FF),
        (0xFB50, 0xFDFF),
        (0xFE70, 0xFEFF),
    ),

    "latin": (
        (0x0041, 0x005A),
        (0x0061, 0x007A),
        (0x00C0, 0x024F),
        (0x1E00, 0x1EFF),
    ),

    "cyrillic": (
        (0x0400, 0x04FF),
        (0x0500, 0x052F),
    ),

    "devanagari": (
        (0x0900, 0x097F),
        (0xA8E0, 0xA8FF),
    ),

    "han": (
        (0x3400, 0x4DBF),
        (0x4E00, 0x9FFF),
        (0xF900, 0xFAFF),
    ),

    "hiragana": (
        (0x3040, 0x309F),
    ),

    "katakana": (
        (0x30A0, 0x30FF),
        (0x31F0, 0x31FF),
    ),

    "hangul": (
        (0x1100, 0x11FF),
        (0x3130, 0x318F),
        (0xAC00, 0xD7AF),
    ),

    "hebrew": (
        (0x0590, 0x05FF),
        (0xFB1D, 0xFB4F),
    ),

    "greek": (
        (0x0370, 0x03FF),
        (0x1F00, 0x1FFF),
    ),

    "thai": (
        (0x0E00, 0x0E7F),
    ),

    "georgian": (
        (0x10A0, 0x10FF),
        (0x2D00, 0x2D2F),
        (0x1C90, 0x1CBF),
    ),

    "armenian": (
        (0x0530, 0x058F),
    ),
}


# =========================================================
# SHARED SCRIPT POLICY
# =========================================================
#
# These scripts are used by multiple natural languages.
#
# A script-only result for these scripts MUST NOT be treated
# as reliable language identification.
# =========================================================

SHARED_LANGUAGE_SCRIPTS: Set[str] = {
    "arabic",
    "latin",
    "cyrillic",
    "devanagari",
    "han",
}


# =========================================================
# LANGUAGE WORD MARKERS
# =========================================================

PERSIAN_WORDS: Set[str] = {
    "است",
    "این",
    "آن",
    "که",
    "را",
    "با",
    "برای",
    "از",
    "در",
    "به",
    "یک",
    "شد",
    "شده",
    "می",
    "نیز",
    "اما",
    "اگر",
    "تا",
    "بر",
    "خواهد",
    "بود",
    "کرد",
    "کرده",
    "گفت",
    "کشور",
    "ایران",
}

ARABIC_WORDS: Set[str] = {
    "في",
    "من",
    "إلى",
    "على",
    "عن",
    "هذا",
    "هذه",
    "التي",
    "الذي",
    "مع",
    "كان",
    "وقد",
    "بعد",
    "قبل",
    "بين",
    "وقال",
    "لكن",
    "هناك",
    "أن",
    "إن",
    "هو",
    "هي",
}

URDU_WORDS: Set[str] = {
    "ہے",
    "ہیں",
    "کے",
    "کی",
    "کا",
    "کو",
    "سے",
    "میں",
    "اور",
    "یہ",
    "وہ",
    "ایک",
    "پر",
    "نے",
    "کہ",
    "بھی",
    "تھا",
    "تھی",
    "گیا",
    "کیا",
}


ENGLISH_WORDS: Set[str] = {
    "the",
    "and",
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "that",
    "is",
    "was",
    "are",
    "as",
    "at",
    "from",
    "by",
    "this",
    "will",
    "has",
    "have",
    "said",
}

FRENCH_WORDS: Set[str] = {
    "le",
    "la",
    "les",
    "de",
    "des",
    "du",
    "et",
    "en",
    "un",
    "une",
    "est",
    "dans",
    "pour",
    "sur",
    "avec",
    "que",
    "qui",
    "au",
    "aux",
    "par",
}

GERMAN_WORDS: Set[str] = {
    "der",
    "die",
    "das",
    "und",
    "ist",
    "in",
    "den",
    "von",
    "zu",
    "mit",
    "auf",
    "für",
    "ein",
    "eine",
    "als",
    "auch",
    "dem",
    "des",
    "nicht",
    "wird",
}

SPANISH_WORDS: Set[str] = {
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "y",
    "en",
    "que",
    "un",
    "una",
    "por",
    "para",
    "con",
    "es",
    "se",
    "al",
    "como",
    "más",
    "ha",
}

ITALIAN_WORDS: Set[str] = {
    "il",
    "lo",
    "la",
    "gli",
    "le",
    "di",
    "del",
    "della",
    "e",
    "in",
    "che",
    "un",
    "una",
    "per",
    "con",
    "è",
    "sono",
    "al",
    "come",
    "ha",
}

PORTUGUESE_WORDS: Set[str] = {
    "o",
    "a",
    "os",
    "as",
    "de",
    "do",
    "da",
    "e",
    "em",
    "que",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "é",
    "no",
    "na",
    "como",
    "não",
}

TURKISH_WORDS: Set[str] = {
    "ve",
    "bir",
    "bu",
    "için",
    "ile",
    "da",
    "de",
    "olan",
    "olarak",
    "gibi",
    "çok",
    "daha",
    "sonra",
    "ancak",
    "ise",
    "tarafından",
    "oldu",
    "olduğunu",
    "var",
    "yeni",
}

INDONESIAN_WORDS: Set[str] = {
    "dan",
    "yang",
    "di",
    "ke",
    "dari",
    "untuk",
    "dengan",
    "ini",
    "itu",
    "pada",
    "adalah",
    "dalam",
    "akan",
    "telah",
    "tidak",
    "juga",
    "sebagai",
    "oleh",
    "atau",
    "karena",
}

MALAY_WORDS: Set[str] = {
    "dan",
    "yang",
    "di",
    "ke",
    "dari",
    "untuk",
    "dengan",
    "ini",
    "itu",
    "pada",
    "adalah",
    "dalam",
    "akan",
    "telah",
    "tidak",
    "juga",
    "sebagai",
    "oleh",
    "atau",
    "kerana",
}


RUSSIAN_WORDS: Set[str] = {
    "и",
    "в",
    "во",
    "не",
    "на",
    "что",
    "он",
    "она",
    "как",
    "это",
    "по",
    "из",
    "за",
    "для",
    "с",
    "со",
    "был",
    "будет",
    "также",
    "после",
}

UKRAINIAN_WORDS: Set[str] = {
    "і",
    "й",
    "в",
    "у",
    "не",
    "на",
    "що",
    "це",
    "як",
    "для",
    "з",
    "із",
    "до",
    "від",
    "після",
    "також",
    "було",
    "буде",
    "його",
    "її",
}


# =========================================================
# UNIQUE / STRONG CHARACTER MARKERS
# =========================================================

PERSIAN_STRONG_CHARS: Set[str] = set(
    "پچژگک‌ی"
)

URDU_STRONG_CHARS: Set[str] = set(
    "ٹڈڑںھہۓے"
)

ARABIC_STRONG_CHARS: Set[str] = set(
    "ةثذظضصط"
)

UKRAINIAN_STRONG_CHARS: Set[str] = set(
    "іїєґ"
)

RUSSIAN_STRONG_CHARS: Set[str] = set(
    "ыэъё"
)

TURKISH_STRONG_CHARS: Set[str] = set(
    "çğıöşüÇĞİÖŞÜ"
)

GERMAN_STRONG_CHARS: Set[str] = set(
    "äöüßÄÖÜ"
)

FRENCH_STRONG_CHARS: Set[str] = set(
    "àâæçéèêëîïôœùûüÿÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ"
)

SPANISH_STRONG_CHARS: Set[str] = set(
    "ñ¿¡Ñ"
)

PORTUGUESE_STRONG_CHARS: Set[str] = set(
    "ãõÃÕ"
)


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_detection_text(
    text: Optional[str],
) -> str:

    value = str(
        text
        or ""
    )

    if not value:
        return ""

    value = URL_RE.sub(
        " ",
        value,
    )

    value = MENTION_RE.sub(
        " ",
        value,
    )

    value = HASHTAG_RE.sub(
        " ",
        value,
    )

    value = NUMBER_RE.sub(
        " ",
        value,
    )

    value = WHITESPACE_RE.sub(
        " ",
        value,
    )

    return value.strip()


# =========================================================
# CHARACTER HELPERS
# =========================================================

def _in_ranges(
    char: str,
    ranges: Tuple[
        Tuple[int, int],
        ...
    ],
) -> bool:

    if not char:
        return False

    codepoint = ord(
        char
    )

    for start, end in ranges:

        if start <= codepoint <= end:
            return True

    return False


def detect_character_script(
    char: str,
) -> str:

    if not char:
        return ""

    for script, ranges in (
        SCRIPT_RANGES.items()
    ):

        if _in_ranges(
            char,
            ranges,
        ):
            return script

    return ""


def _is_letter(
    char: str,
) -> bool:

    try:

        return unicodedata.category(
            char
        ).startswith(
            "L"
        )

    except Exception:
        return False


# =========================================================
# SCRIPT PROFILE
# =========================================================

def script_profile(
    text: str,
) -> Dict[str, int]:

    counter: Counter = Counter()

    for char in text:

        if not _is_letter(
            char
        ):
            continue

        script = detect_character_script(
            char
        )

        if script:
            counter[
                script
            ] += 1

    return dict(
        counter
    )


def dominant_script(
    text: str,
) -> Tuple[
    str,
    float,
    bool,
    Dict[str, int],
]:

    profile = script_profile(
        text
    )

    total = sum(
        profile.values()
    )

    if total <= 0:

        return (
            "",
            0.0,
            False,
            profile,
        )

    ordered = sorted(
        profile.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    top_script, top_count = (
        ordered[0]
    )

    ratio = (
        top_count
        / total
    )

    substantial_scripts = [
        script
        for script, count
        in ordered
        if (
            count >= 3
            and count / total >= 0.15
        )
    ]

    is_mixed = (
        len(
            substantial_scripts
        )
        > 1
    )

    return (
        top_script,
        ratio,
        is_mixed,
        profile,
    )


# =========================================================
# WORD TOKENIZATION
# =========================================================

WORD_RE = re.compile(
    r"[^\W\d_]+",
    re.UNICODE,
)


def tokenize_words(
    text: str,
) -> List[str]:

    return [
        token.casefold()
        for token in WORD_RE.findall(
            text
        )
        if token.strip()
    ]


def _word_marker_score(
    words: Iterable[str],
    markers: Set[str],
) -> int:

    marker_set = {
        value.casefold()
        for value in markers
    }

    return sum(
        1
        for word in words
        if word.casefold()
        in marker_set
    )


def _character_marker_score(
    text: str,
    markers: Set[str],
) -> int:

    return sum(
        1
        for char in text
        if char in markers
    )


# =========================================================
# RESULT FACTORY
# =========================================================

def _confidence_level(
    confidence: float,
) -> str:

    if confidence >= 0.90:
        return CONFIDENCE_HIGH

    if confidence >= 0.70:
        return CONFIDENCE_MEDIUM

    return CONFIDENCE_LOW


def _make_result(
    *,
    language: str,
    confidence: float,
    script: str,
    reliable: bool,
    is_mixed: bool = False,
    alternatives: Optional[
        Iterable[str]
    ] = None,
    reason: str = "",
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> LanguageDetectionResult:

    confidence = max(
        0.0,
        min(
            1.0,
            float(
                confidence
                or 0.0
            ),
        ),
    )

    data = dict(
        metadata
        or {}
    )

    if reason:
        data[
            "reason"
        ] = reason

    return LanguageDetectionResult(
        language=(
            language
            or LANGUAGE_AUTO
        ),
        confidence=confidence,
        confidence_level=(
            _confidence_level(
                confidence
            )
        ),
        script=script,
        reliable=bool(
            reliable
        ),
        is_mixed=bool(
            is_mixed
        ),
        alternatives=tuple(
            alternatives
            or ()
        ),
        detected_by="deterministic",
        metadata=data,
    )


def _unknown_result(
    *,
    script: str = "",
    confidence: float = 0.0,
    is_mixed: bool = False,
    alternatives: Optional[
        Iterable[str]
    ] = None,
    reason: str = "",
    metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> LanguageDetectionResult:

    return _make_result(
        language=LANGUAGE_AUTO,
        confidence=confidence,
        script=script,
        reliable=False,
        is_mixed=is_mixed,
        alternatives=alternatives,
        reason=reason,
        metadata=metadata,
    )


# =========================================================
# ARABIC-SCRIPT DETECTION
# =========================================================

def _detect_arabic_script_language(
    text: str,
    *,
    is_mixed: bool,
    profile: Dict[str, int],
) -> LanguageDetectionResult:

    words = tokenize_words(
        text
    )

    fa_words = _word_marker_score(
        words,
        PERSIAN_WORDS,
    )

    ar_words = _word_marker_score(
        words,
        ARABIC_WORDS,
    )

    ur_words = _word_marker_score(
        words,
        URDU_WORDS,
    )

    fa_chars = _character_marker_score(
        text,
        PERSIAN_STRONG_CHARS,
    )

    ar_chars = _character_marker_score(
        text,
        ARABIC_STRONG_CHARS,
    )

    ur_chars = _character_marker_score(
        text,
        URDU_STRONG_CHARS,
    )

    scores = {
        "fa":
            fa_words * 2
            + fa_chars,

        "ar":
            ar_words * 2
            + ar_chars,

        "ur":
            ur_words * 2
            + ur_chars * 2,
    }

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    winner, winner_score = (
        ordered[0]
    )

    second_score = (
        ordered[1][1]
        if len(
            ordered
        ) > 1
        else 0
    )

    metadata = {
        "script_profile":
            profile,

        "language_scores":
            scores,

        "marker_words": {
            "fa":
                fa_words,
            "ar":
                ar_words,
            "ur":
                ur_words,
        },

        "marker_characters": {
            "fa":
                fa_chars,
            "ar":
                ar_chars,
            "ur":
                ur_chars,
        },
    }

    # Strong unique Urdu evidence.
    if (
        ur_chars >= 2
        and winner == "ur"
    ):

        return _make_result(
            language="ur",
            confidence=0.96,
            script="arabic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("fa", "ar"),
            reason="strong_urdu_character_evidence",
            metadata=metadata,
        )

    # Strong Persian-specific evidence.
    if (
        fa_chars >= 3
        and winner == "fa"
        and winner_score
        >= second_score + 2
    ):

        return _make_result(
            language="fa",
            confidence=0.95,
            script="arabic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("ar", "ur"),
            reason="strong_persian_evidence",
            metadata=metadata,
        )

    # Arabic needs lexical evidence, not merely Arabic script.
    if (
        winner == "ar"
        and ar_words >= 3
        and winner_score
        >= second_score + 2
    ):

        return _make_result(
            language="ar",
            confidence=0.92,
            script="arabic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("fa", "ur"),
            reason="strong_arabic_lexical_evidence",
            metadata=metadata,
        )

    # Persian lexical evidence can identify Persian even where
    # Persian-specific characters are absent.
    if (
        winner == "fa"
        and fa_words >= 3
        and winner_score
        >= second_score + 2
    ):

        return _make_result(
            language="fa",
            confidence=0.91,
            script="arabic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("ar", "ur"),
            reason="strong_persian_lexical_evidence",
            metadata=metadata,
        )

    # Urdu lexical evidence.
    if (
        winner == "ur"
        and ur_words >= 3
        and winner_score
        >= second_score + 2
    ):

        return _make_result(
            language="ur",
            confidence=0.92,
            script="arabic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("fa", "ar"),
            reason="strong_urdu_lexical_evidence",
            metadata=metadata,
        )

    # Shared script remains ambiguous.
    return _unknown_result(
        script="arabic",
        confidence=0.55,
        is_mixed=is_mixed,
        alternatives=(
            "fa",
            "ar",
            "ur",
        ),
        reason=(
            "arabic_script_language_ambiguous"
        ),
        metadata=metadata,
    )


# =========================================================
# CYRILLIC DETECTION
# =========================================================

def _detect_cyrillic_language(
    text: str,
    *,
    is_mixed: bool,
    profile: Dict[str, int],
) -> LanguageDetectionResult:

    words = tokenize_words(
        text
    )

    ru_words = _word_marker_score(
        words,
        RUSSIAN_WORDS,
    )

    uk_words = _word_marker_score(
        words,
        UKRAINIAN_WORDS,
    )

    ru_chars = _character_marker_score(
        text.casefold(),
        RUSSIAN_STRONG_CHARS,
    )

    uk_chars = _character_marker_score(
        text.casefold(),
        UKRAINIAN_STRONG_CHARS,
    )

    ru_score = (
        ru_words * 2
        + ru_chars * 2
    )

    uk_score = (
        uk_words * 2
        + uk_chars * 3
    )

    metadata = {
        "script_profile":
            profile,

        "language_scores": {
            "ru":
                ru_score,
            "uk":
                uk_score,
        },
    }

    if (
        uk_chars >= 2
        or (
            uk_words >= 3
            and uk_score
            >= ru_score + 2
        )
    ):

        return _make_result(
            language="uk",
            confidence=0.95,
            script="cyrillic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("ru",),
            reason="strong_ukrainian_evidence",
            metadata=metadata,
        )

    if (
        ru_chars >= 2
        or (
            ru_words >= 4
            and ru_score
            >= uk_score + 3
        )
    ):

        return _make_result(
            language="ru",
            confidence=0.93,
            script="cyrillic",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=("uk",),
            reason="strong_russian_evidence",
            metadata=metadata,
        )

    # Bulgarian, Serbian, Macedonian, Belarusian, Kazakh,
    # Kyrgyz, Tajik, Mongolian and others also use Cyrillic.
    return _unknown_result(
        script="cyrillic",
        confidence=0.50,
        is_mixed=is_mixed,
        alternatives=(
            "ru",
            "uk",
            "bg",
            "sr",
            "mk",
            "be",
            "kk",
            "ky",
            "tg",
            "mn",
        ),
        reason=(
            "cyrillic_language_ambiguous"
        ),
        metadata=metadata,
    )


# =========================================================
# LATIN DETECTION
# =========================================================

def _detect_latin_language(
    text: str,
    *,
    is_mixed: bool,
    profile: Dict[str, int],
) -> LanguageDetectionResult:

    words = tokenize_words(
        text
    )

    marker_sets = {
        "en":
            ENGLISH_WORDS,

        "fr":
            FRENCH_WORDS,

        "de":
            GERMAN_WORDS,

        "es":
            SPANISH_WORDS,

        "it":
            ITALIAN_WORDS,

        "pt":
            PORTUGUESE_WORDS,

        "tr":
            TURKISH_WORDS,

        "id":
            INDONESIAN_WORDS,

        "ms":
            MALAY_WORDS,
    }

    scores: Dict[str, int] = {}

    for language, markers in (
        marker_sets.items()
    ):

        scores[
            language
        ] = _word_marker_score(
            words,
            markers,
        )

    # Strong orthographic evidence.
    scores["tr"] += (
        _character_marker_score(
            text,
            TURKISH_STRONG_CHARS,
        )
        * 2
    )

    scores["de"] += (
        _character_marker_score(
            text,
            GERMAN_STRONG_CHARS,
        )
        * 2
    )

    scores["fr"] += (
        _character_marker_score(
            text,
            FRENCH_STRONG_CHARS,
        )
    )

    scores["es"] += (
        _character_marker_score(
            text,
            SPANISH_STRONG_CHARS,
        )
        * 2
    )

    scores["pt"] += (
        _character_marker_score(
            text,
            PORTUGUESE_STRONG_CHARS,
        )
        * 2
    )

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    winner, winner_score = (
        ordered[0]
    )

    second_score = (
        ordered[1][1]
        if len(
            ordered
        ) > 1
        else 0
    )

    metadata = {
        "script_profile":
            profile,

        "language_scores":
            scores,

        "word_count":
            len(
                words
            ),
    }

    # We intentionally require more than a single common marker.
    #
    # This prevents Latin text from silently becoming English.
    if (
        winner_score >= 4
        and winner_score
        >= second_score + 2
    ):

        confidence = min(
            0.96,
            0.82
            + min(
                winner_score,
                10,
            )
            * 0.014,
        )

        return _make_result(
            language=winner,
            confidence=confidence,
            script="latin",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=tuple(
                language
                for language, _
                in ordered[1:4]
            ),
            reason="strong_latin_language_evidence",
            metadata=metadata,
        )

    # A longer text with several coherent markers can be accepted
    # with slightly lower margin.
    if (
        len(
            words
        ) >= 12
        and winner_score >= 3
        and winner_score
        >= second_score + 2
    ):

        return _make_result(
            language=winner,
            confidence=0.84,
            script="latin",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=tuple(
                language
                for language, _
                in ordered[1:4]
            ),
            reason="sufficient_latin_lexical_evidence",
            metadata=metadata,
        )

    # Latin is shared by hundreds of languages.
    return _unknown_result(
        script="latin",
        confidence=0.45,
        is_mixed=is_mixed,
        alternatives=tuple(
            language
            for language, _
            in ordered[:5]
            if scores.get(
                language,
                0,
            ) > 0
        ),
        reason="latin_language_ambiguous",
        metadata=metadata,
    )


# =========================================================
# CJK DETECTION
# =========================================================

def _detect_cjk_language(
    *,
    script: str,
    is_mixed: bool,
    profile: Dict[str, int],
) -> LanguageDetectionResult:

    hiragana = profile.get(
        "hiragana",
        0,
    )

    katakana = profile.get(
        "katakana",
        0,
    )

    hangul = profile.get(
        "hangul",
        0,
    )

    han = profile.get(
        "han",
        0,
    )

    metadata = {
        "script_profile":
            profile,
    }

    # Hangul is highly informative for Korean.
    if hangul >= 2:

        return _make_result(
            language="ko",
            confidence=0.98,
            script="hangul",
            reliable=True,
            is_mixed=is_mixed,
            alternatives=(),
            reason="hangul_language_evidence",
            metadata=metadata,
        )

    # Kana strongly identifies Japanese.
    if (
        hiragana >= 2
        or katakana >= 2
    ):

        return _make_result(
            language="ja",
            confidence=0.98,
            script=(
                "hiragana"
                if hiragana >= katakana
                else "katakana"
            ),
            reliable=True,
            is_mixed=is_mixed,
            alternatives=(),
            reason="japanese_kana_evidence",
            metadata=metadata,
        )

    # Han-only text may be Chinese, Japanese, Classical Chinese,
    # or another context. Do not force Chinese solely from Han.
    if han > 0:

        return _unknown_result(
            script="han",
            confidence=0.60,
            is_mixed=is_mixed,
            alternatives=(
                "zh",
                "ja",
            ),
            reason="han_only_language_ambiguous",
            metadata=metadata,
        )

    return _unknown_result(
        script=script,
        confidence=0.30,
        is_mixed=is_mixed,
        reason="cjk_language_unknown",
        metadata=metadata,
    )


# =========================================================
# DEVANAGARI DETECTION
# =========================================================

def _detect_devanagari_language(
    *,
    is_mixed: bool,
    profile: Dict[str, int],
) -> LanguageDetectionResult:
    """
    Deliberately NEVER maps Devanagari directly to Hindi.

    Devanagari is used by several languages including Hindi,
    Marathi, Nepali, Sanskrit and others.

    The deterministic layer does not contain enough robust
    linguistic evidence to distinguish all of them safely.

    Provider fallback is therefore REQUIRED.
    """

    return _unknown_result(
        script="devanagari",
        confidence=0.55,
        is_mixed=is_mixed,
        alternatives=(
            "hi",
            "mr",
            "ne",
            "sa",
        ),
        reason=(
            "devanagari_shared_script_requires_provider"
        ),
        metadata={
            "script_profile":
                profile,

            "provider_fallback_recommended":
                True,
        },
    )


# =========================================================
# DIRECT SCRIPT LANGUAGES
# =========================================================
#
# These mappings are substantially safer because the script is
# strongly associated with the language in ordinary modern text.
# =========================================================

DIRECT_SCRIPT_LANGUAGES: Dict[
    str,
    Tuple[str, float]
] = {
    "hebrew":
        ("he", 0.97),

    "greek":
        ("el", 0.98),

    "thai":
        ("th", 0.98),

    "georgian":
        ("ka", 0.98),

    "armenian":
        ("hy", 0.98),
}


# =========================================================
# MAIN DETECTOR
# =========================================================

def detect_language(
    text: Optional[str],
) -> LanguageDetectionResult:

    normalized = normalize_detection_text(
        text
    )

    if not normalized:

        return _unknown_result(
            reason="empty_or_nonlinguistic_text",
        )

    (
        script,
        script_ratio,
        is_mixed,
        profile,
    ) = dominant_script(
        normalized
    )

    metadata = {
        "script_profile":
            profile,

        "dominant_script_ratio":
            script_ratio,

        "normalized_length":
            len(
                normalized
            ),
    }

    if not script:

        return _unknown_result(
            reason="no_supported_script_detected",
            metadata=metadata,
        )

    # Highly mixed text should be conservative.
    #
    # We still allow Japanese/Korean where mixed Han + Kana/Hangul
    # is normal for the language itself.
    if (
        is_mixed
        and script not in {
            "han",
            "hiragana",
            "katakana",
            "hangul",
        }
        and script_ratio < 0.70
    ):

        return _unknown_result(
            script=script,
            confidence=0.40,
            is_mixed=True,
            reason="mixed_script_language_ambiguous",
            metadata=metadata,
        )

    if script == "arabic":

        return _detect_arabic_script_language(
            normalized,
            is_mixed=is_mixed,
            profile=profile,
        )

    if script == "cyrillic":

        return _detect_cyrillic_language(
            normalized,
            is_mixed=is_mixed,
            profile=profile,
        )

    if script == "latin":

        return _detect_latin_language(
            normalized,
            is_mixed=is_mixed,
            profile=profile,
        )

    if script == "devanagari":

        return _detect_devanagari_language(
            is_mixed=is_mixed,
            profile=profile,
        )

    if script in {
        "han",
        "hiragana",
        "katakana",
        "hangul",
    }:

        return _detect_cjk_language(
            script=script,
            is_mixed=is_mixed,
            profile=profile,
        )

    direct = (
        DIRECT_SCRIPT_LANGUAGES.get(
            script
        )
    )

    if direct is not None:

        language, confidence = (
            direct
        )

        return _make_result(
            language=language,
            confidence=confidence,
            script=script,
            reliable=True,
            is_mixed=is_mixed,
            reason="strong_script_language_mapping",
            metadata=metadata,
        )

    return _unknown_result(
        script=script,
        confidence=0.35,
        is_mixed=is_mixed,
        reason="unsupported_or_ambiguous_script",
        metadata=metadata,
    )


# =========================================================
# PIPELINE SOURCE LANGUAGE
# =========================================================

def get_translation_source_language(
    result: Optional[
        LanguageDetectionResult
    ],
) -> str:
    """
    Return a source language only when deterministic detection is
    safe enough for the Translation Pipeline.

    Any uncertain result becomes "auto", which instructs the
    pipeline to use provider language detection.
    """

    if result is None:
        return LANGUAGE_AUTO

    language = str(
        getattr(
            result,
            "language",
            LANGUAGE_AUTO,
        )
        or LANGUAGE_AUTO
    ).strip().lower()

    reliable = bool(
        getattr(
            result,
            "reliable",
            False,
        )
    )

    confidence = float(
        getattr(
            result,
            "confidence",
            0.0,
        )
        or 0.0
    )

    script = str(
        getattr(
            result,
            "script",
            "",
        )
        or ""
    ).lower()

    if not reliable:
        return LANGUAGE_AUTO

    if language in {
        "",
        LANGUAGE_AUTO,
        "unknown",
        "und",
    }:
        return LANGUAGE_AUTO

    # Stronger threshold for shared scripts.
    #
    # Even when a heuristic says "reliable", a shared script
    # requires high confidence before provider fallback is skipped.
    if (
        script
        in SHARED_LANGUAGE_SCRIPTS
        and confidence < 0.88
    ):
        return LANGUAGE_AUTO

    if confidence < 0.75:
        return LANGUAGE_AUTO

    return language


# =========================================================
# PROVIDER FALLBACK DECISION
# =========================================================

def detection_requires_provider(
    result: Optional[
        LanguageDetectionResult
    ],
) -> bool:

    if result is None:
        return True

    source_language = (
        get_translation_source_language(
            result
        )
    )

    if source_language == LANGUAGE_AUTO:
        return True

    script = str(
        getattr(
            result,
            "script",
            "",
        )
        or ""
    ).lower()

    confidence = float(
        getattr(
            result,
            "confidence",
            0.0,
        )
        or 0.0
    )

    is_mixed = bool(
        getattr(
            result,
            "is_mixed",
            False,
        )
    )

    # Mixed text deserves provider verification unless deterministic
    # evidence is extremely strong.
    if (
        is_mixed
        and confidence < 0.94
    ):
        return True

    # Shared scripts need higher confidence.
    if (
        script
        in SHARED_LANGUAGE_SCRIPTS
        and confidence < 0.90
    ):
        return True

    return False


# =========================================================
# CONTENT LANGUAGE
# =========================================================

def detect_content_language(
    *,
    text: str = "",
    caption: str = "",
    title: str = "",
    body: str = "",
) -> LanguageDetectionResult:
    """
    Detect language from generic content fields without making any
    assumptions about the content type.

    Longer semantic body text is preferred, but all available
    fields are combined.
    """

    parts: List[str] = []

    for value in (
        title,
        text,
        caption,
        body,
    ):

        value = str(
            value
            or ""
        ).strip()

        if value:
            parts.append(
                value
            )

    combined = "\n\n".join(
        parts
    ).strip()

    return detect_language(
        combined
    )


# =========================================================
# CONVENIENCE LANGUAGE CODE
# =========================================================

def detect_language_code(
    text: Optional[str],
) -> str:

    result = detect_language(
        text
    )

    return get_translation_source_language(
        result
    )


# =========================================================
# DIAGNOSTICS
# =========================================================

def language_detection_diagnostics(
    result: Optional[
        LanguageDetectionResult
    ],
) -> Dict[str, Any]:

    if result is None:

        return {
            "language":
                LANGUAGE_AUTO,

            "confidence":
                0.0,

            "confidence_level":
                CONFIDENCE_LOW,

            "script":
                "",

            "reliable":
                False,

            "is_mixed":
                False,

            "alternatives":
                [],

            "detected_by":
                "deterministic",

            "provider_required":
                True,
        }

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

        "provider_required":
            detection_requires_provider(
                result
            ),

        "metadata":
            dict(
                result.metadata
                or {}
            ),
    }


# =========================================================
# COMPATIBILITY ALIAS
# =========================================================

def describe_language_detection(
    text: Optional[str],
) -> Dict[str, Any]:

    return language_detection_diagnostics(
        detect_language(
            text
        )
    )
