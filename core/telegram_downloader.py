import os
import logging
import tempfile
import requests

from telethon import TelegramClient

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


# =========================================================
# ENV
# =========================================================

def get_bot_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."
        )
        return None

    return token


def get_api_id():
    value = os.getenv("TELEGRAM_API_ID")

    if not value:
        logger.error(
            "❌ TELEGRAM_API_ID تنظیم نشده است."
        )
        return None

    try:
        return int(value)

    except ValueError:
        logger.error(
            "❌ TELEGRAM_API_ID باید عدد باشد."
        )
        return None


def get_api_hash():
    value = os.getenv("TELEGRAM_API_HASH")

    if not value:
        logger.error(
            "❌ TELEGRAM_API_HASH تنظیم نشده است."
        )
        return None

    return value


# =========================================================
# BOT API DOWNLOAD
# =========================================================

def download_with_bot_api(file_id):
    """
    دانلود فایل با Telegram Bot API.

    برای فایل‌های معمولی استفاده می‌شود.
    اگر Bot API به دلیل حجم فایل شکست بخورد،
    دانلود به Telethon منتقل می‌شود.
    """

    bot_token = get_bot_token()

    if not bot_token:
        return None, None

    try:

        get_file_url = (
            f"{TELEGRAM_API_BASE}/bot"
            f"{bot_token}/getFile"
        )

        response = requests.get(
            get_file_url,
            params={
                "file_id": file_id
            },
            timeout=60
        )

        if response.status_code != 200:

            logger.warning(
                f"⚠️ Telegram getFile failed | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return None, None

        data = response.json()

        if not data.get("ok"):

            logger.warning(
                f"⚠️ Telegram getFile returned error | "
                f"{data}"
            )

            return None, None

        file_path = (
            data
            .get("result", {})
            .get("file_path")
        )

        if not file_path:

            logger.warning(
                "⚠️ file_path دریافت نشد."
            )

            return None, None

        download_url = (
            f"{TELEGRAM_API_BASE}/file/bot"
            f"{bot_token}/{file_path}"
        )

        file_response = requests.get(
            download_url,
            timeout=300
        )

        if file_response.status_code != 200:

            logger.warning(
                f"⚠️ Telegram file download failed | "
                f"status={file_response.status_code}"
            )

            return None, None

        content = file_response.content

        if not content:

            logger.warning(
                "⚠️ فایل دانلود شده خالی است."
            )

            return None, None

        filename = os.path.basename(
            file_path
        )

        logger.info(
            f"✅ فایل با Bot API دانلود شد | "
            f"name={filename} | "
            f"size={len(content)} bytes"
        )

        return content, filename

    except Exception as e:

        logger.exception(
            f"❌ خطا در download_with_bot_api: {e}"
        )

        return None, None


# =========================================================
# TELETHON DOWNLOAD
# =========================================================

def download_with_telethon(file_id):
    """
    دانلود فایل‌های بزرگ با Telethon.

    Telethon فایل را مستقیماً روی دیسک موقت
    Render ذخیره می‌کند.
    """

    api_id = get_api_id()
    api_hash = get_api_hash()

    if not api_id or not api_hash:
        return None, None

    bot_token = get_bot_token()

    if not bot_token:
        return None, None

    temp_path = None
    client = None

    try:

        session_path = os.getenv(
            "TELETHON_SESSION",
            "/tmp/telegram_downloader"
        )

        logger.info(
            "🚀 شروع دانلود فایل با Telethon..."
        )

        client = TelegramClient(
            session_path,
            api_id,
            api_hash
        )

        # -------------------------------------------------
        # اتصال Telethon
        # -------------------------------------------------

        client.start(
            bot_token=bot_token
        )

        logger.info(
            "✅ Telethon با موفقیت متصل شد."
        )

        # -------------------------------------------------
        # فایل موقت
        # -------------------------------------------------

        with tempfile.NamedTemporaryFile(
            delete=False,
            dir="/tmp"
        ) as temp_file:

            temp_path = temp_file.name

        logger.info(
            f"📥 دانلود فایل بزرگ با Telethon | "
            f"path={temp_path}"
        )

        # -------------------------------------------------
        # دانلود
        # -------------------------------------------------

        downloaded_path = client.loop.run_until_complete(
            client.download_media(
                file_id,
                file=temp_path
            )
        )

        # -------------------------------------------------
        # قطع اتصال
        # -------------------------------------------------

        try:
            client.disconnect()
        except Exception:
            pass

        client = None

        # -------------------------------------------------
        # بررسی مسیر
        # -------------------------------------------------

        if not downloaded_path:

            logger.error(
                "❌ Telethon مسیر فایل دانلود شده را برنگرداند."
            )

            return None, None

        if not os.path.exists(
            temp_path
        ):

            logger.error(
                "❌ فایل دانلود شده توسط Telethon "
                "در مسیر موقت پیدا نشد."
            )

            return None, None

        file_size = os.path.getsize(
            temp_path
        )

        if file_size <= 0:

            logger.error(
                "❌ فایل دانلود شده خالی است."
            )

            return None, None

        # -------------------------------------------------
        # خواندن فایل
        # -------------------------------------------------

        with open(
            temp_path,
            "rb"
        ) as file:

            content = file.read()

        if not content:

            logger.error(
                "❌ محتوای فایل خالی است."
            )

            return None, None

        # -------------------------------------------------
        # نام فایل
        # -------------------------------------------------

        filename = os.path.basename(
            str(downloaded_path)
        )

        if not filename or filename == "/":

            filename = (
                f"telegram_{file_id}.bin"
            )

        logger.info(
            f"✅ فایل با Telethon دانلود شد | "
            f"name={filename} | "
            f"size={len(content)} bytes"
        )

        return content, filename

    except Exception as e:

        logger.exception(
            f"❌ خطا در download_with_telethon: {e}"
        )

        if client:

            try:
                client.disconnect()
            except Exception:
                pass

        return None, None

    finally:

        # -------------------------------------------------
        # حذف فایل موقت
        # -------------------------------------------------

        if temp_path and os.path.exists(
            temp_path
        ):

            try:

                os.remove(
                    temp_path
                )

                logger.info(
                    "🧹 فایل موقت Telethon حذف شد."
                )

            except Exception as e:

                logger.warning(
                    f"⚠️ حذف فایل موقت ناموفق بود: {e}"
                )


# =========================================================
# MAIN DOWNLOADER
# =========================================================

def download_telegram_file(file_id):
    """
    تابع اصلی دانلود فایل از تلگرام.

    ترتیب:

    1. Telegram Bot API
    2. در صورت شکست Bot API
       Telethon
    """

    if not file_id:

        logger.error(
            "❌ file_id خالی است."
        )

        return None, None

    logger.info(
        f"📥 شروع دانلود فایل تلگرام | "
        f"file_id={str(file_id)[:25]}..."
    )

    # =====================================================
    # مرحله اول
    # Bot API
    # =====================================================

    content, filename = (
        download_with_bot_api(
            file_id
        )
    )

    if content is not None:

        logger.info(
            "✅ فایل با روش Bot API دریافت شد."
        )

        return content, filename

    # =====================================================
    # مرحله دوم
    # Telethon
    # =====================================================

    logger.warning(
        "⚠️ دانلود با Bot API ناموفق بود."
    )

    logger.info(
        "🔄 انتقال دانلود فایل به Telethon..."
    )

    content, filename = (
        download_with_telethon(
            file_id
        )
    )

    if content is not None:

        logger.info(
            "🎯 فایل با Telethon با موفقیت دریافت شد."
        )

        return content, filename

    # =====================================================
    # شکست کامل
    # =====================================================

    logger.error(
        "❌ دانلود فایل هم با Bot API "
        "و هم با Telethon ناموفق بود."
    )

    return None, None
