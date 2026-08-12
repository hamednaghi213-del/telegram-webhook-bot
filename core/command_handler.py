import logging
import requests
from core.database import get_tenant, save_tenant

logger = logging.getLogger(__name__)

API_URL = None

def initialize(api_url):
    global API_URL
    API_URL = api_url

def is_command(text):
    return text and text.startswith('/')

def handle_command(text, chat_id):
    if not text or not text.startswith('/'):
        return False
    command = text.split()[0][1:].lower()

    if command == 'start':
        send_message(chat_id, "👋 به ربات خبری خوش آمدید!")
        return True

    if command == 'help':
        send_message(chat_id, "📚 راهنما:\n/register - ثبت‌نام\n/status - وضعیت\n/settelegram @channel\n/setbale @channel\n/setbaletoken TOKEN")
        return True

    if command == 'register':
        if get_tenant(chat_id):
            send_message(chat_id, "✅ ثبت‌نام شده‌اید.")
        else:
            save_tenant(chat_id, "TOKEN_TEMP", "@channel")
            send_message(chat_id, "✅ ثبت‌نام شد. /settelegram @channel")
        return True

    if command == 'settelegram':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /settelegram @channel")
            return True
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", parts[1], tenant[4], tenant[5])
        send_message(chat_id, f"✅ کانال تلگرام: {parts[1]}")
        return True

    if command == 'setbale':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /setbale @channel")
            return True
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", tenant[3] or "@channel", parts[1], tenant[5])
        send_message(chat_id, f"✅ کانال بله: {parts[1]}")
        return True

    if command == 'setbaletoken':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /setbaletoken TOKEN")
            return True
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", tenant[3] or "@channel", tenant[4] or "", parts[1])
        send_message(chat_id, "✅ توکن بله ذخیره شد.")
        return True

    if command == 'status':
        tenant = get_tenant(chat_id)
        if tenant:
            send_message(chat_id, f"📊 وضعیت:\nکانال تلگرام: {tenant[3]}\nکانال بله: {tenant[4] or 'تنظیم نشده'}\nتوکن بله: {'✅' if tenant[5] else '❌'}")
        else:
            send_message(chat_id, "❌ ثبت‌نام نکرده‌اید. /register")
        return True

    send_message(chat_id, f"❌ دستور '{command}' شناسایی نشد.\n/help")
    return True

def send_message(chat_id, text):
    if not API_URL:
        return
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"❌ خطا: {e}")
