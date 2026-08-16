import logging
import math

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
# ADAPTIVE TARGET POLICY
#
# هدف:
#
# اگر Validator اجازه ندهد متن تا requested target
# کوتاه شود، یک Target ایمن‌تر ساخته می‌شود.
#
# مثال واقعی:
#
# body=3918
# NEWS_ANALYSIS_MAX_REDUCTION_RATIO=0.75
#
# minimum_safe ~= 980
#
# requested=950
#
# effective_target =
# minimum_safe + buffer
# = 1060
# =========================================================

ADAPTIVE_TARGET_ENABLED = True

ADAPTIVE_TARGET_BUFFER = 80

MAX_ADAPTIVE_TARGET = 1800


# =========================================================
# REGENERATION POLICY
# =========================================================

MAX_REGENERATION_COUNT = 3

REGENERATION_TARGET_MARGIN = 40

MIN_REGENERATION_TARGET = 300


# =========================================================
# ADMIN INSTRUCTION POLICY
# =========================================================

MAX_ADMIN_INSTRUCTION_LENGTH = 1500

ADMIN_INSTRUCTION_TARGET_MARGIN = 20

MIN_ADMIN_INSTRUCTION_TARGET = 300


# =========================================================
# VALIDATION RETRY POLICY
# =========================================================

CERTAINTY_RETRY_ENABLED = True

LENGTH_RETRY_ENABLED = True

LENGTH_RETRY_MARGIN = 25


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

        return (
            CONTENT_TYPE_UNCERTAIN
        )

    if "OPINION_NOTE" in value:

        return (
            CONTENT_TYPE_OPINION_NOTE
        )

    if "NEWS_ANALYSIS" in value:

        return (
            CONTENT_TYPE_NEWS_ANALYSIS
        )

    if "SENSITIVE_CONTENT" in value:

        return (
            CONTENT_TYPE_SENSITIVE
        )

    if "NORMAL_NEWS" in value:

        return (
            CONTENT_TYPE_NORMAL_NEWS
        )

    if "UNCERTAIN" in value:

        return (
            CONTENT_TYPE_UNCERTAIN
        )

    return (
        CONTENT_TYPE_UNCERTAIN
    )


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

        return (
            CONTENT_TYPE_UNCERTAIN
        )

    if classifier is None:

        if not gemini_provider_configured():

            logger.warning(
                "⚠️ Editorial classifier unavailable | "
                "Gemini provider not configured"
            )

            return (
                CONTENT_TYPE_UNCERTAIN
            )

        classifier = (
            summarize_with_gemini
        )

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

        return (
            CONTENT_TYPE_UNCERTAIN
        )

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
# ADAPTIVE TARGET
# =========================================================

def calculate_minimum_safe_length(
    original_length: int,
    content_type: str
) -> int:

    original_length = max(
        0,
        int(
            original_length
            or 0
        )
    )

    if original_length <= 0:

        return 0

    max_reduction_ratio = (
        get_review_max_reduction_ratio(
            content_type
        )
    )

    minimum_remaining_ratio = (
        1.0
        - max_reduction_ratio
    )

    minimum_safe = math.ceil(
        original_length
        * minimum_remaining_ratio
    )

    return max(
        1,
        minimum_safe
    )


def calculate_effective_target(
    original_text: str,
    requested_target: int,
    content_type: str
) -> Dict[str, Any]:

    original_text = normalize_text(
        original_text
    )

    original_length = len(
        original_text
    )

    requested_target = max(
        1,
        int(
            requested_target
            or DEFAULT_REVIEW_TARGET
        )
    )

    minimum_safe = (
        calculate_minimum_safe_length(
            original_length=original_length,
            content_type=content_type
        )
    )

    adaptive = False

    effective_target = (
        requested_target
    )

    if (
        ADAPTIVE_TARGET_ENABLED
        and minimum_safe
        > requested_target
    ):

        adaptive = True

        effective_target = (
            minimum_safe
            + ADAPTIVE_TARGET_BUFFER
        )

        effective_target = min(
            effective_target,
            MAX_ADAPTIVE_TARGET
        )

        effective_target = max(
            effective_target,
            minimum_safe
        )

    if original_length > 0:

        effective_target = min(
            effective_target,
            original_length
        )

    effective_target = max(
        1,
        effective_target
    )

    logger.info(
        f"🎯 Editorial adaptive target | "
        f"type={content_type} | "
        f"body={original_length} | "
        f"requested={requested_target} | "
        f"minimum_safe={minimum_safe} | "
        f"effective={effective_target} | "
        f"adaptive={adaptive}"
    )

    return {
        "requested_target":
            requested_target,

        "minimum_safe":
            minimum_safe,

        "effective_target":
            effective_target,

        "adaptive":
            adaptive,

        "original_length":
            original_length
    }


# =========================================================
# VALIDATOR CONTENT TYPE
# =========================================================

def get_validator_content_type(
    content_type: str
) -> str:

    return (
        CONTENT_TYPE_NORMAL
    )


# =========================================================
# REVIEW INSTRUCTION
# =========================================================

def build_editorial_summary_instruction(
    target_length: int,
    content_type: str
) -> str:

    common_instruction = (
        "کل متن را از ابتدا تا انتها به عنوان یک واحد "
        "استدلالی بررسی کن. "

        "خلاصه نباید از انتخاب چند جمله متوالی، "
        "چند پاراگراف پشت سر هم، بخش ابتدایی متن "
        "یا بخش پایانی متن ساخته شود. "

        "خروجی باید نماینده کل متن باشد. "

        "پیش از نوشتن خروجی، در کل متن این عناصر را "
        "برای خودت تشخیص بده: تز یا ایده مرکزی، "
        "استدلال‌های اصلی، مهم‌ترین شواهد و نمونه‌ها، "
        "رابطه علت و نتیجه، پیامدها و جمع‌بندی نهایی. "

        "سپس بر اساس مجموع این عناصر یک متن تازه، "
        "منسجم و فشرده بنویس. "

        "هیچ بخشی را فقط به دلیل قرار گرفتن در ابتدا "
        "یا انتهای متن مهم‌تر از سایر بخش‌ها فرض نکن. "

        "خروجی نباید صرفاً کپی پیوسته یک قسمت از متن اصلی باشد. "

        "عنوان و نام نویسنده قبلاً از متن جدا شده‌اند. "
        "عنوان یا نام نویسنده تازه‌ای تولید نکن. "

        "میزان قطعیت گزاره‌ها را دقیق حفظ کن. "

        "اگر متن می‌گوید احتمال دارد، ممکن است، "
        "به نظر می‌رسد، ادعا شده، گفته شده یا بر اساس "
        "ارزیابی یک شخص یا نهاد نتیجه‌ای مطرح شده است، "
        "آن را به واقعیت قطعی تبدیل نکن. "

        "انتساب دیدگاه‌ها و ادعاها را حفظ کن. "
    )

    if (
        content_type
        == CONTENT_TYPE_OPINION_NOTE
    ):

        return (
            "متن زیر بدنه کامل یک یادداشت یا سرمقاله تحلیلی است. "

            + common_instruction +

            "تز اصلی نویسنده را به روشنی حفظ کن. "

            "استدلال‌های اصلی را بر اساس اهمیت آنها در "
            "کل یادداشت انتخاب کن، نه بر اساس محل قرار گرفتنشان. "

            "رابطه منطقی میان مقدمه، استدلال‌ها، شواهد، "
            "پیامدها و نتیجه‌گیری باید در نسخه کوتاه باقی بماند. "

            "اگر نویسنده چند نمونه برای اثبات یک استدلال "
            "آورده است، نمونه‌های مشابه را فشرده کن اما "
            "اصل استدلال را از بین نبر. "

            "تکرارها، مثال‌های مشابه، توضیحات طولانی، "
            "عبارات کش‌دار و جزئیاتی را که برای فهم تز اصلی "
            "ضروری نیستند حذف یا فشرده کن. "

            "نظر نویسنده را به خبر قطعی تبدیل نکن. "

            "ماهیت دیدگاهی و تحلیلی متن باید در نسخه کوتاه "
            "از نظر معنایی حفظ شود. "

            "هیچ تحلیل، نتیجه‌گیری یا دیدگاه تازه‌ای "
            "از خودت اضافه نکن. "

            "هیچ واقعیت، عدد، نام، تاریخ یا داده تازه‌ای "
            "تولید نکن. "

            "هدف، بازنمایی فشرده کل یادداشت است، "
            "نه بریدن مکانیکی بخشی از آن. "

            f"متن خلاصه بدنه باید حداکثر {target_length} "
            "کاراکتر باشد. "

            "از سقف تعیین‌شده عبور نکن. "

            "تا حد منطقی از ظرفیت موجود استفاده کن و "
            "بی‌دلیل متن را بسیار کوتاه‌تر از سقف تعیین‌شده نساز. "

            "فقط متن خلاصه‌شده بدنه را برگردان."
        )

    if (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        return (
            "متن زیر بدنه کامل یک تحلیل خبری است. "

            + common_instruction +

            "اصل رویداد، مهم‌ترین علت‌ها، رفتار بازیگران، "
            "روند اثرگذار و پیامد اصلی را از سراسر متن حفظ کن. "

            "اگر تحلیل در چند بخش مختلف متن تکمیل شده است، "
            "این بخش‌ها را با یکدیگر ترکیب کن و فقط یک بخش "
            "از تحلیل را انتخاب نکن. "

            "توضیحات تکراری، مثال‌های فرعی و زمینه‌های "
            "غیرضروری را حذف یا فشرده کن. "

            "رابطه منطقی میان خبر و تحلیل باید حفظ شود. "

            "تحلیل تازه، قضاوت تازه یا نتیجه‌گیری خارج "
            "از متن اضافه نکن. "

            "هیچ عدد، نام، تاریخ یا واقعیت جدیدی نساز. "

            "هدف، فشرده‌سازی معنایی کل تحلیل است "
            "و نه قطع مکانیکی متن. "

            f"متن خلاصه بدنه باید حداکثر {target_length} "
            "کاراکتر باشد. "

            "از سقف تعیین‌شده عبور نکن. "

            "تا حد منطقی از ظرفیت موجود استفاده کن و "
            "بی‌دلیل متن را بسیار کوتاه‌تر از سقف تعیین‌شده نساز. "

            "فقط متن خلاصه‌شده بدنه را برگردان."
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
# CERTAINTY RETRY INSTRUCTION
# =========================================================

def build_certainty_retry_instruction(
    target_length: int,
    content_type: str
) -> str:

    base_instruction = (
        build_editorial_summary_instruction(
            target_length=target_length,
            content_type=content_type
        )
    )

    return (
        base_instruction
        + " "

        "نسخه قبلی به دلیل از بین رفتن نشانه‌های "
        "قطعیت یا انتساب مورد تأیید قرار نگرفت. "

        "متن اصلی را دوباره از ابتدا تا انتها بررسی کن. "

        "این بار به طور ویژه دقت کن که گزاره‌های احتمالی، "
        "مشروط، ادعایی، ارزیابی‌شده یا منتسب به اشخاص و نهادها "
        "در خلاصه نیز با همان سطح قطعیت و همان ماهیت باقی بمانند. "

        "عبارت‌هایی مانند احتمال، ممکن است، به نظر می‌رسد، "
        "گفته است، اعلام کرده، معتقد است، ارزیابی می‌کند، "
        "ادعا کرده و سایر نشانه‌های مشابه را در صورت نیاز "
        "برای حفظ معنای اصلی نگه دار. "

        "هیچ گزاره غیرقطعی را قطعی نکن. "

        "هیچ دیدگاه نویسنده یا بازیگر را به واقعیت مستقل "
        "تبدیل نکن. "

        "هیچ اطلاعات تازه‌ای اضافه نکن. "

        f"خروجی همچنان باید حداکثر {target_length} "
        "کاراکتر باشد. "

        "فقط متن خلاصه‌شده نهایی را برگردان."
    )


# =========================================================
# LENGTH RETRY INSTRUCTION
#
# فقط وقتی فعال می‌شود که تنها خطا:
#
# summary_exceeds_target
#
# باشد.
#
# نکته:
#
# متن را با slice یا truncate کوتاه نمی‌کنیم.
# Gemini باید نسخه فشرده‌تر ولی معنایی بسازد.
# =========================================================

def build_length_retry_instruction(
    target_length: int,
    content_type: str,
    previous_candidate: str
) -> str:

    previous_candidate = (
        normalize_text(
            previous_candidate
        )
    )

    safe_target = max(
        1,
        target_length
        - LENGTH_RETRY_MARGIN
    )

    base_instruction = (
        build_editorial_summary_instruction(
            target_length=safe_target,
            content_type=content_type
        )
    )

    return (
        base_instruction
        + " "

        "نسخه قبلی از سقف طول مجاز عبور کرد. "

        "این بار همان معنای اصلی و همان سطح دقت را "
        "با جمله‌بندی فشرده‌تر بازنویسی کن. "

        "اطلاعات مهم را حذف نکن. "

        "نتیجه‌گیری اصلی متن را حذف نکن. "

        "نشانه‌های احتمال، ادعا، ارزیابی و انتساب را "
        "همچنان حفظ کن. "

        "برای کاهش طول، ابتدا تکرارها، توضیح‌های هم‌معنا، "
        "عبارت‌های زائد و ساختارهای طولانی را فشرده کن. "

        "انتهای متن را به صورت مکانیکی حذف نکن. "

        "هیچ اطلاعات تازه‌ای اضافه نکن. "

        f"خروجی نهایی باید حداکثر {safe_target} "
        "کاراکتر باشد. "

        "از این سقف عبور نکن. "

        "\n\n"
        "نسخه قبلی که فقط به دلیل طول زیاد رد شد:\n"
        "-----\n"
        f"{previous_candidate}\n"
        "-----\n\n"

        "فقط نسخه فشرده و نهایی بدنه را برگردان."
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
            "متن اصلی بدنه کامل یک یادداشت یا سرمقاله تحلیلی است. "
            "تز اصلی نویسنده، منطق استدلال، مهم‌ترین شواهد "
            "و نتیجه اصلی باید از سراسر متن استخراج و حفظ شوند. "
        )

    elif (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        type_instruction = (
            "متن اصلی بدنه کامل یک تحلیل خبری است. "
            "اصل رویداد، بازیگران اصلی، علت‌ها، روند اثرگذار "
            "و پیامد اصلی باید از سراسر متن استخراج و حفظ شوند. "
        )

    else:

        type_instruction = (
            "ساختار و معنای اصلی متن باید حفظ شود. "
        )

    return (
        "این متن قبلاً یک بار برای انتشار رسانه‌ای "
        "خلاصه شده است. "

        "وظیفه تو تولید یک نسخه جایگزین و بهتر است. "

        "مبنای اصلی کار فقط بدنه کامل متن اصلی است. "

        "خلاصه قبلی فقط برای مقایسه در اختیار تو قرار گرفته "
        "و نباید مبنای اصلی بازنویسی باشد. "

        + type_instruction +

        "کل متن اصلی را دوباره از ابتدا تا انتها بررسی کن. "

        "خلاصه جدید باید نماینده کل متن باشد و نباید "
        "صرفاً از بخش ابتدایی، میانی یا پایانی متن ساخته شود. "

        "خروجی نباید کپی پیوسته چند جمله یا چند پاراگراف "
        "از یک قسمت متن اصلی باشد. "

        "ابتدا تز مرکزی، استدلال‌های اصلی، مهم‌ترین شواهد، "
        "رابطه علت و نتیجه و جمع‌بندی را در سراسر متن تشخیص بده. "

        "سپس یک نسخه تازه، مستقل و منسجم بر اساس مجموع "
        "این عناصر تولید کن. "

        "بررسی کن آیا خلاصه قبلی یکی از محورهای مهم متن "
        "را نادیده گرفته یا بیش از حد روی یک بخش خاص "
        "تمرکز کرده است و در نسخه جدید این مشکل را اصلاح کن. "

        "نسخه جدید نباید صرفاً تغییر واژه‌های خلاصه قبلی باشد. "

        "تکرارها، توضیحات زائد، مثال‌های فرعی و عبارت‌های "
        "کش‌دار را حذف کن. "

        "هیچ تحلیل، قضاوت، نتیجه‌گیری، واقعیت، عدد، نام، "
        "تاریخ یا اطلاعات تازه‌ای از خودت اضافه نکن. "

        "میزان قطعیت و نسبت دادن دیدگاه‌ها را تغییر نده. "

        "احتمال، ادعا، ارزیابی و دیدگاه را به واقعیت قطعی تبدیل نکن. "

        "عنوان و نام نویسنده را تولید یا بازنویسی نکن. "

        "نسخه جدید باید مستقل، روان، منسجم و قابل انتشار باشد. "

        f"نسخه جدید بدنه نباید بیشتر از {target_length} "
        "کاراکتر باشد. "

        "از سقف طول تعیین‌شده عبور نکن. "

        "فقط نسخه جدید بدنه را برگردان. "

        "\n\n"
        "خلاصه قبلی فقط برای مقایسه:\n"
        "-----\n"
        f"{previous_summary}\n"
        "-----"
    )


# =========================================================
# ADMIN INSTRUCTION BUILDER
# =========================================================

def build_admin_edit_instruction(
    target_length: int,
    content_type: str,
    admin_instruction: str,
    previous_summary: str = ""
) -> str:

    admin_instruction = normalize_text(
        admin_instruction
    )

    previous_summary = normalize_text(
        previous_summary
    )

    if (
        content_type
        == CONTENT_TYPE_OPINION_NOTE
    ):

        type_context = (
            "متن اصلی یک یادداشت یا سرمقاله تحلیلی است. "
            "تز نویسنده، منطق استدلال و نتیجه اصلی باید حفظ شوند. "
        )

    elif (
        content_type
        == CONTENT_TYPE_NEWS_ANALYSIS
    ):

        type_context = (
            "متن اصلی یک تحلیل خبری است. "
            "اصل رویداد، علت‌ها، بازیگران، روند و پیامد "
            "اصلی باید حفظ شوند. "
        )

    else:

        type_context = (
            "ساختار و معنای متن اصلی باید حفظ شود. "
        )

    instruction = (
        "وظیفه تو بازنویسی یک نسخه خلاصه رسانه‌ای "
        "بر اساس دستور مشخص ادمین است. "

        "مبنای اصلی و مرجع حقیقت فقط متن اصلی است. "

        + type_context +

        "دستور ادمین فقط مشخص می‌کند کدام جنبه از متن "
        "در نسخه جدید برجسته‌تر، کوتاه‌تر، منسجم‌تر یا "
        "با اولویت متفاوت ارائه شود. "

        "دستور ادمین اجازه تغییر واقعیت‌های متن اصلی را نمی‌دهد. "

        "اگر بخشی از دستور ادمین مستلزم افزودن واقعیت، تحلیل، "
        "نام، عدد، تاریخ، ادعا یا اطلاعاتی باشد که در متن اصلی "
        "وجود ندارد، آن بخش از دستور را اجرا نکن. "

        "هیچ اطلاعات بیرونی یا دانش عمومی خودت را وارد متن نکن. "

        "هیچ تحلیل، قضاوت یا نتیجه‌گیری تازه‌ای از خودت اضافه نکن. "

        "موضع و دیدگاه نویسنده را تغییر نده. "

        "میزان قطعیت را تغییر نده. "

        "احتمال را به قطعیت تبدیل نکن. "

        "ادعا یا ارزیابی یک شخص یا نهاد را به واقعیت مستقل "
        "تبدیل نکن. "

        "انتساب سخنان و دیدگاه‌ها را حفظ کن. "

        "عدد، نام، سمت، مکان، تاریخ یا داده‌ای که در متن "
        "اصلی نیست تولید نکن. "

        "کل متن اصلی را از ابتدا تا انتها بررسی کن و نسخه "
        "جدید را فقط از اطلاعات موجود در همان متن بساز. "

        "نسخه جدید باید یکپارچه و قابل انتشار باشد. "

        "عنوان و نام نویسنده قبلاً جدا شده‌اند و نباید "
        "آنها را تولید یا بازنویسی کنی. "

        f"نسخه نهایی بدنه باید حداکثر {target_length} "
        "کاراکتر باشد. "

        "از سقف تعیین‌شده عبور نکن. "

        "تا حد منطقی از ظرفیت موجود استفاده کن. "

        "\n\n"
        "دستور ادمین:\n"
        "-----\n"
        f"{admin_instruction}\n"
        "-----\n"
    )

    if previous_summary:

        instruction += (
            "\n"
            "نسخه قبلی فقط برای مقایسه است. "
            "آن را مرجع حقیقت قرار نده و صرفاً واژه‌های آن "
            "را جابه‌جا نکن.\n"
            "-----\n"
            f"{previous_summary}\n"
            "-----\n"
        )

    instruction += (
        "\n"
        "فقط نسخه نهایی بدنه را برگردان."
    )

    return instruction


# =========================================================
# ADMIN CERTAINTY RETRY
# =========================================================

def build_admin_certainty_retry_instruction(
    target_length: int,
    content_type: str,
    admin_instruction: str,
    previous_summary: str = ""
) -> str:

    base_instruction = (
        build_admin_edit_instruction(
            target_length=target_length,
            content_type=content_type,
            admin_instruction=admin_instruction,
            previous_summary=previous_summary
        )
    )

    return (
        base_instruction
        + " "

        "نسخه قبلی به دلیل از بین رفتن یکی از نشانه‌های "
        "قطعیت یا انتساب رد شد. "

        "این بار دستور ادمین را فقط در چهارچوب متن اصلی "
        "اجرا کن و تمام نشانه‌های احتمال، ادعا، ارزیابی، "
        "انتساب و عدم قطعیت را دقیق حفظ کن. "

        "اگر در متن اصلی گفته شده به باور، به گفته، "
        "به نظر می‌رسد، احتمال دارد، ممکن است، ادعا شده، "
        "معتقد است یا ارزیابی می‌شود، ماهیت آن گزاره "
        "نباید به یک واقعیت قطعی تبدیل شود. "

        "فقط متن نهایی را برگردان."
    )


# =========================================================
# ADMIN LENGTH RETRY
# =========================================================

def build_admin_length_retry_instruction(
    target_length: int,
    content_type: str,
    admin_instruction: str,
    previous_summary: str,
    failed_candidate: str
) -> str:

    safe_target = max(
        1,
        target_length
        - LENGTH_RETRY_MARGIN
    )

    base_instruction = (
        build_admin_edit_instruction(
            target_length=safe_target,
            content_type=content_type,
            admin_instruction=admin_instruction,
            previous_summary=previous_summary
        )
    )

    failed_candidate = normalize_text(
        failed_candidate
    )

    return (
        base_instruction
        + " "

        "نسخه تولیدشده فقط به دلیل عبور از سقف طول رد شد. "

        "دستور ادمین همچنان باید اجرا شود. "

        "نسخه را بدون تغییر جهت موردنظر ادمین، "
        "با جمله‌بندی فشرده‌تر بازنویسی کن. "

        "هیچ واقعیت یا تحلیل تازه‌ای اضافه نکن. "

        "هیچ بخش مهمی از منطق متن اصلی را حذف نکن. "

        f"خروجی نهایی حداکثر {safe_target} "
        "کاراکتر باشد. "

        "\n\n"
        "نسخه‌ای که فقط به دلیل طول زیاد رد شد:\n"
        "-----\n"
        f"{failed_candidate}\n"
        "-----\n\n"

        "فقط نسخه نهایی بدنه را برگردان."
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

    return (
        summarize_with_gemini
    )


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
# VALIDATION ERROR HELPERS
# =========================================================

def only_certainty_validation_error(
    validation: Optional[
        Dict[str, Any]
    ]
) -> bool:

    if not validation:

        return False

    errors = set(
        validation.get(
            "errors",
            []
        )
        or []
    )

    return (
        errors
        == {
            "certainty_markers_lost"
        }
    )


def only_length_validation_error(
    validation: Optional[
        Dict[str, Any]
    ]
) -> bool:

    if not validation:

        return False

    errors = set(
        validation.get(
            "errors",
            []
        )
        or []
    )

    return (
        errors
        == {
            "summary_exceeds_target"
        }
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
            ),
            "certainty_retry_called": False,
            "length_retry_called": False
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

    if validation[
        "valid"
    ]:

        return {
            "success": True,
            "candidate": candidate,
            "validation": validation,
            "reason": "accepted",
            "error": None,
            "certainty_retry_called": False,
            "length_retry_called": False
        }

    # =====================================================
    # LENGTH RETRY
    #
    # مثال واقعی:
    #
    # target = 1060
    # output = 1132
    #
    # errors = ['summary_exceeds_target']
    #
    # در این حالت به جای رد کامل،
    # یک بار تولید فشرده‌تر انجام می‌شود.
    # =====================================================

    can_retry_length = (
        LENGTH_RETRY_ENABLED
        and only_length_validation_error(
            validation
        )
    )

    if can_retry_length:

        retry_target = max(
            1,
            target_length
            - LENGTH_RETRY_MARGIN
        )

        logger.info(
            f"📏 Editorial length retry | "
            f"type={content_type} | "
            f"first_output={len(candidate)} | "
            f"target={target_length} | "
            f"retry_target={retry_target}"
        )

        retry_instruction = (
            build_length_retry_instruction(
                target_length=target_length,
                content_type=content_type,
                previous_candidate=candidate
            )
        )

        try:

            retry_candidate = summarizer(
                original_text,
                retry_instruction,
                retry_target
            )

        except Exception as e:

            logger.exception(
                f"❌ Editorial length retry failed | "
                f"{e}"
            )

            return {
                "success": False,
                "candidate": candidate,
                "validation": validation,
                "reason":
                    "length_retry_provider_error",
                "error": str(
                    e
                ),
                "certainty_retry_called": False,
                "length_retry_called": True
            }

        retry_candidate = normalize_text(
            retry_candidate
        )

        retry_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=retry_candidate,

                # Validator روی سقف اصلی بررسی می‌کند.
                # Retry Target فقط برای هدایت AI است.
                target_length=target_length,

                content_type=content_type
            )
        )

        if retry_validation[
            "valid"
        ]:

            logger.info(
                f"✅ Editorial length retry accepted | "
                f"type={content_type} | "
                f"first_output={len(candidate)} | "
                f"output={len(retry_candidate)} | "
                f"target={target_length}"
            )

            return {
                "success": True,
                "candidate":
                    retry_candidate,

                "validation":
                    retry_validation,

                "reason":
                    "accepted_after_length_retry",

                "error":
                    None,

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation
            }

        logger.warning(
            f"⚠️ Editorial length retry rejected | "
            f"type={content_type} | "
            f"errors="
            f"{retry_validation.get('errors', [])} | "
            f"output={len(retry_candidate)} | "
            f"target={target_length}"
        )

        # =================================================
        # اگر Length Retry مشکل طول را حل کرد اما حالا
        # تنها مشکل certainty شد، یک Certainty Retry
        # نهایی مجاز است.
        # =================================================

        if (
            CERTAINTY_RETRY_ENABLED
            and only_certainty_validation_error(
                retry_validation
            )
        ):

            logger.info(
                f"🔁 Editorial certainty retry "
                f"after length retry | "
                f"type={content_type}"
            )

            certainty_instruction = (
                build_certainty_retry_instruction(
                    target_length=target_length,
                    content_type=content_type
                )
            )

            try:

                certainty_candidate = summarizer(
                    original_text,
                    certainty_instruction,
                    target_length
                )

            except Exception as e:

                logger.exception(
                    f"❌ Editorial certainty retry "
                    f"after length failed | {e}"
                )

                return {
                    "success": False,
                    "candidate":
                        retry_candidate,

                    "validation":
                        retry_validation,

                    "reason":
                        "certainty_retry_provider_error",

                    "error":
                        str(e),

                    "certainty_retry_called":
                        True,

                    "length_retry_called":
                        True
                }

            certainty_candidate = normalize_text(
                certainty_candidate
            )

            certainty_validation = (
                validate_editorial_candidate(
                    original_text=original_text,
                    candidate_text=certainty_candidate,
                    target_length=target_length,
                    content_type=content_type
                )
            )

            if certainty_validation[
                "valid"
            ]:

                logger.info(
                    f"✅ Editorial certainty retry "
                    f"after length accepted | "
                    f"type={content_type} | "
                    f"output="
                    f"{len(certainty_candidate)}"
                )

                return {
                    "success": True,
                    "candidate":
                        certainty_candidate,

                    "validation":
                        certainty_validation,

                    "reason":
                        "accepted_after_length_and_certainty_retry",

                    "error":
                        None,

                    "certainty_retry_called":
                        True,

                    "length_retry_called":
                        True,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation,

                    "length_retry_candidate":
                        retry_candidate,

                    "length_retry_validation":
                        retry_validation
                }

        return {
            "success": False,
            "candidate":
                retry_candidate,

            "validation":
                retry_validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                False,

            "length_retry_called":
                True,

            "first_candidate":
                candidate,

            "first_validation":
                validation
        }

    # =====================================================
    # CERTAINTY RETRY
    # =====================================================

    can_retry_certainty = (
        CERTAINTY_RETRY_ENABLED
        and content_type
        in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
        and only_certainty_validation_error(
            validation
        )
    )

    if can_retry_certainty:

        logger.info(
            f"🔁 Editorial certainty retry | "
            f"type={content_type} | "
            f"first_output={len(candidate)} | "
            f"target={target_length}"
        )

        retry_instruction = (
            build_certainty_retry_instruction(
                target_length=target_length,
                content_type=content_type
            )
        )

        try:

            retry_candidate = summarizer(
                original_text,
                retry_instruction,
                target_length
            )

        except Exception as e:

            logger.exception(
                f"❌ Editorial certainty retry failed | "
                f"{e}"
            )

            return {
                "success": False,
                "candidate": candidate,
                "validation": validation,
                "reason":
                    "certainty_retry_provider_error",
                "error": str(
                    e
                ),
                "certainty_retry_called": True,
                "length_retry_called": False
            }

        retry_candidate = normalize_text(
            retry_candidate
        )

        retry_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=retry_candidate,
                target_length=target_length,
                content_type=content_type
            )
        )

        if retry_validation[
            "valid"
        ]:

            logger.info(
                f"✅ Editorial certainty retry accepted | "
                f"type={content_type} | "
                f"output={len(retry_candidate)} | "
                f"target={target_length}"
            )

            return {
                "success": True,
                "candidate": retry_candidate,
                "validation": retry_validation,
                "reason":
                    "accepted_after_certainty_retry",
                "error": None,
                "certainty_retry_called": True,
                "length_retry_called": False,
                "first_candidate": candidate,
                "first_validation": validation
            }

        logger.warning(
            f"⚠️ Editorial certainty retry rejected | "
            f"type={content_type} | "
            f"errors={retry_validation['errors']} | "
            f"output={len(retry_candidate)} | "
            f"target={target_length}"
        )

        # =================================================
        # Certainty Retry ممکن است این بار فقط از نظر طول
        # کمی از Target عبور کند.
        #
        # در این حالت Length Retry نهایی مجاز است.
        # =================================================

        if (
            LENGTH_RETRY_ENABLED
            and only_length_validation_error(
                retry_validation
            )
        ):

            retry_target = max(
                1,
                target_length
                - LENGTH_RETRY_MARGIN
            )

            logger.info(
                f"📏 Editorial length retry "
                f"after certainty | "
                f"type={content_type} | "
                f"output={len(retry_candidate)} | "
                f"target={target_length}"
            )

            length_instruction = (
                build_length_retry_instruction(
                    target_length=target_length,
                    content_type=content_type,
                    previous_candidate=(
                        retry_candidate
                    )
                )
            )

            try:

                length_candidate = summarizer(
                    original_text,
                    length_instruction,
                    retry_target
                )

            except Exception as e:

                logger.exception(
                    f"❌ Editorial length retry "
                    f"after certainty failed | {e}"
                )

                return {
                    "success": False,
                    "candidate":
                        retry_candidate,

                    "validation":
                        retry_validation,

                    "reason":
                        "length_retry_provider_error",

                    "error":
                        str(e),

                    "certainty_retry_called":
                        True,

                    "length_retry_called":
                        True
                }

            length_candidate = normalize_text(
                length_candidate
            )

            length_validation = (
                validate_editorial_candidate(
                    original_text=original_text,
                    candidate_text=length_candidate,
                    target_length=target_length,
                    content_type=content_type
                )
            )

            if length_validation[
                "valid"
            ]:

                logger.info(
                    f"✅ Editorial length retry "
                    f"after certainty accepted | "
                    f"type={content_type} | "
                    f"output="
                    f"{len(length_candidate)}"
                )

                return {
                    "success": True,
                    "candidate":
                        length_candidate,

                    "validation":
                        length_validation,

                    "reason":
                        "accepted_after_certainty_and_length_retry",

                    "error":
                        None,

                    "certainty_retry_called":
                        True,

                    "length_retry_called":
                        True,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation,

                    "certainty_retry_candidate":
                        retry_candidate,

                    "certainty_retry_validation":
                        retry_validation
                }

        return {
            "success": False,
            "candidate":
                retry_candidate,

            "validation":
                retry_validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                True,

            "length_retry_called":
                False,

            "first_candidate":
                candidate,

            "first_validation":
                validation
        }

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
        "error": None,
        "certainty_retry_called": False,
        "length_retry_called": False
    }


# =========================================================
# ADMIN INSTRUCTION GENERATION
# =========================================================

def generate_admin_instruction_candidate(
    original_text: str,
    previous_summary: str,
    admin_instruction: str,
    target_length: int,
    content_type: str,
    summarizer: Callable[
        [str, str, int],
        str
    ]
) -> Dict[str, Any]:

    instruction = (
        build_admin_edit_instruction(
            target_length=target_length,
            content_type=content_type,
            admin_instruction=admin_instruction,
            previous_summary=previous_summary
        )
    )

    try:

        candidate = summarizer(
            original_text,
            instruction,
            target_length
        )

    except Exception as e:

        logger.exception(
            f"❌ Admin editorial generation failed | "
            f"{e}"
        )

        return {
            "success": False,
            "candidate": "",
            "validation": None,
            "reason": "provider_error",
            "error": str(
                e
            ),
            "certainty_retry_called": False,
            "length_retry_called": False
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

    if validation[
        "valid"
    ]:

        return {
            "success": True,
            "candidate": candidate,
            "validation": validation,
            "reason": "accepted",
            "error": None,
            "certainty_retry_called": False,
            "length_retry_called": False
        }

    # =====================================================
    # ADMIN LENGTH RETRY
    # =====================================================

    if (
        LENGTH_RETRY_ENABLED
        and only_length_validation_error(
            validation
        )
    ):

        retry_target = max(
            1,
            target_length
            - LENGTH_RETRY_MARGIN
        )

        logger.info(
            f"📏 Admin editorial length retry | "
            f"type={content_type} | "
            f"first_output={len(candidate)} | "
            f"target={target_length} | "
            f"retry_target={retry_target}"
        )

        retry_instruction = (
            build_admin_length_retry_instruction(
                target_length=target_length,
                content_type=content_type,
                admin_instruction=admin_instruction,
                previous_summary=previous_summary,
                failed_candidate=candidate
            )
        )

        try:

            retry_candidate = summarizer(
                original_text,
                retry_instruction,
                retry_target
            )

        except Exception as e:

            logger.exception(
                f"❌ Admin length retry failed | "
                f"{e}"
            )

            return {
                "success": False,
                "candidate": candidate,
                "validation": validation,
                "reason":
                    "length_retry_provider_error",
                "error": str(
                    e
                ),
                "certainty_retry_called": False,
                "length_retry_called": True
            }

        retry_candidate = normalize_text(
            retry_candidate
        )

        retry_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=retry_candidate,
                target_length=target_length,
                content_type=content_type
            )
        )

        if retry_validation[
            "valid"
        ]:

            logger.info(
                f"✅ Admin editorial length retry accepted | "
                f"type={content_type} | "
                f"output={len(retry_candidate)}"
            )

            return {
                "success": True,
                "candidate":
                    retry_candidate,

                "validation":
                    retry_validation,

                "reason":
                    "accepted_after_length_retry",

                "error":
                    None,

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation
            }

        return {
            "success": False,
            "candidate":
                retry_candidate,

            "validation":
                retry_validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                False,

            "length_retry_called":
                True,

            "first_candidate":
                candidate,

            "first_validation":
                validation
        }

    # =====================================================
    # ADMIN CERTAINTY RETRY
    # =====================================================

    can_retry_certainty = (
        CERTAINTY_RETRY_ENABLED
        and only_certainty_validation_error(
            validation
        )
    )

    if not can_retry_certainty:

        logger.warning(
            f"⚠️ Admin editorial candidate rejected | "
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
            "error": None,
            "certainty_retry_called": False,
            "length_retry_called": False
        }

    logger.info(
        f"🔁 Admin editorial certainty retry | "
        f"type={content_type} | "
        f"first_output={len(candidate)} | "
        f"target={target_length}"
    )

    retry_instruction = (
        build_admin_certainty_retry_instruction(
            target_length=target_length,
            content_type=content_type,
            admin_instruction=admin_instruction,
            previous_summary=previous_summary
        )
    )

    try:

        retry_candidate = summarizer(
            original_text,
            retry_instruction,
            target_length
        )

    except Exception as e:

        logger.exception(
            f"❌ Admin editorial certainty retry failed | "
            f"{e}"
        )

        return {
            "success": False,
            "candidate": candidate,
            "validation": validation,
            "reason":
                "certainty_retry_provider_error",
            "error": str(
                e
            ),
            "certainty_retry_called": True,
            "length_retry_called": False
        }

    retry_candidate = normalize_text(
        retry_candidate
    )

    retry_validation = (
        validate_editorial_candidate(
            original_text=original_text,
            candidate_text=retry_candidate,
            target_length=target_length,
            content_type=content_type
        )
    )

    if retry_validation[
        "valid"
    ]:

        logger.info(
            f"✅ Admin editorial certainty retry accepted | "
            f"type={content_type} | "
            f"output={len(retry_candidate)}"
        )

        return {
            "success": True,
            "candidate": retry_candidate,
            "validation": retry_validation,
            "reason":
                "accepted_after_certainty_retry",
            "error": None,
            "certainty_retry_called": True,
            "length_retry_called": False,
            "first_candidate": candidate,
            "first_validation": validation
        }

    # =====================================================
    # ADMIN CERTAINTY -> LENGTH RETRY
    # =====================================================

    if (
        LENGTH_RETRY_ENABLED
        and only_length_validation_error(
            retry_validation
        )
    ):

        retry_target = max(
            1,
            target_length
            - LENGTH_RETRY_MARGIN
        )

        length_instruction = (
            build_admin_length_retry_instruction(
                target_length=target_length,
                content_type=content_type,
                admin_instruction=admin_instruction,
                previous_summary=previous_summary,
                failed_candidate=retry_candidate
            )
        )

        try:

            length_candidate = summarizer(
                original_text,
                length_instruction,
                retry_target
            )

        except Exception as e:

            logger.exception(
                f"❌ Admin length retry after certainty "
                f"failed | {e}"
            )

            return {
                "success": False,
                "candidate":
                    retry_candidate,

                "validation":
                    retry_validation,

                "reason":
                    "length_retry_provider_error",

                "error":
                    str(e),

                "certainty_retry_called":
                    True,

                "length_retry_called":
                    True
            }

        length_candidate = normalize_text(
            length_candidate
        )

        length_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=length_candidate,
                target_length=target_length,
                content_type=content_type
            )
        )

        if length_validation[
            "valid"
        ]:

            return {
                "success": True,
                "candidate":
                    length_candidate,

                "validation":
                    length_validation,

                "reason":
                    "accepted_after_certainty_and_length_retry",

                "error":
                    None,

                "certainty_retry_called":
                    True,

                "length_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation
            }

    return {
        "success": False,
        "candidate": retry_candidate,
        "validation": retry_validation,
        "reason": "validation_failed",
        "error": None,
        "certainty_retry_called": True,
        "length_retry_called": False,
        "first_candidate": candidate,
        "first_validation": validation
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

    target_policy = (
        calculate_effective_target(
            original_text=original_text,
            requested_target=target_length,
            content_type=content_type
        )
    )

    effective_target = int(
        target_policy[
            "effective_target"
        ]
    )

    minimum_safe = int(
        target_policy[
            "minimum_safe"
        ]
    )

    if (
        len(original_text)
        <= effective_target
    ):

        validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=original_text,
                target_length=effective_target,
                content_type=content_type
            )
        )

        return {
            "success": True,
            "candidate": original_text,
            "validation": validation,
            "reason": "already_fits",
            "summarizer_called": False,
            "certainty_retry_called": False,
            "length_retry_called": False,
            "requested_target":
                target_length,
            "effective_target":
                effective_target,
            "minimum_safe":
                minimum_safe,
            "adaptive_target":
                target_policy[
                    "adaptive"
                ]
        }

    logger.info(
        f"🧠 Editorial full-body summary | "
        f"type={content_type} | "
        f"body={len(original_text)} | "
        f"requested_target={target_length} | "
        f"effective_target={effective_target} | "
        f"minimum_safe={minimum_safe}"
    )

    instruction = (
        build_editorial_summary_instruction(
            target_length=effective_target,
            content_type=content_type
        )
    )

    generation = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=effective_target,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    generation[
        "summarizer_called"
    ] = True

    generation[
        "requested_target"
    ] = target_length

    generation[
        "effective_target"
    ] = effective_target

    generation[
        "minimum_safe"
    ] = minimum_safe

    generation[
        "adaptive_target"
    ] = target_policy[
        "adaptive"
    ]

    return generation


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
            reason=
                "regeneration_not_allowed_for_content_type",
            metadata={
                "regeneration_count":
                    regeneration_count,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

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

                "can_regenerate":
                    False
            }
        )

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
            reason=
                "regeneration_provider_unavailable",
            metadata={
                "regeneration_count":
                    regeneration_count,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

    target_policy = (
        calculate_effective_target(
            original_text=original_text,
            requested_target=target_length,
            content_type=content_type
        )
    )

    effective_target = int(
        target_policy[
            "effective_target"
        ]
    )

    regeneration_target = max(
        MIN_REGENERATION_TARGET,
        effective_target
        - REGENERATION_TARGET_MARGIN
    )

    minimum_safe = int(
        target_policy[
            "minimum_safe"
        ]
    )

    if (
        regeneration_target
        < minimum_safe
    ):

        regeneration_target = (
            effective_target
        )

    regeneration_target = min(
        regeneration_target,
        effective_target
    )

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
        f"body={original_length} | "
        f"previous={len(previous_summary)} | "
        f"requested_target={target_length} | "
        f"effective_target={effective_target} | "
        f"generation_target={regeneration_target}"
    )

    generation = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=effective_target,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    next_count = (
        regeneration_count
        + 1
    )

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
            target_length=effective_target,
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

                "can_regenerate":
                    (
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
                    ),

                "certainty_retry_called":
                    generation.get(
                        "certainty_retry_called",
                        False
                    ),

                "length_retry_called":
                    generation.get(
                        "length_retry_called",
                        False
                    ),

                "requested_target":
                    target_length,

                "effective_target":
                    effective_target,

                "minimum_safe":
                    minimum_safe,

                "adaptive_target":
                    target_policy[
                        "adaptive"
                    ]
            }
        )

    new_summary = normalize_text(
        generation[
            "candidate"
        ]
    )

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
            target_length=effective_target,
            original_length=original_length,
            suggested_length=len(
                previous_summary
            ),
            reason=
                "regeneration_same_as_previous",
            metadata={
                "regeneration_count":
                    next_count,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT,

                "can_regenerate":
                    (
                        next_count
                        < MAX_REGENERATION_COUNT
                    ),

                "validation":
                    generation.get(
                        "validation"
                    ),

                "certainty_retry_called":
                    generation.get(
                        "certainty_retry_called",
                        False
                    ),

                "length_retry_called":
                    generation.get(
                        "length_retry_called",
                        False
                    )
            }
        )

    if (
        len(new_summary)
        > effective_target
    ):

        logger.warning(
            f"⚠️ Regenerated editorial summary "
            f"exceeds final target | "
            f"final={len(new_summary)} | "
            f"target={effective_target}"
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
            target_length=effective_target,
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

                "can_regenerate":
                    (
                        next_count
                        < MAX_REGENERATION_COUNT
                    ),

                "generation_reason":
                    "summary_exceeds_target"
            }
        )

    logger.info(
        f"✅ Editorial regeneration ready | "
        f"type={content_type} | "
        f"count={next_count} | "
        f"body_before={original_length} | "
        f"body_after={len(new_summary)} | "
        f"needs_approval=True"
    )

    return EditorialReviewResult(
        content_type=content_type,
        action=ACTION_NEEDS_APPROVAL,
        needs_approval=True,
        original_text=original_text,
        suggested_text=new_summary,
        summary_success=True,
        target_length=effective_target,
        original_length=original_length,
        suggested_length=len(
            new_summary
        ),
        reason=
            "editorial_regeneration_ready",
        metadata={
            "regeneration_count":
                next_count,

            "max_regeneration_count":
                MAX_REGENERATION_COUNT,

            "can_regenerate":
                (
                    next_count
                    < MAX_REGENERATION_COUNT
                ),

            "previous_summary":
                previous_summary,

            "validation":
                generation.get(
                    "validation"
                ),

            "certainty_retry_called":
                generation.get(
                    "certainty_retry_called",
                    False
                ),

            "length_retry_called":
                generation.get(
                    "length_retry_called",
                    False
                ),

            "requested_target":
                target_length,

            "effective_target":
                effective_target,

            "minimum_safe":
                minimum_safe,

            "adaptive_target":
                target_policy[
                    "adaptive"
                ]
        }
    )


# =========================================================
# APPLY ADMIN INSTRUCTION
# =========================================================

def apply_admin_instruction_to_editorial_summary(
    original_text: str,
    previous_summary: str,
    admin_instruction: str,
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
) -> EditorialReviewResult:

    original_text = normalize_text(
        original_text
    )

    previous_summary = normalize_text(
        previous_summary
    )

    admin_instruction = normalize_text(
        admin_instruction
    )

    original_length = len(
        original_text
    )

    if not original_text:

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text="",
            suggested_text=previous_summary,
            summary_success=False,
            target_length=target_length,
            original_length=0,
            suggested_length=len(
                previous_summary
            ),
            reason=
                "admin_instruction_original_empty",
            metadata={
                "admin_instruction":
                    admin_instruction
            }
        )

    if not admin_instruction:

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
            reason=
                "admin_instruction_empty",
            metadata={
                "admin_instruction":
                    ""
            }
        )

    if (
        len(admin_instruction)
        > MAX_ADMIN_INSTRUCTION_LENGTH
    ):

        logger.warning(
            f"⚠️ Admin instruction too long | "
            f"length={len(admin_instruction)} | "
            f"max={MAX_ADMIN_INSTRUCTION_LENGTH}"
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
            reason=
                "admin_instruction_too_long",
            metadata={
                "admin_instruction":
                    admin_instruction,

                "admin_instruction_length":
                    len(
                        admin_instruction
                    ),

                "max_admin_instruction_length":
                    MAX_ADMIN_INSTRUCTION_LENGTH
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
            f"⚠️ Admin editorial edit blocked | "
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
            reason=
                "admin_instruction_not_allowed_for_content_type",
            metadata={
                "admin_instruction":
                    admin_instruction
            }
        )

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
            reason=
                "admin_instruction_provider_unavailable",
            metadata={
                "admin_instruction":
                    admin_instruction
            }
        )

    target_policy = (
        calculate_effective_target(
            original_text=original_text,
            requested_target=target_length,
            content_type=content_type
        )
    )

    effective_target = int(
        target_policy[
            "effective_target"
        ]
    )

    minimum_safe = int(
        target_policy[
            "minimum_safe"
        ]
    )

    edit_target = max(
        MIN_ADMIN_INSTRUCTION_TARGET,
        effective_target
        - ADMIN_INSTRUCTION_TARGET_MARGIN
    )

    if edit_target < minimum_safe:

        edit_target = (
            effective_target
        )

    edit_target = min(
        edit_target,
        effective_target
    )

    logger.info(
        f"✏️ Admin editorial edit started | "
        f"type={content_type} | "
        f"body={original_length} | "
        f"previous={len(previous_summary)} | "
        f"instruction={len(admin_instruction)} | "
        f"requested_target={target_length} | "
        f"effective_target={effective_target} | "
        f"generation_target={edit_target}"
    )

    generation = (
        generate_admin_instruction_candidate(
            original_text=original_text,
            previous_summary=previous_summary,
            admin_instruction=admin_instruction,
            target_length=effective_target,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    if not generation[
        "success"
    ]:

        logger.warning(
            f"⚠️ Admin editorial edit rejected | "
            f"type={content_type} | "
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
            target_length=effective_target,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason=
                "admin_instruction_failed",
            metadata={
                "admin_instruction":
                    admin_instruction,

                "generation_reason":
                    generation.get(
                        "reason"
                    ),

                "validation":
                    generation.get(
                        "validation"
                    ),

                "failed_candidate":
                    generation.get(
                        "candidate",
                        ""
                    ),

                "certainty_retry_called":
                    generation.get(
                        "certainty_retry_called",
                        False
                    ),

                "length_retry_called":
                    generation.get(
                        "length_retry_called",
                        False
                    ),

                "requested_target":
                    target_length,

                "effective_target":
                    effective_target,

                "minimum_safe":
                    minimum_safe,

                "adaptive_target":
                    target_policy[
                        "adaptive"
                    ]
            }
        )

    new_summary = normalize_text(
        generation[
            "candidate"
        ]
    )

    if (
        previous_summary
        and new_summary
        == previous_summary
    ):

        logger.info(
            "ℹ️ Admin instruction produced "
            "no effective summary change"
        )

        return EditorialReviewResult(
            content_type=content_type,
            action=ACTION_NEEDS_APPROVAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=previous_summary,
            summary_success=False,
            target_length=effective_target,
            original_length=original_length,
            suggested_length=len(
                previous_summary
            ),
            reason=
                "admin_instruction_no_change",
            metadata={
                "admin_instruction":
                    admin_instruction,

                "validation":
                    generation.get(
                        "validation"
                    ),

                "certainty_retry_called":
                    generation.get(
                        "certainty_retry_called",
                        False
                    ),

                "length_retry_called":
                    generation.get(
                        "length_retry_called",
                        False
                    )
            }
        )

    if (
        len(new_summary)
        > effective_target
    ):

        logger.warning(
            f"⚠️ Admin edited summary exceeds "
            f"final target | "
            f"final={len(new_summary)} | "
            f"target={effective_target}"
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
            target_length=effective_target,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason=
                "admin_instruction_failed",
            metadata={
                "admin_instruction":
                    admin_instruction,

                "generation_reason":
                    "summary_exceeds_target"
            }
        )

    logger.info(
        f"✅ Admin editorial edit ready | "
        f"type={content_type} | "
        f"body_before={original_length} | "
        f"body_after={len(new_summary)} | "
        f"instruction={len(admin_instruction)} | "
        f"needs_approval=True"
    )

    return EditorialReviewResult(
        content_type=content_type,
        action=ACTION_NEEDS_APPROVAL,
        needs_approval=True,
        original_text=original_text,
        suggested_text=new_summary,
        summary_success=True,
        target_length=effective_target,
        original_length=original_length,
        suggested_length=len(
            new_summary
        ),
        reason=
            "admin_instruction_ready",
        metadata={
            "admin_instruction":
                admin_instruction,

            "previous_summary":
                previous_summary,

            "validation":
                generation.get(
                    "validation"
                ),

            "certainty_retry_called":
                generation.get(
                    "certainty_retry_called",
                    False
                ),

            "length_retry_called":
                generation.get(
                    "length_retry_called",
                    False
                ),

            "admin_instruction_applied":
                True,

            "requested_target":
                target_length,

            "effective_target":
                effective_target,

            "minimum_safe":
                minimum_safe,

            "adaptive_target":
                target_policy[
                    "adaptive"
                ]
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
            content_type=
                CONTENT_TYPE_UNCERTAIN,
            action=
                ACTION_PUBLISH_DIRECT,
            needs_approval=False,
            original_text="",
            suggested_text="",
            summary_success=True,
            target_length=target_length,
            original_length=0,
            suggested_length=0,
            reason="empty_text",
            metadata={
                "regeneration_count":
                    0,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

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
            action=
                ACTION_PUBLISH_DIRECT,
            needs_approval=False,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=True,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="normal_news_direct",
            metadata={
                "classification_only":
                    True,

                "regeneration_count":
                    0,

                "can_regenerate":
                    False
            }
        )

    # =====================================================
    # SENSITIVE
    # =====================================================

    if (
        content_type
        == CONTENT_TYPE_SENSITIVE
    ):

        return EditorialReviewResult(
            content_type=content_type,
            action=
                ACTION_PUBLISH_ORIGINAL,
            needs_approval=True,
            original_text=original_text,
            suggested_text=original_text,
            summary_success=False,
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason=
                "sensitive_content_preserved",
            metadata={
                "automatic_summary":
                    False,

                "regeneration_count":
                    0,

                "can_regenerate":
                    False
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
                "automatic_summary":
                    False,

                "regeneration_count":
                    0,

                "can_regenerate":
                    False
            }
        )

    # =====================================================
    # OPINION / ANALYSIS
    # =====================================================

    summary_result = (
        summarize_editorial_content(
            original_text=original_text,
            content_type=content_type,
            target_length=target_length,
            summarizer=summarizer
        )
    )

    effective_target = (
        target_length
    )

    minimum_safe = 0

    adaptive_target = False

    if summary_result is not None:

        effective_target = int(
            summary_result.get(
                "effective_target",
                target_length
            )
            or target_length
        )

        minimum_safe = int(
            summary_result.get(
                "minimum_safe",
                0
            )
            or 0
        )

        adaptive_target = bool(
            summary_result.get(
                "adaptive_target",
                False
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
            "regeneration_count":
                0,

            "max_regeneration_count":
                MAX_REGENERATION_COUNT,

            "can_regenerate":
                False,

            "requested_target":
                target_length,

            "effective_target":
                effective_target,

            "minimum_safe":
                minimum_safe,

            "adaptive_target":
                adaptive_target
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
                    ),

                "certainty_retry_called":
                    summary_result.get(
                        "certainty_retry_called",
                        False
                    ),

                "length_retry_called":
                    summary_result.get(
                        "length_retry_called",
                        False
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
            target_length=effective_target,
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
        f"requested_target={target_length} | "
        f"effective_target={effective_target} | "
        f"certainty_retry="
        f"{summary_result.get('certainty_retry_called', False)} | "
        f"length_retry="
        f"{summary_result.get('length_retry_called', False)} | "
        f"needs_approval=True"
    )

    return EditorialReviewResult(
        content_type=content_type,
        action=ACTION_NEEDS_APPROVAL,
        needs_approval=True,
        original_text=original_text,
        suggested_text=suggested_text,
        summary_success=True,
        target_length=effective_target,
        original_length=original_length,
        suggested_length=len(
            suggested_text
        ),
        reason=
            "editorial_summary_ready",
        metadata={
            "summary_reason":
                summary_result.get(
                    "reason"
                ),

            "summary_validation":
                summary_result.get(
                    "validation"
                ),

            "regeneration_count":
                0,

            "max_regeneration_count":
                MAX_REGENERATION_COUNT,

            "can_regenerate":
                True,

            "certainty_retry_called":
                summary_result.get(
                    "certainty_retry_called",
                    False
                ),

            "length_retry_called":
                summary_result.get(
                    "length_retry_called",
                    False
                ),

            "requested_target":
                target_length,

            "effective_target":
                effective_target,

            "minimum_safe":
                minimum_safe,

            "adaptive_target":
                adaptive_target
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
