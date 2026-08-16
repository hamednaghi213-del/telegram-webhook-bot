import logging

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
)

from core.smart_summarizer import (
    CONTENT_TYPE_NORMAL,
    normalize_text,
    validate_summary,
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
# REGENERATION POLICY
# =========================================================

MAX_REGENERATION_COUNT = 3

REGENERATION_TARGET_MARGIN = 40

MIN_REGENERATION_TARGET = 300


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
            f"❌ Editorial classification failed | "
            f"{e}"
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
# VALIDATOR CONTENT TYPE
#
# Editorial Note / Analysis ماهیت حقوقی و حساس ندارند.
# برای استفاده از Validator ضدتحریف، در این لایه
# به عنوان محتوای خبری عادی اعتبارسنجی می‌شوند.
# =========================================================

def get_validator_content_type(
    content_type: str
) -> str:

    if (
        content_type
        in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
    ):

        return CONTENT_TYPE_NORMAL

    return CONTENT_TYPE_NORMAL


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

            "آن را برای انتشار رسانه‌ای به نسخه‌ای کوتاه، "
            "منسجم و وفادار تبدیل کن. "

            "ابتدا تز اصلی نویسنده را تشخیص بده. "

            "سپس فقط استدلال‌های کلیدی، رابطه علت و نتیجه، "
            "نمونه‌های ضروری و جمع‌بندی اصلی را حفظ کن. "

            "تکرارها، مثال‌های مشابه، توضیحات طولانی، "
            "عبارات کش‌دار و جزئیاتی را که برای فهم استدلال "
            "اصلی ضروری نیستند حذف یا فشرده کن. "

            "ترتیب منطقی استدلال باید حفظ شود. "

            "نظر نویسنده را به خبر قطعی تبدیل نکن. "

            "اگر متن ماهیت دیدگاهی دارد، این ماهیت باید "
            "در نسخه کوتاه نیز از نظر معنایی حفظ شود. "

            "هیچ تحلیل، نتیجه‌گیری یا دیدگاه تازه‌ای "
            "از خودت اضافه نکن. "

            "هیچ واقعیت، عدد، نام، تاریخ یا داده تازه‌ای "
            "تولید نکن. "

            "هدف، کوتاه‌کردن هوشمندانه متن است، نه بریدن "
            "مکانیکی جملات. "

            f"خروجی نهایی باید حداکثر {target_length} "
            "کاراکتر باشد. "

            "فقط متن نهایی را برگردان."
        )

    if (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        return (
            "متن زیر یک تحلیل خبری است. "

            "آن را به نسخه‌ای کوتاه، منسجم و وفادار "
            "برای انتشار رسانه‌ای تبدیل کن. "

            "اصل رویداد، مهم‌ترین علت‌ها، رفتار بازیگران، "
            "روند اثرگذار و پیامد اصلی را حفظ کن. "

            "توضیحات تکراری، مثال‌های فرعی و زمینه‌های "
            "غیرضروری را حذف یا فشرده کن. "

            "رابطه منطقی میان خبر و تحلیل باید حفظ شود. "

            "تحلیل تازه، قضاوت تازه یا نتیجه‌گیری خارج "
            "از متن اضافه نکن. "

            "هیچ عدد، نام، تاریخ یا واقعیت جدیدی نساز. "

            "هدف، فشرده‌سازی معنایی است و نه قطع مکانیکی متن. "

            f"خروجی نهایی باید حداکثر {target_length} "
            "کاراکتر باشد. "

            "فقط متن نهایی را برگردان."
        )

    return (
        "متن را بدون تغییر محتوایی حفظ کن. "

        "فقط در حدی کوتاه کن که هیچ اطلاعات مهم، "
        "رسمی یا حساس حذف نشود. "

        f"خروجی نهایی نباید بیشتر از {target_length} "
        "کاراکتر باشد. "

        "فقط متن نهایی را برگردان."
    )


# =========================================================
# REGENERATION INSTRUCTION
# =========================================================

def build_editorial_regeneration_instruction(
    target_length: int,
    content_type: str,
    previous_summary: str
) -> str:

    previous_summary = normalize_text(
        previous_summary
    )

    if (
        content_type
        == CONTENT_TYPE_OPINION_NOTE
    ):

        type_instruction = (
            "متن اصلی یک یادداشت یا سرمقاله تحلیلی است. "
            "تز اصلی نویسنده، منطق استدلال، مهم‌ترین شواهد "
            "و نتیجه اصلی باید حفظ شوند. "
        )

    elif (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        type_instruction = (
            "متن اصلی یک تحلیل خبری است. "
            "اصل رویداد، بازیگران اصلی، علت‌ها، روند اثرگذار "
            "و پیامد اصلی باید حفظ شوند. "
        )

    else:

        type_instruction = (
            "ساختار و معنای اصلی متن باید حفظ شود. "
        )

    return (
        "این متن قبلاً یک بار برای انتشار رسانه‌ای "
        "خلاصه شده است. "

        "وظیفه تو تولید یک نسخه جایگزین و بهتر است. "

        "مبنای کار فقط متن اصلی است. "

        "خلاصه قبلی صرفاً برای تشخیص نقاط ضعف نسخه قبلی "
        "در اختیار تو قرار گرفته و نباید مبنای اصلی "
        "بازنویسی باشد. "

        + type_instruction +

        "متن اصلی را دوباره از ابتدا بررسی کن. "

        "تشخیص بده در خلاصه قبلی چه نکات مهمی بیش از حد "
        "فشرده شده، کم‌رنگ شده یا می‌توانسته دقیق‌تر "
        "بیان شود. "

        "نسخه جدید نباید صرفاً تغییر واژه‌های خلاصه قبلی باشد. "

        "اگر خلاصه قبلی مناسب بوده، باز هم ساختار بیان را "
        "بهبود بده ولی معنای اصلی را تغییر نده. "

        "تکرارها، توضیحات زائد، مثال‌های فرعی و عبارت‌های "
        "کش‌دار را حذف کن. "

        "هیچ تحلیل، قضاوت، نتیجه‌گیری، واقعیت، عدد، نام، "
        "تاریخ یا اطلاعات تازه‌ای از خودت اضافه نکن. "

        "میزان قطعیت و نسبت دادن دیدگاه‌ها را تغییر نده. "

        "نسخه جدید باید مستقل، روان، منسجم و قابل انتشار باشد. "

        f"نسخه جدید نباید بیشتر از {target_length} "
        "کاراکتر باشد. "

        "فقط نسخه جدید را برگردان. "

        "\n\n"
        "خلاصه قبلی فقط برای مقایسه:\n"
        "-----\n"
        f"{previous_summary}\n"
        "-----"
    )


# =========================================================
# PROVIDER RESOLUTION
# =========================================================

def resolve_summarizer(
    summarizer: Optional[
        Callable[
            [str, str, int],
            str
        ]
    ]
) -> Optional[
    Callable[
        [str, str, int],
        str
    ]
]:

    if summarizer is not None:
        return summarizer

    if not gemini_provider_configured():

        logger.warning(
            "⚠️ Editorial summarizer unavailable | "
            "Gemini provider not configured"
        )

        return None

    return summarize_with_gemini


# =========================================================
# EDITORIAL VALIDATION
# =========================================================

def validate_editorial_candidate(
    original_text: str,
    candidate_text: str,
    target_length: int,
    content_type: str
) -> Dict[str, Any]:

    max_reduction_ratio = (
        get_review_max_reduction_ratio(
            content_type
        )
    )

    return validate_summary(
        original_text=original_text,
        summary_text=candidate_text,
        target_length=target_length,
        max_reduction_ratio=(
            max_reduction_ratio
        ),
        content_type=(
            get_validator_content_type(
                content_type
            )
        )
    )


# =========================================================
# PROVIDER GENERATION
# =========================================================

def generate_editorial_candidate(
    original_text: str,
    instruction: str,
    target_length: int,
    content_type: str,
    summarizer: Callable[
        [str, str, int],
        str
    ]
) -> Dict[str, Any]:

    try:

        candidate = summarizer(
            original_text,
            instruction,
            target_length
        )

    except Exception as e:

        logger.exception(
            f"❌ Editorial AI generation failed | "
            f"{e}"
        )

        return {
            "success": False,
            "candidate": "",
            "validation": None,
            "reason": "provider_error",
            "error": str(
                e
            )
        }

    candidate = normalize_text(
        candidate
    )

    validation = (
        validate_editorial_candidate(
            original_text=original_text,
            candidate_text=candidate,
            target_length=target_length,
            content_type=content_type
        )
    )

    if not validation[
        "valid"
    ]:

        logger.warning(
            f"⚠️ Editorial candidate rejected | "
            f"type={content_type} | "
            f"errors={validation['errors']} | "
            f"output={len(candidate)} | "
            f"target={target_length}"
        )

        return {
            "success": False,
            "candidate": candidate,
            "validation": validation,
            "reason": "validation_failed",
            "error": None
        }

    return {
        "success": True,
        "candidate": candidate,
        "validation": validation,
        "reason": "accepted",
        "error": None
    }


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
) -> Optional[Dict[str, Any]]:

    original_text = normalize_text(
        original_text
    )

    if not original_text:
        return None

    if (
        content_type
        not in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
    ):

        logger.info(
            f"ℹ️ Editorial automatic summary skipped | "
            f"type={content_type}"
        )

        return None

    resolved_summarizer = (
        resolve_summarizer(
            summarizer
        )
    )

    if resolved_summarizer is None:
        return None

    if len(original_text) <= target_length:

        validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=original_text,
                target_length=target_length,
                content_type=content_type
            )
        )

        return {
            "success": True,
            "candidate": original_text,
            "validation": validation,
            "reason": "already_fits",
            "summarizer_called": False
        }

    instruction = (
        build_editorial_summary_instruction(
            target_length,
            content_type
        )
    )

    result = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=target_length,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    result[
        "summarizer_called"
    ] = True

    return result


# =========================================================
# REGENERATE EDITORIAL SUMMARY
# =========================================================

def regenerate_editorial_summary(
    original_text: str,
    previous_summary: str,
    content_type: str,
    target_length: int = (
        DEFAULT_REVIEW_TARGET
    ),
    regeneration_count: int = 0,
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

    previous_summary = normalize_text(
        previous_summary
    )

    original_length = len(
        original_text
    )

    # =====================================================
    # BASIC SAFETY
    # =====================================================

    if not original_text:

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text="",
            suggested_text="",
            summary_success=False,
            target_length=target_length,
            original_length=0,
            suggested_length=0,
            reason="regeneration_original_empty",
            metadata={
                "regeneration_count":
                    regeneration_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

    if (
        content_type
        not in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
    ):

        logger.warning(
            f"⚠️ Editorial regeneration blocked | "
            f"type={content_type}"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=(
                previous_summary
                or original_text
            ),
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason="regeneration_not_allowed_for_content_type",
            metadata={
                "regeneration_count":
                    regeneration_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

    # =====================================================
    # MAXIMUM ATTEMPTS
    # =====================================================

    if (
        regeneration_count
        >= MAX_REGENERATION_COUNT
    ):

        logger.warning(
            f"⚠️ Editorial regeneration limit reached | "
            f"count={regeneration_count} | "
            f"max={MAX_REGENERATION_COUNT}"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=(
                previous_summary
                or original_text
            ),
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason="regeneration_limit_reached",
            metadata={
                "regeneration_count":
                    regeneration_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT,
                "can_regenerate": False
            }
        )

    # =====================================================
    # PROVIDER
    # =====================================================

    resolved_summarizer = (
        resolve_summarizer(
            summarizer
        )
    )

    if resolved_summarizer is None:

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=(
                previous_summary
                or original_text
            ),
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason="regeneration_provider_unavailable",
            metadata={
                "regeneration_count":
                    regeneration_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

    # =====================================================
    # TARGET
    #
    # کمی فضای امن ایجاد می‌کنیم تا خروجی AI
    # از سقف اصلی عبور نکند.
    # =====================================================

    regeneration_target = max(
        MIN_REGENERATION_TARGET,
        target_length
        - REGENERATION_TARGET_MARGIN
    )

    regeneration_target = min(
        regeneration_target,
        target_length
    )

    # =====================================================
    # INSTRUCTION
    # =====================================================

    instruction = (
        build_editorial_regeneration_instruction(
            target_length=(
                regeneration_target
            ),
            content_type=content_type,
            previous_summary=previous_summary
        )
    )

    logger.info(
        f"🔄 Editorial regeneration started | "
        f"type={content_type} | "
        f"count={regeneration_count + 1}/"
        f"{MAX_REGENERATION_COUNT} | "
        f"original={original_length} | "
        f"previous={len(previous_summary)} | "
        f"target={regeneration_target}"
    )

    # =====================================================
    # GENERATE FROM ORIGINAL
    # =====================================================

    generation = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=regeneration_target,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    next_count = (
        regeneration_count
        + 1
    )

    # =====================================================
    # FAILED
    #
    # Previous Summary حفظ می‌شود.
    # =====================================================

    if not generation[
        "success"
    ]:

        logger.warning(
            f"⚠️ Editorial regeneration rejected | "
            f"type={content_type} | "
            f"count={next_count} | "
            f"reason={generation['reason']}"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=(
                previous_summary
                or original_text
            ),
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason="regeneration_failed",
            metadata={
                "regeneration_count":
                    next_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT,
                "can_regenerate": (
                    next_count
                    < MAX_REGENERATION_COUNT
                ),
                "generation_reason":
                    generation[
                        "reason"
                    ],
                "validation":
                    generation.get(
                        "validation"
                    ),
                "failed_candidate":
                    generation.get(
                        "candidate",
                        ""
                    )
            }
        )

    new_summary = normalize_text(
        generation[
            "candidate"
        ]
    )

    # =====================================================
    # SAME OUTPUT PROTECTION
    #
    # اگر دقیقاً همان خلاصه قبلی برگشته باشد،
    # آن را نسخه جدید موفق حساب نمی‌کنیم.
    # =====================================================

    if (
        previous_summary
        and new_summary
        == previous_summary
    ):

        logger.warning(
            f"⚠️ Editorial regeneration returned "
            f"same summary | count={next_count}"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=previous_summary,
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
            ),
            reason="regeneration_same_as_previous",
            metadata={
                "regeneration_count":
                    next_count,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT,
                "can_regenerate": (
                    next_count
                    < MAX_REGENERATION_COUNT
                ),
                "validation":
                    generation.get(
                        "validation"
                    )
            }
        )

    logger.info(
        f"✅ Editorial regeneration ready | "
        f"type={content_type} | "
        f"count={next_count} | "
        f"before={original_length} | "
        f"previous={len(previous_summary)} | "
        f"new={len(new_summary)} | "
        f"needs_approval=True"
    )

    return EditorialReviewResult(
        content_type=content_type,
        action=ACTION_NEEDS_APPROVAL,
        needs_approval=True,
        original_text=original_text,
        suggested_text=new_summary,
        summary_success=True,
        target_length=target_length,
        original_length=original_length,
        suggested_length=len(
            new_summary
        ),
        reason="editorial_regeneration_ready",
        metadata={
            "regeneration_count":
                next_count,
            "max_regeneration_count":
                MAX_REGENERATION_COUNT,
            "can_regenerate": (
                next_count
                < MAX_REGENERATION_COUNT
            ),
            "previous_summary":
                previous_summary,
            "validation":
                generation.get(
                    "validation"
                )
        }
    )


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
            metadata={
                "regeneration_count": 0,
                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
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
                "classification_only": True,
                "regeneration_count": 0,
                "can_regenerate": False
            }
        )

    # =====================================================
    # SENSITIVE CONTENT
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
                "automatic_summary": False,
                "regeneration_count": 0,
                "can_regenerate": False
            }
        )

    # =====================================================
    # UNCERTAIN
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
                "automatic_summary": False,
                "regeneration_count": 0,
                "can_regenerate": False
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
        or not summary_result.get(
            "success",
            False
        )
    ):

        metadata: Dict[str, Any] = {
            "regeneration_count": 0,
            "max_regeneration_count":
                MAX_REGENERATION_COUNT,
            "can_regenerate": False
        }

        if summary_result is not None:

            metadata.update({
                "summary_reason":
                    summary_result.get(
                        "reason"
                    ),
                "summary_validation":
                    summary_result.get(
                        "validation"
                    ),
                "failed_candidate":
                    summary_result.get(
                        "candidate",
                        ""
                    )
            })

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
            summary_result[
                "candidate"
            ]
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
                summary_result.get(
                    "reason"
                ),
            "summary_validation":
                summary_result.get(
                    "validation"
                ),
            "regeneration_count": 0,
            "max_regeneration_count":
                MAX_REGENERATION_COUNT,
            "can_regenerate": True
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


# =========================================================
# REGENERATION HELPER
# =========================================================

def can_regenerate_editorial_summary(
    regeneration_count: int
) -> bool:

    return (
        regeneration_count
        < MAX_REGENERATION_COUNT
    )
