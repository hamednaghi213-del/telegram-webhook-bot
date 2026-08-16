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

from core.editorial_structure import (
    EditorialStructure,
    extract_editorial_structure,
    rebuild_editorial_text,
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
# STRUCTURE POLICY
# =========================================================

EDITORIAL_SEPARATOR = "\n\n"


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
# =========================================================

def get_validator_content_type(
    content_type: str
) -> str:

    return CONTENT_TYPE_NORMAL


# =========================================================
# EDITORIAL STRUCTURE
# =========================================================

def get_editorial_structure(
    original_text: str
) -> EditorialStructure:

    structure = (
        extract_editorial_structure(
            original_text
        )
    )

    logger.info(
        f"🧩 Editorial review structure | "
        f"title={structure.title or '-'} | "
        f"author={structure.author or '-'} | "
        f"author_source="
        f"{structure.author_source} | "
        f"body={len(structure.body)}"
    )

    return structure


# =========================================================
# STRUCTURE OVERHEAD
#
# Title و Author جزو سقف نهایی 950 کاراکتر هستند.
# بنابراین ظرفیت واقعی Body جدا محاسبه می‌شود.
# =========================================================

def calculate_editorial_body_target(
    structure: EditorialStructure,
    target_length: int
) -> int:

    target_length = max(
        1,
        int(
            target_length
        )
    )

    overhead = 0

    if structure.title:

        overhead += len(
            structure.title
        )

    if structure.author:

        if overhead:
            overhead += len(
                EDITORIAL_SEPARATOR
            )

        overhead += len(
            structure.author
        )

    if (
        structure.body
        and (
            structure.title
            or structure.author
        )
    ):

        overhead += len(
            EDITORIAL_SEPARATOR
        )

    available = (
        target_length
        - overhead
    )

    return max(
        1,
        available
    )


# =========================================================
# FINAL EDITORIAL OUTPUT
# =========================================================

def rebuild_editorial_summary(
    structure: EditorialStructure,
    summary_body: str
) -> str:

    return (
        rebuild_editorial_text(
            title=structure.title,
            author=structure.author,
            body=summary_body
        )
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

        "تیتر و نام نویسنده در این ورودی وجود ندارند و "
        "نباید تیتر یا نام نویسنده تازه‌ای تولید کنی. "
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

        "تیتر و نام نویسنده را تولید یا بازنویسی نکن. "

        "نسخه جدید باید مستقل، روان، منسجم و قابل انتشار باشد. "

        f"نسخه جدید بدنه نباید بیشتر از {target_length} "
        "کاراکتر باشد. "

        "فقط نسخه جدید بدنه را برگردان. "

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
#
# مهم:
#
# این تابع ساختار متن را استخراج می‌کند.
#
# Title و Author به AI داده نمی‌شوند.
#
# فقط کل Body از ابتدا تا انتها به AI داده می‌شود.
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

    # =====================================================
    # STRUCTURE
    # =====================================================

    structure = (
        get_editorial_structure(
            original_text
        )
    )

    body = normalize_text(
        structure.body
    )

    # اگر به هر دلیل Body خالی شد،
    # برای جلوگیری از از دست رفتن متن، کل متن مبنا می‌شود.
    if not body:

        logger.warning(
            "⚠️ Editorial structure returned empty body | "
            "using original text"
        )

        body = original_text

    body_target = (
        calculate_editorial_body_target(
            structure,
            target_length
        )
    )

    logger.info(
        f"🧠 Editorial full-body summary | "
        f"type={content_type} | "
        f"original={len(original_text)} | "
        f"body={len(body)} | "
        f"title={len(structure.title)} | "
        f"author={len(structure.author)} | "
        f"body_target={body_target} | "
        f"final_target={target_length}"
    )

    resolved_summarizer = (
        resolve_summarizer(
            summarizer
        )
    )

    if resolved_summarizer is None:
        return None

    # =====================================================
    # BODY ALREADY FITS
    # =====================================================

    if len(body) <= body_target:

        validation = (
            validate_editorial_candidate(
                original_text=body,
                candidate_text=body,
                target_length=body_target,
                content_type=content_type
            )
        )

        final_candidate = (
            rebuild_editorial_summary(
                structure,
                body
            )
        )

        return {
            "success": True,
            "candidate": final_candidate,
            "body_candidate": body,
            "validation": validation,
            "reason": "already_fits",
            "summarizer_called": False,
            "structure": {
                "title": structure.title,
                "author": structure.author,
                "author_source":
                    structure.author_source,
                "author_confidence":
                    structure.author_confidence,
                "body_length": len(body),
                "body_target": body_target
            }
        }

    # =====================================================
    # AI INSTRUCTION
    # =====================================================

    instruction = (
        build_editorial_summary_instruction(
            body_target,
            content_type
        )
    )

    # =====================================================
    # AI GETS FULL BODY
    # =====================================================

    generation = (
        generate_editorial_candidate(
            original_text=body,
            instruction=instruction,
            target_length=body_target,
            content_type=content_type,
            summarizer=resolved_summarizer
        )
    )

    if not generation[
        "success"
    ]:

        generation[
            "summarizer_called"
        ] = True

        generation[
            "structure"
        ] = {
            "title": structure.title,
            "author": structure.author,
            "author_source":
                structure.author_source,
            "author_confidence":
                structure.author_confidence,
            "body_length": len(body),
            "body_target": body_target
        }

        return generation

    summarized_body = normalize_text(
        generation[
            "candidate"
        ]
    )

    final_candidate = (
        rebuild_editorial_summary(
            structure,
            summarized_body
        )
    )

    # =====================================================
    # FINAL HARD LIMIT
    # =====================================================

    if len(final_candidate) > target_length:

        logger.warning(
            f"⚠️ Editorial rebuilt summary too long | "
            f"final={len(final_candidate)} | "
            f"target={target_length}"
        )

        return {
            "success": False,
            "candidate": final_candidate,
            "body_candidate": summarized_body,
            "validation": generation.get(
                "validation"
            ),
            "reason": "rebuilt_summary_exceeds_target",
            "error": None,
            "summarizer_called": True,
            "structure": {
                "title": structure.title,
                "author": structure.author,
                "author_source":
                    structure.author_source,
                "author_confidence":
                    structure.author_confidence,
                "body_length": len(body),
                "body_target": body_target
            }
        }

    logger.info(
        f"✅ Editorial full-body summary rebuilt | "
        f"title={structure.title or '-'} | "
        f"author={structure.author or '-'} | "
        f"body_before={len(body)} | "
        f"body_after={len(summarized_body)} | "
        f"final={len(final_candidate)}"
    )

    return {
        "success": True,
        "candidate": final_candidate,
        "body_candidate": summarized_body,
        "validation": generation.get(
            "validation"
        ),
        "reason": "accepted",
        "error": None,
        "summarizer_called": True,
        "structure": {
            "title": structure.title,
            "author": structure.author,
            "author_source":
                structure.author_source,
            "author_confidence":
                structure.author_confidence,
            "body_length": len(body),
            "body_target": body_target
        }
    }


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
    # STRUCTURE
    # =====================================================

    structure = (
        get_editorial_structure(
            original_text
        )
    )

    original_body = normalize_text(
        structure.body
    )

    if not original_body:

        original_body = (
            original_text
        )

    # خلاصه قبلی هم ممکن است Title و Author داشته باشد.
    previous_structure = (
        extract_editorial_structure(
            previous_summary
        )
        if previous_summary
        else None
    )

    previous_body = ""

    if previous_structure is not None:

        previous_body = normalize_text(
            previous_structure.body
        )

    if not previous_body:

        previous_body = (
            previous_summary
        )

    # =====================================================
    # TARGET
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

    body_target = (
        calculate_editorial_body_target(
            structure,
            regeneration_target
        )
    )

    # =====================================================
    # INSTRUCTION
    # =====================================================

    instruction = (
        build_editorial_regeneration_instruction(
            target_length=body_target,
            content_type=content_type,
            previous_summary=previous_body
        )
    )

    logger.info(
        f"🔄 Editorial regeneration started | "
        f"type={content_type} | "
        f"count={regeneration_count + 1}/"
        f"{MAX_REGENERATION_COUNT} | "
        f"original={original_length} | "
        f"body={len(original_body)} | "
        f"previous_body={len(previous_body)} | "
        f"body_target={body_target}"
    )

    # =====================================================
    # GENERATE FROM FULL ORIGINAL BODY
    # =====================================================

    generation = (
        generate_editorial_candidate(
            original_text=original_body,
            instruction=instruction,
            target_length=body_target,
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
                    ),
                "title":
                    structure.title,
                "author":
                    structure.author,
                "author_source":
                    structure.author_source
            }
        )

    new_body_summary = normalize_text(
        generation[
            "candidate"
        ]
    )

    new_summary = (
        rebuild_editorial_summary(
            structure,
            new_body_summary
        )
    )

    # =====================================================
    # SAME OUTPUT PROTECTION
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
                    ),
                "title":
                    structure.title,
                "author":
                    structure.author,
                "author_source":
                    structure.author_source
            }
        )

    # =====================================================
    # FINAL HARD LIMIT
    # =====================================================

    if len(new_summary) > target_length:

        logger.warning(
            f"⚠️ Regenerated editorial summary "
            f"exceeds final target | "
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
                    "rebuilt_summary_exceeds_target",
                "title":
                    structure.title,
                "author":
                    structure.author
            }
        )

    logger.info(
        f"✅ Editorial regeneration ready | "
        f"type={content_type} | "
        f"count={next_count} | "
        f"title={structure.title or '-'} | "
        f"author={structure.author or '-'} | "
        f"body_before={len(original_body)} | "
        f"body_after={len(new_body_summary)} | "
        f"final={len(new_summary)} | "
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
                ),
            "title":
                structure.title,
            "author":
                structure.author,
            "author_source":
                structure.author_source,
            "author_confidence":
                structure.author_confidence,
            "body_length":
                len(original_body),
            "summary_body_length":
                len(new_body_summary)
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
    #
    # Classification همچنان روی متن کامل انجام می‌شود.
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
                    ),
                "structure":
                    summary_result.get(
                        "structure",
                        {}
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

    structure_metadata = (
        summary_result.get(
            "structure",
            {}
        )
        or {}
    )

    logger.info(
        f"✅ Editorial review prepared | "
        f"type={content_type} | "
        f"title="
        f"{structure_metadata.get('title') or '-'} | "
        f"author="
        f"{structure_metadata.get('author') or '-'} | "
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
            "can_regenerate": True,
            "title":
                structure_metadata.get(
                    "title",
                    ""
                ),
            "author":
                structure_metadata.get(
                    "author",
                    ""
                ),
            "author_source":
                structure_metadata.get(
                    "author_source",
                    "none"
                ),
            "author_confidence":
                structure_metadata.get(
                    "author_confidence",
                    "none"
                ),
            "body_length":
                structure_metadata.get(
                    "body_length",
                    0
                ),
            "body_target":
                structure_metadata.get(
                    "body_target",
                    0
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
