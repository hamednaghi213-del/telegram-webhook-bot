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

CHANNEL_ID = "@Donya24News"
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
    
    # 1. حذف @ها (به جز @Donya24News)
    def replace_at(match):
        return match.group(0) if match.group(0) == CHANNEL_TAG else ""
    text = AT_PATTERN.sub(replace_at, text)
    
    # 2. حذف #ها (به جز #دنیا_۲۴_نیوز)
    def replace_hash(match):
        return match.group(0) if match.group(0) == HASHTAG else ""
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
    if not text:
        return ""
    for i in range(len(text) - 1, -1, -1):
        if ALLOWED_CHARS_PATTERN.match(text[i]):
            return text[:i+1].rstrip()
    return ""

def clean_all_trailing_content(text: str) -> str:
    """
    حذف هوشمندانه تمام موارد اضافی از انتهای متن:
    - ایموجی‌ها و پرچم‌ها
    - عبارات مثل "| اخبار ..."
    - @آیدی‌ها
    - کلمات تکراری مثل "اخبار"، "کانال"، "تلگرام"
    - هرگونه کاراکتر غیرضروری بعد از آخرین کلمه مفید
    """
    if not text:
        return ""
    
    # 1. حذف پرچم‌های کشورها (🇮🇷🇺🇸🇬🇧 و ...)
    text = re.sub(r'[\U0001F1E6-\U0001F1FF]+', '', text)
    
    # 2. حذف هر چیزی که با | شروع می‌شود تا انتهای خط
    text = re.sub(r'\|.*$', '', text, flags=re.MULTILINE)
    
    # 3. حذف عبارات "اخبار کانال" یا "کانال تلگرام"
    text = re.sub(r'(اخبار|کانال|تلگرام|channel|telegram)\s+[^\s]+$', '', text, flags=re.IGNORECASE)
    
    # 4. حذف @آیدی‌های باقی‌مانده
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    
    # 5. حذف هرگونه کلمه تکراری که به کانال اشاره دارد
    text = re.sub(r'\b(کانال|تلگرام|channel|telegram)\b', '', text, flags=re.IGNORECASE)
    
    # 6. حذف فاصله‌های اضافی و خطوط خالی
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 7. حذف ایموجی‌های انتهایی
    text = clean_trailing_emojis(text)
    
    return text

def format_news(raw_text: str) -> str:
    # مرحله ۱: پاکسازی @، #، لینک‌ها و عبارات دعوت
    cleaned = clean_foreign_mentions_and_hashtags(raw_text)
    
    # مرحله ۲: حذف هوشمندانه تمام موارد اضافی از انتها
    cleaned = clean_all_trailing_content(cleaned)
    
    if not cleaned:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"
    
    # مرحله ۳: تقسیم به خطوط
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"
    
    # مرحله ۴: قالب‌بندی
    title = lines[0]
    body = lines[1:]
    
    result = f"‏❇️ {title}\n"
    for line in body:
        result += f"🔹 {line}\n"
    
    result += f"\n‏{HASHTAG}\n‏{CHANNEL_TAG}"
    return result

# ---------- باقی توابع (split, send, webhook) به همان شکل ----------
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
            reply = format_news(content)

            send_long_to_channel(reply)

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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)
