import os
import time
import logging
import threading
import requests
from logging.handlers import RotatingFileHandler
from flask import Flask, request

from core.webhook_handler import initialize as init_webhook, handle_webhook
from core.cleaner import initialize as init_cleaner
from core.formatter import initialize as init_formatter
from core.media_handler import initialize as init_media_handler
from core.command_handler import initialize as init_commands
from core.deep_reply_handler import initialize as init_deep_reply

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("توکن در متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده.")

SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "my_secret_token_123")
API = f"https://api.telegram.org/bot{TOKEN}"

CHANNEL_ID = "@Donya24News"
HASHTAG = "#دنیا_۲۴_نیوز"
CHANNEL_TAG = "@Donya24News"

init_cleaner(CHANNEL_TAG, HASHTAG)
init_formatter(CHANNEL_TAG, HASHTAG)
init_media_handler(API, CHANNEL_ID)
init_commands(API)
init_deep_reply(API, CHANNEL_ID)
init_webhook(API, CHANNEL_ID, SECRET_TOKEN)

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

@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        return handle_webhook()
    return "🤖 ربات خبری هوشمند - نسخه نهایی"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 ربات روی پورت {port} در حال اجراست...")
    app.run(host="0.0.0.0", port=port)
