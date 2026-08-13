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
    # ارسال به بله بعد از موفقیت
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

        # ========== دستورات ==========
        if text == "/register":
            tenant = get_tenant(chat_id)
            if tenant:
                send_message(chat_id, "✅ شما قبلاً ثبت‌نام کرده‌اید.")
            else:
                save_tenant(chat_id, "TOKEN_TEMP", "@channel")
                send_message(chat_id, "✅ ثبت‌نام شد. /settelegram @channel")
            return {"ok": True}

        elif text.startswith("/settelegram"):
            parts = text.split()
            if len(parts) < 2:
                send_message(chat_id, "❌ /settelegram @channel")
                return {"ok": True}
            channel = parts[1]
            tenant = get_tenant(chat_id)
            if not tenant:
                send_message(chat_id, "❌ ابتدا /register")
                return {"ok": True}
            save_tenant(
                chat_id,
                tenant.get("bot_token", "TOKEN_TEMP"),
                channel,
                tenant.get("bale_channel", ""),
                tenant.get("bale_token", ""),
                tenant.get("hashtag", "#دنیا_۲۴_نیوز"),
                tenant.get("channel_tag", "@Donya24News")
            )
            send_message(chat_id, f"✅ کانال تلگرام: {channel}")
            return {"ok": True}

        elif text == "/status":
            tenant = get_tenant(chat_id)
            if tenant:
                send_message(chat_id, f"📊 وضعیت:\nکانال تلگرام: {tenant.get('telegram_channel', 'تنظیم نشده')}\nکانال بله: {tenant.get('bale_channel', 'تنظیم نشده')}\nتوکن بله: {'✅' if tenant.get('bale_token') else '❌'}")
            else:
                send_message(chat_id, "❌ ثبت‌نام نکرده‌اید. /register")
            return {"ok": True}

        elif text == "/start":
            send_message(chat_id, "👋 به ربات خبری خوش آمدید!")
            return {"ok": True}

        # ========== پردازش خبر ==========
        else:
            tenant = get_tenant(chat_id)
            if not tenant or not tenant.get("telegram_channel"):
                send_message(chat_id, "❌ ابتدا با /register ثبت‌نام و کانال را تنظیم کنید.")
                return {"ok": True}

            media_info = get_media_from_message(msg)

            # ====== آلبوم ======
            if media_info["type"] and is_media_group(msg):
                branding = get_branding(chat_id)
                handle_media_group_message(
                    msg,
                    media_info["file_id"],
                    media_info["type"],
                    media_info["caption"]
                )
                send_message(chat_id, "✅ آلبوم شما در حال پردازش است...")
                return {"ok": True}

            # ====== رسانه تکی ======
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
                    # ارسال به بله بعد از موفقیت
                    send_to_bale_for_user(chat_id, formatted_caption, media_info["file_id"], media_info["type"])
                else:
                    send_message(chat_id, "❌ ارسال رسانه با مشکل روبرو شد.")
                return {"ok": True}

            # ====== فقط متن ======
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
