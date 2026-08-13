import os
import logging
import tempfile
import asyncio
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
# TELETHON ASYNC DOWNLOAD
# =========================================================

async def _telethon_download(
    file_id,
    temp_path,
    session_path,
    api_id,
    api_hash,
    bot_token
):

    client = TelegramClient(
        session_path,
        api_id,
        api_hash
    )

    try:

        logger.info(
            "🔌 اتصال Telethon..."
        )

        await client.start(
            bot_token=bot_token
        )

        logger.info(
            "✅ Telethon با موفقیت متصل شد."
        )

        logger.info(
            f"📥 شروع دانلود با Telethon | "
            f"path={temp_path}"
        )

        result = await client.download_media(
            file_id,
            file=temp_path
        )

        if not result:

            logger.error(
                "❌ Telethon download_media "
                "نتیجه‌ای برنگرداند."
            )

            return False

        if not os.path.exists(temp_path):

            logger.error(
                "❌ فایل خروجی Telethon پیدا نشد."
            )

            return False

        file_size = os.path.getsize(
            temp_path
        )

        if file_size <= 0:

            logger.error(
                "❌ فایل دانلود شده خالی است."
            )

            return False

        logger.info(
            f"✅ Telethon دانلود را کامل کرد | "
            f"size={file_size} bytes"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطا در Telethon: {e}"
        )

        return False

    finally:

        try:

            await client.disconnect()

            logger.info(
                "🔌 Telethon disconnected."
            )

        except Exception:
            pass


# =========================================================
# TELETHON DOWNLOAD
# =========================================================

def download_with_telethon(file_id):

    api_id = get_api_id()
    api_hash = get_api_hash()
    bot_token = get_bot_token()

    if not api_id:
        return None, None

    if not api_hash:
        return None, None

    if not bot_token:
        return None, None

    temp_path = None

    try:

        # -------------------------------------------------
        # Session
        # -------------------------------------------------

        session_path = os.getenv(
            "TELETHON_SESSION",
            "/tmp/telegram_downloader"
        )

        # -------------------------------------------------
        # Temporary file
        # -------------------------------------------------

        with tempfile.NamedTemporaryFile(
            delete=False,
            dir="/tmp",
            suffix=".bin"
        ) as temp_file:

            temp_path = temp_file.name

        logger.info(
            f"📦 فایل موقت ساخته شد | "
            f"path={temp_path}"
        )

        # -------------------------------------------------
        # Event Loop مستقل
        # -------------------------------------------------

        loop = asyncio.new_event_loop()

        try:

            asyncio.set_event_loop(
                loop
            )

            success = loop.run_until_complete(
                _telethon_download(
                    file_id,
                    temp_path,
                    session_path,
                    api_id,
                    api_hash,
                    bot_token
                )
            )

        finally:

            try:

                loop.run_until_complete(
                    asyncio.sleep(0)
                )

            except Exception:
                pass

            asyncio.set_event_loop(
                None
            )

            loop.close()

        if not success:

            return None, None

        # -------------------------------------------------
        # Read file
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
        # Filename
        # -------------------------------------------------

        filename = (
            f"telegram_{file_id}.bin"
        )

        logger.info(
            f"🎯 فایل با Telethon آماده شد | "
            f"name={filename} | "
            f"size={len(content)} bytes"
        )

        return content, filename

    except Exception as e:

        logger.exception(
            f"❌ خطا در download_with_telethon: {e}"
        )

        return None, None

    finally:

        # -------------------------------------------------
        # Cleanup
        # -------------------------------------------------

        if temp_path and os.path.exists(
            temp_path
        ):

            try:

                os.remove(
                    temp_path
                )

                logger.info(
                    "🧹 فایل موقت حذف شد."
                )

            except Exception as e:

                logger.warning(
                    f"⚠️ حذف فایل موقت ناموفق بود: {e}"
                )


# =========================================================
# MAIN DOWNLOADER
# =========================================================

def download_telegram_file(file_id):

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
    # STEP 1
    # BOT API
    # =====================================================

    content, filename = (
        download_with_bot_api(
            file_id
        )
    )

    if content is not None:

        logger.info(
            "✅ دانلود با Bot API موفق بود."
        )

        return content, filename

    # =====================================================
    # STEP 2
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
            "✅ دانلود با Telethon موفق بود."
        )

        return content, filename

    # =====================================================
    # FAILED
    # =====================================================

    logger.error(
        "❌ دانلود فایل با هر دو روش "
        "Bot API و Telethon ناموفق بود."
    )

    return None, None
