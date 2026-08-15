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
# INVITE PATTERNS
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
        r'خبرگزاری|'
        r'رسانه|'
        r'منبع|'
        r'اخبار|'
        r'عضویت|'
        r'لینک|'
        r'بیشتر|'
        r'ادامه|'
        r'channel|'
        r'telegram|'
        r'news|'
        r'media'
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
    حذف Emojiهای منبع.

    دو علامت قالب دنیا ۲۴ حفظ می‌شوند:

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
# CLEAN FOREIGN MENTIONS AND HASHTAGS
# =========================================================

def clean_foreign_mentions_and_hashtags(
    text: str
) -> str:

    if not text:
        return ""

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

    text = URL_PATTERN.sub(
        "",
        text
    )

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
    """
    تشخیص نقطه اعشاری.

    مثال:
        2.5
        ۲.۵
    """

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
    """
    آخرین پایان واقعی جمله را پیدا می‌کند.

    نقطه اعشاری به‌عنوان پایان جمله
    در نظر گرفته نمی‌شود.
    """

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
    """
    بررسی محافظه‌کارانه اینکه بخش انتهایی
    شبیه Footer رسانه‌ای است یا نه.
    """

    if not text:
        return False

    value = (
        text.strip()
    )

    if not value:
        return False

    lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]

    if not lines:
        return False

    # Footer باید کوچک باشد.
    if len(lines) > 4:

        return False

    if len(value) > 220:

        return False

    # Mention
    if AT_PATTERN.search(
        value
    ):

        return True

    # URL
    if URL_PATTERN.search(
        value
    ):

        return True

    # عبارت‌های شناخته‌شده
    if FOOTER_HINT_PATTERN.search(
        value
    ):

        return True

    # -----------------------------------------------------
    # حالت بسیار رایج:
    #
    # متن تمام شده و فقط یک نام کوتاه رسانه مانده.
    #
    # مثال:
    #
    # سپاه سایبری پاسداران
    #
    # یا:
    #
    # رسانه اقتصاد ایران
    #
    # -----------------------------------------------------

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
    """
    نسخه امن منطق قدیمی.

    اگر بعد از آخرین پایان جمله
    فقط Footer کوتاه رسانه‌ای وجود داشته باشد،
    آن Footer حذف می‌شود.

    اگر Tail شبیه متن واقعی خبر باشد،
    هیچ چیزی حذف نمی‌شود.
    """

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
# CLEAN TRAILING CONTENT
# =========================================================

def clean_all_trailing_content(
    text: str
) -> str:

    if not text:
        return ""

    text = re.sub(
        r'\|.*$',
        '',
        text,
        flags=re.MULTILINE
    )

    text = re.sub(
        (
            r'(اخبار|کانال|تلگرام|channel|telegram)'
            r'\s+[^\s]+$'
        ),
        '',
        text,
        flags=re.IGNORECASE
    )

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

    text = re.sub(
        r'\b(کانال|تلگرام|channel|telegram)\b',
        '',
        text,
        flags=re.IGNORECASE
    )

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

    lines = text.splitlines()

    cleaned_lines = []

    for line in lines:

        stripped = line.strip()

        if not stripped:

            cleaned_lines.append(
                ""
            )

            continue

        if re.match(
            (
                r'^\s*[@\-–—]+\s*'
                r'(Link|لینک|More|بیشتر)?\s*$'
            ),
            line,
            re.IGNORECASE
        ):

            continue

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

        cleaned_lines.append(
            stripped
        )

    text = "\n".join(
        cleaned_lines
    )

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

    ترتیب:

    Entity Parsing
        ↓
    Emoji Cleanup
        ↓
    Mention / URL Cleanup
        ↓
    Trailing Cleanup
        ↓
    Safe Last Sentence Cleanup
        ↓
    Media Footer Cleanup
        ↓
    Final Normalization
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

    # =====================================================
    # STEP 2
    # MENTIONS / HASHTAGS / URLS
    # =====================================================

    text = (
        clean_foreign_mentions_and_hashtags(
            text
        )
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

    # =====================================================
    # STEP 4
    # SAFE OLD BEHAVIOR
    # =====================================================

    text = (
        clean_after_last_sentence(
            text
        )
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
