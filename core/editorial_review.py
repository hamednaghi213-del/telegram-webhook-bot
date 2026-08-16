import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from core.smart_summarizer import (
    normalize_text,
    summarize_text_safely,
)

from core.ai_summarizer_provider import (
    gemini_provider_configured,
    summarize_with_gemini,
)


logger = logging.getLogger(__name__)


# =========================================================
# EDITORIAL CONTENT TYPES
# =========================================================

CONTENT_TYPE_NORMAL_NEWS = "normal_news"
CONTENT_TYPE_NEWS_ANALYSIS = "news_analysis"
CONTENT_TYPE_OPINION_NOTE = "opinion_note"
CONTENT_TYPE_SENSITIVE = "sensitive_content"
CONTENT_TYPE_UNCERTAIN = "uncertain"


# =========================================================
# REVIEW ACTIONS
# =========================================================

ACTION_PUBLISH_DIRECT = "publish_direct"
ACTION_NEEDS_APPROVAL = "needs_approval"
ACTION_PUBLISH_ORIGINAL = "publish_original"
ACTION_UNCERTAIN = "uncertain"


# =========================================================
# REVIEW POLICY
# =========================================================

DEFAULT_REVIEW_TARGET = 950

OPINION_NOTE_MAX_REDUCTION_RATIO = 0.85
NEWS_ANALYSIS_MAX_REDUCTION_RATIO = 0.75

SENSITIVE_MAX_REDUCTION_RATIO = 0.30
UNCERTAIN_MAX_REDUCTION_RATIO = 0.40


# =========================================================
# RESULT OBJECT
# =========================================================

@dataclass
class EditorialReviewResult:

    content_type: str

    action: str

    needs_approval: bool

    original_text: str

    suggested_text: str

    summary_success: bool

    target_length: int

    original_length: int

    suggested_length: int

    reason: str

    metadata: Dict[str, Any]


# =========================================================
# CLASSIFICATION INSTRUCTION
# =========================================================

def build_editorial_classification_instruction() -> str:

    return (
        "وظیفه شما فقط تشخیص نوع محتوای رسانه‌ای متن زیر است. "
        "متن را خلاصه نکن و درباره آن توضیح نده. "

        "اگر متن یک خبر عادی، گزارش رویداد، گزارش رسانه‌ای، "
        "اطلاع‌رسانی خبری یا روایت مستقیم از یک اتفاق است، "
        "فقط این عبارت را برگردان:\n"
        "NORMAL_NEWS\n\n"

        "اگر متن یک تحلیل خبری است که علاوه بر خبر، "
        "علت‌ها، پیامدها، رفتار بازیگران، روندها یا "
        "تفسیر تحلیلی رویداد را بررسی می‌کند، فقط این عبارت را برگردان:\n"
        "NEWS_ANALYSIS\n\n"

        "اگر متن یک یادداشت، سرمقاله، دیدگاه نویسنده، "
        "مقاله تحلیلی شخصی، استدلال سیاست خارجی یا "
        "متنی است که یک تز یا استدلال مرکزی را دنبال می‌کند، "
        "فقط این عبارت را برگردان:\n"
        "OPINION_NOTE\n\n"

        "اگر متن شامل بیانیه رسمی، اعلامیه رسمی، مفاد توافق، "
        "تفاهم‌نامه، قرارداد، قطعنامه، شروط رسمی، بندهای حقوقی، "
        "فهرست تعهدات، متن قانونی یا محتوایی است که حذف جزئیات "
        "می‌تواند معنای حقوقی یا رسمی آن را تغییر دهد، "
        "فقط این عبارت را برگردان:\n"
        "SENSITIVE_CONTENT\n\n"

        "اگر با اطمینان قابل تشخیص نیست، فقط این عبارت را برگردان:\n"
        "UNCERTAIN\n\n"

        "هیچ عبارت دیگری ننویس."
    )


# =========================================================
# PARSE CLASSIFICATION
# =========================================================

def parse_editorial_classification(
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

    if "OPINION_NOTE" in value:
        return CONTENT_TYPE_OPINION_NOTE

    if "NEWS_ANALYSIS" in value:
        return CONTENT_TYPE_NEWS_ANALYSIS

    if "SENSITIVE_CONTENT" in value:
        return CONTENT_TYPE_SENSITIVE

    if "NORMAL_NEWS" in value:
        return CONTENT_TYPE_NORMAL_NEWS

    if "UNCERTAIN" in value:
        return CONTENT_TYPE_UNCERTAIN

    return CONTENT_TYPE_UNCERTAIN


# =========================================================
# CLASSIFY WITH AI
# =========================================================

def classify_editorial_content(
    original_text: str,
    classifier: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ] = None
) -> str:

    original_text = normalize_text(
        original_text
    )

    if not original_text:
        return CONTENT_TYPE_UNCERTAIN

    if classifier is None:

        if not gemini_provider_configured():

            logger.warning(
                "⚠️ Editorial classifier unavailable | "
                "Gemini provider not configured"
            )

            return CONTENT_TYPE_UNCERTAIN

        classifier = summarize_with_gemini

    instruction = (
        build_editorial_classification_instruction()
    )

    try:

        response = classifier(
            original_text,
            instruction,
            64
        )

    except Exception as e:

        logger.exception(
            f"❌ Editorial classification failed | {e}"
        )

        return CONTENT_TYPE_UNCERTAIN

    content_type = (
        parse_editorial_classification(
            response
        )
    )

    logger.info(
        f"🧠 Editorial content classified | "
        f"type={content_type}"
    )

    return content_type


# =========================================================
# SUMMARY POLICY
# =========================================================

def get_review_max_reduction_ratio(
    content_type: str
) -> float:

    if (
        content_type
        == CONTENT_TYPE_OPINION_NOTE
    ):

        return (
            OPINION_NOTE_MAX_REDUCTION_RATIO
        )

    if (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        return (
            NEWS_ANALYSIS_MAX_REDUCTION_RATIO
        )

    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
    ):

        return (
            SENSITIVE_MAX_REDUCTION_RATIO
        )

    return (
        UNCERTAIN_MAX_REDUCTION_RATIO
    )


# =========================================================
# REVIEW INSTRUCTION
# =========================================================

def build_editorial_summary_instruction(
    target_length: int,
    content_type: str
) -> str:

    if (
        content_type
        == CONTENT_TYPE_OPINION_NOTE
    ):

        return (
            "متن زیر یک یادداشت یا سرمقاله تحلیلی است. "
            "آن را برای انتشار رسانه‌ای کوتاه و وفادار بازنویسی کن. "

            "تز اصلی نویسنده، استدلال‌های کلیدی، رابطه علت و نتیجه، "
            "نمونه‌های ضروری و جمع‌بندی اصلی را حفظ کن. "

            "تکرارها، مثال‌های فرعی، توضیحات طولانی، "
            "عبارات کش‌دار و جزئیاتی را که برای فهم استدلال اصلی "
            "ضروری نیستند حذف یا فشرده کن. "

            "نظر نویسنده را به خبر قطعی تبدیل نکن. "
            "اگر متن ماهیت دیدگاهی دارد، نسبت دیدگاه به نویسنده "
            "یا ماهیت تحلیلی آن باید در معنا حفظ شود. "

            "هیچ تحلیل، نتیجه‌گیری یا دیدگاه تازه‌ای از خودت اضافه نکن. "
            "هیچ واقعیت، عدد، نام، تاریخ یا داده تازه‌ای تولید نکن. "

            f"خروجی نهایی باید حداکثر {target_length} کاراکتر باشد. "
            "فقط متن نهایی را برگردان."
        )

    if (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        return (
            "متن زیر یک تحلیل خبری است. "
            "آن را به نسخه‌ای کوتاه، منسجم و وفادار برای انتشار رسانه‌ای تبدیل کن. "

            "اصل رویداد، مهم‌ترین علت‌ها، رفتار بازیگران، "
            "روند اثرگذار و پیامد اصلی را حفظ کن. "

            "توضیحات تکراری، مثال‌های فرعی و زمینه‌های غیرضروری "
            "را حذف یا فشرده کن. "

            "تحلیل تازه، قضاوت تازه یا نتیجه‌گیری خارج از متن اضافه نکن. "
            "هیچ عدد، نام، تاریخ یا واقعیت جدیدی نساز. "

            f"خروجی نهایی باید حداکثر {target_length} کاراکتر باشد. "
            "فقط متن نهایی را برگردان."
        )

    return (
        "متن را بدون تغییر محتوایی حفظ کن. "
        "فقط در حدی کوتاه کن که هیچ اطلاعات مهم، رسمی یا حساس حذف نشود. "
        f"خروجی نهایی نباید بیشتر از {target_length} کاراکتر باشد. "
        "فقط متن نهایی را برگردان."
    )


# =========================================================
# EDITORIAL SUMMARY
# =========================================================

def summarize_editorial_content(
    original_text: str,
    content_type: str,
    target_length: int = (
        DEFAULT_REVIEW_TARGET
    ),
    summarizer: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ] = None
):

    original_text = normalize_text(
        original_text
    )

    if not original_text:
        return None

    if summarizer is None:

        if not gemini_provider_configured():

            logger.warning(
                "⚠️ Editorial summarizer unavailable | "
                "Gemini provider not configured"
            )

            return None

        summarizer = summarize_with_gemini

    max_reduction_ratio = (
        get_review_max_reduction_ratio(
            content_type
        )
    )

    instruction = (
        build_editorial_summary_instruction(
            target_length,
            content_type
        )
    )

    # Wrapper تا smart_summarizer همان Provider را
    # با Instruction مخصوص Editorial صدا بزند.
    def editorial_provider(
        text: str,
        _instruction: str,
        provider_target: int
    ) -> str:

        return summarizer(
            text,
            instruction,
            provider_target
        )

    result = (
        summarize_text_safely(
            original_text=original_text,
            target_length=target_length,
            summarizer=editorial_provider,
            max_reduction_ratio=(
                max_reduction_ratio
            )
        )
    )

    return result


# =========================================================
# MAIN REVIEW ANALYZER
# =========================================================

def analyze_editorial_content(
    original_text: str,
    target_length: int = (
        DEFAULT_REVIEW_TARGET
    ),
    classifier: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ] = None,
    summarizer: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ] = None
) -> EditorialReviewResult:

    original_text = normalize_text(
        original_text
    )

    original_length = len(
        original_text
    )

    if not original_text:

        return EditorialReviewResult(
            content_type=CONTENT_TYPE_UNCERTAIN,
            action=ACTION_PUBLISH_DIRECT,
            needs_approval=False,
            original_text="",
            suggested_text="",
            summary_success=True,
            target_length=target_length,
            original_length=0,
            suggested_length=0,
            reason="empty_text",
            metadata={}
        )

    # =====================================================
    # CLASSIFICATION
    # =====================================================

    content_type = (
        classify_editorial_content(
            original_text,
            classifier=classifier
        )
    )

    # =====================================================
    # NORMAL NEWS
    #
    # این ماژول در خبر عادی دخالت نمی‌کند.
    # =====================================================

    if (
        content_type
        == CONTENT_TYPE_NORMAL_NEWS
    ):

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_PUBLISH_DIRECT,
            needs_approval=False,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=True,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="normal_news_direct",
            metadata={
                "classification_only": True
            }
        )

    # =====================================================
    # SENSITIVE CONTENT
    #
    # فعلاً خودکار خلاصه نمی‌شود.
    # =====================================================

    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
    ):

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_PUBLISH_ORIGINAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="sensitive_content_preserved",
            metadata={
                "automatic_summary": False
            }
        )

    # =====================================================
    # UNCERTAIN
    #
    # محافظه‌کارانه عمل می‌کنیم.
    # =====================================================

    if (
        content_type
        == CONTENT_TYPE_UNCERTAIN
    ):

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_UNCERTAIN,
            needs_approval=True,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="uncertain_content",
            metadata={
                "automatic_summary": False
            }
        )

    # =====================================================
    # OPINION NOTE / NEWS ANALYSIS
    # =====================================================

    summary_result = (
        summarize_editorial_content(
            original_text=original_text,
            content_type=content_type,
            target_length=target_length,
            summarizer=summarizer
        )
    )

    if (
        summary_result is None
        or not summary_result.success
    ):

        metadata = {}

        if summary_result is not None:

            metadata = {
                "summary_reason":
                    summary_result.reason,
                "summary_metadata":
                    summary_result.metadata
            }

        logger.warning(
            f"⚠️ Editorial summary unavailable | "
            f"type={content_type}"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="summary_unavailable",
            metadata=metadata
        )

    suggested_text = (
        normalize_text(
            summary_result.summary_text
        )
    )

    logger.info(
        f"✅ Editorial review prepared | "
        f"type={content_type} | "
        f"before={original_length} | "
        f"after={len(suggested_text)} | "
        f"needs_approval=True"
    )

    return EditorialReviewResult(
        content_type=content_type,
        action=ACTION_NEEDS_APPROVAL,
        needs_approval=True,
        original_text=original_text,
        suggested_text=suggested_text,
        summary_success=True,
        target_length=target_length,
        original_length=original_length,
        suggested_length=len(
            suggested_text
        ),
        reason="editorial_summary_ready",
        metadata={
            "summary_reason":
                summary_result.reason,
            "summary_metadata":
                summary_result.metadata
        }
    )


# =========================================================
# PUBLIC HELPER
# =========================================================

def needs_editorial_approval(
    original_text: str
) -> bool:

    result = (
        analyze_editorial_content(
            original_text
        )
    )

    return bool(
        result.needs_approval
    )
