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
#
# علاوه بر آن یک لایه Display مستقل دارد که می‌تواند
# عنوان و نویسنده را برای خروجی نهایی رسانه‌ای تزئین کند.
#
# آیکون‌ها هرگز وارد متن اصلی AI یا Validator نمی‌شوند.
# =========================================================


# =========================================================
# DISPLAY ICONS
# =========================================================

EDITORIAL_TITLE_ICON = "📝"
EDITORIAL_AUTHOR_ICON = "✍️"


# =========================================================
# SOURCE / DECORATIVE ICONS
#
# این آیکون‌ها ممکن است توسط Formatter یا منبع خبر
# در ابتدای تیتر / نویسنده قرار گرفته باشند.
#
# در مسیر Editorial حذف می‌شوند.
#
# خبرهای عادی تحت تأثیر این ماژول قرار نمی‌گیرند.
# =========================================================

EDITORIAL_REMOVABLE_TITLE_ICONS = (
    "✳️",
    "❇️",
    "✅",
    "🟢",
    "🟩",
)

EDITORIAL_AUTHOR_PREFIX_ICONS = (
    "🔹",
    "🔸",
    "▪️",
    "▫️",
    "•",
)


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
# TITLE CLEANUP
#
# فقط تزئینات Editorial / Formatter را از ابتدای تیتر
# حذف می‌کند.
#
# مثال:
#
# ✳️ تعهد در عصر بی تعهدی
#
# becomes:
#
# تعهد در عصر بی تعهدی
#
# همچنین اگر 📝 از قبل وجود داشته باشد حذف می‌شود،
# چون Display Layer خودش دقیقاً یک بار آن را اضافه می‌کند.
# =========================================================

def clean_editorial_title(
    value: str
) -> str:

    value = normalize_spaces(
        value
    )

    if not value:
        return ""

    changed = True

    while changed:

        changed = False

        # ---------------------------------------------
        # Our own display icon
        # ---------------------------------------------

        if value.startswith(
            EDITORIAL_TITLE_ICON
        ):

            value = (
                value[
                    len(
                        EDITORIAL_TITLE_ICON
                    ):
                ]
                .lstrip()
            )

            changed = True

        # ---------------------------------------------
        # Green / source icons
        # ---------------------------------------------

        for icon in (
            EDITORIAL_REMOVABLE_TITLE_ICONS
        ):

            if value.startswith(
                icon
            ):

                value = (
                    value[
                        len(icon):
                    ]
                    .lstrip()
                )

                changed = True

                break

    return normalize_spaces(
        value
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

    # ---------------------------------------------
    # Remove our own display icon
    # ---------------------------------------------

    if value.startswith(
        EDITORIAL_AUTHOR_ICON
    ):

        value = (
            value[
                len(
                    EDITORIAL_AUTHOR_ICON
                ):
            ]
            .lstrip()
        )

    # ---------------------------------------------
    # Remove source bullet icons
    # ---------------------------------------------

    changed = True

    while changed:

        changed = False

        for icon in (
            EDITORIAL_AUTHOR_PREFIX_ICONS
        ):

            if value.startswith(
                icon
            ):

                value = (
                    value[
                        len(icon):
                    ]
                    .lstrip()
                )

                changed = True

                break

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

    if len(value) > 120:
        return False

    # =====================================================
    # Parenthetical role is allowed:
    #
    # حامد نقی لو (کارشناس سیاست خارجی)
    #
    # For person-name validation we inspect the name part
    # separately.
    # =====================================================

    person_part = re.sub(
        r"\s*\([^)]{1,80}\)\s*$",
        "",
        value
    ).strip()

    if not person_part:

        return False

    words = [
        part
        for part in person_part.split()
        if part
    ]

    if not words:
        return False

    if len(words) > 6:
        return False

    if re.search(
        r"[0-9۰-۹٠-٩]",
        person_part
    ):

        return False

    if re.search(
        r"https?://|@[A-Za-z0-9_]+|#[^\s#]+",
        person_part,
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
        "گفت",
        "اعلام",
        "معتقد",
        "تأکید",
        "تاکید",
    }

    lowered_words = {
        word.strip(
            "،,؛;:.؟?!()"
        )
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
# DECORATED AUTHOR LINE
#
# Examples:
#
# 🔹 حامد نقی لو
#
# 🔹 حامد نقی لو (کارشناس سیاست خارجی)
#
# 🔸 محمدرضا احمدی (پژوهشگر روابط بین‌الملل)
#
# این تشخیص فقط در جایگاه Header و پس از Title
# استفاده می‌شود؛ بنابراین روی Bulletهای عادی داخل Body
# اعمال نمی‌شود.
# =========================================================

def detect_decorated_author_line(
    line: str
) -> Optional[
    Tuple[str, str]
]:

    original_line = normalize_spaces(
        line
    )

    if not original_line:
        return None

    matched_prefix = False

    candidate = original_line

    for icon in (
        EDITORIAL_AUTHOR_PREFIX_ICONS
    ):

        if candidate.startswith(
            icon
        ):

            candidate = (
                candidate[
                    len(icon):
                ]
                .lstrip()
            )

            matched_prefix = True

            break

    if not matched_prefix:
        return None

    candidate = clean_author_name(
        candidate
    )

    if not candidate:
        return None

    # =====================================================
    # Sentence-like content should never become author.
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
    # If a role exists in parentheses, preserve it.
    #
    # Example:
    #
    # حامد نقی لو (کارشناس سیاست خارجی)
    # =====================================================

    role_match = re.match(
        r"^(.{2,80}?)\s*\((.{2,80})\)\s*$",
        candidate
    )

    if role_match:

        person_name = clean_author_name(
            role_match.group(1)
        )

        role = normalize_spaces(
            role_match.group(2)
        )

        if not looks_like_person_name(
            person_name
        ):

            return None

        # ---------------------------------------------
        # Role markers make confidence high.
        # ---------------------------------------------

        role_markers = (
            "کارشناس",
            "پژوهشگر",
            "نویسنده",
            "روزنامه‌نگار",
            "روزنامه نگار",
            "تحلیلگر",
            "استاد",
            "دیپلمات",
            "سفیر",
            "فعال",
            "عضو",
            "مدیر",
            "دبیر",
            "متخصص",
        )

        role_is_plausible = any(
            marker
            in role
            for marker
            in role_markers
        )

        if not role_is_plausible:

            return None

        return (
            candidate,
            AUTHOR_CONFIDENCE_HIGH
        )

    # =====================================================
    # Without role:
    #
    # Conservative 2–4 word name.
    # =====================================================

    if not looks_like_person_name(
        candidate
    ):

        return None

    person_words = (
        candidate.split()
    )

    if not (
        2
        <= len(person_words)
        <= 4
    ):

        return None

    return (
        candidate,
        AUTHOR_CONFIDENCE_MEDIUM
    )


# =========================================================
# AUTHOR IN OPENING PHRASE
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

    line = clean_editorial_title(
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
        re.sub(
            r"\s*\([^)]{1,80}\)\s*$",
            "",
            candidate_without_title
        )
        .strip()
        .split()
    )

    if len(words) == 1:

        return (
            candidate,
            AUTHOR_CONFIDENCE_LOW
        )

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
        "title_source": "none",
        "title_source_icons_removed": False
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

    cleaned_first_line = (
        clean_editorial_title(
            first_line
        )
    )

    if not looks_like_title(
        cleaned_first_line
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
        cleaned_first_line
    )

    if (
        title
        != normalize_spaces(
            first_line
        )
    ):

        metadata[
            "title_source_icons_removed"
        ] = True

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
# DECORATED AUTHOR EXTRACTION
#
# فقط خط اول پس از Title بررسی می‌شود.
#
# این محدودیت عمدی است تا Bulletهای داخل Body
# اشتباهاً نویسنده تشخیص داده نشوند.
# =========================================================

def extract_author_from_decorated_header(
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
        "decorated_author_detected": False
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
        detect_decorated_author_line(
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
        "decorated_author_detected"
    ] = True

    metadata[
        "decorated_author_original"
    ] = first_line

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
    # Priority:
    #
    # 1. Explicit header
    # 2. Decorated header: 🔹 Name (Role)
    # 3. Opening phrase: Name می‌نویسد
    # 4. Footer signature
    # =====================================================

    author = ""

    author_source = (
        AUTHOR_SOURCE_NONE
    )

    author_confidence = (
        AUTHOR_CONFIDENCE_NONE
    )

    # -----------------------------------------------------
    # EXPLICIT HEADER
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
    # DECORATED AUTHOR
    # -----------------------------------------------------

    if not author:

        (
            decorated_author,
            decorated_source,
            decorated_confidence,
            decorated_lines,
            decorated_metadata
        ) = (
            extract_author_from_decorated_header(
                working_lines
            )
        )

        metadata.update(
            decorated_metadata
        )

        if decorated_author:

            author = (
                decorated_author
            )

            author_source = (
                decorated_source
            )

            author_confidence = (
                decorated_confidence
            )

            working_lines = (
                decorated_lines
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
        f"title_value={title or '-'} | "
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
# RAW REBUILD
#
# بدون Display Icon.
#
# برای سازگاری با تست‌ها و کدهای قبلی.
# =========================================================

def rebuild_editorial_text(
    title: str = "",
    author: str = "",
    body: str = ""
) -> str:

    parts: List[str] = []

    title = clean_editorial_title(
        title
    )

    author = clean_author_name(
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
# EDITORIAL DISPLAY TITLE
# =========================================================

def build_editorial_display_title(
    title: str
) -> str:

    # =====================================================
    # مهم:
    #
    # قبل از اضافه کردن 📝، آیکون سبز / قدیمی حذف می‌شود.
    # =====================================================

    title = clean_editorial_title(
        title
    )

    if not title:
        return ""

    return (
        f"{EDITORIAL_TITLE_ICON} "
        f"{title}"
    )


# =========================================================
# EDITORIAL DISPLAY AUTHOR
# =========================================================

def build_editorial_display_author(
    author: str
) -> str:

    author = clean_author_name(
        author
    )

    if not author:
        return ""

    return (
        f"{EDITORIAL_AUTHOR_ICON} "
        f"{author}"
    )


# =========================================================
# FINAL EDITORIAL DISPLAY TEXT
#
# خروجی هدف:
#
# 📝 تعهد در عصر بی تعهدی
# ✍️ حامد نقی لو (کارشناس سیاست خارجی)
#
# متن خلاصه...
#
# آیکون سبز تیتر و 🔹 نویسنده در خروجی
# Editorial نمایش داده نمی‌شوند.
# =========================================================

def rebuild_editorial_display_text(
    title: str = "",
    author: str = "",
    body: str = ""
) -> str:

    parts: List[str] = []

    title = clean_editorial_title(
        title
    )

    author = clean_author_name(
        author
    )

    body = normalize_text(
        body
    )

    display_title = (
        build_editorial_display_title(
            title
        )
    )

    display_author = (
        build_editorial_display_author(
            author
        )
    )

    header_lines: List[str] = []

    if display_title:

        header_lines.append(
            display_title
        )

    if display_author:

        header_lines.append(
            display_author
        )

    if header_lines:

        parts.append(
            "\n".join(
                header_lines
            )
        )

    if body:

        parts.append(
            body
        )

    result = "\n\n".join(
        parts
    )

    logger.info(
        f"📝 Editorial display built | "
        f"title={bool(display_title)} | "
        f"author={bool(display_author)} | "
        f"body={len(body)} | "
        f"total={len(result)}"
    )

    return result


# =========================================================
# STRUCTURE DISPLAY HELPER
# =========================================================

def rebuild_editorial_structure_display(
    structure: EditorialStructure,
    body: Optional[str] = None
) -> str:

    if structure is None:
        return ""

    display_body = (
        structure.body
        if body is None
        else body
    )

    return (
        rebuild_editorial_display_text(
            title=structure.title,
            author=structure.author,
            body=display_body
        )
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
