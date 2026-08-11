import os
import re
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request
import requests

# ---------- تنظیمات اولیه ----------
app = Flask(__name__)

# خواندن توکن از متغیر محیطی
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("توکن در متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده.")

SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "my_secret_token_123")
API = f"https://api.telegram.org/bot{TOKEN}"

# ثابت‌های قالب
HASHTAG = "#دنیا_۲۴_نیوز"
CHANNEL_TAG = "@Donya24News"
MAX_MESSAGE_LENGTH = 4096

# ---------- تنظیم لاگ ----------
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # لاگ در کنسول
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # لاگ در فایل با چرخش خودکار
    try:
        file_handler = RotatingFileHandler(
            'bot.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(console_format)
        logger.addHandler(file_handler)
    except Exception as e:
        logging.warning(f"امکان نوشتن لاگ در فایل وجود ندارد: {e}")

    return logger

logger = setup_logging()

# ---------- کامپایل RegExها برای سرعت بیشتر ----------
URL_PATTERN = re.compile(r'(?:https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)[^\s]+')
AT_PATTERN = re.compile(r'@[a-zA-Z0-9_]+')
HASH_PATTERN = re.compile(r'#[^\s]+')

# عبارات دعوت به عضویت
INVITE_PATTERNS = [
    re.compile(r'عضویت در کانال', re.IGNORECASE),
    re.compile(r'برای عضویت کلیک کنید', re.IGNORECASE),
    re.compile(r'برای عضویت در کانال', re.IGNORECASE),
    re.compile(r'عضویت در تلگرام', re.IGNORECASE),
    re.compile(r'join our channel', re.IGNORECASE),
    re.compile(r'join us on telegram', re.IGNORECASE),
    re.compile(r'کانال ما', re.IGNORECASE),
    re.compile(r'telegram channel', re.IGNORECASE),
    re.compile(r'joinchat', re.IGNORECASE),
    re.compile(r'عضویت', re.IGNORECASE),
    re.compile(r'برای عضویت', re.IGNORECASE),
]

# کاراکترهای مجاز (برای حذف ایموجی‌ها)
ALLOWED_CHARS_PATTERN = re.compile(
    r'[\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF'
    r'\uFB50-\uFDFF\uFE70-\uFEFF\u200C\u200D'
    r'.،؛:!؟()"\' ]'
)

# ---------- توابع پاکسازی ----------
def clean_foreign_mentions_and_hashtags(text: str) -> str:
    """حذف @، #، لینک‌ها و عبارات دعوت (به جز موارد خودمان)"""
    if not text:
        return ""

    # 1. حذف @ها (به جز @Donya24News)
    def replace_at(match):
        full = match.group(0)
        return full if full == CHANNEL_TAG else ""

    text = AT_PATTERN.sub(replace_at, text)

    # 2. حذف #ها (به جز #دنیا_۲۴_نیوز)
    def replace_hash(match):
        full = match.group(0)
        return full if full == HASHTAG else ""

    text = HASH_PATTERN.sub(replace_hash, text)

    # 3. حذف تمام لینک‌ها
    text = URL_PATTERN.sub('', text)

    # 4. حذف عبارات دعوت
    for pattern in INVITE_PATTERNS:
        text = pattern.sub('', text)

    # 5. حذف فضاهای اضافی
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_trailing_emojis(text: str) -> str:
    """حذف ایموجی‌ها و کاراکترهای غیرمجاز از انتهای متن"""
    if not text:
        return ""

    # از انتها به عقب برو تا اولین کاراکتر مجاز را پیدا کن
    for i in range(len(text) - 1, -1, -1):
        if ALLOWED_CHARS_PATTERN.match(text[i]):
            cleaned = text[:i+1]
            return cleaned.rstrip()

    return ""

def format_news(raw_text: str) -> str:
    """قالب‌بندی خبر با ❇️ و 🔹 و راست‌چینی کامل"""
    # مرحله ۱: پاکسازی @، #، لینک‌ها و عبارات دعوت
    cleaned = clean_foreign_mentions_and_hashtags(raw_text)

    # مرحله ۲: حذف ایموجی‌ها از انتها
    cleaned = clean_trailing_emojis(cleaned)

    # اگر متنی باقی نماند
    if not cleaned:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"

    # تقسیم به خطوط
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"

    title = lines[0]
    body = lines[1:]

    # ساخت خبر با RTL در ابتدا
    result = f"‏❇️ {title}\n"
    for line in body:
        result += f"🔹 {line}\n"

    # اضافه کردن هشتگ و تگ در انتها (با RTL جداگانه)
    result += f"\n‏{HASHTAG}\n‏{CHANNEL_TAG}"
    return result

# ---------- تقسیم پیام‌های طولانی ----------
def split_long_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list:
    """تقسیم پیام‌های بلند به چند بخش با شماره‌گذاری"""
    if len(text) <= max_len:
        return [text]

    parts = []
    start = 0
    total_len = len(text)

    while start < total_len:
        end = min(start + max_len, total_len)
        if end < total_len:
            # برش در انتهای خط یا فاصله
            last_newline = text.rfind('\n', start, end)
            last_space = text.rfind(' ', start, end)
            cut_at = max(last_newline, last_space)
            if cut_at > start:
                end = cut_at + 1

        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end

    # شماره‌گذاری قطعات
    if len(parts) > 1:
        total = len(parts)
        for i, part in enumerate(parts, 1):
            parts[i-1] = f"({i}/{total})\n{part}"

    return parts

# ---------- ارسال پیام با Retry و Rate Limiting ----------
def send_message_with_retry(chat_id: int, text: str, max_retries: int = 3) -> bool:
    """ارسال پیام با تلاش مجدد و مدیریت محدودیت سرعت"""
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{API}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10
            )

            if resp.status_code == 200:
                logger.info(f"✅ پیام به {chat_id} ارسال شد (طول: {len(text)})")
                return True
            elif resp.status_code == 429:
                # محدودیت سرعت - صبر کن
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(f"⏳ Rate limit: صبر {retry_after} ثانیه")
                time.sleep(retry_after)
            else:
                # خطای دیگر - تلاش مجدد با تأخیر
                logger.warning(f"⚠️ تلاش {attempt+1} ناموفق: کد {resp.status_code}")
                time.sleep(2 ** attempt)  # 1, 2, 4 ثانیه

        except Exception as e:
            logger.warning(f"⚠️ تلاش {attempt+1} ناموفق: {e}")
            time.sleep(2 ** attempt)

    logger.error(f"❌ ارسال به {chat_id} پس از {max_retries} تلاش ناموفق")
    return False

def send_long_message(chat_id: int, text: str):
    """ارسال پیام‌های بلند به صورت چند بخش"""
    parts = split_long_message(text)
    for i, part in enumerate(parts):
        success = send_message_with_retry(chat_id, part)
        if not success and i < len(parts) - 1:
            # اگر بخشی ناموفق بود، ادامه نده
            logger.error(f"❌ ارسال بخش {i+1}/{len(parts)} ناموفق، متوقف شد")
            break
        if len(parts) > 1 and i < len(parts) - 1:
            time.sleep(0.5)  # مکث بین قطعات

# ---------- استخراج محتوای پیام ----------
def get_content_from_message(msg: dict) -> str:
    """استخراج متن از پیام (بدون اطلاعات فوروارد)"""
    # استیکر را نادیده بگیر
    if "sticker" in msg:
        return ""

    # اولویت با کپشن (برای رسانه‌ها)
    if "caption" in msg and msg["caption"]:
        return msg["caption"]

    # پیام متنی معمولی
    if "text" in msg and msg["text"]:
        return msg["text"]

    # رسانه بدون کپشن
    if any(key in msg for key in ("photo", "video", "document", "voice", "audio")):
        return ""

    return ""

# ---------- Webhook اصلی ----------
@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        # ایجاد شناسه یکتا برای این درخواست
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"[{request_id}] دریافت درخواست جدید")

        # اعتبارسنجی امنیتی
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET_TOKEN:
            logger.warning(f"[{request_id}] تلاش غیرمجاز")
            return {"ok": False, "error": "Unauthorized"}, 403

        try:
            data = request.get_json()
            if not data or "message" not in data:
                logger.info(f"[{request_id}] درخواست بدون پیام")
                return {"ok": True}

            msg = data["message"]
            chat_id = msg["chat"]["id"]

            # استخراج محتوا
            content = get_content_from_message(msg)

            # قالب‌بندی خبر
            reply = format_news(content)

            # ارسال
            send_long_message(chat_id, reply)

            logger.info(f"[{request_id}] ✅ پردازش پیام از {chat_id} با موفقیت")

        except Exception as e:
            logger.error(f"[{request_id}] ❌ خطای غیرمنتظره: {e}")
            return {"ok": False}, 500

        return {"ok": True}

    # پاسخ به درخواست GET
    return "🤖 ربات خبری هوشمند نسخه ۲.۰ - در حال اجراست"

# ---------- اجرا ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)





