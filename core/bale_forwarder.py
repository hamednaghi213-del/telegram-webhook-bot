import os
import requests
import logging
from core.branding_manager import get_branding

logger = logging.getLogger(__name__)


def send_to_bale_for_user(
    user_id,
    text,
    file_id=None,
    media_type=None
):
    """
    ارسال متن یا رسانه از تلگرام به بله
    """

    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        logger.info("ℹ️ ENABLE_BALE فعال نیست.")
        return True

    branding = get_branding(user_id)

    bale_channel = branding.get(
        "bale_channel",
        ""
    )

    bale_token = branding.get(
        "bale_token",
        ""
    )

    if not bale_channel or not bale_token:

        logger.warning(
            f"⚠️ بله برای کاربر {user_id} تنظیم نشده است."
        )

        return False

    logger.info(
        f"📦 BALE FORWARD | "
        f"user={user_id} | "
        f"type={media_type} | "
        f"has_file={bool(file_id)}"
    )

    # ==========================================
    # TEXT
    # ==========================================

    if not file_id or not media_type:

        return send_text_to_bale(
            bale_channel,
            bale_token,
            text or ""
        )

    # ==========================================
    # PHOTO
    # ==========================================

    if media_type == "photo":

        return send_photo_to_bale(
            bale_channel,
            bale_token,
            text or "",
            file_id
        )

    # ==========================================
    # VIDEO
    # ==========================================

    if media_type == "video":

        return send_video_to_bale(
            bale_channel,
            bale_token,
            text or "",
            file_id
        )

    # ==========================================
    # OTHER FILES
    # ==========================================

    return send_document_to_bale(
        bale_channel,
        bale_token,
        text or "",
        file_id
    )


# =========================================================
# TEXT
# =========================================================

def send_text_to_bale(
    channel,
    token,
    text
):

    try:

        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendMessage",
            json={
                "chat_id": channel,
                "text": text
            },
            timeout=120
        )

        if resp.status_code == 200:

            logger.info(
                "✅ متن به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال متن به بله | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در send_text_to_bale: {e}"
        )

        return False


# =========================================================
# DOWNLOAD TELEGRAM FILE
# =========================================================

def download_file_from_telegram(
    file_id
):

    bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not bot_token:

        logger.error(
            "❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."
        )

        return None, None

    try:

        # -----------------------------------------
        # getFile
        # -----------------------------------------

        resp = requests.get(
            "https://api.telegram.org/"
            f"bot{bot_token}/getFile",
            params={
                "file_id": file_id
            },
            timeout=120
        )

        if resp.status_code != 200:

            logger.error(
                f"❌ getFile failed | "
                f"status={resp.status_code} | "
                f"response={resp.text}"
            )

            return None, None

        file_info = resp.json()

        if not file_info.get("ok"):

            logger.error(
                f"❌ Telegram getFile error: "
                f"{file_info}"
            )

            return None, None

        file_path = file_info["result"]["file_path"]

        file_url = (
            "https://api.telegram.org/"
            f"file/bot{bot_token}/{file_path}"
        )

        logger.info(
            f"📥 دانلود فایل تلگرام: "
            f"{file_path}"
        )

        # -----------------------------------------
        # Download
        # -----------------------------------------

        file_resp = requests.get(
            file_url,
            timeout=180
        )

        if file_resp.status_code != 200:

            logger.error(
                f"❌ دانلود فایل شکست خورد | "
                f"status={file_resp.status_code}"
            )

            return None, None

        logger.info(
            f"✅ فایل دانلود شد | "
            f"size={len(file_resp.content)} bytes"
        )

        return (
            file_resp.content,
            os.path.basename(file_path)
        )

    except Exception as e:

        logger.exception(
            f"❌ خطا در دانلود فایل تلگرام: {e}"
        )

        return None, None


# =========================================================
# PHOTO
# =========================================================

def send_photo_to_bale(
    channel,
    token,
    caption,
    file_id
):

    file_content, filename = (
        download_file_from_telegram(file_id)
    )

    if file_content is None:

        return False

    try:

        files = {
            "photo": (
                filename,
                file_content
            )
        }

        data = {
            "chat_id": channel
        }

        if caption:

            data["caption"] = caption

        logger.info(
            f"📤 ارسال عکس به بله | "
            f"size={len(file_content)} bytes"
        )

        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendPhoto",
            data=data,
            files=files,
            timeout=180
        )

        if resp.status_code == 200:

            logger.info(
                "✅ عکس با موفقیت به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ Bale sendPhoto failed | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در send_photo_to_bale: {e}"
        )

        return False


# =========================================================
# VIDEO
# =========================================================

def send_video_to_bale(
    channel,
    token,
    caption,
    file_id
):

    file_content, filename = (
        download_file_from_telegram(file_id)
    )

    if file_content is None:

        return False

    try:

        files = {
            "video": (
                filename,
                file_content
            )
        }

        data = {
            "chat_id": channel
        }

        if caption:

            data["caption"] = caption

        logger.info(
            f"📤 ارسال ویدئو به بله | "
            f"size={len(file_content)} bytes"
        )

        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendVideo",
            data=data,
            files=files,
            timeout=300
        )

        if resp.status_code == 200:

            logger.info(
                "✅ ویدئو با موفقیت به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ Bale sendVideo failed | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در send_video_to_bale: {e}"
        )

        return False


# =========================================================
# DOCUMENT
# =========================================================

def send_document_to_bale(
    channel,
    token,
    caption,
    file_id
):

    file_content, filename = (
        download_file_from_telegram(file_id)
    )

    if file_content is None:

        return False

    try:

        files = {
            "document": (
                filename,
                file_content
            )
        }

        data = {
            "chat_id": channel
        }

        if caption:

            data["caption"] = caption

        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendDocument",
            data=data,
            files=files,
            timeout=300
        )

        if resp.status_code == 200:

            logger.info(
                "✅ فایل به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ Bale sendDocument failed | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در send_document_to_bale: {e}"
        )

        return False
