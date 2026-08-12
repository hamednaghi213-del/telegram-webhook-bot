import logging
import uuid
import requests
from flask import request
from core.command_handler import is_command, handle_command
from core.media_handler import is_media_group, handle_media_group_message
from core.deep_reply_handler import has_reply, process_deep_reply
from core.formatter import format_news

logger = logging.getLogger(__name__)

API_URL = None
CHANNEL_ID = None
SECRET_TOKEN = None

def initialize(api_url, channel_id, secret_token):
    global API_URL, CHANNEL_ID, SECRET_TOKEN
    API_URL = api_url
    CHANNEL_ID = channel_id
    SECRET_TOKEN = secret_token
    logger.info("✅ Webhook Handler initialized")

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

def send_media_to_channel(file_id: str, media_type: str, caption: str = ""):
    from core.formatter import HASHTAG, CHANNEL_TAG
    try:
        if caption:
            caption = caption + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
        else:
            caption = f"{HASHTAG}\n{CHANNEL_TAG}"
        if media_type == "photo":
            endpoint = f"{API_URL}/sendPhoto"
        elif media_type == "video":
            endpoint = f"{API_URL}/sendVideo"
        elif media_type == "document":
            endpoint = f"{API_URL}/sendDocument"
        elif media_type == "voice":
            endpoint = f"{API_URL}/sendVoice"
        elif media_type == "audio":
            endpoint = f"{API_URL}/sendAudio"
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

def send_long_to_channel(text: str):
    from core.formatter import HASHTAG, CHANNEL_TAG
    text = text + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
    max_len = 4096
    if len(text) <= max_len:
        send_simple_message(text)
        return
    parts = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        if end < len(text):
            last_newline = text.rfind('\n', start, end)
            last_space = text.rfind(' ', start, end)
            cut_at = max(last_newline, last_space)
            if cut_at > start:
                end = cut_at + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    for i, part in enumerate(parts):
        if len(parts) > 1:
            part = f"({i+1}/{len(parts)})\n{part}"
        send_simple_message(part)
        import time
        time.sleep(0.5)

def send_simple_message(text: str):
    try:
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text},
            timeout=10
        )
        resp.raise_for_status()
        logger.info(f"✅ پیام در کانال منتشر شد (طول: {len(text)})")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال پیام: {e}")

def handle_webhook():
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
        if has_reply(msg):
            if process_deep_reply(msg):
                try:
                    requests.post(
                        f"{API_URL}/sendMessage",
                        json={"chat_id": chat_id, "text": "✅ خبر با پاسخ‌ها در کانال منتشر شد."},
                        timeout=5
                    )
                except:
                    pass
                return {"ok": True}
        content = get_content_from_message(msg)
        if content and is_command(content):
            handle_command(content, chat_id)
            return {"ok": True}
        media_info = get_media_from_message(msg)
        if media_info["type"] and is_media_group(msg):
            handle_media_group_message(
                msg,
                media_info["file_id"],
                media_info["type"],
                media_info["caption"]
            )
            try:
                requests.post(
                    f"{API_URL}/sendMessage",
                    json={"chat_id": chat_id, "text": "✅ آلبوم شما در حال پردازش است..."},
                    timeout=5
                )
            except:
                pass
            return {"ok": True}
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
                    f"{API_URL}/sendMessage",
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
                        f"{API_URL}/sendMessage",
                        json={"chat_id": chat_id, "text": "✅ خبر شما در کانال منتشر شد."},
                        timeout=5
                    )
                except:
                    pass
        logger.info(f"[{request_id}] ✅ خبر در کانال منتشر شد")
        return {"ok": True}
    except Exception as e:
        logger.error(f"[{request_id}] ❌ خطا: {e}")
        return {"ok": False}, 500
