import os
import time
import logging
import threading
import requests

from flask import Flask, request
from logging.handlers import RotatingFileHandler

from core.webhook_handler import (
    initialize as init_webhook,
    handle_webhook
)

from core.cleaner import (
    initialize as init_cleaner
)

from core.formatter import (
    initialize as init_formatter
)

from core.media_handler import (
    initialize as init_media_handler
)

from core.command_handler import (
    initialize as init_commands
)

from core.deep_reply_handler import (
    initialize as init_deep_reply
)

from core.database import (
    init_db
)


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

if not TOKEN:

    raise ValueError(
        "❌ توکن در متغیر محیطی "
        "TELEGRAM_BOT_TOKEN تنظیم نشده."
    )


SECRET_TOKEN = os.getenv(
    "TELEGRAM_SECRET_TOKEN",
    "my_secret_token_123"
)


API = (
    f"https://api.telegram.org/"
    f"bot{TOKEN}"
)


CHANNEL_ID = os.getenv(
    "TELEGRAM_CHANNEL_ID",
    "@Donya24News"
)


HASHTAG = os.getenv(
    "CHANNEL_HASHTAG",
    "#دنیا_۲۴_نیوز"
)


CHANNEL_TAG = os.getenv(
    "CHANNEL_TAG",
    "@Donya24News"
)


# =========================================================
# LOGGING
# =========================================================

def setup_logging():

    logger = logging.getLogger()

    logger.setLevel(
        logging.INFO
    )

    # جلوگیری از اضافه شدن چند Handler
    if logger.handlers:

        return logger

    console_handler = (
        logging.StreamHandler()
    )

    console_handler.setLevel(
        logging.INFO
    )

    console_format = (
        logging.Formatter(
            "%(asctime)s - "
            "%(levelname)s - "
            "%(message)s"
        )
    )

    console_handler.setFormatter(
        console_format
    )

    logger.addHandler(
        console_handler
    )

    # -----------------------------------------
    # File Log
    # -----------------------------------------

    try:

        file_handler = (
            RotatingFileHandler(
                "bot.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8"
            )
        )

        file_handler.setLevel(
            logging.INFO
        )

        file_handler.setFormatter(
            console_format
        )

        logger.addHandler(
            file_handler
        )

    except Exception as e:

        print(
            f"⚠️ فعال‌سازی فایل لاگ "
            f"ناموفق بود: {e}"
        )

    return logger


logger = setup_logging()


# =========================================================
# INITIALIZE ALL MODULES
# =========================================================

def initialize_modules():

    logger.info(
        "🚀 شروع مقداردهی اولیه ماژول‌ها..."
    )

    # -----------------------------------------
    # Database
    # -----------------------------------------

    init_db()

    logger.info(
        "✅ Database initialized"
    )

    # -----------------------------------------
    # Cleaner
    # -----------------------------------------

    init_cleaner(
        CHANNEL_TAG,
        HASHTAG
    )

    logger.info(
        "✅ Cleaner initialized"
    )

    # -----------------------------------------
    # Formatter
    # -----------------------------------------

    init_formatter(
        CHANNEL_TAG,
        HASHTAG
    )

    logger.info(
        "✅ Formatter initialized"
    )

    # -----------------------------------------
    # Media Handler
    # -----------------------------------------

    init_media_handler(
        API,
        CHANNEL_ID
    )

    logger.info(
        "✅ Media Handler initialized"
    )

    # -----------------------------------------
    # Command Handler
    # -----------------------------------------

    init_commands(
        API
    )

    logger.info(
        "✅ Command Handler initialized"
    )

    # -----------------------------------------
    # Deep Reply Handler
    # -----------------------------------------

    init_deep_reply(
        API,
        CHANNEL_ID
    )

    logger.info(
        "✅ Deep Reply Handler initialized"
    )

    # -----------------------------------------
    # Webhook Handler
    # -----------------------------------------

    init_webhook(
        API,
        CHANNEL_ID,
        SECRET_TOKEN
    )

    logger.info(
        "✅ Webhook Handler initialized"
    )

    logger.info(
        "🎯 تمام ماژول‌ها با موفقیت "
        "مقداردهی شدند."
    )


# =========================================================
# SELF PING
# =========================================================

def self_ping():

    # بهتر است URL از Environment خوانده شود
    url = os.getenv(
        "SELF_PING_URL",
        "https://telegram-webhook-bot-onyd.onrender.com/"
    )

    interval = int(
        os.getenv(
            "SELF_PING_INTERVAL",
            "420"
        )
    )

    logger.info(
        f"🔄 Self-ping فعال شد | "
        f"interval={interval}s"
    )

    while True:

        try:

            response = requests.get(
                url,
                timeout=15
            )

            logger.info(
                f"🔄 Self-ping | "
                f"status={response.status_code}"
            )

        except Exception as e:

            logger.error(
                f"❌ Self-ping خطا: {e}"
            )

        time.sleep(
            interval
        )


# =========================================================
# START SELF PING
# =========================================================

def start_self_ping():

    # جلوگیری از اجرای چندباره
    thread = threading.Thread(
        target=self_ping,
        name="SelfPingThread",
        daemon=True
    )

    thread.start()

    return thread


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def health_check():

    return (
        "🤖 ربات خبری هوشمند - "
        "نسخه نهایی"
    )


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route(
    "/",
    methods=["POST"]
)
def webhook():

    return handle_webhook()


# =========================================================
# STARTUP
# =========================================================

initialize_modules()

start_self_ping()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            10000
        )
    )

    logger.info(
        f"🚀 ربات روی پورت "
        f"{port} در حال اجراست..."
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
