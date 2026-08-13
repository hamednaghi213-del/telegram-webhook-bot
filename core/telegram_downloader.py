import os
import logging
import tempfile
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def get_bot_token():
    """
    دریافت توکن ربات تلگرام از Environment
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."
        )
        return None

    return token


def download_with_bot_api(file_id):
    """
    روش اول:
    دانلود فایل با Telegram Bot API

    این روش برای فایل‌های معمولی استفاده می‌شود.
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


def download_telegram_file(file_id):
    """
    تابع اصلی دانلود فایل از تلگرام.

    فعلاً ابتدا Bot API را امتحان می‌کند.

    در مرحله بعدی Telethon را به همین تابع
    اضافه می‌کنیم تا فایل‌های بزرگ نیز
    قابل دانلود باشند.
    """

    if not file_id:

        logger.error(
            "❌ file_id خالی است."
        )

        return None, None

    logger.info(
        f"📥 شروع دانلود فایل تلگرام | "
        f"file_id={str(file_id)[:20]}..."
    )

    content, filename = (
        download_with_bot_api(
            file_id
        )
    )

    if content is not None:

        return content, filename

    logger.warning(
        "⚠️ دانلود با Bot API ناموفق بود. "
        "در مرحله بعدی Telethon استفاده خواهد شد."
    )

    return None, None
