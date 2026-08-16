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
# معماری:
#
# 1. متن کوتاه → بدون AI
#
# 2. کاهش معمولی تا 40٪
#    → مستقیم وارد خلاصه‌سازی امن می‌شود.
#
# 3. کاهش بیشتر از 40٪
#    → AI ابتدا نوع و حساسیت محتوا را تشخیص می‌دهد.
#
# 4. خبر عادی
#    → امکان فشرده‌سازی عمیق‌تر
#
# 5. متن حساس
#    → سیاست محافظه‌کارانه
#
# 6. خروجی در تمام حالت‌ها
#    → Validator ضدتحریف
#
# 7. شکست AI / Validation
#    → متن اصلی دقیقاً حفظ می‌شود.
# =========================================================


# =========================================================
# BASE POLICY
#
# IMPORTANT:
#
# مقدار 0.40 برای سازگاری با معماری و تست‌های قبلی
# حفظ شده است.
#
# این مقدار دیگر سقف مطلق تمام خبرها نیست.
# =========================================================

DEFAULT_MAX_REDUCTION_RATIO = 0.40

DEFAULT_CAPTION_TARGET = 940
DEFAULT_TEXT_TARGET = 3900

MINIMUM_SUMMARY_LENGTH = 80


# =========================================================
# ADAPTIVE AI POLICY
# =========================================================

# خبر عادی در صورت تأیید AI می‌تواند عمیق‌تر خلاصه شود.
NORMAL_NEWS_MAX_REDUCTION_RATIO = 0.60

# متن حساس باید بسیار محافظه‌کارانه‌تر باقی بماند.
SENSITIVE_CONTENT_MAX_REDUCTION_RATIO = 0.30

# اگر AI نتواند نوع محتوا را با قطعیت تشخیص دهد.
UNCERTAIN_CONTENT_MAX_REDUCTION_RATIO = 0.40

# در یا بالاتر از این مقدار، حتی برای خبر عادی
# خلاصه‌سازی خودکار انجام نمی‌شود.
#
# این مرز مانع تبدیل خبر بسیار بلند به خلاصه بیش از حد
# فشرده و بالقوه تحریف‌شده می‌شود.
ABSOLUTE_MAX_REDUCTION_RATIO = 0.60


# =========================================================
# CONTENT CLASSIFICATION
# =========================================================

CONTENT_TYPE_NORMAL = "normal_news"
CONTENT_TYPE_SENSITIVE = "sensitive_content"
CONTENT_TYPE_UNCERTAIN = "uncertain"


# =========================================================
# CRITICAL LANGUAGE MARKERS
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
# REQUIRED REDUCTION
# =========================================================

def calculate_required_reduction_ratio(
    original_length: int,
    target_length: int
) -> float:

    if original_length <= 0:
        return 0.0

    if target_length >= original_length:
        return 0.0

    if target_length <= 0:
        return 1.0

    return (
        (
            original_length
            - target_length
        )
        / original_length
    )


# =========================================================
# EXTRACT NUMBERS
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
# CONTENT CLASSIFICATION INSTRUCTION
#
# AI فقط باید نوع محتوا را تعیین کند.
#
# هیچ خلاصه‌ای در این مرحله ساخته نمی‌شود.
# =========================================================

def build_content_classification_instruction() -> str:

    return (
        "وظیفه شما فقط تشخیص میزان حساسیت این متن "
        "برای خلاصه‌سازی خبری است. "
        "متن را خلاصه نکن و درباره محتوای آن توضیح نده. "

        "اگر متن یک خبر عادی، گزارش رسانه‌ای، روایت رویداد، "
        "گزارش سیاسی، توضیح زمینه‌ای یا متن خبری قابل "
        "فشرده‌سازی است، فقط این عبارت را برگردان:\n"
        "NORMAL_NEWS\n\n"

        "اگر متن شامل بیانیه رسمی، اعلامیه رسمی، "
        "مفاد توافق، تفاهم‌نامه، قرارداد، قطعنامه، "
        "شروط رسمی، بندهای حقوقی، فهرست تعهدات، "
        "متن قانونی، دستورالعمل رسمی یا متنی است که "
        "حذف جزئیات آن ممکن است معنای حقوقی یا رسمی "
        "را تغییر دهد، فقط این عبارت را برگردان:\n"
        "SENSITIVE_CONTENT\n\n"

        "اگر با اطمینان قابل تشخیص نیست، فقط این عبارت "
        "را برگردان:\n"
        "UNCERTAIN\n\n"

        "هیچ عبارت دیگری ننویس."
    )


# =========================================================
# PARSE AI CLASSIFICATION
# =========================================================

def parse_content_classification(
    value: Optional[str]
) -> str:

    value = (
        normalize_text(
            value
        )
        .upper()
    )

    if not value:

        return CONTENT_TYPE_UNCERTAIN

    if (
        "SENSITIVE_CONTENT"
        in value
    ):

        return CONTENT_TYPE_SENSITIVE

    if (
        "NORMAL_NEWS"
        in value
    ):

        return CONTENT_TYPE_NORMAL

    if (
        "UNCERTAIN"
        in value
    ):

        return CONTENT_TYPE_UNCERTAIN

    return CONTENT_TYPE_UNCERTAIN


# =========================================================
# AI CONTENT CLASSIFICATION
# =========================================================

def classify_content_with_ai(
    original_text: str,
    summarizer: Callable[
        [str, str, int],
        str
    ]
) -> str:

    instruction = (
        build_content_classification_instruction()
    )

    try:

        response = summarizer(
            original_text,
            instruction,
            64
        )

    except Exception as e:

        logger.exception(
            f"❌ AI content classification failed | "
            f"{e}"
        )

        return CONTENT_TYPE_UNCERTAIN

    classification = (
        parse_content_classification(
            response
        )
    )

    logger.info(
        f"🧠 AI content classification | "
        f"type={classification}"
    )

    return classification


# =========================================================
# POLICY FOR CONTENT TYPE
# =========================================================

def get_max_reduction_for_content_type(
    content_type: str
) -> float:

    if (
        content_type
        == CONTENT_TYPE_NORMAL
    ):

        return (
            NORMAL_NEWS_MAX_REDUCTION_RATIO
        )

    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
    ):

        return (
            SENSITIVE_CONTENT_MAX_REDUCTION_RATIO
        )

    return (
        UNCERTAIN_CONTENT_MAX_REDUCTION_RATIO
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
    ),
    content_type: str = (
        CONTENT_TYPE_UNCERTAIN
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
    # NUMBERS
    # =====================================================

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

    new_numbers = (
        summary_numbers
        - original_numbers
    )

    missing_numbers = (
        original_numbers
        - summary_numbers
    )

    if new_numbers:

        errors.append(
            "new_numbers_detected"
        )

    # در متن حساس حذف عدد هم خطرناک محسوب می‌شود.
    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
        and missing_numbers
    ):

        errors.append(
            "sensitive_numbers_lost"
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
    # CERTAINTY / ATTRIBUTION
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

        "content_type":
            content_type,

        "max_reduction_ratio":
            max_reduction_ratio,

        "reduction_ratio":
            reduction_ratio,

        "new_numbers": sorted(
            new_numbers
        ),

        "missing_numbers": sorted(
            missing_numbers
        ),

        "original_numbers": sorted(
            original_numbers
        ),

        "summary_numbers": sorted(
            summary_numbers
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
# SMART SUMMARIZATION INSTRUCTION
#
# مهم:
#
# AI خودش باید تشخیص دهد چه چیزهایی برای معنای خبر
# اصلی هستند و چه چیزهایی قابل حذف‌اند.
# =========================================================

def build_summarization_instruction(
    target_length: int,
    content_type: str = CONTENT_TYPE_NORMAL
) -> str:

    sensitive_instruction = ""

    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
    ):

        sensitive_instruction = (
            "این متن از نوع حساس تشخیص داده شده است. "
            "در حذف جزئیات بسیار محافظه‌کار باش. "
            "مفاد، بندها، شروط، تعهدات، اعداد، تاریخ‌ها، "
            "استثناها و روابط میان بندها را حذف یا ادغام نکن. "
        )

    return (
        "متن زیر یک محتوای خبری است. "

        "وظیفه شما فشرده‌سازی معنایی و وفادارانه متن است. "

        "خودت تشخیص بده کدام بخش‌ها هسته اصلی خبر، "
        "اطلاعات حیاتی، علت رویداد، نتیجه اصلی، "
        "موضع بازیگران، داده‌های ضروری و اطلاعاتی هستند "
        "که حذف آنها معنای خبر را تغییر می‌دهد. "

        "در مقابل می‌توانی تکرارها، توضیحات زائد، "
        "عبارات کش‌دار، جزئیات کم‌اهمیت، توصیف‌های تکراری، "
        "زمینه‌های غیرضروری و بخش‌هایی را که بدون آسیب "
        "به معنای اصلی خبر قابل حذف‌اند فشرده یا حذف کنی. "

        + sensitive_instruction +

        "حق تحلیل، تفسیر، نتیجه‌گیری، قضاوت، "
        "اصلاح محتوایی یا افزودن اطلاعات جدید را نداری. "

        "هیچ واقعیت جدیدی تولید نکن. "

        "هیچ عدد، تاریخ، نام، سمت، مکان، نهاد یا "
        "نسبت دادن سخنی را تغییر نده. "

        "اگر اطلاعاتی را حذف می‌کنی باید مطمئن باشی "
        "حذف آن معنای اصلی خبر را تغییر نمی‌دهد. "

        "میزان قطعیت را دقیقاً حفظ کن. "

        "احتمال را به قطعیت تبدیل نکن. "
        "ادعا را به واقعیت قطعی تبدیل نکن. "

        "اگر یک ادعا به شخص، رسانه یا مقام خاصی "
        "نسبت داده شده است این نسبت را حفظ کن. "

        "در صورت تعارض میان کوتاه‌شدن و وفاداری، "
        "وفاداری به خبر اولویت مطلق دارد. "

        f"خروجی نهایی نباید بیشتر از {target_length} "
        "کاراکتر باشد. "

        "فقط متن نهایی خلاصه‌شده را برگردان."
    )


# =========================================================
# SMART SUMMARIZE
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
    # PRESERVE ORIGINAL
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
                "summarizer_called": False,
                "classifier_called": False,
                "content_type": (
                    CONTENT_TYPE_UNCERTAIN
                )
            }
        )

    # =====================================================
    # ALREADY FITS
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
                "summarizer_called": False,
                "classifier_called": False,
                "content_type": (
                    CONTENT_TYPE_UNCERTAIN
                )
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
                "summarizer_called": False,
                "classifier_called": False,
                "content_type": (
                    CONTENT_TYPE_UNCERTAIN
                )
            }
        )

    # =====================================================
    # NO PROVIDER
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
                "summarizer_called": False,
                "classifier_called": False,
                "content_type": (
                    CONTENT_TYPE_UNCERTAIN
                )
            }
        )

    # =====================================================
    # REQUIRED REDUCTION
    # =====================================================

    required_reduction_ratio = (
        calculate_required_reduction_ratio(
            original_length,
            target_length
        )
    )

    # =====================================================
    # ABSOLUTE HARD LIMIT
    #
    # اگر نیاز به حذف 60٪ یا بیشتر باشد،
    # Provider حتی برای تشخیص هم فراخوانی نمی‌شود.
    #
    # این رفتار همچنین با تست محافظتی قبلی سازگار می‌ماند.
    # =====================================================

    if (
        required_reduction_ratio
        >= ABSOLUTE_MAX_REDUCTION_RATIO
    ):

        logger.warning(
            f"⚠️ Smart summarization skipped | "
            f"required_reduction="
            f"{required_reduction_ratio:.3f} | "
            f"absolute_max="
            f"{ABSOLUTE_MAX_REDUCTION_RATIO:.3f}"
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
                "effective_max_reduction_ratio": (
                    ABSOLUTE_MAX_REDUCTION_RATIO
                ),
                "summarizer_called": False,
                "classifier_called": False,
                "content_type": (
                    CONTENT_TYPE_UNCERTAIN
                )
            }
        )

    # =====================================================
    # ADAPTIVE POLICY
    #
    # تا سقف قدیمی 40٪:
    # همان رفتار قبلی و بدون Classification.
    #
    # بیش از 40٪:
    # AI خودش حساسیت متن را تشخیص می‌دهد.
    # =====================================================

    content_type = (
        CONTENT_TYPE_NORMAL
    )

    classifier_called = False

    effective_max_reduction_ratio = (
        max_reduction_ratio
    )

    if (
        required_reduction_ratio
        > max_reduction_ratio
    ):

        classifier_called = True

        content_type = (
            classify_content_with_ai(
                raw_original_text,
                summarizer
            )
        )

        effective_max_reduction_ratio = (
            get_max_reduction_for_content_type(
                content_type
            )
        )

        logger.info(
            f"🧠 Adaptive summarization policy | "
            f"content_type={content_type} | "
            f"required="
            f"{required_reduction_ratio:.3f} | "
            f"allowed="
            f"{effective_max_reduction_ratio:.3f}"
        )

        if (
            required_reduction_ratio
            > effective_max_reduction_ratio
        ):

            logger.warning(
                f"⚠️ Adaptive summary rejected "
                f"before generation | "
                f"content_type={content_type} | "
                f"required="
                f"{required_reduction_ratio:.3f} | "
                f"allowed="
                f"{effective_max_reduction_ratio:.3f}"
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
                reason=(
                    "content_policy_reduction_limit"
                ),
                metadata={
                    "required_reduction_ratio": (
                        required_reduction_ratio
                    ),
                    "effective_max_reduction_ratio": (
                        effective_max_reduction_ratio
                    ),
                    "summarizer_called": False,
                    "classifier_called": True,
                    "content_type": (
                        content_type
                    )
                }
            )

    # =====================================================
    # BUILD SMART INSTRUCTION
    # =====================================================

    instruction = (
        build_summarization_instruction(
            target_length,
            content_type=content_type
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
                "summarizer_called": True,
                "classifier_called": (
                    classifier_called
                ),
                "content_type": (
                    content_type
                ),
                "effective_max_reduction_ratio": (
                    effective_max_reduction_ratio
                )
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
                effective_max_reduction_ratio
            ),
            content_type=content_type
        )
    )

    if not validation[
        "valid"
    ]:

        logger.warning(
            f"⚠️ Smart summary rejected | "
            f"content_type={content_type} | "
            f"errors="
            f"{validation['errors']}"
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
            reason="validation_failed",
            metadata={
                "validation": validation,
                "candidate_summary": (
                    generated
                ),
                "summarizer_called": True,
                "classifier_called": (
                    classifier_called
                ),
                "content_type": (
                    content_type
                ),
                "effective_max_reduction_ratio": (
                    effective_max_reduction_ratio
                )
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
        f"content_type={content_type} | "
        f"before={original_length} | "
        f"after={len(generated)} | "
        f"target={target_length} | "
        f"reduction="
        f"{reduction_ratio:.3f} | "
        f"max_allowed="
        f"{effective_max_reduction_ratio:.3f}"
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
            "summarizer_called": True,
            "classifier_called": (
                classifier_called
            ),
            "content_type": (
                content_type
            ),
            "effective_max_reduction_ratio": (
                effective_max_reduction_ratio
            ),
            "required_reduction_ratio": (
                required_reduction_ratio
            )
        }
    )
