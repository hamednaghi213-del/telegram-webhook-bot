import logging
import re

from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Any,
)


logger = logging.getLogger(__name__)


# =========================================================
# SMART SUMMARIZER
#
# هدف:
# خلاصه‌سازی وفادار به متن بدون تفسیر، تحلیل،
# قضاوت یا افزودن اطلاعات جدید.
#
# IMPORTANT:
#
# این ماژول به‌تنهایی هیچ Network Call انجام نمی‌دهد.
#
# مدل هوش مصنوعی بعداً به‌صورت یک Callable
# به این ماژول متصل خواهد شد.
# =========================================================


# =========================================================
# DEFAULT POLICY
# =========================================================

DEFAULT_MAX_REDUCTION_RATIO = 0.40

DEFAULT_CAPTION_TARGET = 940
DEFAULT_TEXT_TARGET = 3900

MINIMUM_SUMMARY_LENGTH = 80


# =========================================================
# CRITICAL LANGUAGE MARKERS
#
# حذف یا تغییر این واژه‌ها می‌تواند معنای خبر را
# کاملاً تغییر دهد.
# =========================================================

CERTAINTY_MARKERS = {
    "احتمال",
    "احتمالاً",
    "ممکن",
    "ممکن است",
    "شاید",
    "گمان",
    "گفته می‌شود",
    "گزارش شده",
    "گزارش شده است",
    "ادعا",
    "مدعی",
    "مدعی شد",
    "تأیید",
    "تایید",
    "تأیید کرد",
    "تایید کرد",
    "تکذیب",
    "تکذیب کرد",
    "رد کرد",
    "اعلام کرد",
    "گفت",
    "به گفته",
    "براساس گزارش",
    "بر اساس گزارش",
    "هنوز تأیید نشده",
    "هنوز تایید نشده",
    "رسماً",
    "رسمی",
}


# =========================================================
# RESULT OBJECT
# =========================================================

@dataclass
class SummaryResult:

    success: bool

    original_text: str

    summary_text: str

    target_length: int

    original_length: int

    summary_length: int

    reduction_ratio: float

    validation_passed: bool

    reason: str

    metadata: Dict[str, Any]


# =========================================================
# NORMALIZATION
#
# فقط برای تحلیل داخلی استفاده می‌شود.
#
# IMPORTANT:
# هنگام fallback نباید نسخه normalize شده جای متن اصلی
# برگردد. متن خام اولیه باید دقیقاً حفظ شود.
# =========================================================

def normalize_text(
    text: Optional[str]
) -> str:

    if not text:
        return ""

    return str(
        text
    ).strip()


# =========================================================
# RAW TEXT
#
# متن اصلی را بدون strip نگه می‌دارد.
# =========================================================

def preserve_original_text(
    text: Optional[str]
) -> str:

    if text is None:
        return ""

    return str(
        text
    )


# =========================================================
# BASIC LENGTH
# =========================================================

def text_length(
    text: Optional[str]
) -> int:

    return len(
        preserve_original_text(
            text
        )
    )


# =========================================================
# SHOULD SUMMARIZE?
# =========================================================

def needs_summarization(
    text: str,
    target_length: int
) -> bool:

    raw_text = preserve_original_text(
        text
    )

    if not raw_text:
        return False

    if target_length <= 0:
        return False

    return (
        len(raw_text)
        > target_length
    )


# =========================================================
# REDUCTION RATIO
# =========================================================

def calculate_reduction_ratio(
    original_text: str,
    summary_text: str
) -> float:

    original_text = normalize_text(
        original_text
    )

    summary_text = normalize_text(
        summary_text
    )

    if not original_text:
        return 0.0

    reduction = (
        len(original_text)
        - len(summary_text)
    )

    if reduction <= 0:
        return 0.0

    return (
        reduction
        / len(original_text)
    )


# =========================================================
# EXTRACT NUMBERS
#
# اعداد در خبر جزو داده‌های حساس هستند.
# مدل نباید عدد جدید بسازد یا عدد موجود را تغییر دهد.
# =========================================================

def extract_numbers(
    text: str
) -> Set[str]:

    text = normalize_text(
        text
    )

    if not text:
        return set()

    pattern = (
        r"[0-9۰-۹٠-٩]+"
        r"(?:[.,٫٬][0-9۰-۹٠-٩]+)?"
        r"(?:\s*٪|\s*%)?"
    )

    return set(
        re.findall(
            pattern,
            text
        )
    )


# =========================================================
# EXTRACT MENTIONS
# =========================================================

def extract_mentions(
    text: str
) -> Set[str]:

    text = normalize_text(
        text
    )

    if not text:
        return set()

    return set(
        re.findall(
            r"@[A-Za-z0-9_]+",
            text
        )
    )


# =========================================================
# EXTRACT HASHTAGS
# =========================================================

def extract_hashtags(
    text: str
) -> Set[str]:

    text = normalize_text(
        text
    )

    if not text:
        return set()

    return set(
        re.findall(
            r"#[^\s#]+",
            text
        )
    )


# =========================================================
# EXTRACT URLS
# =========================================================

def extract_urls(
    text: str
) -> Set[str]:

    text = normalize_text(
        text
    )

    if not text:
        return set()

    return set(
        re.findall(
            r"https?://[^\s]+",
            text,
            flags=re.IGNORECASE
        )
    )


# =========================================================
# EXTRACT CERTAINTY MARKERS
# =========================================================

def extract_certainty_markers(
    text: str
) -> Set[str]:

    text = normalize_text(
        text
    )

    if not text:
        return set()

    found: Set[str] = set()

    normalized_lower = (
        text.lower()
    )

    for marker in CERTAINTY_MARKERS:

        if (
            marker.lower()
            in normalized_lower
        ):

            found.add(
                marker
            )

    return found


# =========================================================
# PROTECTED FACTS
# =========================================================

def extract_protected_facts(
    text: str
) -> Dict[str, Set[str]]:

    return {
        "numbers": extract_numbers(
            text
        ),
        "mentions": extract_mentions(
            text
        ),
        "hashtags": extract_hashtags(
            text
        ),
        "urls": extract_urls(
            text
        ),
        "certainty_markers": (
            extract_certainty_markers(
                text
            )
        ),
    }


# =========================================================
# DETECT NEW NUMBERS
# =========================================================

def detect_new_numbers(
    original_text: str,
    summary_text: str
) -> Set[str]:

    original_numbers = (
        extract_numbers(
            original_text
        )
    )

    summary_numbers = (
        extract_numbers(
            summary_text
        )
    )

    return (
        summary_numbers
        - original_numbers
    )


# =========================================================
# VALIDATE SUMMARY
# =========================================================

def validate_summary(
    original_text: str,
    summary_text: str,
    target_length: int,
    max_reduction_ratio: float = (
        DEFAULT_MAX_REDUCTION_RATIO
    )
) -> Dict[str, Any]:

    original_text = normalize_text(
        original_text
    )

    summary_text = normalize_text(
        summary_text
    )

    errors: List[str] = []

    warnings: List[str] = []

    if not original_text:

        errors.append(
            "original_text_empty"
        )

    if not summary_text:

        errors.append(
            "summary_text_empty"
        )

    if (
        summary_text
        and len(summary_text)
        > target_length
    ):

        errors.append(
            "summary_exceeds_target"
        )

    if (
        summary_text
        and len(summary_text)
        < MINIMUM_SUMMARY_LENGTH
        and len(original_text)
        >= MINIMUM_SUMMARY_LENGTH
    ):

        warnings.append(
            "summary_very_short"
        )

    reduction_ratio = (
        calculate_reduction_ratio(
            original_text,
            summary_text
        )
    )

    if (
        reduction_ratio
        > max_reduction_ratio
    ):

        errors.append(
            "reduction_too_aggressive"
        )

    # =====================================================
    # NEW NUMBERS ARE NOT ALLOWED
    # =====================================================

    new_numbers = (
        detect_new_numbers(
            original_text,
            summary_text
        )
    )

    if new_numbers:

        errors.append(
            "new_numbers_detected"
        )

    # =====================================================
    # MENTIONS
    # =====================================================

    original_mentions = (
        extract_mentions(
            original_text
        )
    )

    summary_mentions = (
        extract_mentions(
            summary_text
        )
    )

    new_mentions = (
        summary_mentions
        - original_mentions
    )

    if new_mentions:

        errors.append(
            "new_mentions_detected"
        )

    # =====================================================
    # URLs
    # =====================================================

    original_urls = (
        extract_urls(
            original_text
        )
    )

    summary_urls = (
        extract_urls(
            summary_text
        )
    )

    new_urls = (
        summary_urls
        - original_urls
    )

    if new_urls:

        errors.append(
            "new_urls_detected"
        )

    # =====================================================
    # CERTAINTY / ATTRIBUTION MARKERS
    #
    # اگر اصل خبر دارای نشانگرهای احتیاط یا نسبت‌دهی باشد،
    # خلاصه نباید تمام آن‌ها را حذف کند.
    # =====================================================

    original_markers = (
        extract_certainty_markers(
            original_text
        )
    )

    summary_markers = (
        extract_certainty_markers(
            summary_text
        )
    )

    if (
        original_markers
        and not summary_markers
    ):

        errors.append(
            "certainty_markers_lost"
        )

    return {
        "valid": (
            len(errors)
            == 0
        ),
        "errors": errors,
        "warnings": warnings,
        "reduction_ratio": (
            reduction_ratio
        ),
        "new_numbers": sorted(
            new_numbers
        ),
        "original_numbers": sorted(
            extract_numbers(
                original_text
            )
        ),
        "summary_numbers": sorted(
            extract_numbers(
                summary_text
            )
        ),
        "original_certainty_markers": (
            sorted(
                original_markers
            )
        ),
        "summary_certainty_markers": (
            sorted(
                summary_markers
            )
        ),
    }


# =========================================================
# SYSTEM INSTRUCTION
# =========================================================

def build_summarization_instruction(
    target_length: int
) -> str:

    return (
        "متن زیر یک خبر است. "
        "وظیفه شما فقط کوتاه‌کردن وفادارانه متن است. "
        "حق تحلیل، تفسیر، نتیجه‌گیری، قضاوت، "
        "اصلاح محتوایی یا افزودن اطلاعات جدید را ندارید. "
        "هیچ واقعیت جدیدی تولید نکنید. "
        "نام افراد، نهادها، سمت‌ها، اعداد، تاریخ‌ها، "
        "مکان‌ها و نسبت دادن سخنان به گویندگان را تغییر ندهید. "
        "میزان قطعیت خبر را تغییر ندهید. "
        "عباراتی مانند احتمال، ادعا، به گفته، "
        "تکذیب، تأیید، گزارش شده و هنوز تأیید نشده "
        "در صورت وجود باید از نظر معنایی حفظ شوند. "
        "در صورت نیاز ابتدا تکرارها، توضیحات زائد، "
        "جزئیات فرعی و عبارت‌های قابل فشرده‌سازی را کوتاه کنید. "
        "معنای اصلی هر گزاره باید حفظ شود. "
        "هیچ دیدگاه یا برداشت شخصی به متن اضافه نکنید. "
        "اگر کوتاه‌کردن بدون تحریف ممکن نیست، "
        "متن را تا حد امکان نزدیک به اصل نگه دارید. "
        f"خروجی نهایی نباید بیشتر از {target_length} "
        "کاراکتر باشد. "
        "فقط متن خلاصه‌شده را برگردانید."
    )


# =========================================================
# SMART SUMMARIZE
#
# summarizer:
#
# Callable receiving:
#
#   original_text
#   instruction
#   target_length
#
# and returning summarized text.
# =========================================================

def summarize_text_safely(
    original_text: str,
    target_length: int,
    summarizer: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ] = None,
    max_reduction_ratio: float = (
        DEFAULT_MAX_REDUCTION_RATIO
    )
) -> SummaryResult:

    # =====================================================
    # PRESERVE RAW ORIGINAL
    #
    # مهم‌ترین اصل:
    # اگر خلاصه‌سازی انجام نشد یا شکست خورد،
    # دقیقاً همین رشته اولیه باید برگردد.
    # =====================================================

    raw_original_text = (
        preserve_original_text(
            original_text
        )
    )

    normalized_original_text = (
        normalize_text(
            raw_original_text
        )
    )

    original_length = len(
        raw_original_text
    )

    # =====================================================
    # EMPTY
    # =====================================================

    if not normalized_original_text:

        return SummaryResult(
            success=True,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=True,
            reason="empty_text",
            metadata={
                "summarizer_called": False
            }
        )

    # =====================================================
    # ALREADY FITS
    #
    # اگر متن داخل سقف باشد مدل نباید صدا زده شود.
    # متن خام دقیقاً بدون تغییر برمی‌گردد.
    # =====================================================

    if (
        target_length > 0
        and original_length
        <= target_length
    ):

        return SummaryResult(
            success=True,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=True,
            reason="already_fits",
            metadata={
                "summarizer_called": False
            }
        )

    # =====================================================
    # INVALID TARGET
    # =====================================================

    if target_length <= 0:

        return SummaryResult(
            success=False,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=False,
            reason="invalid_target_length",
            metadata={
                "summarizer_called": False
            }
        )

    # =====================================================
    # NO SUMMARIZER CONNECTED
    # =====================================================

    if summarizer is None:

        logger.info(
            "ℹ️ Smart summarization required "
            "but no summarizer provider is connected"
        )

        return SummaryResult(
            success=False,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=False,
            reason="summarizer_not_configured",
            metadata={
                "summarizer_called": False
            }
        )

    # =====================================================
    # MAXIMUM SAFE REDUCTION CHECK
    #
    # اگر فقط برای رسیدن به Target مجبور باشیم بیش از
    # مقدار مجاز حذف کنیم، Provider اصلاً فراخوانی نمی‌شود.
    # =====================================================

    required_reduction_ratio = (
        (
            original_length
            - target_length
        )
        / original_length
    )

    if (
        required_reduction_ratio
        > max_reduction_ratio
    ):

        logger.warning(
            f"⚠️ Smart summarization skipped | "
            f"required_reduction="
            f"{required_reduction_ratio:.3f} | "
            f"max_allowed="
            f"{max_reduction_ratio:.3f}"
        )

        return SummaryResult(
            success=False,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=False,
            reason="required_reduction_too_aggressive",
            metadata={
                "required_reduction_ratio": (
                    required_reduction_ratio
                ),
                "summarizer_called": False
            }
        )

    # =====================================================
    # BUILD INSTRUCTION
    # =====================================================

    instruction = (
        build_summarization_instruction(
            target_length
        )
    )

    # =====================================================
    # CALL PROVIDER
    # =====================================================

    try:

        generated = summarizer(
            raw_original_text,
            instruction,
            target_length
        )

    except Exception as e:

        logger.exception(
            f"❌ Smart summarizer provider failed | "
            f"{e}"
        )

        return SummaryResult(
            success=False,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=False,
            reason="provider_error",
            metadata={
                "error": str(
                    e
                ),
                "summarizer_called": True
            }
        )

    generated = normalize_text(
        generated
    )

    # =====================================================
    # VALIDATION
    # =====================================================

    validation = (
        validate_summary(
            original_text=raw_original_text,
            summary_text=generated,
            target_length=target_length,
            max_reduction_ratio=(
                max_reduction_ratio
            )
        )
    )

    if not validation[
        "valid"
    ]:

        logger.warning(
            f"⚠️ Smart summary rejected | "
            f"errors="
            f"{validation['errors']}"
        )

        # =================================================
        # FAIL CLOSED
        #
        # خلاصه ناسالم هرگز منتشر نمی‌شود.
        # متن خام اصلی دقیقاً برمی‌گردد.
        # =================================================

        return SummaryResult(
            success=False,
            original_text=raw_original_text,
            summary_text=raw_original_text,
            target_length=target_length,
            original_length=original_length,
            summary_length=original_length,
            reduction_ratio=0.0,
            validation_passed=False,
            reason="validation_failed",
            metadata={
                "validation": validation,
                "candidate_summary": (
                    generated
                ),
                "summarizer_called": True
            }
        )

    reduction_ratio = (
        calculate_reduction_ratio(
            raw_original_text,
            generated
        )
    )

    logger.info(
        f"✅ Smart summary accepted | "
        f"before={original_length} | "
        f"after={len(generated)} | "
        f"target={target_length} | "
        f"reduction="
        f"{reduction_ratio:.3f}"
    )

    return SummaryResult(
        success=True,
        original_text=raw_original_text,
        summary_text=generated,
        target_length=target_length,
        original_length=original_length,
        summary_length=len(
            generated
        ),
        reduction_ratio=(
            reduction_ratio
        ),
        validation_passed=True,
        reason="summary_accepted",
        metadata={
            "validation": validation,
            "summarizer_called": True
        }
    )
