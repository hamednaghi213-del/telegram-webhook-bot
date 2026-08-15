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
# INVITE / FOLLOW PATTERNS
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
    ),

    re.compile(
        r'[^\n]{0,80}\s+را\s+در\s+بله\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'[^\n]{0,80}\s+را\s+در\s+تلگرام\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'ما\s+را\s+در\s+بله\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'ما\s+را\s+در\s+تلگرام\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'در\s+بله\s+ما\s+را\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'در\s+تلگرام\s+ما\s+را\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'[^\n]{0,80}\s+را\s+در\s+ایتا\s+دنبال\s+کنید',
        re.IGNORECASE
    ),

    re.compile(
        r'[^\n]{0,80}\s+را\s+در\s+روبیکا\s+دنبال\s+کنید',
        re.IGNORECASE
    )
]


# =========================================================
# EMOJI PATTERN
# =========================================================
#
# نکته مهم:
#
# بازه U+1F100 تا U+1F1FF اضافه شده است.
#
# Emojiهایی مثل:
#
# 🆔
# 🆕
# 🆒
# 🆗
#
# در این محدوده قرار دارند.
# =========================================================

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F100-\U0001F1FF"
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
# PROMOTIONAL FOOTER LINE
# =========================================================
#
# فقط خطوطی حذف می‌شوند که تمام محتوای آن‌ها
# یک عبارت تبلیغاتی/شبکه‌ای باشد.
#
# بنابراین وجود کلمه "سایت" داخل یک جمله واقعی
# باعث حذف جمله نمی‌شود.
# =========================================================

PROMOTIONAL_ONLY_PATTERN = re.compile(
    (
        r'^\s*'
        r'(?:'
        r'سایت|'
        r'وب\s*سایت|'
        r'وبسایت|'
        r'تلگرام|'
        r'بله|'
        r'ایتا|'
        r'روبیکا|'
        r'واتس\s*اپ|'
        r'واتساپ|'
        r'یوتیوب|'
        r'آپارات|'
        r'اینستاگرام|'
        r'اینستا|'
        r'کست\s*باکس|'
        r'کست‌باکس|'
        r'پادکست|'
        r'لینک|'
        r'کانال|'
        r'عضویت|'
        r'دنبال\s*کنید|'
        r'website|'
        r'telegram|'
        r'youtube|'
        r'instagram|'
        r'whatsapp|'
        r'podcast'
        r')'
        r'\s*$'
    ),
    re.IGNORECASE
)


# =========================================================
# EMPTY / SEPARATOR ONLY LINE
# =========================================================

SEPARATOR_ONLY_PATTERN = re.compile(
    r'^[\s|/\\\-–—_:.,،؛;]+$'
)


# =========================================================
# SENTENCE END CONFIG
# =========================================================

SENTENCE_ENDINGS = (
    ".",
    "؟",
    "?",
    "!",
    "…"
)


FOOTER_HINT_PATTERN = re.compile(
    (
        r'('
        r'کانال|'
        r'تلگرام|'
        r'بله|'
        r'ایتا|'
        r'روبیکا|'
        r'خبرگزاری|'
        r'رسانه|'
        r'منبع|'
        r'اخبار|'
        r'عضویت|'
        r'دنبال کنید|'
        r'لینک|'
        r'بیشتر|'
        r'ادامه|'
        r'سایت|'
        r'واتس.?اپ|'
        r'یوتیوب|'
        r'اینستاگرام|'
        r'کست.?باکس|'
        r'پادکست|'
        r'channel|'
        r'telegram|'
        r'news|'
        r'media|'
        r'follow|'
        r'website|'
        r'youtube|'
        r'instagram|'
        r'whatsapp|'
        r'podcast'
        r')'
    ),
    re.IGNORECASE
)


# =========================================================
# NORMALIZE SPACES
# =========================================================

def normalize_spaces(text: str) -> str:

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

    if not text:
        return ""

    lines = text.splitlines()

    result = []

    blank_count = 0

    for line in lines:

        if not line.strip():

            blank_count += 1

            if (
                blank_count
                <= max_blank_lines
            ):

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
    Emojiهای منبع حذف می‌شوند.

    فقط دو علامت قالب دنیا ۲۴ حفظ می‌شوند:

        ❇️
        🔹
    """

    if not text:
        return ""

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

    text = EMOJI_PATTERN.sub(
        "",
        text
    )

    text = text.replace(
        "\uFE0F",
        ""
    )

    text = text.replace(
        "\uFE0E",
        ""
    )

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
# CLEAN FOREIGN MENTIONS / HASHTAGS / URLS
# =========================================================

def clean_foreign_mentions_and_hashtags(
    text: str
) -> str:

    if not text:
        return ""

    # =====================================================
    # MENTION
    # =====================================================

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

    # =====================================================
    # HASHTAG
    # =====================================================

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

    # =====================================================
    # URL
    # =====================================================

    text = URL_PATTERN.sub(
        "",
        text
    )

    # =====================================================
    # INVITE / FOLLOW
    # =====================================================

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

    if not text:
        return ""

    text = text.rstrip()

    while text:

        last_char = text[-1]

        if last_char.isspace():

            text = text[:-1]

            continue

        if EMOJI_PATTERN.fullmatch(
            last_char
        ):

            text = text[:-1]

            continue

        if last_char in (
            "\uFE0F",
            "\uFE0E"
        ):

            text = text[:-1]

            continue

        if last_char == "\u200D":

            text = text[:-1]

            continue

        break

    return text.rstrip()


# =========================================================
# DECIMAL SAFE PERIOD CHECK
# =========================================================

def is_decimal_period(
    text: str,
    index: int
) -> bool:

    if (
        index <= 0
        or index >= len(text) - 1
    ):

        return False

    before = text[
        index - 1
    ]

    after = text[
        index + 1
    ]

    return (
        before.isdigit()
        and after.isdigit()
    )


# =========================================================
# FIND LAST REAL SENTENCE END
# =========================================================

def find_last_sentence_end(
    text: str
) -> int:

    if not text:
        return -1

    for index in range(
        len(text) - 1,
        -1,
        -1
    ):

        char = text[
            index
        ]

        if (
            char
            not in SENTENCE_ENDINGS
        ):

            continue

        if (
            char == "."
            and is_decimal_period(
                text,
                index
            )
        ):

            continue

        return index

    return -1


# =========================================================
# FOOTER LIKELIHOOD
# =========================================================

def looks_like_footer(
    text: str
) -> bool:

    if not text:
        return False

    value = (
        text.strip()
    )

    if not value:
        return False

    lines = [
        line.strip()

        for line
        in value.splitlines()

        if line.strip()
    ]

    if not lines:
        return False

    if len(lines) > 4:
        return False

    if len(value) > 220:
        return False

    if AT_PATTERN.search(
        value
    ):

        return True

    if URL_PATTERN.search(
        value
    ):

        return True

    if FOOTER_HINT_PATTERN.search(
        value
    ):

        return True

    if (
        len(lines) == 1
        and len(value) <= 60
        and not any(
            ending in value

            for ending
            in SENTENCE_ENDINGS
        )
    ):

        return True

    return False


# =========================================================
# SAFE CLEAN AFTER LAST SENTENCE
# =========================================================

def clean_after_last_sentence(
    text: str
) -> str:

    if not text:
        return ""

    sentence_end = (
        find_last_sentence_end(
            text
        )
    )

    if sentence_end < 0:
        return text

    main_text = (
        text[
            :sentence_end + 1
        ].rstrip()
    )

    trailing = (
        text[
            sentence_end + 1:
        ].strip()
    )

    if not trailing:
        return text

    if looks_like_footer(
        trailing
    ):

        logger.info(
            f"🧹 Trailing footer removed | "
            f"length={len(trailing)} | "
            f"preview={trailing[:100]!r}"
        )

        return main_text

    return text


# =========================================================
# CLEAN MEDIA FOOTER
# =========================================================

def clean_media_footer(
    text: str
) -> str:

    if not text:
        return ""

    text = re.sub(
        r'/\s*[^\s/]+\s+[A-Za-z]+\.?\s*$',
        '',
        text
    )

    text = re.sub(
        r'/\s*[^\s/]+\.?\s*$',
        '',
        text
    )

    text = re.sub(
        r'[A-Za-z]+\.[A-Za-z]*\s*$',
        '',
        text
    )

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
# IS PROMOTIONAL FOOTER LINE
# =========================================================

def is_promotional_footer_line(
    line: str
) -> bool:
    """
    فقط خطوط مستقل تبلیغاتی را تشخیص می‌دهد.

    مثال‌های حذف‌شونده:

        سایت
        یوتیوب
        واتس‌اپ
        کست باکس
        |

    ولی جمله واقعی مثل:

        سایت وزارت خارجه این خبر را منتشر کرد.

    حذف نمی‌شود.
    """

    if not line:
        return False

    value = (
        line.strip()
    )

    if not value:
        return False

    if SEPARATOR_ONLY_PATTERN.fullmatch(
        value
    ):

        return True

    if PROMOTIONAL_ONLY_PATTERN.fullmatch(
        value
    ):

        return True

    return False


# =========================================================
# CLEAN TRAILING CONTENT
# =========================================================

def clean_all_trailing_content(
    text: str
) -> str:

    if not text:
        return ""

    # =====================================================
    # CONTENT AFTER |
    # =====================================================
    #
    # مثال:
    #
    # سایت | واتس‌اپ | یوتیوب
    #
    # تبدیل می‌شود به:
    #
    # سایت
    #
    # سپس در مرحله Line Cleanup
    # خود "سایت" نیز حذف می‌شود.
    # =====================================================

    text = re.sub(
        r'\|.*$',
        '',
        text,
        flags=re.MULTILINE
    )

    # =====================================================
    # CHANNEL / TELEGRAM FOOTER
    # =====================================================

    text = re.sub(
        (
            r'(اخبار|کانال|تلگرام|بله|ایتا|روبیکا|'
            r'channel|telegram)'
            r'\s+[^\s]+$'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

    # =====================================================
    # TRAILING FOREIGN MENTION
    # =====================================================

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

    # =====================================================
    # GENERIC PROMOTIONAL WORDS
    # =====================================================

    text = re.sub(
        (
            r'\b('
            r'کانال|'
            r'تلگرام|'
            r'channel|'
            r'telegram'
            r')\b'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

    # =====================================================
    # LINK / MORE FOOTER
    # =====================================================

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

    # =====================================================
    # COMMON MEDIA NAMES
    # =====================================================

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

    # =====================================================
    # GENERIC FOOTER
    # =====================================================

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

    # =====================================================
    # LINE-BY-LINE CLEANUP
    # =====================================================

    lines = text.splitlines()

    cleaned_lines = []

    for line in lines:

        stripped = (
            line.strip()
        )

        # -------------------------------------------------
        # PRESERVE BLANK LINE
        # -------------------------------------------------

        if not stripped:

            cleaned_lines.append(
                ""
            )

            continue

        # -------------------------------------------------
        # PROMOTIONAL ONLY LINE
        # -------------------------------------------------

        if is_promotional_footer_line(
            stripped
        ):

            logger.debug(
                f"🧹 Promotional footer line removed | "
                f"{stripped!r}"
            )

            continue

        # -------------------------------------------------
        # MENTION / LINK ONLY
        # -------------------------------------------------

        if re.match(
            (
                r'^\s*[@\-–—]+\s*'
                r'(Link|لینک|More|بیشتر)?\s*$'
            ),
            stripped,
            re.IGNORECASE
        ):

            continue

        # -------------------------------------------------
        # MENTION + LINK
        # -------------------------------------------------

        match = re.search(
            (
                r'(@[a-zA-Z0-9_]+)\s*'
                r'[-–—]\s*'
                r'(Link|لینک|More|بیشتر)'
            ),
            stripped,
            re.IGNORECASE
        )

        if match:

            mention = (
                match.group(1)
            )

            if not (
                CHANNEL_TAG
                and mention.lower()
                == str(
                    CHANNEL_TAG
                ).lower()
            ):

                continue

        # -------------------------------------------------
        # GENERIC FOLLOW PROMPT
        # -------------------------------------------------

        follow_line = False

        for pattern in INVITE_PATTERNS:

            if pattern.fullmatch(
                stripped
            ):

                follow_line = True

                break

        if follow_line:
            continue

        cleaned_lines.append(
            stripped
        )

    text = "\n".join(
        cleaned_lines
    )

    # =====================================================
    # REMOVE TRAILING BLANK / PROMO LINES AGAIN
    # =====================================================
    #
    # دفاع دوم:
    # اگر پاکسازی قبلی یک Footer جدید ایجاد کرده باشد،
    # از انتهای متن حذف می‌شود.
    # =====================================================

    lines = (
        text.splitlines()
    )

    while lines:

        last = (
            lines[-1].strip()
        )

        if not last:

            lines.pop()

            continue

        if is_promotional_footer_line(
            last
        ):

            lines.pop()

            continue

        break

    text = "\n".join(
        lines
    )

    # =====================================================
    # NORMALIZE
    # =====================================================

    text = normalize_spaces(
        text
    )

    text = normalize_blank_lines(
        text,
        max_blank_lines=1
    )

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

    مراحل:

    1. حذف Emojiهای منبع
    2. حذف Mention / Hashtag / URL خارجی
    3. حذف Follow / Invite
    4. حذف Footerهای عمومی
    5. حذف امن محتوای پس از آخرین جمله
    6. حذف Media Footer
    7. Normalization
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
    # EMOJI
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
    # MENTION / HASHTAG / URL / INVITE
    # =====================================================

    text = (
        clean_foreign_mentions_and_hashtags(
            text
        )
    )

    logger.debug(
        f"After mentions/invites | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 3
    # GENERAL TRAILING CLEANUP
    # =====================================================

    text = (
        clean_all_trailing_content(
            text
        )
    )

    logger.debug(
        f"After trailing cleanup | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 4
    # SAFE LAST SENTENCE CLEANUP
    # =====================================================

    text = (
        clean_after_last_sentence(
            text
        )
    )

    logger.debug(
        f"After last sentence cleanup | "
        f"length={len(text)} | "
        f"preview={text[:80]!r}"
    )

    # =====================================================
    # STEP 5
    # MEDIA FOOTER
    # =====================================================

    text = (
        clean_media_footer(
            text
        )
    )

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
