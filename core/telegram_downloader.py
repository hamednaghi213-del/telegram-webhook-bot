import os
import logging
import tempfile
import requests

from telethon import TelegramClient


logger = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

TELEGRAM_API_BASE = "https://api.telegram.org"

BOT_API_TIMEOUT = (
    30,
    300
)

GET_FILE_TIMEOUT = (
    30,
    60
)

TELETHON_DOWNLOAD_TIMEOUT = 600

TEMP_DIR = "/tmp"


# =========================================================
# ENV
# =========================================================

def get_bot_token():
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not token:
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."
        )
        return None

    return token


def get_api_id():
    value = os.getenv(
        "TELEGRAM_API_ID"
    )

    if not value:
        logger.error(
            "❌ TELEGRAM_API_ID تنظیم نشده است."
        )
        return None

    try:
        return int(value)

    except (TypeError, ValueError):

        logger.error(
            "❌ TELEGRAM_API_ID باید عدد باشد."
        )

        return None


def get_api_hash():
    value = os.getenv(
        "TELEGRAM_API_HASH"
    )

    if not value:
        logger.error(
            "❌ TELEGRAM_API_HASH تنظیم نشده است."
        )
        return None

    return value


def get_telethon_session():
    return os.getenv(
        "TELETHON_SESSION",
        "/tmp/telegram_downloader"
    )


# =========================================================
# BOT API DOWNLOAD
# =========================================================

def download_with_bot_api(file_id):
    """
    دانلود فایل از Telegram Bot API.

    خروجی موفق:
        (content, filename)

    خروجی ناموفق:
        (None, None)
    """

    bot_token = get_bot_token()

    if not bot_token:
        return None, None

    if not file_id:

        logger.error(
            "❌ file_id برای Bot API خالی است."
        )

        return None, None

    try:

        # -------------------------------------------------
        # getFile
        # -------------------------------------------------

        get_file_url = (
            f"{TELEGRAM_API_BASE}/bot"
            f"{bot_token}/getFile"
        )

        logger.info(
            "📡 Telegram Bot API getFile..."
        )

        response = requests.get(
            get_file_url,
            params={
                "file_id": file_id
            },
            timeout=GET_FILE_TIMEOUT
        )

        logger.info(
            f"📡 getFile response | "
            f"status={response.status_code}"
        )

        if response.status_code != 200:

            logger.warning(
                f"⚠️ Telegram getFile failed | "
                f"status={response.status_code} | "
                f"response={response.text[:1000]}"
            )

            return None, None

        try:

            data = response.json()

        except ValueError:

            logger.error(
                "❌ پاسخ getFile JSON معتبر نیست."
            )

            return None, None

        if not data.get("ok"):

            logger.warning(
                f"⚠️ Telegram getFile returned error | "
                f"{data}"
            )

            return None, None

        result = data.get(
            "result",
            {}
        )

        file_path = result.get(
            "file_path"
        )

        if not file_path:

            logger.warning(
                "⚠️ file_path از Telegram دریافت نشد."
            )

            return None, None

        logger.info(
            f"📁 Telegram file_path دریافت شد | "
            f"path={file_path}"
        )

        # -------------------------------------------------
        # Download
        # -------------------------------------------------

        download_url = (
            f"{TELEGRAM_API_BASE}/file/bot"
            f"{bot_token}/{file_path}"
        )

        logger.info(
            "📥 شروع دانلود فایل با Bot API..."
        )

        file_response = requests.get(
            download_url,
            timeout=BOT_API_TIMEOUT
        )

        logger.info(
            f"📡 Telegram file response | "
            f"status={file_response.status_code}"
        )

        if file_response.status_code != 200:

            logger.warning(
                f"⚠️ Telegram file download failed | "
                f"status={file_response.status_code} | "
                f"response={file_response.text[:1000]}"
            )

            return None, None

        content = file_response.content

        if not content:

            logger.warning(
                "⚠️ فایل دریافت‌شده خالی است."
            )

            return None, None

        filename = os.path.basename(
            file_path
        )

        if not filename:

            filename = (
                f"telegram_{file_id}.bin"
            )

        logger.info(
            f"✅ فایل با Bot API دانلود شد | "
            f"name={filename} | "
            f"size={len(content)} bytes"
        )

        return content, filename

    except requests.exceptions.Timeout as e:

        logger.warning(
            f"⏰ Timeout در Bot API | {e}"
        )

        return None, None

    except requests.exceptions.RequestException as e:

        logger.warning(
            f"⚠️ RequestException در Bot API | {e}"
        )

        return None, None

    except Exception as e:

        logger.exception(
            f"❌ Exception در download_with_bot_api: {e}"
        )

        return None, None


# =========================================================
# TELETHON DOWNLOAD
# =========================================================

def download_with_telethon(file_id):
    """
    دانلود فایل با Telethon.

    در صورت شکست Bot API استفاده می‌شود.
    """

    api_id = get_api_id()
    api_hash = get_api_hash()
    bot_token = get_bot_token()

    if not api_id:
        return None, None

    if not api_hash:
        return None, None

    if not bot_token:
        return None, None

    if not file_id:

        logger.error(
            "❌ file_id برای Telethon خالی است."
        )

        return None, None

    client = None
    temp_path = None

    try:

        session_path = get_telethon_session()

        logger.info(
            "🚀 شروع اتصال Telethon..."
        )

        client = TelegramClient(
            session_path,
            api_id,
            api_hash
        )

        # -------------------------------------------------
        # Connect
        # -------------------------------------------------

        client.start(
            bot_token=bot_token
        )

        logger.info(
            "✅ Telethon با موفقیت متصل شد."
        )

        # -------------------------------------------------
        # Temporary file
        # -------------------------------------------------

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            dir=TEMP_DIR,
            prefix="telegram_"
        )

        temp_path = temp_file.name

        temp_file.close()

        logger.info(
            f"📥 مسیر موقت Telethon ساخته شد | "
            f"path={temp_path}"
        )

        # -------------------------------------------------
        # Download
        # -------------------------------------------------

        logger.info(
            "📥 شروع دانلود فایل با Telethon..."
        )

        downloaded_path = (
            client.loop.run_until_complete(
                client.download_media(
                    file_id,
                    file=temp_path
                )
            )
        )

        logger.info(
            f"📡 Telethon download result | "
            f"path={downloaded_path}"
        )

        if not downloaded_path:

            logger.error(
                "❌ Telethon فایل را دانلود نکرد."
            )

            return None, None

        # -------------------------------------------------
        # Verify
        # -------------------------------------------------

        actual_path = str(
            downloaded_path
        )

        if not os.path.exists(
            actual_path
        ):

            if os.path.exists(
                temp_path
            ):

                actual_path = temp_path

            else:

                logger.error(
                    "❌ فایل دانلودشده روی دیسک پیدا نشد."
                )

                return None, None

        file_size = os.path.getsize(
            actual_path
        )

        if file_size <= 0:

            logger.error(
                "❌ فایل دانلودشده خالی است."
            )

            return None, None

        # -------------------------------------------------
        # Read file
        # -------------------------------------------------

        with open(
            actual_path,
            "rb"
        ) as file:

            content = file.read()

        if not content:

            logger.error(
                "❌ محتوای فایل Telethon خالی است."
            )

            return None, None

        # -------------------------------------------------
        # Filename
        # -------------------------------------------------

        filename = os.path.basename(
            actual_path
        )

        if not filename:

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
            f"❌ Exception در download_with_telethon: {e}"
        )

        return None, None

    finally:

        # -------------------------------------------------
        # Disconnect
        # -------------------------------------------------

        if client:

            try:

                client.disconnect()

                logger.info(
                    "🔌 Telethon disconnected."
                )

            except Exception as e:

                logger.warning(
                    f"⚠️ خطا در قطع Telethon | {e}"
                )

        # -------------------------------------------------
        # Cleanup
        # -------------------------------------------------

        if temp_path:

            try:

                if os.path.exists(
                    temp_path
                ):

                    os.remove(
                        temp_path
                    )

                    logger.info(
                        "🧹 فایل موقت Telethon حذف شد."
                    )

            except Exception as e:

                logger.warning(
                    f"⚠️ حذف فایل موقت ناموفق بود | {e}"
                )


# =========================================================
# MAIN DOWNLOADER
# =========================================================

def download_telegram_file(file_id):
    """
    تابع اصلی دانلود فایل تلگرام.

    ترتیب:

    1. Bot API
    2. Telethon

    خروجی موفق:

        content, filename

    شکست کامل:

        None, None
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
    # METHOD 1
    # BOT API
    # =====================================================

    content, filename = (
        download_with_bot_api(
            file_id
        )
    )

    if content is not None:

        logger.info(
            "🎯 دانلود فایل با Bot API موفق بود."
        )

        return content, filename

    # =====================================================
    # METHOD 2
    # TELETHON
    # =====================================================

    logger.warning(
        "⚠️ Bot API نتوانست فایل را دانلود کند."
    )

    logger.info(
        "🔄 انتقال دانلود به Telethon..."
    )

    content, filename = (
        download_with_telethon(
            file_id
        )
    )

    if content is not None:

        logger.info(
            "🎯 دانلود فایل با Telethon موفق بود."
        )

        return content, filename

    # =====================================================
    # COMPLETE FAILURE
    # =====================================================

    logger.error(
        "❌ دانلود فایل تلگرام با هر دو روش "
        "Bot API و Telethon ناموفق بود."
    )

    return None, None
