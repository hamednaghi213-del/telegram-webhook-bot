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
        return text
    # حذف @ها
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    # حذف #ها (با یا بدون فاصله)
    text = re.sub(r'#\s*[^\s#]+', '', text)
    # حذف ❇️ و 🔹 اضافی (اگر در ورودی باشند)
    text = re.sub(r'❇️', '', text)
    text = re.sub(r'🔹', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_news(raw_text: str) -> str:
    # پاکسازی متن با cleaner
    cleaned = clean_text(raw_text)
    cleaned = remove_all_hashtags_and_mentions(cleaned)
    if not cleaned:
        return ""
    
    # تقسیم به خطوط و حذف خطوط خالی
    lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
    if not lines:
        return ""
    
    # خط اول = تیتر، بقیه = بند
    title = lines[0]
    body = lines[1:] if len(lines) > 1 else []
    
    # ساخت خروجی با آیکون‌ها
    result = f"❇️ {title}"
    for line in body:
        result += f"\n🔹 {line}"
    
    return result
