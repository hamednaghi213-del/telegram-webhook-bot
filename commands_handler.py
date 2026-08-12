import logging
import requests

logger = logging.getLogger(__name__)

API_URL = None

def initialize(api_url):
    global API_URL
    API_URL = api_url

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
                              "1. یک خبر را به همراه عکس یا فیلم ارسال کنید.\n"
                              "2. می‌توانید چند عکس را به صورت آلبوم بفرستید.\n"
                              "3. خبر شما به طور خودکار در کانال منتشر می‌شود.\n"
                              "4. تمام آیدی‌ها و هشتگ‌های غیرخودی حذف می‌شوند.")
        return True
    
    elif command == 'stats':
        send_message(chat_id, "📊 آمار ربات:\n"
                              "▪️ نسخه: 2.0\n"
                              "▪️ وضعیت: فعال\n"
                              "▪️ سرویس: بیدار (Self-Ping فعال)")
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
