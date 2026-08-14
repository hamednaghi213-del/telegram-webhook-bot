import re
import logging

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

CHANNEL_TAG = None
HASHTAG = None


# =========================================================
# INITIALIZE
# =========================================================

def initialize(channel_tag, hashtag):
    """
    مقداردهی Cleaner.

    Args:
        channel_tag: منشن اصلی کانال
        hashtag: هشتگ اصلی رسانه
    """

    global CHANNEL_TAG, HASHTAG

    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag

    logger.info(
        "✅ Cleaner initialized"
    )


# =========================================================
# REGEX PATTERNS
# =========================================================

URL_PATTERN = re.compile(
    r'(?:https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)[^\s]+',
    re.IGNORECASE
)

AT_PATTERN = re.compile(
    r'@[a-zA-Z0-9_]+'
)

HASH_PATTERN = re.compile(
    r'#[^\s]+'
)


# =========================================================
# INVITE PATTERNS
# =========================================================
#
# نکته مهم:
#
# Pattern عمومی "عضویت" عمداً وجود ندارد.
#
# چون ممکن است در متن واقعی خبر عباراتی مانند:
#
# "عضویت ایران در بریکس"
#
# وجود داشته باشد.
# =========================================================

INVITE_PATTERNS = [

    re.compile(
        r'عضویت در کانال',
        re.IGNORECASE
    ),

    re.compile(
        r'برای عضویت کلیک کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'برای عضویت در کانال',
        re.IGNORECASE
    ),

    re.compile(
        r'عضویت در تلگرام',
        re.IGNORECASE
    ),

    re.compile(
        r'join our channel',
        re.IGNORECASE
    ),

    re.compile(
        r'joinchat',
        re.IGNORECASE
    ),

    re.compile(
        r'برای ورود به کانال',
        re.IGNORECASE
    ),

    re.compile(
        r'برای مشاهده کانال',
        re.IGNORECASE
    )
]


# =========================================================
# EMOJI PATTERN
# =========================================================
#
# بازه کامل:
#
# \uFE00-\uFEFF
#
# عمداً استفاده نشده است.
#
# فقط Variation Selectorهای واقعی FE0E و FE0F
# در بخش مربوط به خودشان مدیریت می‌شوند.
# =========================================================

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\u2300-\u23FF"
    "\u2B00-\u2BFF"
    "\u25A0-\u25FF"
    "]+",
    flags=re.UNICODE
)


# =========================================================
# NORMALIZE SPACES
# =========================================================

def normalize_spaces(text: str) -> str:
    """
    فاصله و Tab اضافی داخل هر خط را اصلاح می‌کند.

    Line breakها و ساختار پاراگرافی حفظ می‌شوند.
    """

    if not text:
        return ""

    lines = text.splitlines()

    normalized_lines = []

    for line in lines:

        line = re.sub(
            r'[ \t]+',
            ' ',
            line
        ).strip()

        normalized_lines.append(
            line
        )

    return "\n".join(
        normalized_lines
    ).strip()


# =========================================================
# NORMALIZE BLANK LINES
# =========================================================

def normalize_blank_lines(
    text: str,
    max_blank_lines: int = 1
) -> str:
    """
    ساختار پاراگراف‌ها را حفظ می‌کند،
    اما تعداد زیاد خطوط خالی متوالی را محدود می‌کند.

    max_blank_lines=1 یعنی:

    پاراگراف اول

    پاراگراف دوم

    حفظ می‌شود؛ ولی ۳ یا ۴ خط خالی متوالی
    به یک خط خالی کاهش پیدا می‌کند.
    """

    if not text:
        return ""

    lines = text.splitlines()

    result = []

    blank_count = 0

    for line in lines:

        if not line.strip():

            blank_count += 1

            if blank_count <= max_blank_lines:
                result.append("")

            continue

        blank_count = 0

        result.append(
            line.strip()
        )

    return "\n".join(
        result
    ).strip()


# =========================================================
# REMOVE ALL EMOJIS
# =========================================================

def remove_all_emojis(text: str) -> str:
    """
    حذف Emojiها از متن.

    دو علامت قالب‌بندی دنیا ۲۴ حفظ می‌شوند:

    ❇️
    🔹

    هشدار معماری:
    این تابع باید بعد از Telegram Entity Parsing
    روی main_text اجرا شود.
    """

    if not text:
        return ""

    # -----------------------------------------------------
    # حفظ علامت‌های قالب دنیا ۲۴
    # -----------------------------------------------------

    title_placeholder = (
        "[[DONYA24_TITLE_MARK]]"
    )

    bullet_placeholder = (
        "[[DONYA24_BULLET_MARK]]"
    )

    text = text.replace(
        "❇️",
        title_placeholder
    )

    text = text.replace(
        "🔹",
        bullet_placeholder
    )

    # -----------------------------------------------------
    # حذف Emoji
    # -----------------------------------------------------

    text = EMOJI_PATTERN.sub(
        "",
        text
    )

    # -----------------------------------------------------
    # حذف فقط Variation Selectorها
    # -----------------------------------------------------

    text = text.replace(
        "\uFE0F",
        ""
    )

    text = text.replace(
        "\uFE0E",
        ""
    )

    # -----------------------------------------------------
    # بازگرداندن علامت‌های قالب
    # -----------------------------------------------------

    text = text.replace(
        title_placeholder,
        "❇️"
    )

    text = text.replace(
        bullet_placeholder,
        "🔹"
    )

    return normalize_spaces(
        text
    )


# =========================================================
# CLEAN FOREIGN MENTIONS AND HASHTAGS
# =========================================================

def clean_foreign_mentions_and_hashtags(
    text: str
) -> str:
    """
    حذف منشن و هشتگ‌های خارجی.

    CHANNEL_TAG و HASHTAG خود سیستم
    در صورت وجود حفظ می‌شوند.

    URL و عبارت‌های دعوت تبلیغاتی نیز حذف می‌شوند.
    """

    if not text:
        return ""

    # -----------------------------------------------------
    # Mention
    # -----------------------------------------------------

    def replace_at(match):

        full = match.group(0)

        if (
            CHANNEL_TAG
            and full.lower()
            == str(CHANNEL_TAG).lower()
        ):
            return full

        return ""

    text = AT_PATTERN.sub(
        replace_at,
        text
    )

    # -----------------------------------------------------
    # Hashtag
    # -----------------------------------------------------

    def replace_hash(match):

        full = match.group(0)

        if (
            HASHTAG
            and full == HASHTAG
        ):
            return full

        return ""

    text = HASH_PATTERN.sub(
        replace_hash,
        text
    )

    # -----------------------------------------------------
    # URLs
    # -----------------------------------------------------

    text = URL_PATTERN.sub(
        "",
        text
    )

    # -----------------------------------------------------
    # Invite phrases
    # -----------------------------------------------------

    for pattern in INVITE_PATTERNS:

        text = pattern.sub(
            "",
            text
        )

    return normalize_spaces(
        text
    )


# =========================================================
# CLEAN TRAILING EMOJIS
# =========================================================

def clean_trailing_emojis(
    text: str
) -> str:
    """
    حذف Emojiهای باقی‌مانده از انتهای متن.
    """

    if not text:
        return ""

    text = text.rstrip()

    while text:

        last_char = text[-1]

        # -------------------------------------------------
        # Space / newline
        # -------------------------------------------------

        if last_char.isspace():

            text = text[:-1]
            continue

        # -------------------------------------------------
        # Emoji
        # -------------------------------------------------

        if EMOJI_PATTERN.fullmatch(
            last_char
        ):

            text = text[:-1]
            continue

        # -------------------------------------------------
        # Variation Selector
        # -------------------------------------------------

        if last_char in (
            "\uFE0F",
            "\uFE0E"
        ):

            text = text[:-1]
            continue

        # -------------------------------------------------
        # Zero Width Joiner
        # -------------------------------------------------

        if last_char == "\u200D":

            text = text[:-1]
            continue

        break

    return text.rstrip()


# =========================================================
# CLEAN AFTER LAST PERIOD
# =========================================================

def clean_after_last_period(
    text: str
) -> str:
    """
    عمداً غیرفعال است.

    علت:

    اعداد اعشاری مانند:

    ۱.۵۷
    2.5

    نباید اشتباهاً باعث حذف ادامه متن شوند.
    """

    return text or ""


# =========================================================
# CLEAN MEDIA FOOTER
# =========================================================

def clean_media_footer(
    text: str
) -> str:
    """
    حذف Footerهای ساده رسانه‌ای و تبلیغاتی
    از انتهای متن.
    """

    if not text:
        return ""

    # -----------------------------------------------------
    # / MediaName English
    # -----------------------------------------------------

    text = re.sub(
        r'/\s*[^\s/]+\s+[A-Za-z]+\.?\s*$',
        '',
        text
    )

    # -----------------------------------------------------
    # / MediaName
    # -----------------------------------------------------

    text = re.sub(
        r'/\s*[^\s/]+\.?\s*$',
        '',
        text
    )

    # -----------------------------------------------------
    # Domain-like footer
    # -----------------------------------------------------

    text = re.sub(
        r'[A-Za-z]+\.[A-Za-z]*\s*$',
        '',
        text
    )

    # -----------------------------------------------------
    # @channel - Link
    # -----------------------------------------------------

    text = re.sub(
        (
            r'@[a-zA-Z0-9_]+\s*'
            r'[-–—]\s*'
            r'(Link|لینک|More|بیشتر)\s*$'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


# =========================================================
# CLEAN TRAILING CONTENT
# =========================================================

def clean_all_trailing_content(
    text: str
) -> str:
    """
    حذف Footer، لینک، منبع و محتوای تبلیغاتی.

    ساختار پاراگراف‌ها حفظ می‌شود.

    CHANNEL_TAG اصلی سیستم نیز
    در صورت وجود عمداً حذف نمی‌شود.
    """

    if not text:
        return ""

    # -----------------------------------------------------
    # محتوای بعد از |
    # -----------------------------------------------------

    text = re.sub(
        r'\|.*$',
        '',
        text,
        flags=re.MULTILINE
    )

    # -----------------------------------------------------
    # عبارت‌های انتهایی channel / telegram
    # -----------------------------------------------------

    text = re.sub(
        (
            r'(اخبار|کانال|تلگرام|channel|telegram)'
            r'\s+[^\s]+$'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

    # -----------------------------------------------------
    # حذف Mention خارجی
    # CHANNEL_TAG خودمان حفظ می‌شود
    # -----------------------------------------------------

    def replace_trailing_mention(
        match
    ):

        full = match.group(0)

        if (
            CHANNEL_TAG
            and full.lower()
            == str(CHANNEL_TAG).lower()
        ):
            return full

        return ""

    text = AT_PATTERN.sub(
        replace_trailing_mention,
        text
    )

    # -----------------------------------------------------
    # حذف کلمات تبلیغاتی مستقل
    # -----------------------------------------------------

    text = re.sub(
        r'\b(کانال|تلگرام|channel|telegram)\b',
        '',
        text,
        flags=re.IGNORECASE
    )

    # -----------------------------------------------------
    # Link / More footer
    # -----------------------------------------------------

    text = re.sub(
        (
            r'\s*[-–—]\s*'
            r'(Link|لینک|More|بیشتر|ادامه|'
            r'مشاهده|بخوانید|کلیک|اینجا)\s*$'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

    # -----------------------------------------------------
    # نام رسانه‌های رایج
    # فقط در انتهای متن
    # -----------------------------------------------------

    media_names = [

        "صداوسیما",
        "ایسنا",
        "فارس",
        "مهر",
        "تسنیم",
        "ایرنا",
        "خبرگزاری",
        "ایسکانیوز",
        "دانشجو",
        "ایلنا",
        "باشگاه خبرنگاران",
        "عصرایران",
        "Asriran",
        "FarsNews",
        "Tasnim",
        "Mehr",
        "IRNA",
        "رویترز",
        "روترز",
        "Reuters",
        "AP",
        "BBC",
        "CNN",
        "Al Jazeera",
        "العربیه",
        "العربية",
        "Sky News",
        "فرانس پرس",
        "AFP"
    ]

    for media in media_names:

        text = re.sub(
            (
                r'/?\s*'
                + re.escape(media)
                + r'\.?\s*$'
            ),
            '',
            text,
            flags=re.IGNORECASE
        )

    # -----------------------------------------------------
    # Footerهای عمومی باقی‌مانده
    # -----------------------------------------------------

    text = re.sub(
        r'/\s*[^\s/]+\s*\.?\s*$',
        '',
        text
    )

    text = re.sub(
        r'[A-Za-z]+\.\s*$',
        '',
        text
    )

    # -----------------------------------------------------
    # پردازش خط به خط
    # -----------------------------------------------------

    lines = text.splitlines()

    cleaned_lines = []

    for line in lines:

        stripped = line.strip()

        # -------------------------------------------------
        # اصلاح مهم:
        # خطوط خالی را حذف نمی‌کنیم.
        #
        # با این کار پاراگراف‌های خبر حفظ می‌شوند.
        # -------------------------------------------------

        if not stripped:

            cleaned_lines.append(
                ""
            )

            continue

        # -------------------------------------------------
        # خط فقط شامل Mention / Link
        # -------------------------------------------------

        if re.match(
            (
                r'^\s*[@\-–—]+\s*'
                r'(Link|لینک|More|بیشتر)?\s*$'
            ),
            line,
            re.IGNORECASE
        ):

            continue

        # -------------------------------------------------
        # Mention خارجی + Link
        # -------------------------------------------------

        match = re.search(
            (
                r'(@[a-zA-Z0-9_]+)\s*'
                r'[-–—]\s*'
                r'(Link|لینک|More|بیشتر)'
            ),
            line,
            re.IGNORECASE
        )

        if match:

            mention = match.group(1)

            if not (
                CHANNEL_TAG
                and mention.lower()
                == str(CHANNEL_TAG).lower()
            ):

                continue

        cleaned_lines.append(
            stripped
        )

    text = "\n".join(
        cleaned_lines
    )

    # -----------------------------------------------------
    # فاصله‌های داخل خطوط
    # -----------------------------------------------------

    text = normalize_spaces(
        text
    )

    # -----------------------------------------------------
    # اصلاح مهم:
    # حفظ پاراگراف‌ها ولی جلوگیری از
    # چندین خط خالی متوالی
    # -----------------------------------------------------

    text = normalize_blank_lines(
        text,
        max_blank_lines=1
    )

    # -----------------------------------------------------
    # حذف Emoji انتهایی
    # -----------------------------------------------------

    text = clean_trailing_emojis(
        text
    )

    return text


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(
    text: str
) -> str:
    """
    پاکسازی کامل متن خبری.

    ترتیب پردازش:

    1. حذف Emojiهای غیرضروری
    2. حذف Mention / Hashtag خارجی
    3. حذف URLs و Invite
    4. حذف trailing content
    5. حذف Media Footer
    6. حفظ و Normalization ساختار پاراگراف‌ها

    =======================================================
    قانون معماری بسیار مهم
    =======================================================

    این تابع نباید مستقیماً روی متن خام Telegram
    قبل از Entity Parsing اجرا شود.

    ترتیب صحیح:

        Telegram raw text
                +
        Telegram entities
                ↓
        parse_telegram_entities()
                ↓
            main_text
                ↓
            clean_text()
                ↓
            format_news()

    علت:

    Telegram offset و length را بر اساس UTF-16
    و متن خام محاسبه می‌کند.

    Cleaner طول و ساختار متن را تغییر می‌دهد.

    بنابراین اگر Cleaner قبل از Entity Parser اجرا شود،
    offsetهای Entity دیگر معتبر نخواهند بود.
    =======================================================
    """

    if not text:
        return ""

    logger.debug(
        f"🧹 Cleaning text | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 1
    # Emoji
    # =====================================================

    text = remove_all_emojis(
        text
    )

    logger.debug(
        f"After emojis | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 2
    # Mentions / Hashtags / URLs / Invite
    # =====================================================

    text = clean_foreign_mentions_and_hashtags(
        text
    )

    logger.debug(
        f"After mentions | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 3
    # Trailing Content
    # =====================================================

    text = clean_all_trailing_content(
        text
    )

    logger.debug(
        f"After trailing | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 4
    # Media Footer
    # =====================================================

    text = clean_media_footer(
        text
    )

    logger.debug(
        f"After footer | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # clean_after_last_period
    # عمداً غیرفعال
    # =====================================================

    # text = clean_after_last_period(
    #     text
    # )

    # =====================================================
    # FINAL NORMALIZATION
    # =====================================================

    text = normalize_spaces(
        text
    )

    text = normalize_blank_lines(
        text,
        max_blank_lines=1
    )

    logger.debug(
        f"✅ Final cleaned text | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    return text
