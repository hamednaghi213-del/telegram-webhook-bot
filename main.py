import os
import re
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request
import requests
from media_group_handler import handle_media_group_message, is_media_group, initialize as init_media_handler

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

# ---------- تنظیم media_group_handler ----------
init_media_handler(API, CHANNEL_ID)

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
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    text = text.replace('[[TITLE]]', '❇️')
    text = text.replace('[[BULLET]]', '🔹')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

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

def clean_trailing_emojis(text: str) -> str:
    if not text:
        return ""
    for i in range(len(text) - 1, -1, -1):
        if ALLOWED_CHARS_PATTERN.match(text[i]):
            return text[:i+1].rstrip()
    return ""

def clean_after_last_period(text: str) -> str:
    if not text:
        return text
    last_dot = text.rfind('.')
    last_persian_dot = text.rfind('۔')
    last_index = max(last_dot, last_persian_dot)
    if last_index != -1:
        return text[:last_index + 1].strip()
    return text

def clean_media_footer(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'/\s*[^\s/]+\s+[A-Za-z]+\.?\s*$', '', text)
    text = re.sub(r'/\s*[^\s/]+\.?\s*$', '', text)
    text = re.sub(r'[A-Za-z]+\.[A-Za-z]*\s*$', '', text)
    text = re.sub(r'@[a-zA-Z0-9_]+\s*[-–—]\s*(Link|لینک|More|بیشتر)\s*$', '', text, flags=re.IGNORECASE)
    return text.strip()

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

def format_news(raw_text: str) -> str:
    cleaned = remove_all_emojis(raw_text)
    cleaned = clean_foreign_mentions_and_hashtags(cleaned)
    cleaned = clean_all_trailing_content(cleaned)
    cleaned = clean_media_footer(cleaned)
    cleaned = clean_after_last_period(cleaned)
    
    if not cleaned:
        return f"‏{HASHTAG}\n‏{CHANNEL_TAG}"
    
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

# ---------- ارسال عکس و فیلم ----------
def send_media_to_channel(file_id: str, media_type: str, caption: str = ""):
    try:
        if media_type == "photo":
            endpoint = f"{API}/sendPhoto"
        elif media_type == "video":
            endpoint = f"{API}/sendVideo"
        elif media_type == "document":
            endpoint = f"{API}/sendDocument"
        elif media_type == "voice":
            endpoint = f"{API}/sendVoice"
        elif media_type == "audio":
            endpoint = f"{API}/sendAudio"
        else:
            return False
        
        resp = requests.post(
            endpoint,
            json={"chat_id": CHANNEL_ID, media_type: file_id, "caption": caption},
            timeout=30
        )
        resp.raise_for_status()
        logger.info(f"✅ {media_type} در کانال منتشر شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال {media_type} به کانال: {e}")
        return False

# ---------- استخراج اطلاعات رسانه ----------
def get_media_from_message(msg: dict) -> dict:
    result = {"type": None, "file_id": None, "caption": ""}
    
    if "video" in msg:
        result["type"] = "video"
        result["file_id"] = msg["video"]["file_id"]
        result["caption"] = msg.get("caption", "")
    elif "photo" in msg:
        result["type"] = "photo"
        result["file_id"] = msg["photo"][-1]["file_id"]
        result["caption"] = msg.get("caption", "")
    elif "document" in msg:
        result["type"] = "document"
        result["file_id"] = msg["document"]["file_id"]
        result["caption"] = msg.get("caption", "")
    elif "voice" in msg:
        result["type"] = "voice"
        result["file_id"] = msg["voice"]["file_id"]
        result["caption"] = msg.get("caption", "")
    elif "audio" in msg:
        result["type"] = "audio"
        result["file_id"] = msg["audio"]["file_id"]
        result["caption"] = msg.get("caption", "")
    
    return result

def get_content_from_message(msg: dict) -> str:
    if "sticker" in msg:
        return ""
    if "caption" in msg and msg["caption"]:
        return msg["caption"]
    if "text" in msg and msg["text"]:
        return msg["text"]
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

            media_info = get_media_from_message(msg)
            
            # 🆕 بررسی آلبوم
            if media_info["type"] and is_media_group(msg):
                handle_media_group_message(
                    msg,
                    media_info["file_id"],
                    media_info["type"],
                    media_info["caption"]
                )
                try:
                    requests.post(
                        f"{API}/sendMessage",
                        json={"chat_id": chat_id, "text": "✅ آلبوم شما در حال پردازش است..."},
                        timeout=5
                    )
                except:
                    pass
                return {"ok": True}

            # پردازش عادی
            if media_info["type"]:
                caption = media_info["caption"]
                if caption:
                    formatted_caption = format_news(caption)
                else:
                    formatted_caption = ""
                
                send_media_to_channel(
                    media_info["file_id"],
                    media_info["type"],
                    formatted_caption
                )
                
                try:
                    requests.post(
                        f"{API}/sendMessage",
                        json={"chat_id": chat_id, "text": "✅ خبر تصویری/ویدیویی شما در کانال منتشر شد."},
                        timeout=5
                    )
                except:
                    pass
            else:
                content = get_content_from_message(msg)
                if content:
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

    return "🤖 ربات خبری هوشمند - نسخه ۰۱ + پشتیبانی از آلبوم"

# ---------- اجرا ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)
