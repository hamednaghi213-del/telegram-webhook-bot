import logging
from typing import Optional, List

from core.cleaner import clean_text

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

CHANNEL_TAG: Optional[str] = None
HASHTAG: Optional[str] = None


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    channel_tag: str,
    hashtag: str
) -> None:
    """
    مقداردهی Formatter.

    Args:
        channel_tag: منشن اصلی کانال
        hashtag: هشتگ اصلی رسانه
    """

    global CHANNEL_TAG, HASHTAG

    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag

    logger.info(
        f"✅ Formatter initialized | "
        f"channel={CHANNEL_TAG} | "
        f"hashtag={HASHTAG}"
    )


# =========================================================
# SPLIT LINES PRESERVING STRUCTURE
# =========================================================

def split_lines(
    text: str
) -> List[str]:
    """
    تقسیم متن به خطوط با حفظ خطوط خالی.

    خطوط خالی برای تشخیص مرز پاراگراف‌ها
    در مرحله قالب‌بندی استفاده می‌شوند.
    """

    if not text:
        return []

    return text.splitlines()


# =========================================================
# FORMAT PARAGRAPH
# =========================================================

def format_paragraph(
    lines: List[str],
    bullet: str = "🔹"
) -> str:
    """
    قالب‌بندی یک پاراگراف خبری.

    هر خط غیرخالی با Bullet استاندارد
    دنیا ۲۴ نمایش داده می‌شود.
    """

    if not lines:
        return ""

    formatted_lines = []

    for line in lines:

        stripped = line.strip()

        if not stripped:
            continue

        formatted_lines.append(
            f"{bullet} {stripped}"
        )

    return "\n".join(
        formatted_lines
    )


# =========================================================
# FORMAT NEWS
# =========================================================

def format_news(
    raw_text: str
) -> str:
    """
    تبدیل متن خبر به قالب استاندارد دنیا ۲۴.

    معماری صحیح:

        Telegram raw text
                +
        Telegram entities
                ↓
        parse_telegram_entities()
                ↓
            main_text
                ↓
        format_news(main_text)
                ↓
            clean_text()
                ↓
        قالب استاندارد دنیا ۲۴


    نکته بسیار مهم:

    raw_text در این تابع باید در مسیر Entity-aware
    همان main_text خروجی content_entities.py باشد.

    Formatter مسئول تشخیص Telegram Entity نیست.

    وظایف Formatter فقط:

    1. پاکسازی متن با Cleaner
    2. تشخیص اولین خط غیرخالی به‌عنوان تیتر
    3. قالب‌بندی خطوط بعدی
    4. حفظ مرز پاراگراف‌ها

    خروجی نمونه:

        ❇️ تیتر خبر

        🔹 خط اول
        🔹 خط دوم

        🔹 پاراگراف بعدی
    """

    if not raw_text:
        return ""

    logger.debug(
        f"📝 Formatting news | "
        f"length={len(raw_text)} | "
        f"preview={raw_text[:80]!r}"
    )

    # =====================================================
    # STEP 1
    # CLEAN TEXT
    # =====================================================

    cleaned = clean_text(
        raw_text
    )

    if not cleaned:

        logger.warning(
            "⚠️ Text is empty after cleaning"
        )

        return ""

    logger.debug(
        f"After clean_text | "
        f"length={len(cleaned)}"
    )

    # =====================================================
    # STEP 2
    # SPLIT LINES
    # =====================================================

    all_lines = split_lines(
        cleaned
    )

    if not all_lines:

        logger.warning(
            "⚠️ No lines found"
        )

        return ""

    logger.debug(
        f"Split into {len(all_lines)} lines"
    )

    # =====================================================
    # STEP 3
    # FIND TITLE
    # =====================================================

    title = None
    title_index = None

    for index, line in enumerate(
        all_lines
    ):

        stripped = line.strip()

        if stripped:

            title = stripped
            title_index = index
            break

    if (
        title is None
        or title_index is None
    ):

        logger.warning(
            "⚠️ No title found"
        )

        return ""

    logger.debug(
        f"Title detected | "
        f"title={title[:80]!r}"
    )

    # =====================================================
    # STEP 4
    # BODY
    # =====================================================

    body_lines = all_lines[
        title_index + 1:
    ]

    # =====================================================
    # STEP 5
    # BUILD RESULT
    # =====================================================

    result = (
        f"❇️ {title}"
    )

    if body_lines:

        current_paragraph = []

        for line in body_lines:

            stripped = line.strip()

            # -------------------------------------------------
            # خط خالی = مرز پاراگراف
            # -------------------------------------------------

            if not stripped:

                if current_paragraph:

                    formatted_paragraph = (
                        format_paragraph(
                            current_paragraph
                        )
                    )

                    if formatted_paragraph:

                        result += (
                            f"\n\n"
                            f"{formatted_paragraph}"
                        )

                    current_paragraph = []

                continue

            # -------------------------------------------------
            # خط معمولی
            # -------------------------------------------------

            current_paragraph.append(
                stripped
            )

        # -----------------------------------------------------
        # پاراگراف آخر
        # -----------------------------------------------------

        if current_paragraph:

            formatted_paragraph = (
                format_paragraph(
                    current_paragraph
                )
            )

            if formatted_paragraph:

                result += (
                    f"\n\n"
                    f"{formatted_paragraph}"
                )

    logger.debug(
        f"✅ Formatted news | "
        f"length={len(result)}"
    )

    return result


# =========================================================
# ADD BRANDING
# =========================================================

def add_branding(
    formatted_text: str,
    include_hashtag: bool = True,
    include_channel: bool = True
) -> str:
    """
    افزودن Branding استاندارد دنیا ۲۴.

    خروجی نمونه:

        ❇️ تیتر

        🔹 متن خبر

        #دنیا_۲۴_نیوز
        @Donya24News

    نکته:
    Branding فقط در این لایه اضافه می‌شود
    و Cleaner مسئول ساخت Branding نیست.
    """

    if not formatted_text:
        return ""

    result = formatted_text.rstrip()

    branding_lines = []

    # -----------------------------------------------------
    # HASHTAG
    # -----------------------------------------------------

    if (
        include_hashtag
        and HASHTAG
    ):

        branding_lines.append(
            HASHTAG
        )

    # -----------------------------------------------------
    # CHANNEL TAG
    # -----------------------------------------------------

    if (
        include_channel
        and CHANNEL_TAG
    ):

        branding_lines.append(
            CHANNEL_TAG
        )

    # -----------------------------------------------------
    # APPEND BRANDING
    # -----------------------------------------------------

    if branding_lines:

        result += (
            "\n\n"
            + "\n".join(
                branding_lines
            )
        )

    return result


# =========================================================
# PROCESS NEWS
# =========================================================

def process_news(
    raw_text: str,
    add_brand: bool = True
) -> str:
    """
    پردازش کامل متن خبری.

    این تابع یک Wrapper ساده برای:

        format_news()
                ↓
        add_branding()

    است.

    نکته معماری:

    در مسیر Telegram Entity-aware، raw_text
    باید main_text خروجی content_entities.py باشد.
    """

    if not raw_text:
        return ""

    # =====================================================
    # FORMAT
    # =====================================================

    formatted = format_news(
        raw_text
    )

    if not formatted:
        return ""

    # =====================================================
    # BRANDING
    # =====================================================

    if add_brand:

        formatted = add_branding(
            formatted
        )

    return formatted
