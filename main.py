import os
import time
import logging
import threading
import requests

from flask import (
    Flask,
    request,
    jsonify
)

from logging.handlers import (
    RotatingFileHandler
)

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

from core.smart_summarizer import (
    summarize_text_safely
)

from core.ai_summarizer_provider import (
    summarize_with_gemini
)
from core.release_readiness import parse_bool


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
    "TELEGRAM_SECRET_TOKEN"
)

if not SECRET_TOKEN:
    raise ValueError(
        "❌ متغیر محیطی TELEGRAM_SECRET_TOKEN تنظیم نشده است."
    )


GEMINI_TEST_SECRET = os.getenv(
    "GEMINI_TEST_SECRET",
    ""
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

ENABLE_SELF_PING = parse_bool(
    os.getenv("ENABLE_SELF_PING", "false")
)

APPLICATION_READY = False


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

    global APPLICATION_READY

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

    APPLICATION_READY = True


# =========================================================
# SELF PING
# =========================================================

def self_ping():

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


@app.route("/healthz", methods=["GET"])
def liveness_check():
    return jsonify({"ok": True, "status": "alive"}), 200


@app.route("/readyz", methods=["GET"])
def readiness_check():
    status_code = 200 if APPLICATION_READY else 503
    return jsonify({
        "ok": APPLICATION_READY,
        "status": "ready" if APPLICATION_READY else "starting",
    }), status_code


# =========================================================
# GEMINI LIVE TEST
# =========================================================

@app.route(
    "/test-gemini",
    methods=["GET"]
)
def test_gemini():

    # -----------------------------------------
    # Security
    # -----------------------------------------

    configured_secret = (
        GEMINI_TEST_SECRET
        or ""
    )

    supplied_secret = (
        request.args.get(
            "secret",
            ""
        )
        or ""
    )

    if not configured_secret:

        logger.error(
            "❌ GEMINI_TEST_SECRET "
            "is not configured"
        )

        return jsonify({
            "ok": False,
            "error": (
                "GEMINI_TEST_SECRET "
                "is not configured"
            )
        }), 503

    if supplied_secret != configured_secret:

        logger.warning(
            "⚠️ Unauthorized Gemini "
            "test request"
        )

        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    # -----------------------------------------
    # Test Text
    # -----------------------------------------

    original_text = (
        "وزیر خارجه اعلام کرد احتمال دارد "
        "مذاکرات در هفته آینده آغاز شود. "
        "او گفت رایزنی‌های دیپلماتیک در "
        "روزهای اخیر ادامه داشته و طرف‌ها "
        "در حال بررسی پیشنهادهای مطرح شده "
        "هستند. مقام‌های مسئول هنوز زمان "
        "قطعی آغاز مذاکرات را اعلام نکرده‌اند. "
        "بر اساس این گزارش، رایزنی‌ها برای "
        "رسیدن به چارچوب اولیه همچنان "
        "ادامه دارد."
    )

    target_length = 220

    logger.info(
        "🧠 Gemini live test started | "
        f"original_length={len(original_text)} | "
        f"target_length={target_length}"
    )

    # -----------------------------------------
    # Smart Summarizer
    # -----------------------------------------

    try:

        result = summarize_text_safely(
            original_text=original_text,
            target_length=target_length,
            summarizer=summarize_with_gemini
        )

    except Exception as e:

        logger.exception(
            f"❌ Gemini live test crashed | "
            f"{e}"
        )

        return jsonify({
            "ok": False,
            "error": "test_execution_failed",
            "detail": str(e)
        }), 500

    # -----------------------------------------
    # Result
    # -----------------------------------------

    logger.info(
        "🧠 Gemini live test completed | "
        f"success={result.success} | "
        f"reason={result.reason} | "
        f"validation="
        f"{result.validation_passed} | "
        f"original_length="
        f"{result.original_length} | "
        f"summary_length="
        f"{result.summary_length}"
    )

    return jsonify({

        "ok": True,

        "summary_success":
            result.success,

        "reason":
            result.reason,

        "validation_passed":
            result.validation_passed,

        "original_length":
            result.original_length,

        "summary_length":
            result.summary_length,

        "reduction_ratio":
            result.reduction_ratio,

        "original_text":
            result.original_text,

        "summary_text":
            result.summary_text,

        "metadata":
            result.metadata
    })


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

if ENABLE_SELF_PING:
    start_self_ping()
else:
    logger.info("ℹ️ Self-ping disabled")


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
