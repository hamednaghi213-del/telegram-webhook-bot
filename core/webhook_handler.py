import logging
import uuid
import requests
import os
import traceback
from flask import request
from core.database import get_tenant, save_tenant

logger = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"

def send_message(chat_id, text):
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"❌ send_message: {e}")

def handle_webhook():
    req_id = str(uuid.uuid4())[:8]
    logger.info(f"[{req_id}] دریافت درخواست")

    try:
        data = request.get_json()
        if not data or "message" not in data:
            return {"ok": True}

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        logger.info(f"[{req_id}] پیام از {chat_id}: {text}")

        # ========== دستورات ==========
        if text == "/register":
            logger.info(f"[{req_id}] ثبت‌نام کاربر {chat_id}")
            if get_tenant(chat_id):
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
            save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", channel, tenant[4], tenant[5])
            send_message(chat_id, f"✅ کانال تلگرام: {channel}")
            return {"ok": True}

        elif text == "/status":
            tenant = get_tenant(chat_id)
            if tenant:
                send_message(chat_id, f"📊 وضعیت:\nکانال تلگرام: {tenant[3]}\nکانال بله: {tenant[4] or 'تنظیم نشده'}\nتوکن بله: {'✅' if tenant[5] else '❌'}")
            else:
                send_message(chat_id, "❌ ثبت‌نام نکرده‌اید. /register")
            return {"ok": True}

        elif text == "/start":
            send_message(chat_id, "👋 به ربات خبری خوش آمدید!")
            return {"ok": True}

        else:
            send_message(chat_id, "❌ دستور نامعتبر. /help")
            return {"ok": True}

    except Exception as e:
        logger.error(f"[{req_id}] ❌ خطا:")
        traceback.print_exc()
        return {"ok": False}, 500
