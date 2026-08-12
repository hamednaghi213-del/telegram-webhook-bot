import logging
import requests
from core.database import get_tenant, save_tenant

logger = logging.getLogger(__name__)

API_URL = None

def initialize(api_url):
    global API_URL
    API_URL = api_url
    logger.info("✅ Command Handler initialized")

def is_command(text: str) -> bool:
    return text and text.startswith('/')

def handle_command(text: str, chat_id: int) -> bool:
    if not text or not text.startswith('/'):
        return False

    command = text.split()[0][1:].lower()

    if command == 'start':
        send_message(chat_id, "👋 به ربات خبری خوش آمدید!\n"
                              "می‌توانید خبر خود را به همراه عکس، فیلم یا به صورت متنی ارسال کنید.\n"
                              "خبر شما پس از پردازش در کانال منتشر خواهد شد.")
        return True

    elif command == 'help':
        send_message(chat_id, "📚 راهنمای ربات:\n\n"
                              "/register - ثبت‌نام در سیستم\n"
                              "/status - مشاهده وضعیت تنظیمات شما\n"
                              "/settelegram @channel - تنظیم کانال تلگرام\n"
                              "/setbale @channel - تنظیم کانال بله\n"
                              "/setbaletoken TOKEN - تنظیم توکن ربات بله")
        return True

    elif command == 'register':
        if get_tenant(chat_id):
            send_message(chat_id, "✅ شما قبلاً ثبت‌نام کرده‌اید.")
        else:
            save_tenant(chat_id, "TOKEN_TEMP", "@channel")
            send_message(chat_id, "✅ ثبت‌نام اولیه انجام شد.\n"
                                  "لطفاً با دستور /settelegram @channel کانال تلگرام خود را تنظیم کنید.\n"
                                  "و با /setbale @channel کانال بله را تنظیم کنید (اختیاری).")
        return True

    elif command == 'settelegram':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ لطفاً کانال را وارد کنید: /settelegram @channel")
            return True
        channel = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا با /register ثبت‌نام کنید.")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", channel, tenant[4], tenant[5])
        send_message(chat_id, f"✅ کانال تلگرام شما به {channel} تنظیم شد.")
        return True

    elif command == 'setbale':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ لطفاً کانال بله را وارد کنید: /setbale @channel")
            return True
        channel = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا با /register ثبت‌نام کنید.")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", tenant[3] or "@channel", channel, tenant[5])
        send_message(chat_id, f"✅ کانال بله شما به {channel} تنظیم شد.")
        return True

    elif command == 'setbaletoken':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ لطفاً توکن ربات بله را وارد کنید.")
            return True
        token = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا با /register ثبت‌نام کنید.")
            return True
        save_tenant(chat_id, tenant[2] or "TOKEN_TEMP", tenant[3] or "@channel", tenant[4] or "", token)
        send_message(chat_id, "✅ توکن بله ذخیره شد.")
        return True

    elif command == 'status':
        tenant = get_tenant(chat_id)
        if tenant:
            send_message(chat_id, f"📊 وضعیت شما:\n"
                                  f"کانال تلگرام: {tenant[3]}\n"
                                  f"کانال بله: {tenant[4] or 'تنظیم نشده'}\n"
                                  f"توکن بله: {'✅' if tenant[5] else '❌'}")
        else:
            send_message(chat_id, "❌ شما ثبت‌نام نکرده‌اید. لطفاً /register را بفرستید.")
        return True

    else:
        send_message(chat_id, f"❌ دستور '{command}' شناسایی نشد.\n"
                              f"برای مشاهده راهنما، /help را بفرستید.")
        return True

def send_message(chat_id: int, text: str):
    if not API_URL:
        logger.error("API_URL تنظیم نشده است!")
        return
    try:
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
        resp.raise_for_status()
        logger.info(f"✅ پیام به {chat_id} ارسال شد")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال پیام: {e}")
