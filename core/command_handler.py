import logging
import requests
from core.database import get_tenant, save_tenant

logger = logging.getLogger(__name__)
API_URL = None

def initialize(api_url):
    global API_URL
    API_URL = api_url
    logger.info("✅ Command Handler initialized")

def is_command(text):
    return text and text.startswith('/')

def send_message(chat_id, text):
    if not API_URL:
        return
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"❌ خطا در ارسال پیام: {e}")

def handle_command(text, chat_id):
    if not text or not text.startswith('/'):
        return False

    command = text.split()[0][1:].lower()

    # ====== ثبت‌نام ======
    if command == 'register':
        tenant = get_tenant(chat_id)
        if tenant:
            send_message(chat_id, "✅ شما قبلاً ثبت‌نام کرده‌اید.")
        else:
            save_tenant(chat_id, "TOKEN_TEMP", "@channel")
            send_message(chat_id, "✅ ثبت‌نام شد. /settelegram @channel")
        return True

    # ====== تنظیم کانال تلگرام ======
    elif command == 'settelegram':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /settelegram @channel")
            return True
        channel = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
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
        return True

    # ====== 🆕 تنظیم کانال بله ======
    elif command == 'setbale':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /setbale @channel")
            return True
        channel = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
        save_tenant(
            chat_id,
            tenant.get("bot_token", "TOKEN_TEMP"),
            tenant.get("telegram_channel", "@channel"),
            channel,  # bale_channel
            tenant.get("bale_token", ""),  # bale_token
            tenant.get("hashtag", "#دنیا_۲۴_نیوز"),
            tenant.get("channel_tag", "@Donya24News")
        )
        send_message(chat_id, f"✅ کانال بله: {channel}")
        logger.info(f"✅ کانال بله برای کاربر {chat_id} به {channel} تنظیم شد.")
        return True

    # ====== 🆕 تنظیم توکن بله ======
    elif command == 'setbaletoken':
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ /setbaletoken TOKEN")
            return True
        token = parts[1]
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(chat_id, "❌ ابتدا /register")
            return True
        save_tenant(
            chat_id,
            tenant.get("bot_token", "TOKEN_TEMP"),
            tenant.get("telegram_channel", "@channel"),
            tenant.get("bale_channel", ""),  # bale_channel
            token,  # bale_token
            tenant.get("hashtag", "#دنیا_۲۴_نیوز"),
            tenant.get("channel_tag", "@Donya24News")
        )
        send_message(chat_id, "✅ توکن بله ذخیره شد.")
        logger.info(f"✅ توکن بله برای کاربر {chat_id} ذخیره شد.")
        return True

    # ====== وضعیت ======
    elif command == 'status':
        tenant = get_tenant(chat_id)
        if tenant:
            send_message(chat_id, f"📊 وضعیت:\nکانال تلگرام: {tenant.get('telegram_channel', 'تنظیم نشده')}\nکانال بله: {tenant.get('bale_channel', 'تنظیم نشده')}\nتوکن بله: {'✅' if tenant.get('bale_token') else '❌'}")
        else:
            send_message(chat_id, "❌ ثبت‌نام نکرده‌اید. /register")
        return True

    # ====== راهنما ======
    elif command == 'help':
        send_message(chat_id, "📚 راهنما:\n/register - ثبت‌نام\n/status - وضعیت\n/settelegram @channel\n/setbale @channel\n/setbaletoken TOKEN")
        return True

    elif command == 'start':
        send_message(chat_id, "👋 به ربات خبری خوش آمدید!")
        return True

    else:
        send_message(chat_id, f"❌ دستور '{command}' شناسایی نشد.\n/help")
        return True
