import logging
import uuid
import requests
import os
import traceback
from flask import request
from core.database import get_tenant, save_tenant
from core.formatter import format_news
from core.media_sender import send_media_to_channel
from core.branding_manager import get_branding
from core.media_handler import is_media_group, handle_media_group_message
from core.bale_forwarder import send_to_bale_for_user
from core.command_handler import is_command, handle_command

logger = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
CHANNEL_ID = "@Donya24News"

def initialize(api_url, channel_id, secret_token):
    global API_URL, CHANNEL_ID
    API_URL = api_url
    CHANNEL_ID = channel_id
    logger.info("✅ Webhook Handler initialized")

def send_message(chat_id, text):
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"❌ send_message: {e}")

def split_long_message(text, max_len=4096):
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_len:
            current_part += line + "\n"
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + "\n"
    if current_part:
        parts.append(current_part.strip())
    return parts

def send_to_channel(text):
    try:
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text},
            timeout=10
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به کانال: {e}")
        return False

def send_long_to_channel(text, chat_id):
    branding = get_branding(chat_id)
    hashtag = branding["hashtag"]
    channel_tag = branding["channel_tag"]
    text = text + f"\n\n{hashtag}\n{channel_tag}"
    parts = split_long_message(text)
    for part in parts:
        success = send_to_channel(part)
        if not success:
            break
    send_to_bale_for_user(chat_id, text)

def get_message_text(msg):
    if "caption" in msg and msg["caption"]:
        return msg["caption"]
    if "text" in msg and msg["text"]:
        return msg["text"]
    return ""

def get_media_from_message(msg):
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

def handle_webhook():
    req_id = str(uuid.uuid4())[:8]
    logger.info(f"[{req_id}] دریافت درخواست")

    try:
        data = request.get_json()
        if not data or "message" not in data:
            return {"ok": True}

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = get_message_text(msg)

        logger.info(f"[{req_id}] پیام از {chat_id}")

        if text and is_command(text):
            handle_command(text, chat_id)
            return {"ok": True}

        tenant = get_tenant(chat_id)
        if not tenant or not tenant.get("telegram_channel"):
            send_message(chat_id, "❌ ابتدا با /register ثبت‌نام و کانال را تنظیم کنید.")
            return {"ok": True}

        media_info = get_media_from_message(msg)

        if media_info["type"] and is_media_group(msg):
            handle_media_group_message(
                msg,
                media_info["file_id"],
                media_info["type"],
                media_info["caption"]
            )
            send_message(chat_id, "✅ آلبوم شما در حال پردازش است...")
            return {"ok": True}

        elif media_info["type"]:
            caption = text if text else media_info.get("caption", "")
            if caption:
                formatted_caption = format_news(caption)
                branding = get_branding(chat_id)
                formatted_caption = formatted_caption + f"\n\n{branding['hashtag']}\n{branding['channel_tag']}"
            else:
                branding = get_branding(chat_id)
                formatted_caption = f"{branding['hashtag']}\n{branding['channel_tag']}"
            success = send_media_to_channel(API_URL, CHANNEL_ID, media_info["file_id"], media_info["type"], formatted_caption)
            if success:
                send_message(chat_id, "✅ خبر تصویری/ویدیویی شما در کانال منتشر شد.")
                send_to_bale_for_user(chat_id, formatted_caption, media_info["file_id"], media_info["type"])
            else:
                send_message(chat_id, "❌ ارسال رسانه با مشکل روبرو شد.")
            return {"ok": True}

        else:
            if text.strip():
                formatted = format_news(text)
                if formatted:
                    send_long_to_channel(formatted, chat_id)
                    send_message(chat_id, "✅ خبر شما در کانال منتشر شد.")
                else:
                    send_message(chat_id, "❌ خبر قابل پردازش نیست.")
            else:
                send_message(chat_id, "❌ پیام خالی است.")
            return {"ok": True}

    except Exception as e:
        logger.error(f"[{req_id}] ❌ خطا:")
        traceback.print_exc()
        return {"ok": False}, 500
