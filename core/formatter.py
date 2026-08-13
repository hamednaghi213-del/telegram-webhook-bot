import logging
import re

from core.cleaner import clean_text

logger = logging.getLogger(__name__)

CHANNEL_TAG = None
HASHTAG = None


def initialize(channel_tag, hashtag):
    global CHANNEL_TAG, HASHTAG

    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag

    logger.info("✅ Formatter initialized")


def remove_all_hashtags_and_mentions(text: str) -> str:
    if not text:
        return ""

    # حذف منشن‌ها
    text = re.sub(
        r'@[a-zA-Z0-9_]+',
        '',
        text
    )

    # حذف هشتگ‌ها
    text = re.sub(
        r'#\s*[^\s#]+',
        '',
        text
    )

    # حذف نشانه‌های قالب‌بندی اضافی
    text = text.replace('❇️', '')
    text = text.replace('🔹', '')

    # فقط فاصله‌های داخل خطوط را اصلاح می‌کنیم
    # و خطوط جدید را حفظ می‌کنیم
    text = re.sub(
        r'[ \t]+',
        ' ',
        text
    )

    # حذف خطوط خالی اضافی
    text = re.sub(
        r'\n\s*\n+',
        '\n',
        text
    )

    return text.strip()


def format_news(raw_text: str) -> str:
    """
    تبدیل متن خام خبر به قالب استاندارد دنیا ۲۴

    خروجی:

    ❇️ تیتر

    🔹 متن
    🔹 متن
    """

    if not raw_text:
        return ""

    # ---------------------------------------------
    # پاکسازی اولیه
    # ---------------------------------------------

    cleaned = clean_text(raw_text)

    if not cleaned:
        return ""

    # ---------------------------------------------
    # حذف منشن و هشتگ‌های ورودی
    # ---------------------------------------------

    cleaned = remove_all_hashtags_and_mentions(
        cleaned
    )

    if not cleaned:
        return ""

    # ---------------------------------------------
    # تقسیم خطوط
    # ---------------------------------------------

    lines = [
        line.strip()
        for line in cleaned.splitlines()
        if line.strip()
    ]

    if not lines:
        return ""

    # ---------------------------------------------
    # خط اول = تیتر
    # ---------------------------------------------

    title = lines[0]

    # ---------------------------------------------
    # خطوط بعدی = متن
    # ---------------------------------------------

    body = lines[1:]

    # ---------------------------------------------
    # ساخت خروجی
    # ---------------------------------------------

    result = f"❇️ {title}"

    for line in body:
        result += f"\n🔹 {line}"

    return result
