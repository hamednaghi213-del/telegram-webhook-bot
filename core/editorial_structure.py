import logging
import re

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)


logger = logging.getLogger(__name__)


# =========================================================
# EDITORIAL STRUCTURE
#
# هدف:
#
# استخراج ساختار یادداشت / تحلیل پیش از خلاصه‌سازی.
#
# این ماژول:
#
# - هیچ Network Call ندارد.
# - هیچ AI Call ندارد.
# - هیچ خلاصه‌سازی انجام نمی‌دهد.
# - هیچ چیزی منتشر نمی‌کند.
#
# فقط متن را به این اجزا تقسیم می‌کند:
#
# title
# author
# author_source
# author_confidence
# body
#
# اصل مهم:
#
# Body باید تا حد ممکن کامل حفظ شود.
# هیچ پاراگراف محتوایی نباید صرفاً بر اساس حدس حذف شود.
# =========================================================


# =========================================================
# AUTHOR SOURCES
# =========================================================

AUTHOR_SOURCE_NONE = "none"
AUTHOR_SOURCE_HEADER = "header"
AUTHOR_SOURCE_OPENING_PHRASE = "opening_phrase"
AUTHOR_SOURCE_FOOTER_SIGNATURE = "footer_signature"


# =========================================================
# CONFIDENCE
# =========================================================

AUTHOR_CONFIDENCE_NONE = "none"
AUTHOR_CONFIDENCE_LOW = "low"
AUTHOR_CONFIDENCE_MEDIUM = "medium"
AUTHOR_CONFIDENCE_HIGH = "high"


# =========================================================
# RESULT OBJECT
# =========================================================

@dataclass
class EditorialStructure:

    original_text: str

    title: str

    author: str

    author_source: str

    author_confidence: str

    body: str

    metadata: Dict[str, Any]


# =========================================================
# BASIC NORMALIZATION
# =========================================================

def normalize_text(
    text: Optional[str]
) -> str:

    if not text:
        return ""

    return str(
        text
    ).strip()


def preserve_original_text(
    text: Optional[str]
) -> str:

    if text is None:
        return ""

    return str(
        text
    )


# =========================================================
# LINE HELPERS
# =========================================================

def get_non_empty_lines(
    text: str
) -> List[str]:

    text = preserve_original_text(
        text
    )

    result: List[str] = []

    for line in text.splitlines():

        value = line.strip()

        if value:

            result.append(
                value
            )

    return result


def normalize_spaces(
    text: str
) -> str:

    text = normalize_text(
        text
    )

    if not text:
        return ""

    return re.sub(
        r"[ \t]+",
        " ",
        text
    )


# =========================================================
# AUTHOR NAME CLEANUP
# =========================================================

def clean_author_name(
    value: str
) -> str:

    value = normalize_spaces(
        value
    )

    if not value:
        return ""

    value = re.sub(
        r"^[\s:：\-–—|]+",
        "",
        value
    )

    value = re.sub(
        r"[\s:：\-–—|]+$",
        "",
        value
    )

    value = value.strip(
        "،,؛;.؟?!"
    )

    return normalize_spaces(
        value
    )


# =========================================================
# AUTHOR NAME VALIDATION
# =========================================================

def looks_like_person_name(
    value: str
) -> bool:

    value = clean_author_name(
        value
    )

    if not value:
        return False

    if len(value) > 80:
        return False

    words = [
        part
        for part in value.split()
        if part
    ]

    if not words:
        return False

    if len(words) > 6:
        return False

    if re.search(
        r"[0-9۰-۹٠-٩]",
        value
    ):

        return False

    if re.search(
        r"https?://|@[A-Za-z0-9_]+|#[^\s#]+",
        value,
        flags=re.IGNORECASE
    ):

        return False

    suspicious_words = {
        "است",
        "بود",
        "شد",
        "می‌شود",
        "می شود",
        "خواهد",
        "کرد",
        "کرده",
        "داشت",
        "دارد",
        "باید",
        "اگر",
        "اما",
        "زیرا",
        "که",
    }

    lowered_words = {
        word.strip()
        for word in words
    }

    if (
        lowered_words
        & suspicious_words
    ):

        return False

    return True


# =========================================================
# AUTHOR IN HEADER
#
# Examples:
#
# نویسنده: حامد محمدی
# نویسنده حامد محمدی
# به قلم حامد محمدی
# قلم: حامد محمدی
# یادداشت از حامد محمدی
# =========================================================

def detect_author_header(
    line: str
) -> Optional[
    Tuple[str, str]
]:

    line = normalize_spaces(
        line
    )

    if not line:
        return None

    patterns = (
        r"^(?:نویسنده)\s*[:：\-–—]?\s*(.+)$",
        r"^(?:به\s+قلم)\s*[:：\-–—]?\s*(.+)$",
        r"^(?:قلم)\s*[:：\-–—]?\s*(.+)$",
        r"^(?:یادداشت\s+از)\s*[:：\-–—]?\s*(.+)$",
        r"^(?:یادداشت\s+نوشته(?:‌| )?ی)\s*[:：\-–—]?\s*(.+)$",
        r"^(?:یادداشت)\s*[:：\-–—]\s*(.+)$",
    )

    for pattern in patterns:

        match = re.match(
            pattern,
            line,
            flags=re.IGNORECASE
        )

        if not match:
            continue

        author = clean_author_name(
            match.group(1)
        )

        if not looks_like_person_name(
            author
        ):

            continue

        return (
            author,
            AUTHOR_CONFIDENCE_HIGH
        )

    return None


# =========================================================
# AUTHOR IN OPENING PHRASE
#
# Examples:
#
# حامد می‌نویسد
# حامد محمدی می نویسد
# حامد محمدی نوشت
# حامد محمدی در یادداشتی می‌نویسد
# =========================================================

def detect_opening_author_phrase(
    line: str
) -> Optional[
    Tuple[
        str,
        str,
        str
    ]
]:

    line = normalize_spaces(
        line
    )

    if not line:
        return None

    verb = (
        r"(?:"
        r"می(?:‌| )?نویسد"
        r"|نوشت"
        r"|نوشته(?:‌| )?است"
        r")"
    )

    patterns = (
        rf"^(.{{2,80}}?)\s+در\s+"
        rf"(?:یادداشتی|سرمقاله(?:‌| )?ای|مقاله(?:‌| )?ای)"
        rf"\s+{verb}\s*[:：\-–—]?\s*(.*)$",

        rf"^(.{{2,80}}?)\s+{verb}\s*[:：\-–—]?\s*(.*)$",
    )

    for pattern in patterns:

        match = re.match(
            pattern,
            line,
            flags=re.IGNORECASE
        )

        if not match:
            continue

        author = clean_author_name(
            match.group(1)
        )

        remainder = normalize_text(
            match.group(2)
        )

        if not looks_like_person_name(
            author
        ):

            continue

        return (
            author,
            remainder,
            AUTHOR_CONFIDENCE_HIGH
        )

    return None


# =========================================================
# TITLE HEURISTICS
# =========================================================

def looks_like_title(
    line: str
) -> bool:

    line = normalize_spaces(
        line
    )

    if not line:
        return False

    if len(line) > 140:
        return False

    if re.search(
        r"https?://|@[A-Za-z0-9_]+",
        line,
        flags=re.IGNORECASE
    ):

        return False

    if line.startswith("#"):
        return False

    if detect_author_header(
        line
    ) is not None:

        return False

    if detect_opening_author_phrase(
        line
    ) is not None:

        return False

    sentence_marks = (
        ".",
        "؟",
        "?",
        "!",
        "؛",
    )

    if (
        len(line) > 90
        and line.endswith(
            sentence_marks
        )
    ):

        return False

    return True


# =========================================================
# FOOTER SIGNATURE
#
# این بخش عمداً محافظه‌کارانه است.
#
# فقط خط پایانی‌ای را نویسنده فرض می‌کنیم که:
#
# - کوتاه باشد
# - شبیه نام شخص باشد
# - جمله نباشد
# - برندینگ / هشتگ / یوزرنیم نباشد
# - واژه‌های عمومی محتوایی نداشته باشد
#
# Examples:
#
# حامد محمدی
# دکتر حامد محمدی
# محمدرضا احمدی
#
# اما:
#
# پاراگراف ششم
# نتیجه نهایی
# تحلیل سیاسی
#
# نباید نویسنده تشخیص داده شوند.
# =========================================================

def detect_footer_author(
    line: str
) -> Optional[
    Tuple[str, str]
]:

    line = normalize_spaces(
        line
    )

    if not line:
        return None

    if line.startswith(
        (
            "#",
            "@",
        )
    ):

        return None

    if re.search(
        r"https?://",
        line,
        flags=re.IGNORECASE
    ):

        return None

    # =====================================================
    # EXPLICIT AUTHOR LABEL
    # =====================================================

    header_result = (
        detect_author_header(
            line
        )
    )

    if header_result is not None:

        author, _ = (
            header_result
        )

        return (
            author,
            AUTHOR_CONFIDENCE_HIGH
        )

    candidate = line

    # =====================================================
    # SENTENCE-LIKE FOOTER
    # =====================================================

    if candidate.endswith(
        (
            ".",
            "؟",
            "?",
            "!",
            "؛",
            "،",
            ",",
            ":",
            "：",
        )
    ):

        return None

    # =====================================================
    # CONTENT MARKERS
    #
    # این واژه‌ها معمولاً نشان می‌دهند خط پایانی
    # بخشی از محتوای متن است نه نام نویسنده.
    # =====================================================

    content_markers = {
        "پاراگراف",
        "بخش",
        "فصل",
        "نتیجه",
        "نتیجه‌گیری",
        "نتیجه گیری",
        "جمع‌بندی",
        "جمع بندی",
        "تحلیل",
        "یادداشت",
        "خبر",
        "گزارش",
        "ادامه",
        "پایان",
        "مقدمه",
        "تیتر",
        "عنوان",
        "قسمت",
        "بند",
        "مرحله",
        "شماره",
        "اول",
        "دوم",
        "سوم",
        "چهارم",
        "پنجم",
        "ششم",
        "هفتم",
        "هشتم",
        "نهم",
        "دهم",
        "نهایی",
    }

    candidate_words = {
        word.strip(
            "،,؛;:.؟?!"
        )
        for word
        in candidate.split()
        if word.strip()
    }

    if (
        candidate_words
        & content_markers
    ):

        return None

    # =====================================================
    # HONORIFIC
    # =====================================================

    candidate_without_title = re.sub(
        r"^(?:"
        r"دکتر"
        r"|مهندس"
        r"|سید"
        r"|حجت(?:‌| )?الاسلام"
        r"|آیت(?:‌| )?الله"
        r")\s+",
        "",
        candidate
    )

    if not looks_like_person_name(
        candidate_without_title
    ):

        return None

    words = (
        candidate_without_title
        .split()
    )

    # =====================================================
    # ONE-WORD FOOTER
    # =====================================================

    if len(words) == 1:

        return (
            candidate,
            AUTHOR_CONFIDENCE_LOW
        )

    # =====================================================
    # 2–5 WORD PERSON-LIKE SIGNATURE
    # =====================================================

    if 2 <= len(words) <= 5:

        return (
            candidate,
            AUTHOR_CONFIDENCE_MEDIUM
        )

    return None


# =========================================================
# TITLE EXTRACTION
# =========================================================

def extract_title_from_lines(
    lines: List[str]
) -> Tuple[
    str,
    List[str],
    Dict[str, Any]
]:

    working = list(
        lines
    )

    metadata: Dict[str, Any] = {
        "title_detected": False,
        "title_source": "none"
    }

    if not working:

        return (
            "",
            working,
            metadata
        )

    first_line = (
        working[0]
    )

    if not looks_like_title(
        first_line
    ):

        return (
            "",
            working,
            metadata
        )

    if len(working) < 2:

        return (
            "",
            working,
            metadata
        )

    title = (
        first_line
    )

    working = (
        working[1:]
    )

    metadata[
        "title_detected"
    ] = True

    metadata[
        "title_source"
    ] = "first_line"

    return (
        title,
        working,
        metadata
    )


# =========================================================
# HEADER AUTHOR EXTRACTION
# =========================================================

def extract_author_from_header(
    lines: List[str]
) -> Tuple[
    str,
    str,
    str,
    List[str],
    Dict[str, Any]
]:

    working = list(
        lines
    )

    metadata: Dict[str, Any] = {
        "header_author_detected": False
    }

    if not working:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    first_line = (
        working[0]
    )

    result = (
        detect_author_header(
            first_line
        )
    )

    if result is None:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    author, confidence = (
        result
    )

    working = (
        working[1:]
    )

    metadata[
        "header_author_detected"
    ] = True

    return (
        author,
        AUTHOR_SOURCE_HEADER,
        confidence,
        working,
        metadata
    )


# =========================================================
# OPENING PHRASE AUTHOR EXTRACTION
# =========================================================

def extract_author_from_opening_phrase(
    lines: List[str]
) -> Tuple[
    str,
    str,
    str,
    List[str],
    Dict[str, Any]
]:

    working = list(
        lines
    )

    metadata: Dict[str, Any] = {
        "opening_author_detected": False,
        "opening_remainder_kept": False
    }

    if not working:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    first_line = (
        working[0]
    )

    result = (
        detect_opening_author_phrase(
            first_line
        )
    )

    if result is None:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    (
        author,
        remainder,
        confidence
    ) = result

    working = (
        working[1:]
    )

    if remainder:

        working.insert(
            0,
            remainder
        )

        metadata[
            "opening_remainder_kept"
        ] = True

    metadata[
        "opening_author_detected"
    ] = True

    return (
        author,
        AUTHOR_SOURCE_OPENING_PHRASE,
        confidence,
        working,
        metadata
    )


# =========================================================
# FOOTER AUTHOR EXTRACTION
# =========================================================

def extract_author_from_footer(
    lines: List[str]
) -> Tuple[
    str,
    str,
    str,
    List[str],
    Dict[str, Any]
]:

    working = list(
        lines
    )

    metadata: Dict[str, Any] = {
        "footer_author_detected": False
    }

    if not working:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    last_line = (
        working[-1]
    )

    result = (
        detect_footer_author(
            last_line
        )
    )

    if result is None:

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    author, confidence = (
        result
    )

    # یک‌کلمه‌ای هنوز بیش از حد مبهم است.
    if (
        confidence
        == AUTHOR_CONFIDENCE_LOW
    ):

        metadata[
            "footer_author_candidate"
        ] = author

        metadata[
            "footer_author_candidate_confidence"
        ] = confidence

        return (
            "",
            AUTHOR_SOURCE_NONE,
            AUTHOR_CONFIDENCE_NONE,
            working,
            metadata
        )

    working = (
        working[:-1]
    )

    metadata[
        "footer_author_detected"
    ] = True

    return (
        author,
        AUTHOR_SOURCE_FOOTER_SIGNATURE,
        confidence,
        working,
        metadata
    )


# =========================================================
# BODY BUILD
# =========================================================

def build_body_from_lines(
    lines: List[str]
) -> str:

    values: List[str] = []

    for line in lines:

        value = normalize_text(
            line
        )

        if value:

            values.append(
                value
            )

    return "\n\n".join(
        values
    ).strip()


# =========================================================
# MAIN STRUCTURE EXTRACTOR
# =========================================================

def extract_editorial_structure(
    text: Optional[str]
) -> EditorialStructure:

    raw_original = (
        preserve_original_text(
            text
        )
    )

    normalized = (
        normalize_text(
            raw_original
        )
    )

    if not normalized:

        return EditorialStructure(
            original_text=raw_original,
            title="",
            author="",
            author_source=(
                AUTHOR_SOURCE_NONE
            ),
            author_confidence=(
                AUTHOR_CONFIDENCE_NONE
            ),
            body="",
            metadata={
                "empty": True,
                "title_detected": False,
                "author_detected": False,
                "body_length": 0
            }
        )

    lines = (
        get_non_empty_lines(
            normalized
        )
    )

    metadata: Dict[str, Any] = {
        "empty": False,
        "original_length": len(
            raw_original
        ),
        "normalized_length": len(
            normalized
        ),
        "line_count": len(
            lines
        )
    }

    # =====================================================
    # TITLE
    # =====================================================

    (
        title,
        working_lines,
        title_metadata
    ) = (
        extract_title_from_lines(
            lines
        )
    )

    metadata.update(
        title_metadata
    )

    # =====================================================
    # AUTHOR
    #
    # اولویت:
    #
    # 1. Header صریح
    # 2. Opening phrase
    # 3. Footer signature
    # =====================================================

    author = ""

    author_source = (
        AUTHOR_SOURCE_NONE
    )

    author_confidence = (
        AUTHOR_CONFIDENCE_NONE
    )

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    (
        header_author,
        header_source,
        header_confidence,
        header_lines,
        header_metadata
    ) = (
        extract_author_from_header(
            working_lines
        )
    )

    metadata.update(
        header_metadata
    )

    if header_author:

        author = (
            header_author
        )

        author_source = (
            header_source
        )

        author_confidence = (
            header_confidence
        )

        working_lines = (
            header_lines
        )

    # -----------------------------------------------------
    # OPENING PHRASE
    # -----------------------------------------------------

    if not author:

        (
            opening_author,
            opening_source,
            opening_confidence,
            opening_lines,
            opening_metadata
        ) = (
            extract_author_from_opening_phrase(
                working_lines
            )
        )

        metadata.update(
            opening_metadata
        )

        if opening_author:

            author = (
                opening_author
            )

            author_source = (
                opening_source
            )

            author_confidence = (
                opening_confidence
            )

            working_lines = (
                opening_lines
            )

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------

    if not author:

        (
            footer_author,
            footer_source,
            footer_confidence,
            footer_lines,
            footer_metadata
        ) = (
            extract_author_from_footer(
                working_lines
            )
        )

        metadata.update(
            footer_metadata
        )

        if footer_author:

            author = (
                footer_author
            )

            author_source = (
                footer_source
            )

            author_confidence = (
                footer_confidence
            )

            working_lines = (
                footer_lines
            )

    # =====================================================
    # BODY
    # =====================================================

    body = (
        build_body_from_lines(
            working_lines
        )
    )

    metadata[
        "author_detected"
    ] = bool(
        author
    )

    metadata[
        "author_source"
    ] = (
        author_source
    )

    metadata[
        "author_confidence"
    ] = (
        author_confidence
    )

    metadata[
        "body_length"
    ] = len(
        body
    )

    metadata[
        "body_line_count"
    ] = len(
        working_lines
    )

    logger.info(
        f"🧩 Editorial structure extracted | "
        f"title={bool(title)} | "
        f"title_length={len(title)} | "
        f"author={author or '-'} | "
        f"author_source={author_source} | "
        f"author_confidence="
        f"{author_confidence} | "
        f"body_length={len(body)}"
    )

    return EditorialStructure(
        original_text=raw_original,
        title=title,
        author=author,
        author_source=author_source,
        author_confidence=(
            author_confidence
        ),
        body=body,
        metadata=metadata
    )


# =========================================================
# DICT HELPER
# =========================================================

def editorial_structure_to_dict(
    structure: EditorialStructure
) -> Dict[str, Any]:

    return {
        "original_text":
            structure.original_text,

        "title":
            structure.title,

        "author":
            structure.author,

        "author_source":
            structure.author_source,

        "author_confidence":
            structure.author_confidence,

        "body":
            structure.body,

        "metadata":
            dict(
                structure.metadata
                or {}
            )
    }


# =========================================================
# REBUILD DISPLAY TEXT
# =========================================================

def rebuild_editorial_text(
    title: str = "",
    author: str = "",
    body: str = ""
) -> str:

    parts: List[str] = []

    title = normalize_text(
        title
    )

    author = normalize_text(
        author
    )

    body = normalize_text(
        body
    )

    if title:

        parts.append(
            title
        )

    if author:

        parts.append(
            author
        )

    if body:

        parts.append(
            body
        )

    return "\n\n".join(
        parts
    )


# =========================================================
# BODY COVERAGE DEBUG
# =========================================================

def body_contains_text(
    structure: EditorialStructure,
    value: str
) -> bool:

    value = normalize_text(
        value
    )

    if not value:

        return False

    return (
        value
        in (
            structure.body
            or ""
        )
    )
