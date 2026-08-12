import re
import logging

logger = logging.getLogger(__name__)

# ---------- تنظیمات اولیه ----------
CHANNEL_TAG = None
HASHTAG = None

def initialize(channel_tag, hashtag):
    global CHANNEL_TAG, HASHTAG
    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag
    logger.info("✅ Cleaner initialized")

# ---------- RegExهای ثابت ----------
URL_PATTERN = re.compile(r'(?:https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)[^\s]+')
AT_PATTERN = re.compile(r'@[a-zA-Z0-9_]+')
HASH_PATTERN = re.compile(r'#[^\s]+')
INVITE_PATTERNS = [
    re.compile(r'عضویت در کانال', re.IGNORECASE),
    re.compile(r'برای عضویت کلیک کنید', re.IGNORECASE),
    re.compile(r'برای عضویت در کانال', re.IGNORECASE),
    re.compile(r'عضویت در تلگرام', re.IGNORECASE),
    re.compile(r'join our channel', re.IGNORECASE),
    re.compile(r'کانال ما', re.IGNORECASE),
    re.compile(r'joinchat', re.IGNORECASE),
    re.compile(r'عضویت', re.IGNORECASE),
]

# ---------- حذف تمام ایموجی‌ها (به جز ❇️ و 🔹) ----------
def remove_all_emojis(text: str) -> str:
    if not text:
        return text
    text = text.replace('❇️', '[[TITLE]]')
    text = text.replace('🔹', '[[BULLET]]')
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\uFE00-\uFEFF"
        "\u2300-\u23FF"
        "\u2B00-\u2BFF"
        "\u25A0-\u25FF"
        "\u2764-\u2764"          # ❤️ قلب
        "\u2763-\u2763"          # ❣️ قلب شکسته
        "\u274C-\u274C"          # ❌
        "\u2753-\u2753"          # ❓
        "\u2757-\u2757"          # ❗
        "\u2B50-\u2B50"          # ⭐
        "\u2B55-\u2B55"          # 🔴
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    text = text.replace('[[TITLE]]', '❇️')
    text = text.replace('[[BULLET]]', '🔹')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ---------- حذف @ و #های غیرخودی ----------
def clean_foreign_mentions_and_hashtags(text: str) -> str:
    if not text:
        return ""
    
    def replace_at(match):
        full = match.group(0)
        return full if full == CHANNEL_TAG else ""
    text = AT_PATTERN.sub(replace_at, text)
    
    def replace_hash(match):
        full = match.group(0)
        return full if full == HASHTAG else ""
    text = HASH_PATTERN.sub(replace_hash, text)
    
    text = URL_PATTERN.sub('', text)
    
    for pattern in INVITE_PATTERNS:
        text = pattern.sub('', text)
    
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ---------- حذف ایموجی‌های انتهایی ----------
def clean_trailing_emojis(text: str) -> str:
    if not text:
        return ""
    allowed_chars = re.compile(r'[\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u200C\u200D.،؛:!؟()"\' ]')
    for i in range(len(text) - 1, -1, -1):
        if allowed_chars.match(text[i]):
            return text[:i+1].rstrip()
    return ""

# ---------- حذف هر چیزی بعد از آخرین نقطه ----------
def clean_after_last_period(text: str) -> str:
    if not text:
        return text
    last_dot = text.rfind('.')
    last_persian_dot = text.rfind('۔')
    last_index = max(last_dot, last_persian_dot)
    if last_index != -1:
        return text[:last_index + 1].strip()
    return text

# ---------- حذف فوتر رسانه‌ها (مثل /صداوسیما Asriran) ----------
def clean_media_footer(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'/\s*[^\s/]+\s+[A-Za-z]+\.?\s*$', '', text)
    text = re.sub(r'/\s*[^\s/]+\.?\s*$', '', text)
    text = re.sub(r'[A-Za-z]+\.[A-Za-z]*\s*$', '', text)
    text = re.sub(r'@[a-zA-Z0-9_]+\s*[-–—]\s*(Link|لینک|More|بیشتر)\s*$', '', text, flags=re.IGNORECASE)
    return text.strip()

# ---------- حذف تمام موارد اضافی از انتهای متن ----------
def clean_all_trailing_content(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\|.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'(اخبار|کانال|تلگرام|channel|telegram)\s+[^\s]+$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    text = re.sub(r'\b(کانال|تلگرام|channel|telegram)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*[-–—]\s*(Link|لینک|More|بیشتر|ادامه|مشاهده|بخوانید|کلیک|اینجا)\s*$', '', text, flags=re.IGNORECASE)
    media_names = [
        'صداوسیما', 'ایسنا', 'فارس', 'مهر', 'تسنیم', 'ایرنا', 
        'خبرگزاری', 'ایسکانیوز', 'دانشجو', 'ایلنا', 'باشگاه خبرنگاران',
        'اسریران', 'Asriran', 'FarsNews', 'Tasnim', 'Mehr', 'IRNA',
        'رویترز', 'روترز', 'Reuters', 'AP', 'BBC', 'CNN', 'Al Jazeera',
        'العربیه', 'العربية', 'Sky News', 'فرانس پرس', 'AFP'
    ]
    for media in media_names:
        text = re.sub(r'/?\s*' + re.escape(media) + r'\.?\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'/\s*[^\s/]+\s*\.?\s*$', '', text)
    text = re.sub(r'[A-Za-z]+\.\s*$', '', text)
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        if re.match(r'^\s*[@\-–—]+\s*(Link|لینک|More|بیشتر)?\s*$', line, re.IGNORECASE):
            continue
        if re.search(r'@[a-zA-Z0-9_]+\s*[-–—]\s*(Link|لینک|More|بیشتر)', line, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\s+', ' ', text).strip()
    text = clean_trailing_emojis(text)
    return text

# ---------- تابع جامع پاکسازی ----------
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = remove_all_emojis(text)
    text = clean_foreign_mentions_and_hashtags(text)
    text = clean_all_trailing_content(text)
    text = clean_media_footer(text)
    text = clean_after_last_period(text)
    return text
