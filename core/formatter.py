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
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    text = re.sub(r'#[^\s]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_news(raw_text: str) -> str:
    # 1. پاکسازی
    cleaned = clean_text(raw_text)
    cleaned = remove_all_hashtags_and_mentions(cleaned)
    if not cleaned:
        return ""
    
    # 2. تقسیم به خطوط و حذف خطوط خالی
    lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
    if not lines:
        return ""
    
    # 3. خط اول = تیتر، بقیه = بند
    title = lines[0]
    body = lines[1:] if len(lines) > 1 else []
    
    # 4. ساخت خروجی بدون فاصله اضافی
    result = f"❇️ {title}"
    for line in body:
        result += f"\n🔹 {line}"
    
    return result
