import logging
import uuid
import requests
import os
import traceback
from flask import request
from core.database import get_tenant, save_tenant
from core.formatter import format_news

logger = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
CHANNEL_ID = "@Donya24News"
HASHTAG = "#دنیا_۲۴_نیوز"
CHANNEL_TAG = "@Donya24News"

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

def send_long_to_channel(text):
    text = text + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
    parts = split_long_message(text)
    for part in parts:
        success = send_to_channel(part)
        if not success:
            break

def get_message_text(msg):
    """استخراج متن از پیام (اولویت با caption)"""
    if "caption" in msg and msg["caption"]:
        return msg["caption"]
    if "text" in msg and msg["text"]:
        return msg["text"]
    return ""

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

        logger.info(f"[{req_id}] پیام از {chat_id}: {text[:50]}...")

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
                tenant.get("bale_token", "")
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

        # ========== ارسال خبر به کانال ==========
        else:
            if text.strip():
                tenant = get_tenant(chat_id)
                if tenant and tenant.get("telegram_channel"):
                    formatted = format_news(text)
                    if formatted:
                        send_long_to_channel(formatted)
                        send_message(chat_id, "✅ خبر شما در کانال منتشر شد.")
                    else:
                        send_message(chat_id, "❌ خبر قابل پردازش نیست.")
                else:
                    send_message(chat_id, "❌ ابتدا با /register ثبت‌نام و کانال را تنظیم کنید.")
            else:
                send_message(chat_id, "❌ پیام خالی است.")
            return {"ok": True}

    except Exception as e:
        logger.error(f"[{req_id}] ❌ خطا:")
        traceback.print_exc()
        return {"ok": False}, 500
