import logging
import re
from typing import Optional, List

from core.cleaner import clean_text

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

CHANNEL_TAG: Optional[str] = None
HASHTAG: Optional[str] = None


# =========================================================
# FORMAT CONFIG
# =========================================================

TITLE_ICON = "❇️"
BODY_BULLET = "🔹"

KNOWN_BULLETS = (
    "🔹",
    "🔷",
    "▪️",
    "▫️",
    "◾",
    "◽",
    "•",
    "▪",
    "▫",
)


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    channel_tag: str,
    hashtag: str
) -> None:
    """
    مقداردهی Formatter.
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
# NORMALIZE USERNAME
# =========================================================

def normalize_username(
    username: Optional[str]
) -> str:
    """
    username را برای مقایسه استاندارد می‌کند.

    example:
        sepah_cyberi_iran
        @sepah_cyberi_iran

    هر دو به:
        @sepah_cyberi_iran
    """

    if not username:
        return ""

    username = str(username).strip()

    if not username:
        return ""

    if not username.startswith("@"):
        username = f"@{username}"

    return username.lower()


# =========================================================
# STRIP LEADING DECORATION
# =========================================================

def strip_leading_decoration(
    text: str
) -> str:
    """
    Bullet و تزئینات ابتدای خط را برای مقایسه حذف می‌کند.

    مثال:

        🔹 سپاه سایبری پاسداران
        🔷 کانال سپاه سایبری پاسداران
        🇮🇷 @sepah_cyberi_iran

    خروجی برای مقایسه تمیزتر می‌شود.
    """

    if not text:
        return ""

    value = text.strip()

    # حذف Bulletهای شناخته‌شده
    changed = True

    while changed:

        changed = False

        for bullet in KNOWN_BULLETS:

            if value.startswith(bullet):

                value = value[
                    len(bullet):
                ].strip()

                changed = True

                break

    # حذف چند علامت متداول معرفی منبع
    value = re.sub(
        r"^(?:🆔|📡|📢|🔗|🌐|🇮🇷)\s*",
        "",
        value
    ).strip()

    return value


# =========================================================
# IS SOURCE LINE
# =========================================================

def is_source_line(
    line: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> bool:
    """
    بررسی می‌کند آیا خط مربوط به امضای کانال مبدأ است.

    فقط مقایسه محافظه‌کارانه انجام می‌شود تا
    متن واقعی خبر اشتباهی حذف نشود.
    """

    if not line:
        return False

    stripped = line.strip()

    if not stripped:
        return False

    normalized_line = (
        strip_leading_decoration(
            stripped
        )
    )

    normalized_line_lower = (
        normalized_line.lower()
    )

    # =====================================================
    # SOURCE USERNAME
    # =====================================================

    normalized_source_username = (
        normalize_username(
            source_username
        )
    )

    if normalized_source_username:

        # اگر خط دقیقاً username باشد
        if (
            normalized_line_lower
            == normalized_source_username
        ):
            return True

        # یا username همراه یک تزئین ساده
        if (
            normalized_source_username
            in normalized_line_lower
            and len(normalized_line_lower) <= (
                len(normalized_source_username) + 20
            )
        ):
            return True

    # =====================================================
    # SOURCE TITLE
    # =====================================================

    if source_title:

        source_title_clean = (
            str(source_title)
            .strip()
        )

        source_title_lower = (
            source_title_clean.lower()
        )

        if source_title_lower:

            # عنوان دقیق کانال
            if (
                normalized_line_lower
                == source_title_lower
            ):
                return True

            # کانال + عنوان کانال
            if (
                normalized_line_lower
                == f"کانال {source_title_lower}"
            ):
                return True

            # عنوان + کانال
            if (
                normalized_line_lower
                == f"{source_title_lower} کانال"
            ):
                return True

    return False


# =========================================================
# REMOVE SOURCE SIGNATURE
# =========================================================

def remove_source_signature(
    text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    """
    اطلاعات کانال مبدأ را فقط از انتهای خبر حذف می‌کند.

    نکته:
    در متن اصلی خبر جستجوی کور انجام نمی‌دهیم.

    فقط بخش انتهایی بررسی می‌شود تا مثلاً اگر وسط خبر
    نام همان کانال آمده، اشتباهی حذف نشود.
    """

    if not text:
        return ""

    lines = text.splitlines()

    if not lines:
        return text

    # حداکثر 6 خط انتهایی را بررسی می‌کنیم.
    start_index = max(
        0,
        len(lines) - 6
    )

    removable_indexes = set()

    for index in range(
        start_index,
        len(lines)
    ):

        line = lines[index]

        if is_source_line(
            line,
            source_title=source_title,
            source_username=source_username
        ):

            removable_indexes.add(
                index
            )

    # -----------------------------------------------------
    # اگر خط username یا title حذف شد،
    # خطوط تزئینی خالی/ایموجی-only مجاور آن هم حذف شوند.
    # -----------------------------------------------------

    if removable_indexes:

        for index in list(
            removable_indexes
        ):

            for neighbor in (
                index - 1,
                index + 1
            ):

                if (
                    neighbor < start_index
                    or neighbor >= len(lines)
                ):
                    continue

                candidate = (
                    lines[
                        neighbor
                    ].strip()
                )

                if not candidate:

                    removable_indexes.add(
                        neighbor
                    )

                    continue

                # فقط Emoji/Decoration
                decoration_only = re.fullmatch(
                    r"[\s🔹🔷▪▫◾◽•🆔📡📢🔗🌐🇮🇷]+",
                    candidate
                )

                if decoration_only:

                    removable_indexes.add(
                        neighbor
                    )

    if not removable_indexes:

        return text

    cleaned_lines = [
        line
        for index, line
        in enumerate(lines)
        if index
        not in removable_indexes
    ]

    # حذف خطوط خالی انتهای متن
    while (
        cleaned_lines
        and not cleaned_lines[-1].strip()
    ):

        cleaned_lines.pop()

    cleaned_text = "\n".join(
        cleaned_lines
    )

    logger.info(
        f"🧹 Source signature removed | "
        f"title={source_title or '-'} | "
        f"username={source_username or '-'}"
    )

    return cleaned_text


# =========================================================
# SPLIT LINES PRESERVING STRUCTURE
# =========================================================

def split_lines(
    text: str
) -> List[str]:
    """
    تقسیم متن به خطوط با حفظ خطوط خالی.
    """

    if not text:
        return []

    return text.splitlines()


# =========================================================
# HAS BULLET
# =========================================================

def has_known_bullet(
    text: str
) -> bool:
    """
    آیا خط از قبل Bullet دارد؟
    """

    if not text:
        return False

    stripped = text.strip()

    return any(
        stripped.startswith(
            bullet
        )
        for bullet in KNOWN_BULLETS
    )


# =========================================================
# NORMALIZE BODY LINE
# =========================================================

def normalize_body_line(
    line: str,
    bullet: str = BODY_BULLET
) -> str:
    """
    هر خط خبری دقیقاً یک Bullet خواهد داشت.

    اگر خودش Bullet داشته باشد:
        همان یک Bullet حفظ می‌شود.

    اگر نداشته باشد:
        Bullet استاندارد اضافه می‌شود.

    بنابراین:

        🔹 متن

    دیگر تبدیل نمی‌شود به:

        🔹 🔹 متن
    """

    if not line:
        return ""

    stripped = line.strip()

    if not stripped:
        return ""

    # -----------------------------------------------------
    # اگر از قبل Bullet دارد
    # -----------------------------------------------------

    if has_known_bullet(
        stripped
    ):

        # همه Bulletهای متوالی ابتدای خط را حذف می‌کنیم
        # و فقط Bullet استاندارد خودمان را قرار می‌دهیم.

        cleaned = stripped

        changed = True

        while changed:

            changed = False

            for existing_bullet in KNOWN_BULLETS:

                if cleaned.startswith(
                    existing_bullet
                ):

                    cleaned = cleaned[
                        len(
                            existing_bullet
                        ):
                    ].strip()

                    changed = True

                    break

        if not cleaned:
            return ""

        return (
            f"{bullet} {cleaned}"
        )

    # -----------------------------------------------------
    # خط بدون Bullet
    # -----------------------------------------------------

    return (
        f"{bullet} {stripped}"
    )


# =========================================================
# FORMAT PARAGRAPH
# =========================================================

def format_paragraph(
    lines: List[str],
    bullet: str = BODY_BULLET
) -> str:
    """
    قالب‌بندی یک پاراگراف خبری.

    هر خط دقیقاً یک Bullet خواهد داشت.
    """

    if not lines:
        return ""

    formatted_lines = []

    for line in lines:

        formatted_line = (
            normalize_body_line(
                line,
                bullet=bullet
            )
        )

        if formatted_line:

            formatted_lines.append(
                formatted_line
            )

    return "\n".join(
        formatted_lines
    )


# =========================================================
# NORMALIZE TITLE
# =========================================================

def normalize_title(
    title: str
) -> str:
    """
    جلوگیری از تکرار آیکون تیتر.

    مثال:

        ❇️ تیتر

    دوباره تبدیل نمی‌شود به:

        ❇️ ❇️ تیتر
    """

    if not title:
        return ""

    value = title.strip()

    if value.startswith(
        TITLE_ICON
    ):

        value = value[
            len(
                TITLE_ICON
            ):
        ].strip()

    return value


# =========================================================
# FORMAT NEWS
# =========================================================

def format_news(
    raw_text: str,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    """
    تبدیل متن خبر به قالب استاندارد دنیا ۲۴.

    قابلیت‌های این نسخه:

    1. Cleaner
    2. حذف امضای کانال مبدأ
    3. جلوگیری از Bullet تکراری
    4. جلوگیری از تکرار Icon تیتر
    5. حفظ مرز پاراگراف‌ها
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

    # =====================================================
    # STEP 2
    # REMOVE SOURCE SIGNATURE
    # =====================================================

    cleaned = (
        remove_source_signature(
            cleaned,
            source_title=source_title,
            source_username=source_username
        )
    )

    if not cleaned:

        logger.warning(
            "⚠️ Text empty after source cleanup"
        )

        return ""

    logger.debug(
        f"After cleanup | "
        f"length={len(cleaned)}"
    )

    # =====================================================
    # STEP 3
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

    # =====================================================
    # STEP 4
    # FIND TITLE
    # =====================================================

    title = None
    title_index = None

    for index, line in enumerate(
        all_lines
    ):

        stripped = (
            line.strip()
        )

        if stripped:

            title = (
                normalize_title(
                    stripped
                )
            )

            title_index = (
                index
            )

            break

    if (
        title is None
        or title_index is None
    ):

        logger.warning(
            "⚠️ No title found"
        )

        return ""

    # =====================================================
    # STEP 5
    # BODY
    # =====================================================

    body_lines = all_lines[
        title_index + 1:
    ]

    # =====================================================
    # STEP 6
    # BUILD RESULT
    # =====================================================

    result = (
        f"{TITLE_ICON} {title}"
    )

    if body_lines:

        current_paragraph = []

        for line in body_lines:

            stripped = (
                line.strip()
            )

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
                            "\n\n"
                            + formatted_paragraph
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
                    "\n\n"
                    + formatted_paragraph
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
    افزودن Branding استاندارد.
    """

    if not formatted_text:
        return ""

    result = (
        formatted_text.rstrip()
    )

    branding_lines = []

    # =====================================================
    # HASHTAG
    # =====================================================

    if (
        include_hashtag
        and HASHTAG
    ):

        branding_lines.append(
            HASHTAG
        )

    # =====================================================
    # CHANNEL TAG
    # =====================================================

    if (
        include_channel
        and CHANNEL_TAG
    ):

        branding_lines.append(
            CHANNEL_TAG
        )

    # =====================================================
    # APPEND BRANDING
    # =====================================================

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
    add_brand: bool = True,
    source_title: Optional[str] = None,
    source_username: Optional[str] = None
) -> str:
    """
    پردازش کامل خبر.
    """

    if not raw_text:
        return ""

    formatted = (
        format_news(
            raw_text,
            source_title=source_title,
            source_username=source_username
        )
    )

    if not formatted:
        return ""

    if add_brand:

        formatted = (
            add_branding(
                formatted
            )
        )

    return formatted
