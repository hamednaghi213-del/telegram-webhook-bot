import logging
from core.cleaner import clean_text

logger = logging.getLogger(__name__)

# ---------- تنظیمات اولیه ----------
CHANNEL_TAG = None
HASHTAG = None

def initialize(channel_tag, hashtag):
    global CHANNEL_TAG, HASHTAG
    CHANNEL_TAG = channel_tag
    HASHTAG = hashtag
    logger.info("✅ Formatter initialized")

def format_news(raw_text: str) -> str:
    # پاکسازی متن با استفاده از cleaner
    cleaned = clean_text(raw_text)
    
    if not cleaned:
        return f"{HASHTAG}\n{CHANNEL_TAG}"
    
    # تقسیم به خطوط
    lines = cleaned.split('\n')
    
    # اگر همه چیز در یک خط بود
    if len(lines) == 1:
        if '🔹' in lines[0]:
            parts = lines[0].split('🔹')
            lines = []
            for i, part in enumerate(parts):
                part = part.strip()
                if part:
                    if i == 0:
                        lines.append(part)
                    else:
                        lines.append(f"🔹{part}")
    
    lines = [line.strip() for line in lines if line.strip()]
    
    if not lines:
        return f"{HASHTAG}\n{CHANNEL_TAG}"
    
    title = lines[0]
    body = lines[1:]
    
    if title.startswith('🔹'):
        title = title[1:].strip()
    
    result = f"❇️ {title}\n"
    for line in body:
        if not line.startswith('🔹'):
            result += f"🔹 {line}\n"
        else:
            result += f"{line}\n"
    
    # اضافه کردن هشتگ و تگ کانال در انتها
    result += f"\n{HASHTAG}\n{CHANNEL_TAG}"
    return result
