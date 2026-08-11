import os
import re
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request
import requests

app = Flask(__name__)

# ---------- تنظیمات ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("توکن در متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده.")

SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "my_secret_token_123")
API = f"https://api.telegram.org/bot{TOKEN}"

# 🔻 فقط این خط را با آیدی کانال خود جایگزین کنید 🔻
CHANNEL_ID = "@Donya24News"  # ← آیدی کانال خود را اینجا بگذارید
# 🔺

HASHTAG = "#دنیا_۲۴_نیوز"
CHANNEL_TAG = "@Donya24News"
MAX_MESSAGE_LENGTH = 4096

# ---------- لاگ ----------
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    try:
        file_handler = RotatingFileHandler('bot.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(console_format)
        logger.addHandler(file_handler)
    except:
        pass
    return logger

logger = setup_logging()

# ---------- RegExهای کامپایل شده ----------
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
ALLOWED_CHARS_PATTERN = re.compile(r'[\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u200C\u200D.،؛:!؟()"\' ]')

# ---------- توابع پاکسازی ----------
def clean_foreign_mentions_and_hashtags(text: str) -> str:
    if not text:
        return ""
    
    def replace_at(match):
        return match.group(0) if match.group(0) == CHANNEL_TAG else ""
    text = AT_PATTERN.sub(replace_at, text)
    
    def replace_hash(match):
        return match.group(0) if match.group(0) == HASHTAG else ""
    text = HASH_PATTERN.sub(replace_hash, text)
    
    text = URL_PATTERN.sub('', text)
    
    for pattern in INVITE_PATTERNS:
        text = pattern.sub('', text)
    
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_trailing_emojis(text: str) -> str:
    if not text:
        return ""
    for i in range(len(text) - 1, -1, -1):
        if ALLOWED_CHARS_PATTERN.match(text[i]):
            return text[:i+1].rstrip()
    return ""

def clean_after_last_period(text: str) -> str:
    """
    حذف هر چیزی بعد از آخرین نقطه (.) یا (۔) در متن.
    این روش منطقی‌ترین و کلی‌ترین روش برای حذف موارد اضافی است.
    """
    if not text:
        return text
    
    last_dot = text.rfind('.')
    last_persian_dot = text.rfind('۔')
    last_index = max(last_dot, last_persian_dot)
    
    if last_index != -1:
        trimmed = text[:last_index + 1].strip()
        return trimmed
    else:
        return text

def clean_all_trailing_content(text: str) -> str:
    """حذف هوشمندانه موارد اضافی از انتهای متن (پرچم، |، کلمات اضافی)"""
    if not text:
        return ""
    
    # 1. حذف پرچم‌های کشورها
    text = re.sub(r'[\U0001F1E6-\U0001F1FF]+', '', text)
    
    # 2. حذف هر چیزی که با | شروع می‌شود
    text = re.sub(r'\|.*$', '', text, flags=re.MULTILINE)
    
    # 3. حذف عبارات "اخبار کانال"
    text = re.sub(r'(اخبار|کانال|تلگرام|channel|telegram)\s+[^\s]+$', '', text, flags=re.IGNORECASE)
    
    # 4. حذف @آیدی‌ها
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    
    # 5. حذف کلمات تکراری
    text = re.sub(r'\b(کانال|تلگرام|channel|telegram)\b', '', text, flags=re.IGNORECASE)
    
    # 6. حذف عباراتی مثل "- Link"
    text = re.sub(r'\s*[-–—]\s*(Link|لینک|More|بیشتر|ادامه|مشاهده|بخوانید|کلیک|اینجا)\s*$', '', text, flags=re.IGNORECASE)
    
    # 7. حذف نام رسانه‌ها
    media_names = [
        'صداوسیما', 'ایسنا', 'فارس', 'مهر', 'تسنیم', 'ایرنا', 
        'خبرگزاری', 'ایسکانیوز', 'دانشجو', 'ایلنا', 'باشگاه خبرنگاران',
        'اسریران', 'Asriran', 'FarsNews', 'Tasnim', 'Mehr', 'IRNA',
        'رویترز', 'روترز', 'Reuters', 'AP', 'BBC', 'CNN', 'Al Jazeera',
        'العربیه', 'العربية', 'Sky News', 'فرانس پرس', 'AFP'
    ]
    for media in media_names:
        text = re.sub(r'/?\s*' + re.escape(media) + r'\.?\s*$', '', text, flags=re.IGNORECASE)
    
    # 8. حذف هر چیزی که با / شروع می‌شود و یک کلمه است
    text = re.sub(r'/\s*[^\s/]+\s*\.?\s*$', '', text)
    
    # 9. حذف عبارات با نقطه انتهایی که اسم رسانه هستند
    text = re.sub(r'[A-Za-z]+\.\s*$', '', text)
    
    # 10. حذف خطوط اضافی
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        if re.match(r'^\s*[@\-–—]+\s*(Link|لینک|More|بیشتر)?\s*$', line, re.IGNORECASE):
            continue
        if re.search(r'@[a-zA-Z0-9_]+\s*[-–—]\s*(Link|لینک|More|بیشتر)', line, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    
    # 11. حذف فضاهای اضافی
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 12. حذف ایموجی‌های انتهایی
    text = clean_trailing_emojis(text)
    
    return text

def format_news(raw_text: str) -> str:
    # مرحله ۱: پاکسازی @، #، لینک‌ها و عبارات دعوت
    cleaned = clean_foreign_mentions_and_hashtags(raw_text)
    
    # مرحله ۲: حذف ایموجی‌ها و نشانه‌های اضافی
    cleaned = clean_all_trailing_content(cleaned)
    
    # مرحله ۳: 🎯 حذف هر چیزی بعد از آخرین نقطه (منطقی‌ترین روش)
    cleaned = clean_after_last_period(cleaned)
    
    if not cleaned:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"
    
    # مرحله ۴: تقسیم به خطوط
    lines = cleaned.split('\n')
    
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
        elif '۔' in lines[0] or '.' in lines[0]:
            parts = re.split(r'(?<=[.۔])\s+', lines[0])
            if len(parts) > 1:
                lines = [p.strip() for p in parts if p.strip()]
            else:
                lines = [lines[0]]
    
    lines = [line.strip() for line in lines if line.strip()]
    
    if not lines:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"
    
    title = lines[0]
    body = lines[1:]
    
    if title.startswith('🔹'):
        title = title[1:].strip()
    
    result = f"‏❇️ {title}\n"
    for line in body:
        if not line.startswith('🔹'):
            result += f"🔹 {line}\n"
        else:
            result += f"{line}\n"
    
    result += f"\n‏{HASHTAG}\n‏{CHANNEL_TAG}"
    return result

# ---------- تقسیم پیام طولانی ----------
def split_long_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list:
    if len(text) <= max_len:
        return [text]
    parts = []
    start = 0
    total_len = len(text)
    while start < total_len:
        end = min(start + max_len, total_len)
        if end < total_len:
            last_newline = text.rfind('\n', start, end)
            last_space = text.rfind(' ', start, end)
            cut_at = max(last_newline, last_space)
            if cut_at > start:
                end = cut_at + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    if len(parts) > 1:
        total = len(parts)
        for i, part in enumerate(parts, 1):
            parts[i-1] = f"({i}/{total})\n{part}"
    return parts

# ---------- ارسال به کانال ----------
def send_to_channel(text: str):
    try:
        resp = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text},
            timeout=10
        )
        resp.raise_for_status()
        logger.info(f"✅ خبر در کانال منتشر شد (طول: {len(text)})")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به کانال: {e}")
        return False

def send_long_to_channel(text: str):
    parts = split_long_message(text)
    for part in parts:
        success = send_to_channel(part)
        if not success:
            break
        if len(parts) > 1:
            time.sleep(0.5)

# ---------- استخراج محتوای پیام ----------
def get_content_from_message(msg: dict) -> str:
    if "sticker" in msg:
        return ""
    if "caption" in msg and msg["caption"]:
        return msg["caption"]
    if "text" in msg and msg["text"]:
        return msg["text"]
    if any(key in msg for key in ("photo", "video", "document", "voice", "audio")):
        return ""
    return ""

# ---------- Webhook ----------
@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"[{request_id}] دریافت درخواست جدید")

        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET_TOKEN:
            logger.warning(f"[{request_id}] تلاش غیرمجاز")
            return {"ok": False}, 403

        try:
            data = request.get_json()
            if not data or "message" not in data:
                return {"ok": True}

            msg = data["message"]
            chat_id = msg["chat"]["id"]

            content = get_content_from_message(msg)
            
            if content:
                # قالب‌بندی خبر
                reply = format_news(content)
                
                # ارسال به کانال
                send_long_to_channel(reply)
                
                # پیام تأیید به کاربر
                try:
                    requests.post(
                        f"{API}/sendMessage",
                        json={"chat_id": chat_id, "text": "✅ خبر شما در کانال منتشر شد."},
                        timeout=5
                    )
                except:
                    pass

            logger.info(f"[{request_id}] ✅ خبر در کانال منتشر شد")

        except Exception as e:
            logger.error(f"[{request_id}] ❌ خطا: {e}")
            return {"ok": False}, 500

        return {"ok": True}

    return "🤖 ربات خبری هوشمند - نسخه نهایی"

# ---------- اجرا ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)
