import logging
import re

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
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
# =========================================================

ADAPTIVE_TARGET_ENABLED = True

ADAPTIVE_TARGET_MARGIN = 80


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

# اگر مدل فقط کمی بیشتر از سقف خروجی بدهد،
# یک بار دیگر با هدف پایین‌تر بازتولید می‌کنیم.
OVERFLOW_RETRY_ENABLED = True

# میزان فاصله هدف Retry از سقف نهایی.
# مثال:
# final target = 1059
# minimum safe = 979
# retry target ≈ 979
OVERFLOW_RETRY_MARGIN = 80


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

    value = normalize_text(
        value
    ).upper()

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
        Callable[[str, str, int], str]
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
# MINIMUM SAFE LENGTH
# =========================================================

def calculate_minimum_safe_length(
    original_text: str,
    content_type: str
) -> int:

    original_text = normalize_text(
        original_text
    )

    if not original_text:
        return 0

    max_reduction_ratio = (
        get_review_max_reduction_ratio(
            content_type
        )
    )

    minimum_safe = int(
        len(original_text)
        * (
            1.0
            - max_reduction_ratio
        )
    )

    return max(
        1,
        minimum_safe
    )


# =========================================================
# ADAPTIVE TARGET
# =========================================================

def resolve_effective_target(
    original_text: str,
    content_type: str,
    requested_target: int
) -> Dict[str, Any]:

    original_text = normalize_text(
        original_text
    )

    requested_target = max(
        1,
        int(
            requested_target
        )
    )

    minimum_safe = (
        calculate_minimum_safe_length(
            original_text=original_text,
            content_type=content_type
        )
    )

    effective_target = (
        requested_target
    )

    adaptive_target = False

    if (
        ADAPTIVE_TARGET_ENABLED
        and minimum_safe
        > requested_target
    ):

        effective_target = (
            minimum_safe
            + ADAPTIVE_TARGET_MARGIN
        )

        adaptive_target = True

    logger.info(
        f"🎯 Editorial adaptive target | "
        f"type={content_type} | "
        f"body={len(original_text)} | "
        f"requested={requested_target} | "
        f"minimum_safe={minimum_safe} | "
        f"effective={effective_target} | "
        f"adaptive={adaptive_target}"
    )

    return {
        "requested_target":
            requested_target,

        "minimum_safe":
            minimum_safe,

        "effective_target":
            effective_target,

        "adaptive_target":
            adaptive_target
    }


# =========================================================
# VALIDATOR CONTENT TYPE
# =========================================================

def get_validator_content_type(
    content_type: str
) -> str:

    return CONTENT_TYPE_NORMAL


# =========================================================
# REVIEW INSTRUCTION
# =========================================================

def build_editorial_summary_instruction(
    target_length: int,
    content_type: str,
    minimum_length: int = 0
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

    length_instruction = (
        f"متن خلاصه بدنه باید حداکثر "
        f"{target_length} کاراکتر باشد. "
    )

    if minimum_length > 0:

        length_instruction += (
            f"برای حفظ اطلاعات ضروری، خروجی را کمتر از "
            f"{minimum_length} کاراکتر نساز. "
            f"بنابراین طول مطلوب خروجی بین "
            f"{minimum_length} و {target_length} "
            "کاراکتر است. "
        )

    length_instruction += (
        "تا حد منطقی از ظرفیت موجود استفاده کن و "
        "بی‌دلیل متن را بسیار کوتاه‌تر از سقف تعیین‌شده نساز. "
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

            + length_instruction +

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

            + length_instruction +

            "فقط متن خلاصه‌شده بدنه را برگردان."
        )

    return (
        "متن را بدون تغییر محتوایی حفظ کن. "
        "فقط در حدی کوتاه کن که هیچ اطلاعات مهم، "
        "رسمی یا حساس حذف نشود. "
        + length_instruction +
        "فقط متن نهایی را برگردان."
    )


# =========================================================
# CERTAINTY RETRY INSTRUCTION
# =========================================================

def build_certainty_retry_instruction(
    target_length: int,
    content_type: str,
    minimum_length: int = 0
) -> str:

    base_instruction = (
        build_editorial_summary_instruction(
            target_length=target_length,
            content_type=content_type,
            minimum_length=minimum_length
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

        "فقط متن خلاصه‌شده نهایی را برگردان."
    )


# =========================================================
# LENGTH RETRY INSTRUCTION
# =========================================================

def build_length_retry_instruction(
    target_length: int,
    minimum_length: int,
    content_type: str
) -> str:

    base_instruction = (
        build_editorial_summary_instruction(
            target_length=target_length,
            content_type=content_type,
            minimum_length=minimum_length
        )
    )

    return (
        base_instruction
        + " "

        "نسخه قبلی بیش از حد کوتاه بود و بخشی از "
        "اطلاعات یا استدلال لازم برای بازنمایی امن متن "
        "در آن حذف شده بود. "

        "این بار متن اصلی را دوباره از ابتدا تا انتها "
        "بررسی کن و خلاصه را کامل‌تر بنویس. "

        f"خروجی باید حداقل {minimum_length} و حداکثر "
        f"{target_length} کاراکتر باشد. "

        "به سقف طول نزدیک بمان و از کوتاه‌سازی بیش از حد "
        "خودداری کن. "

        "برای افزایش طول، اطلاعات تازه تولید نکن. "

        "فقط از استدلال‌ها، شواهد، علت‌ها، پیامدها "
        "و اطلاعات موجود در متن اصلی استفاده کن. "

        "میزان قطعیت و انتساب دیدگاه‌ها را دقیق حفظ کن. "

        "فقط متن خلاصه‌شده نهایی را برگردان."
    )


# =========================================================
# OVERFLOW RETRY INSTRUCTION
#
# وقتی مدل فقط به دلیل عبور از سقف رد شده باشد،
# کل خلاصه را دور نمی‌اندازیم.
#
# مدل متن اصلی را دوباره می‌بیند و یک نسخه کمی
# فشرده‌تر می‌سازد.
# =========================================================

def build_overflow_retry_instruction(
    target_length: int,
    final_limit: int,
    minimum_length: int,
    content_type: str
) -> str:

    base_instruction = (
        build_editorial_summary_instruction(
            target_length=target_length,
            content_type=content_type,
            minimum_length=minimum_length
        )
    )

    return (
        base_instruction
        + " "

        "نسخه قبلی از نظر محتوایی قابل بررسی بود اما "
        "از سقف فنی طول عبور کرد. "

        "این بار متن اصلی را دوباره از ابتدا تا انتها "
        "بررسی کن و نسخه‌ای کمی فشرده‌تر تولید کن. "

        f"هدف تولید را حدود {target_length} کاراکتر در نظر بگیر "
        f"و تحت هیچ شرایطی از سقف نهایی {final_limit} "
        "کاراکتر عبور نکن. "

        "برای کوتاه‌تر شدن متن، ابتدا تکرارها، توضیحات مشابه، "
        "عبارات کش‌دار، مثال‌های فرعی و جزئیات کم‌اهمیت را "
        "فشرده یا حذف کن. "

        "تز اصلی، استدلال‌های اصلی، علت و نتیجه، بازیگران، "
        "پیامدها و جمع‌بندی مهم متن را حفظ کن. "

        "میزان قطعیت و انتساب دیدگاه‌ها را تغییر نده. "

        "هیچ واقعیت، نام، عدد، تاریخ، تحلیل یا نتیجه تازه‌ای "
        "از خودت اضافه نکن. "

        f"نسخه نهایی نباید کمتر از {minimum_length} کاراکتر "
        "باشد مگر اینکه متن اصلی برای رسیدن به این مقدار "
        "ظرفیت محتوایی نداشته باشد. "

        "فقط متن خلاصه‌شده نهایی را برگردان."
    )


# =========================================================
# REGENERATION INSTRUCTION
# =========================================================

def build_editorial_regeneration_instruction(
    target_length: int,
    content_type: str,
    previous_summary: str,
    minimum_length: int = 0
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

    length_instruction = (
        f"نسخه جدید بدنه نباید بیشتر از "
        f"{target_length} کاراکتر باشد. "
    )

    if minimum_length > 0:

        length_instruction += (
            f"نسخه جدید را کمتر از {minimum_length} "
            "کاراکتر نساز. "
            f"طول مطلوب خروجی بین {minimum_length} "
            f"و {target_length} کاراکتر است. "
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

        + length_instruction +

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
# PROVIDER RESOLUTION
# =========================================================

def resolve_summarizer(
    summarizer: Optional[
        Callable[[str, str, int], str]
    ]
) -> Optional[
    Callable[[str, str, int], str]
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
        max_reduction_ratio=max_reduction_ratio,
        content_type=(
            get_validator_content_type(
                content_type
            )
        )
    )


# =========================================================
# VALIDATION ERROR HELPERS
# =========================================================

def get_validation_errors(
    validation: Optional[
        Dict[str, Any]
    ]
) -> set:

    if not validation:

        return set()

    return set(
        validation.get(
            "errors",
            []
        )
        or []
    )


def only_certainty_validation_error(
    validation: Optional[
        Dict[str, Any]
    ]
) -> bool:

    return (
        get_validation_errors(
            validation
        )
        == {
            "certainty_markers_lost"
        }
    )


def only_overflow_validation_error(
    validation: Optional[
        Dict[str, Any]
    ]
) -> bool:

    return (
        get_validation_errors(
            validation
        )
        == {
            "summary_exceeds_target"
        }
    )


def can_length_retry_validation(
    validation: Optional[
        Dict[str, Any]
    ]
) -> bool:

    errors = (
        get_validation_errors(
            validation
        )
    )

    if not errors:

        return False

    return errors.issubset({
        "reduction_too_aggressive",
        "certainty_markers_lost",
    }) and (
        "reduction_too_aggressive"
        in errors
    )


# =========================================================
# OVERFLOW SAFE REDUCTION
# =========================================================

SENTENCE_BOUNDARY_PATTERN = re.compile(
    r"[.!?؟؛۔](?:[\]\)»\"'”’\s]|$)"
)

BOUNDARY_RANK = {
    "word":
        1,
    "sentence":
        2,
    "paragraph":
        3,
}

# =========================================================
# FIX A: PERSIAN INCOMPLETE CONNECTOR DETECTION
#
# هنگامی که برش مرزی-کلمه‌ای متن را در میانه یک
# ساختار ناقص فارسی قطع می‌کند، نتیجه معنایی ندارد.
# این فهرست غیر جامع است؛ شامل رایج‌ترین موارد است.
# =========================================================

PERSIAN_INCOMPLETE_CONNECTORS = (
    "نه از",
    "نه به",
    "نه برای",
    "در حالی که",
    "به دلیل",
    "به رغم",
    "در نتیجه",
    "از سوی",
    "از جمله",
    "از",
    "به",
    "در",
    "با",
    "برای",
    "که",
    "و",
    "یا",
    "اما",
    "بلکه",
    "اگر",
    "چون",
    "تا",
    "این",
    "آن",
)


def _ends_with_incomplete_connector(
    text: str
) -> bool:
    """
    بررسی می‌کند که آیا متن با یک接続詞 ناقص فارسی پایان می‌یابد.
    فقط زمانی مثبت است که کلمه آخر دقیقاً با فاصله از متن قبل جدا شده باشد.
    """

    stripped = text.rstrip()

    if not stripped:
        return False

    for connector in PERSIAN_INCOMPLETE_CONNECTORS:

        if not stripped.endswith(connector):
            continue

        prefix = stripped[
            : -len(connector)
        ]

        if (
            not prefix
            or prefix[-1].isspace()
        ):
            return True

    return False


def _cuts_word_middle(
    text: str,
    cut_index: int
) -> bool:

    if (
        cut_index <= 0
        or cut_index >= len(text)
    ):
        return False

    return (
        text[
            cut_index - 1
        ].isalnum()
        and text[
            cut_index
        ].isalnum()
    )


def reduce_overflow_at_safe_boundaries(
    text: str,
    limit: int
) -> List[Dict[str, str]]:

    text = normalize_text(
        text
    )

    if not text:
        return []

    if (
        limit <= 0
        or len(text)
        <= limit
    ):
        return []

    def build_reduced(
        cut_index: int,
        boundary: str
    ) -> Optional[Dict[str, str]]:

        if (
            cut_index <= 0
            or cut_index > len(text)
            or cut_index > limit
        ):
            return None

        if _cuts_word_middle(
            text,
            cut_index
        ):
            return None

        reduced = normalize_text(
            text[
                :cut_index
            ].rstrip()
        )

        if (
            not reduced
            or len(reduced)
            > limit
        ):
            return None

        return {
            "text":
                reduced,
            "boundary":
                boundary,
        }

    candidates: List[Dict[str, str]] = []

    paragraph_index = -1

    for separator in (
        "\r\n\r\n",
        "\n\n",
    ):

        found = text.rfind(
            separator,
            0,
            limit + 1
        )

        if found > paragraph_index:
            paragraph_index = found

    if paragraph_index > 0:

        reduced = build_reduced(
            paragraph_index,
            "paragraph"
        )

        if reduced is not None:
            candidates.append(
                reduced
            )

    sentence_cut = -1

    for match in (
        SENTENCE_BOUNDARY_PATTERN.finditer(
            text
        )
    ):

        boundary = match.start() + 1

        if boundary <= limit:
            sentence_cut = boundary
        else:
            break

    if sentence_cut > 0:

        reduced = build_reduced(
            sentence_cut,
            "sentence"
        )

        if (
            reduced is not None
            and all(
                item["text"] != reduced["text"]
                for item in candidates
            )
        ):
            candidates.append(
                reduced
            )

    whitespace_cut = -1

    for index in range(
        limit,
        0,
        -1
    ):

        if text[
            index - 1
        ].isspace():
            whitespace_cut = index - 1
            break

    if whitespace_cut > 0:

        reduced = build_reduced(
            whitespace_cut,
            "word"
        )

        if (
            reduced is not None
            and not _ends_with_incomplete_connector(
                reduced["text"]
            )
            and all(
                item["text"] != reduced["text"]
                for item in candidates
            )
        ):
            candidates.append(
                reduced
            )

    if not candidates:
        return []

    return candidates


def reduce_overflow_at_safe_boundary(
    text: str,
    limit: int
) -> Optional[Dict[str, str]]:

    reduced_candidates = (
        reduce_overflow_at_safe_boundaries(
            text=text,
            limit=limit
        )
    )

    if not reduced_candidates:
        return None

    return reduced_candidates[0]


def reduce_valid_overflow_candidate(
    original_text: str,
    candidate_text: str,
    validation: Optional[
        Dict[str, Any]
    ],
    target_length: int,
    content_type: str
) -> Optional[Dict[str, Any]]:

    if not only_overflow_validation_error(
        validation
    ):
        return None

    reduced_candidates: List[
        Dict[str, Any]
    ] = []

    for reduced in (
        reduce_overflow_at_safe_boundaries(
            text=candidate_text,
            limit=target_length
        )
    ):
        reduced_text = reduced[
            "text"
        ]

        if any(
            item[
                "candidate"
            ] == reduced_text
            for item in reduced_candidates
        ):
            continue

        reduced_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=reduced_text,
                target_length=target_length,
                content_type=content_type
            )
        )

        if reduced_validation[
            "valid"
        ]:
            reduced_candidates.append({
                "candidate":
                    reduced_text,
                "validation":
                    reduced_validation,
                "boundary":
                    reduced[
                        "boundary"
                    ],
            })

    if not reduced_candidates:
        return None

    return (
        select_best_reduced_overflow_candidate(
            reduced_candidates
        )
    )


def select_best_reduced_overflow_candidate(
    candidates: List[
        Dict[str, Any]
    ]
) -> Optional[Dict[str, Any]]:

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: (
            BOUNDARY_RANK.get(
                item.get(
                    "boundary",
                    "word"
                ),
                0
            ),
            len(
                item.get(
                    "candidate",
                    ""
                )
            ),
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
    ],
    minimum_length: int = 0
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
            "success":
                False,

            "candidate":
                "",

            "validation":
                None,

            "reason":
                "provider_error",

            "error":
                str(
                    e
                ),

            "certainty_retry_called":
                False,

            "length_retry_called":
                False,

            "overflow_retry_called":
                False
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
            "success":
                True,

            "candidate":
                candidate,

            "validation":
                validation,

            "reason":
                "accepted",

            "error":
                None,

            "certainty_retry_called":
                False,

            "length_retry_called":
                False,

            "overflow_retry_called":
                False
        }

    # =====================================================
    # OVERFLOW RETRY
    #
    # مثال واقعی:
    #
    # target = 1059
    # Gemini = 1103
    #
    # قبلاً خلاصه کامل رد می‌شد.
    #
    # اکنون اگر تنها ایراد summary_exceeds_target باشد،
    # یک بار دیگر با هدف پایین‌تر بازتولید می‌کنیم.
    # =====================================================

    can_retry_overflow = (
        OVERFLOW_RETRY_ENABLED
        and content_type
        in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
        and only_overflow_validation_error(
            validation
        )
    )

    if can_retry_overflow:
        reduced_candidates: List[
            Dict[str, Any]
        ] = []

        first_reduced = (
            reduce_valid_overflow_candidate(
                original_text=original_text,
                candidate_text=candidate,
                validation=validation,
                target_length=target_length,
                content_type=content_type
            )
        )

        if first_reduced is not None:
            reduced_candidates.append({
                **first_reduced,
                "source":
                    "first",
            })


        overflow_target = (
            target_length
            - OVERFLOW_RETRY_MARGIN
        )

        if minimum_length > 0:

            overflow_target = max(
                minimum_length,
                overflow_target
            )

        overflow_target = max(
            1,
            overflow_target
        )

        overflow_target = min(
            overflow_target,
            target_length
        )

        logger.info(
            f"📐 Editorial overflow retry | "
            f"type={content_type} | "
            f"first_output={len(candidate)} | "
            f"final_limit={target_length} | "
            f"retry_target={overflow_target} | "
            f"minimum={minimum_length}"
        )

        overflow_instruction = (
            build_overflow_retry_instruction(
                target_length=(
                    overflow_target
                ),
                final_limit=(
                    target_length
                ),
                minimum_length=(
                    minimum_length
                ),
                content_type=(
                    content_type
                )
            )
        )

        try:

            overflow_candidate = (
                summarizer(
                    original_text,
                    overflow_instruction,
                    overflow_target
                )
            )

        except Exception as e:

            logger.exception(
                f"❌ Editorial overflow retry failed | "
                f"{e}"
            )

            best_reduced = (
                select_best_reduced_overflow_candidate(
                    reduced_candidates
                )
            )

            if best_reduced is not None:

                logger.info(
                    f"✅ Editorial overflow boundary "
                    f"fallback accepted | "
                    f"type={content_type} | "
                    f"source={best_reduced['source']} | "
                    f"boundary={best_reduced['boundary']} | "
                    f"final={len(best_reduced['candidate'])} | "
                    f"target={target_length}"
                )

                return {
                    "success":
                        True,

                    "candidate":
                        best_reduced[
                            "candidate"
                        ],

                    "validation":
                        best_reduced[
                            "validation"
                        ],

                    "reason":
                        "accepted_after_overflow_boundary_reduction",

                    "error":
                        None,

                    "certainty_retry_called":
                        False,

                    "length_retry_called":
                        False,

                    "overflow_retry_called":
                        True,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation,

                    "overflow_target":
                        overflow_target,

                    "overflow_reduction_source":
                        best_reduced[
                            "source"
                        ],

                    "overflow_reduction_boundary":
                        best_reduced[
                            "boundary"
                        ]
                }

            return {
                "success":
                    False,

                "candidate":
                    candidate,

                "validation":
                    validation,

                "reason":
                    "overflow_retry_provider_error",

                "error":
                    str(
                        e
                    ),

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    False,

                "overflow_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation,

                "overflow_target":
                    overflow_target
            }

        overflow_candidate = normalize_text(
            overflow_candidate
        )

        # مهم:
        # Validator با سقف نهایی اصلی اجرا می‌شود،
        # نه سقف کوچک‌تر Retry.
        #
        # بنابراین اگر Gemini مثلاً target=979 گرفته ولی
        # خروجی 1010 داده باشد، هنوز چون از final=1059
        # کمتر است می‌تواند معتبر باشد.
        overflow_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=(
                    overflow_candidate
                ),
                target_length=(
                    target_length
                ),
                content_type=(
                    content_type
                )
            )
        )

        if overflow_validation[
            "valid"
        ]:

            logger.info(
                f"✅ Editorial overflow retry accepted | "
                f"type={content_type} | "
                f"first={len(candidate)} | "
                f"final={len(overflow_candidate)} | "
                f"retry_target={overflow_target} | "
                f"final_limit={target_length}"
            )

            return {
                "success":
                    True,

                "candidate":
                    overflow_candidate,

                "validation":
                    overflow_validation,

                "reason":
                    "accepted_after_overflow_retry",

                "error":
                    None,

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    False,

                "overflow_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation,

                "overflow_target":
                    overflow_target
            }

        # اگر Retry طولی، متن را بیش از حد کوتاه کرد،
        # مسیر موجود LENGTH RETRY اجازه دارد اصلاحش کند.
        if (
            LENGTH_RETRY_ENABLED
            and minimum_length > 0
            and can_length_retry_validation(
                overflow_validation
            )
        ):

            logger.info(
                f"📏 Editorial length retry "
                f"after overflow | "
                f"type={content_type} | "
                f"output={len(overflow_candidate)} | "
                f"minimum={minimum_length} | "
                f"target={target_length}"
            )

            length_instruction = (
                build_length_retry_instruction(
                    target_length=(
                        target_length
                    ),
                    minimum_length=(
                        minimum_length
                    ),
                    content_type=(
                        content_type
                    )
                )
            )

            try:

                length_candidate = (
                    summarizer(
                        original_text,
                        length_instruction,
                        target_length
                    )
                )

            except Exception as e:

                logger.exception(
                    f"❌ Editorial length retry "
                    f"after overflow failed | {e}"
                )

                return {
                    "success":
                        False,

                    "candidate":
                        overflow_candidate,

                    "validation":
                        overflow_validation,

                    "reason":
                        "length_retry_provider_error",

                    "error":
                        str(
                            e
                        ),

                    "certainty_retry_called":
                        False,

                    "length_retry_called":
                        True,

                    "overflow_retry_called":
                        True,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation,

                    "overflow_target":
                        overflow_target
                }

            length_candidate = (
                normalize_text(
                    length_candidate
                )
            )

            length_validation = (
                validate_editorial_candidate(
                    original_text=original_text,
                    candidate_text=(
                        length_candidate
                    ),
                    target_length=(
                        target_length
                    ),
                    content_type=(
                        content_type
                    )
                )
            )

            if length_validation[
                "valid"
            ]:

                logger.info(
                    f"✅ Editorial overflow + length "
                    f"retry accepted | "
                    f"type={content_type} | "
                    f"final="
                    f"{len(length_candidate)}"
                )

                return {
                    "success":
                        True,

                    "candidate":
                        length_candidate,

                    "validation":
                        length_validation,

                    "reason":
                        "accepted_after_overflow_and_length_retry",

                    "error":
                        None,

                    "certainty_retry_called":
                        False,

                    "length_retry_called":
                        True,

                    "overflow_retry_called":
                        True,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation,

                    "overflow_target":
                        overflow_target
                }

        overflow_reduced = (
            reduce_valid_overflow_candidate(
                original_text=original_text,
                candidate_text=overflow_candidate,
                validation=overflow_validation,
                target_length=target_length,
                content_type=content_type
            )
        )

        if overflow_reduced is not None:
            reduced_candidates.append({
                **overflow_reduced,
                "source":
                    "retry",
            })

        best_reduced = (
            select_best_reduced_overflow_candidate(
                reduced_candidates
            )
        )

        if best_reduced is not None:

            logger.info(
                f"✅ Editorial overflow boundary "
                f"fallback accepted | "
                f"type={content_type} | "
                f"source={best_reduced['source']} | "
                f"boundary={best_reduced['boundary']} | "
                f"first={len(candidate)} | "
                f"retry={len(overflow_candidate)} | "
                f"final={len(best_reduced['candidate'])} | "
                f"target={target_length}"
            )

            return {
                "success":
                    True,

                "candidate":
                    best_reduced[
                        "candidate"
                    ],

                "validation":
                    best_reduced[
                        "validation"
                    ],

                "reason":
                    "accepted_after_overflow_boundary_reduction",

                "error":
                    None,

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    False,

                "overflow_retry_called":
                    True,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation,

                "overflow_target":
                    overflow_target,

                "overflow_reduction_source":
                    best_reduced[
                        "source"
                    ],

                "overflow_reduction_boundary":
                    best_reduced[
                        "boundary"
                    ]
            }

        logger.warning(
            f"⚠️ Editorial overflow retry rejected | "
            f"type={content_type} | "
            f"first={len(candidate)} | "
            f"retry={len(overflow_candidate)} | "
            f"errors="
            f"{overflow_validation.get('errors', [])} | "
            f"final_limit={target_length}"
        )

        return {
            "success":
                False,

            "candidate":
                overflow_candidate,

            "validation":
                overflow_validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                False,

            "length_retry_called":
                False,

            "overflow_retry_called":
                True,

            "first_candidate":
                candidate,

            "first_validation":
                validation,

            "overflow_target":
                overflow_target
        }

    # =====================================================
    # LENGTH RETRY
    # =====================================================

    can_retry_length = (
        LENGTH_RETRY_ENABLED
        and content_type
        in (
            CONTENT_TYPE_OPINION_NOTE,
            CONTENT_TYPE_NEWS_ANALYSIS,
        )
        and minimum_length > 0
        and can_length_retry_validation(
            validation
        )
    )

    if can_retry_length:

        logger.info(
            f"📏 Editorial length retry | "
            f"type={content_type} | "
            f"first_output={len(candidate)} | "
            f"minimum={minimum_length} | "
            f"target={target_length} | "
            f"errors="
            f"{validation.get('errors', [])}"
        )

        retry_instruction = (
            build_length_retry_instruction(
                target_length=target_length,
                minimum_length=minimum_length,
                content_type=content_type
            )
        )

        try:

            retry_candidate = (
                summarizer(
                    original_text,
                    retry_instruction,
                    target_length
                )
            )

        except Exception as e:

            logger.exception(
                f"❌ Editorial length retry failed | "
                f"{e}"
            )

            return {
                "success":
                    False,

                "candidate":
                    candidate,

                "validation":
                    validation,

                "reason":
                    "length_retry_provider_error",

                "error":
                    str(
                        e
                    ),

                "certainty_retry_called":
                    False,

                "length_retry_called":
                    True,

                "overflow_retry_called":
                    False
            }

        retry_candidate = (
            normalize_text(
                retry_candidate
            )
        )

        retry_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=(
                    retry_candidate
                ),
                target_length=(
                    target_length
                ),
                content_type=(
                    content_type
                )
            )
        )

        if retry_validation[
            "valid"
        ]:

            logger.info(
                f"✅ Editorial length retry accepted | "
                f"type={content_type} | "
                f"output={len(retry_candidate)} | "
                f"minimum={minimum_length} | "
                f"target={target_length}"
            )

            return {
                "success":
                    True,

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

                "overflow_retry_called":
                    False,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation
            }

        if (
            CERTAINTY_RETRY_ENABLED
            and only_certainty_validation_error(
                retry_validation
            )
        ):

            logger.info(
                f"🔁 Editorial certainty retry "
                f"after length retry | "
                f"type={content_type} | "
                f"output={len(retry_candidate)} | "
                f"target={target_length}"
            )

            certainty_instruction = (
                build_certainty_retry_instruction(
                    target_length=target_length,
                    content_type=content_type,
                    minimum_length=minimum_length
                )
            )

            try:

                certainty_candidate = (
                    summarizer(
                        original_text,
                        certainty_instruction,
                        target_length
                    )
                )

            except Exception as e:

                logger.exception(
                    f"❌ Editorial certainty retry "
                    f"after length failed | "
                    f"{e}"
                )

                return {
                    "success":
                        False,

                    "candidate":
                        retry_candidate,

                    "validation":
                        retry_validation,

                    "reason":
                        "certainty_retry_provider_error",

                    "error":
                        str(
                            e
                        ),

                    "certainty_retry_called":
                        True,

                    "length_retry_called":
                        True,

                    "overflow_retry_called":
                        False
                }

            certainty_candidate = (
                normalize_text(
                    certainty_candidate
                )
            )

            certainty_validation = (
                validate_editorial_candidate(
                    original_text=original_text,
                    candidate_text=(
                        certainty_candidate
                    ),
                    target_length=(
                        target_length
                    ),
                    content_type=(
                        content_type
                    )
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
                    "success":
                        True,

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

                    "overflow_retry_called":
                        False,

                    "first_candidate":
                        candidate,

                    "first_validation":
                        validation
                }

            retry_candidate = (
                certainty_candidate
            )

            retry_validation = (
                certainty_validation
            )

        logger.warning(
            f"⚠️ Editorial length retry rejected | "
            f"type={content_type} | "
            f"errors="
            f"{retry_validation['errors']} | "
            f"output={len(retry_candidate)} | "
            f"minimum={minimum_length} | "
            f"target={target_length}"
        )

        return {
            "success":
                False,

            "candidate":
                retry_candidate,

            "validation":
                retry_validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                only_certainty_validation_error(
                    retry_validation
                ),

            "length_retry_called":
                True,

            "overflow_retry_called":
                False,

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
                content_type=content_type,
                minimum_length=minimum_length
            )
        )

        try:

            retry_candidate = (
                summarizer(
                    original_text,
                    retry_instruction,
                    target_length
                )
            )

        except Exception as e:

            logger.exception(
                f"❌ Editorial certainty retry failed | "
                f"{e}"
            )

            return {
                "success":
                    False,

                "candidate":
                    candidate,

                "validation":
                    validation,

                "reason":
                    "certainty_retry_provider_error",

                "error":
                    str(
                        e
                    ),

                "certainty_retry_called":
                    True,

                "length_retry_called":
                    False,

                "overflow_retry_called":
                    False
            }

        retry_candidate = (
            normalize_text(
                retry_candidate
            )
        )

        retry_validation = (
            validate_editorial_candidate(
                original_text=original_text,
                candidate_text=(
                    retry_candidate
                ),
                target_length=(
                    target_length
                ),
                content_type=(
                    content_type
                )
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
                "success":
                    True,

                "candidate":
                    retry_candidate,

                "validation":
                    retry_validation,

                "reason":
                    "accepted_after_certainty_retry",

                "error":
                    None,

                "certainty_retry_called":
                    True,

                "length_retry_called":
                    False,

                "overflow_retry_called":
                    False,

                "first_candidate":
                    candidate,

                "first_validation":
                    validation
            }

        logger.warning(
            f"⚠️ Editorial certainty retry rejected | "
            f"type={content_type} | "
            f"errors="
            f"{retry_validation['errors']} | "
            f"output={len(retry_candidate)} | "
            f"target={target_length}"
        )

        return {
            "success":
                False,

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

            "overflow_retry_called":
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
        f"minimum={minimum_length} | "
        f"target={target_length}"
    )

    return {
        "success":
            False,

        "candidate":
            candidate,

        "validation":
            validation,

        "reason":
            "validation_failed",

        "error":
            None,

        "certainty_retry_called":
            False,

        "length_retry_called":
            False,

        "overflow_retry_called":
            False
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
            "success":
                False,

            "candidate":
                "",

            "validation":
                None,

            "reason":
                "provider_error",

            "error":
                str(
                    e
                ),

            "certainty_retry_called":
                False
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
            "success":
                True,

            "candidate":
                candidate,

            "validation":
                validation,

            "reason":
                "accepted",

            "error":
                None,

            "certainty_retry_called":
                False
        }

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
            "success":
                False,

            "candidate":
                candidate,

            "validation":
                validation,

            "reason":
                "validation_failed",

            "error":
                None,

            "certainty_retry_called":
                False
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
            "success":
                False,

            "candidate":
                candidate,

            "validation":
                validation,

            "reason":
                "certainty_retry_provider_error",

            "error":
                str(
                    e
                ),

            "certainty_retry_called":
                True
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
            "success":
                True,

            "candidate":
                retry_candidate,

            "validation":
                retry_validation,

            "reason":
                "accepted_after_certainty_retry",

            "error":
                None,

            "certainty_retry_called":
                True,

            "first_candidate":
                candidate,

            "first_validation":
                validation
        }

    return {
        "success":
            False,

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

        "first_candidate":
            candidate,

        "first_validation":
            validation
    }


# =========================================================
# EDITORIAL SUMMARY
# =========================================================

def summarize_editorial_content(
    original_text: str,
    content_type: str,
    target_length: int = DEFAULT_REVIEW_TARGET,
    summarizer: Optional[
        Callable[[str, str, int], str]
    ] = None
) -> Optional[Dict[str, Any]]:

    original_text = normalize_text(
        original_text
    )

    if not original_text:

        return None

    if content_type not in (
        CONTENT_TYPE_OPINION_NOTE,
        CONTENT_TYPE_NEWS_ANALYSIS,
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

    target_info = (
        resolve_effective_target(
            original_text=original_text,
            content_type=content_type,
            requested_target=target_length
        )
    )

    effective_target = (
        target_info[
            "effective_target"
        ]
    )

    minimum_safe = (
        target_info[
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
            "success":
                True,

            "candidate":
                original_text,

            "validation":
                validation,

            "reason":
                "already_fits",

            "summarizer_called":
                False,

            "certainty_retry_called":
                False,

            "length_retry_called":
                False,

            "overflow_retry_called":
                False,

            **target_info
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
            content_type=content_type,
            minimum_length=minimum_safe
        )
    )

    generation = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=effective_target,
            content_type=content_type,
            summarizer=resolved_summarizer,
            minimum_length=minimum_safe
        )
    )

    generation[
        "summarizer_called"
    ] = True

    generation.update(
        target_info
    )

    return generation


# =========================================================
# REGENERATE EDITORIAL SUMMARY
# =========================================================

def regenerate_editorial_summary(
    original_text: str,
    previous_summary: str,
    content_type: str,
    target_length: int = DEFAULT_REVIEW_TARGET,
    regeneration_count: int = 0,
    summarizer: Optional[
        Callable[[str, str, int], str]
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

    if content_type not in (
        CONTENT_TYPE_OPINION_NOTE,
        CONTENT_TYPE_NEWS_ANALYSIS,
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
            reason=(
                "regeneration_not_allowed_for_content_type"
            ),
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
            reason=(
                "regeneration_provider_unavailable"
            ),
            metadata={
                "regeneration_count":
                    regeneration_count,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT
            }
        )

    target_info = (
        resolve_effective_target(
            original_text=original_text,
            content_type=content_type,
            requested_target=target_length
        )
    )

    effective_target = (
        target_info[
            "effective_target"
        ]
    )

    minimum_safe = (
        target_info[
            "minimum_safe"
        ]
    )

    generation_target = max(
        MIN_REGENERATION_TARGET,
        effective_target
        - REGENERATION_TARGET_MARGIN
    )

    generation_target = max(
        generation_target,
        minimum_safe
    )

    generation_target = min(
        generation_target,
        effective_target
    )

    instruction = (
        build_editorial_regeneration_instruction(
            target_length=generation_target,
            content_type=content_type,
            previous_summary=previous_summary,
            minimum_length=minimum_safe
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
        f"generation_target={generation_target}"
    )

    generation = (
        generate_editorial_candidate(
            original_text=original_text,
            instruction=instruction,
            target_length=generation_target,
            content_type=content_type,
            summarizer=resolved_summarizer,
            minimum_length=minimum_safe
        )
    )

    generation.update(
        target_info
    )

    generation[
        "generation_target"
    ] = generation_target

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

                "can_regenerate":
                    next_count
                    < MAX_REGENERATION_COUNT,

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

                "overflow_retry_called":
                    generation.get(
                        "overflow_retry_called",
                        False
                    ),

                "requested_target":
                    target_length,

                "effective_target":
                    effective_target,

                "minimum_safe":
                    minimum_safe,

                "generation_target":
                    generation_target
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
            f"same summary | "
            f"count={next_count}"
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
            reason=(
                "regeneration_same_as_previous"
            ),
            metadata={
                "regeneration_count":
                    next_count,

                "max_regeneration_count":
                    MAX_REGENERATION_COUNT,

                "can_regenerate":
                    next_count
                    < MAX_REGENERATION_COUNT,

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

                "overflow_retry_called":
                    generation.get(
                        "overflow_retry_called",
                        False
                    ),

                "requested_target":
                    target_length,

                "effective_target":
                    effective_target,

                "minimum_safe":
                    minimum_safe,

                "generation_target":
                    generation_target
            }
        )

    if (
        len(new_summary)
        > effective_target
    ):

        logger.warning(
            f"⚠️ Regenerated editorial summary "
            f"exceeds effective target | "
            f"final={len(new_summary)} | "
            f"effective={effective_target}"
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

                "can_regenerate":
                    next_count
                    < MAX_REGENERATION_COUNT,

                "generation_reason":
                    "summary_exceeds_target",

                "requested_target":
                    target_length,

                "effective_target":
                    effective_target,

                "minimum_safe":
                    minimum_safe,

                "generation_target":
                    generation_target
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
        target_length=target_length,
        original_length=original_length,
        suggested_length=len(
            new_summary
        ),
        reason=(
            "editorial_regeneration_ready"
        ),
        metadata={
            "regeneration_count":
                next_count,

            "max_regeneration_count":
                MAX_REGENERATION_COUNT,

            "can_regenerate":
                next_count
                < MAX_REGENERATION_COUNT,

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

            "overflow_retry_called":
                generation.get(
                    "overflow_retry_called",
                    False
                ),

            "requested_target":
                target_length,

            "effective_target":
                effective_target,

            "minimum_safe":
                minimum_safe,

            "generation_target":
                generation_target
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
    target_length: int = DEFAULT_REVIEW_TARGET,
    summarizer: Optional[
        Callable[[str, str, int], str]
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
            reason=(
                "admin_instruction_original_empty"
            ),
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
            reason="admin_instruction_empty",
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
            reason=(
                "admin_instruction_too_long"
            ),
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

    if content_type not in (
        CONTENT_TYPE_OPINION_NOTE,
        CONTENT_TYPE_NEWS_ANALYSIS,
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
            reason=(
                "admin_instruction_not_allowed_for_content_type"
            ),
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
            reason=(
                "admin_instruction_provider_unavailable"
            ),
            metadata={
                "admin_instruction":
                    admin_instruction
            }
        )

    edit_target = max(
        MIN_ADMIN_INSTRUCTION_TARGET,
        target_length
        - ADMIN_INSTRUCTION_TARGET_MARGIN
    )

    edit_target = min(
        edit_target,
        target_length
    )

    logger.info(
        f"✏️ Admin editorial edit started | "
        f"type={content_type} | "
        f"body={original_length} | "
        f"previous={len(previous_summary)} | "
        f"instruction={len(admin_instruction)} | "
        f"target={edit_target}"
    )

    generation = (
        generate_admin_instruction_candidate(
            original_text=original_text,
            previous_summary=previous_summary,
            admin_instruction=admin_instruction,
            target_length=edit_target,
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
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
                or original_text
            ),
            reason=(
                "admin_instruction_failed"
            ),
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
                    )
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
            target_length=target_length,
            original_length=original_length,
            suggested_length=len(
                previous_summary
            ),
            reason=(
                "admin_instruction_no_change"
            ),
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
                    )
            }
        )

    if (
        len(new_summary)
        > target_length
    ):

        logger.warning(
            f"⚠️ Admin edited summary exceeds "
            f"final target | "
            f"final={len(new_summary)} | "
            f"target={target_length}"
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
            reason=(
                "admin_instruction_failed"
            ),
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
        target_length=target_length,
        original_length=original_length,
        suggested_length=len(
            new_summary
        ),
        reason="admin_instruction_ready",
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

            "admin_instruction_applied":
                True
        }
    )


# =========================================================
# MAIN REVIEW ANALYZER
# =========================================================

def analyze_editorial_content(
    original_text: str,
    target_length: int = DEFAULT_REVIEW_TARGET,
    classifier: Optional[
        Callable[[str, str, int], str]
    ] = None,
    summarizer: Optional[
        Callable[[str, str, int], str]
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
            content_type=(
                CONTENT_TYPE_UNCERTAIN
            ),
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
                "classification_only":
                    True,

                "regeneration_count":
                    0,

                "can_regenerate":
                    False
            }
        )

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
            reason=(
                "sensitive_content_preserved"
            ),
            metadata={
                "automatic_summary":
                    False,

                "regeneration_count":
                    0,

                "can_regenerate":
                    False
            }
        )

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

        metadata: Dict[
            str,
            Any
        ] = {
            "regeneration_count":
                0,

            "max_regeneration_count":
                MAX_REGENERATION_COUNT,

            "can_regenerate":
                False
        }

        if (
            summary_result
            is not None
        ):

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
                    ),

                "overflow_retry_called":
                    summary_result.get(
                        "overflow_retry_called",
                        False
                    ),

                "requested_target":
                    summary_result.get(
                        "requested_target"
                    ),

                "effective_target":
                    summary_result.get(
                        "effective_target"
                    ),

                "minimum_safe":
                    summary_result.get(
                        "minimum_safe"
                    ),

                "adaptive_target":
                    summary_result.get(
                        "adaptive_target",
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
            target_length=target_length,
            original_length=original_length,
            suggested_length=original_length,
            reason="summary_unavailable",
            metadata=metadata
        )

    suggested_text = normalize_text(
        summary_result[
            "candidate"
        ]
    )

    logger.info(
        f"✅ Editorial review prepared | "
        f"type={content_type} | "
        f"before={original_length} | "
        f"after={len(suggested_text)} | "
        f"certainty_retry="
        f"{summary_result.get('certainty_retry_called', False)} | "
        f"length_retry="
        f"{summary_result.get('length_retry_called', False)} | "
        f"overflow_retry="
        f"{summary_result.get('overflow_retry_called', False)} | "
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

            "overflow_retry_called":
                summary_result.get(
                    "overflow_retry_called",
                    False
                ),

            "requested_target":
                summary_result.get(
                    "requested_target"
                ),

            "effective_target":
                summary_result.get(
                    "effective_target"
                ),

            "minimum_safe":
                summary_result.get(
                    "minimum_safe"
                ),

            "adaptive_target":
                summary_result.get(
                    "adaptive_target",
                    False
                )
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
