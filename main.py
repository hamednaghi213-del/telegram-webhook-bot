import os
import re
import time
import uuid
import logging
import threading
import requests
from logging.handlers import RotatingFileHandler
from flask import Flask, request

# ---------- import ماژول‌های جدید ----------
from core.cleaner import initialize as init_cleaner
from core.formatter import initialize as init_formatter, format_news
from core.media_handler import handle_media_group_message, is_media_group, initialize as init_media_handler
from core.command_handler import is_command, handle_command, initialize as init_commands

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

# ---------- مقداردهی اولیه ماژول‌ها ----------
init_cleaner(CHANNEL_TAG, HASHTAG)
init_formatter(CHANNEL_TAG, HASHTAG)
init_media_handler(API, CHANNEL_ID)
init_commands(API)

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

# ---------- Self-Ping ----------
def self_ping():
    url = "https://telegram-webhook-bot-onyd.onrender.com/"
    while True:
        try:
            response = requests.get(url, timeout=10)
            logger.info(f"🔄 Self-ping: وضعیت {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Self-ping خطا: {e}")
        time.sleep(420)

ping_thread = threading.Thread(target=self_ping)
ping_thread.daemon = True
ping_thread.start()
logger.info("✅ Self-ping فعال شد (هر ۷ دقیقه یک بار)")

# ---------- توابع کمکی ----------
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
    text = text + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
    parts = split_long_message(text)
    for part in parts:
        success = send_to_channel(part)
        if not success:
            break
        if len(parts) > 1:
            time.sleep(0.5)

def send_media_to_channel(file_id: str, media_type: str, caption: str = ""):
    try:
        if caption:
            caption = caption + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
        else:
            caption = f"{HASHTAG}\n{CHANNEL_TAG}"
        
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

            # بررسی دستورات متنی
            content = get_content_from_message(msg)
            if content and is_command(content):
                handle_command(content, chat_id)
                return {"ok": True}

            media_info = get_media_from_message(msg)
            
            # بررسی آلبوم
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

    return "🤖 ربات خبری هوشمند - نسخه نهایی با ساختار ماژولار"

# ---------- اجرا ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)
