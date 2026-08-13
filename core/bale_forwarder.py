import os
import json
import logging
import requests

from core.branding_manager import get_branding


logger = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

BALE_API_BASE = "https://tapi.bale.ai/bot"


# =========================================================
# MAIN ENTRY
# =========================================================

def send_to_bale_for_user(
    user_id,
    text,
    file_id=None,
    media_type=None
):
    """
    ارسال متن یا رسانه به کانال بله کاربر
    """

    logger.info(
        f"📦 BALE FORWARD | "
        f"user={user_id} | "
        f"type={media_type} | "
        f"file_id={'YES' if file_id else 'NO'}"
    )

    # -----------------------------------------------------
    # فعال بودن بله
    # -----------------------------------------------------

    if os.getenv(
        "ENABLE_BALE",
        "false"
    ).lower() != "true":

        logger.info(
            "ℹ️ ارسال به بله غیرفعال است."
        )

        return True

    # -----------------------------------------------------
    # دریافت Branding
    # -----------------------------------------------------

    try:

        branding = get_branding(
            user_id
        )

    except Exception as e:

        logger.exception(
            f"❌ خطا در دریافت branding "
            f"برای user={user_id}: {e}"
        )

        return False

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
            f"⚠️ تنظیمات بله برای "
            f"user={user_id} کامل نیست."
        )

        return False

    # -----------------------------------------------------
    # متن
    # -----------------------------------------------------

    if not file_id or not media_type:

        return send_text_to_bale(
            bale_channel,
            bale_token,
            text or ""
        )

    # -----------------------------------------------------
    # عکس
    # -----------------------------------------------------

    if media_type == "photo":

        return send_photo_to_bale(
            bale_channel,
            bale_token,
            text or "",
            file_id
        )

    # -----------------------------------------------------
    # ویدئو
    # -----------------------------------------------------

    if media_type == "video":

        return send_video_to_bale(
            bale_channel,
            bale_token,
            text or "",
            file_id
        )

    # -----------------------------------------------------
    # فایل
    # -----------------------------------------------------

    return send_document_to_bale(
        bale_channel,
        bale_token,
        text or "",
        file_id
    )


# =========================================================
# SEND TEXT
# =========================================================

def send_text_to_bale(
    channel,
    token,
    text
):
    """
    ارسال پیام متنی به بله
    """

    try:

        url = (
            f"{BALE_API_BASE}"
            f"{token}/sendMessage"
        )

        payload = {
            "chat_id": channel,
            "text": text
        }

        logger.info(
            "📤 ارسال متن به بله..."
        )

        response = requests.post(
            url,
            json=payload,
            timeout=120
        )

        if response.status_code == 200:

            logger.info(
                "✅ متن با موفقیت "
                "به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال متن به بله | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_text_to_bale: {e}"
        )

        return False


# =========================================================
# DOWNLOAD FILE FROM TELEGRAM
# =========================================================

def download_file_from_telegram(
    file_id
):
    """
    دریافت file_path از Telegram
    و سپس دانلود فایل
    """

    bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not bot_token:

        logger.error(
            "❌ TELEGRAM_BOT_TOKEN "
            "تنظیم نشده است."
        )

        return None, None

    try:

        # -------------------------------------------------
        # getFile
        # -------------------------------------------------

        get_file_url = (
            "https://api.telegram.org/"
            f"bot{bot_token}/getFile"
        )

        logger.info(
            f"📥 دریافت اطلاعات فایل تلگرام | "
            f"file_id={file_id[:20]}..."
        )

        response = requests.get(
            get_file_url,
            params={
                "file_id": file_id
            },
            timeout=120
        )

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram getFile HTTP error | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return None, None

        try:

            data = response.json()

        except Exception:

            logger.error(
                "❌ پاسخ Telegram JSON معتبر نیست."
            )

            return None, None

        if not data.get("ok"):

            logger.error(
                f"❌ Telegram getFile failed | "
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

            logger.error(
                "❌ file_path از تلگرام دریافت نشد."
            )

            return None, None

        # -------------------------------------------------
        # Download
        # -------------------------------------------------

        download_url = (
            "https://api.telegram.org/"
            f"file/bot{bot_token}/"
            f"{file_path}"
        )

        logger.info(
            f"📥 دانلود فایل از تلگرام | "
            f"path={file_path}"
        )

        file_response = requests.get(
            download_url,
            timeout=300
        )

        if file_response.status_code != 200:

            logger.error(
                f"❌ خطا در دانلود فایل تلگرام | "
                f"status={file_response.status_code}"
            )

            return None, None

        file_content = (
            file_response.content
        )

        if not file_content:

            logger.error(
                "❌ فایل دانلود شده خالی است."
            )

            return None, None

        filename = os.path.basename(
            file_path
        )

        logger.info(
            f"✅ فایل دانلود شد | "
            f"name={filename} | "
            f"size={len(file_content)} bytes"
        )

        return (
            file_content,
            filename
        )

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"download_file_from_telegram: {e}"
        )

        return None, None


# =========================================================
# SEND PHOTO
# =========================================================

def send_photo_to_bale(
    channel,
    token,
    caption,
    file_id
):
    """
    دانلود عکس از تلگرام
    و آپلود آن به بله
    """

    file_content, filename = (
        download_file_from_telegram(
            file_id
        )
    )

    if file_content is None:

        return False

    try:

        url = (
            f"{BALE_API_BASE}"
            f"{token}/sendPhoto"
        )

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

        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=300
        )

        if response.status_code == 200:

            logger.info(
                "✅ عکس با موفقیت "
                "به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال عکس به بله | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_photo_to_bale: {e}"
        )

        return False


# =========================================================
# SEND VIDEO
# =========================================================

def send_video_to_bale(
    channel,
    token,
    caption,
    file_id
):
    """
    دانلود ویدئو از تلگرام
    و آپلود آن به بله
    """

    file_content, filename = (
        download_file_from_telegram(
            file_id
        )
    )

    if file_content is None:

        return False

    try:

        url = (
            f"{BALE_API_BASE}"
            f"{token}/sendVideo"
        )

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

        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=300
        )

        if response.status_code == 200:

            logger.info(
                "✅ ویدئو با موفقیت "
                "به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال ویدئو به بله | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_video_to_bale: {e}"
        )

        return False


# =========================================================
# SEND DOCUMENT
# =========================================================

def send_document_to_bale(
    channel,
    token,
    caption,
    file_id
):
    """
    ارسال فایل به بله
    """

    file_content, filename = (
        download_file_from_telegram(
            file_id
        )
    )

    if file_content is None:

        return False

    try:

        url = (
            f"{BALE_API_BASE}"
            f"{token}/sendDocument"
        )

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

        logger.info(
            f"📤 ارسال فایل به بله | "
            f"name={filename} | "
            f"size={len(file_content)} bytes"
        )

        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=300
        )

        if response.status_code == 200:

            logger.info(
                "✅ فایل با موفقیت "
                "به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال فایل به بله | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_document_to_bale: {e}"
        )

        return False


# =========================================================
# SEND MEDIA GROUP TO BALE
# =========================================================

def send_media_group_to_bale(
    user_id,
    files,
    caption=""
):
    """
    ارسال آلبوم واقعی به بله

    files:
    [
        {
            "type": "photo",
            "file_id": "..."
        },
        {
            "type": "video",
            "file_id": "..."
        }
    ]
    """

    logger.info(
        f"📦 BALE MEDIA GROUP | "
        f"user={user_id} | "
        f"count={len(files) if files else 0}"
    )

    # -----------------------------------------------------
    # ENABLE_BALE
    # -----------------------------------------------------

    if os.getenv(
        "ENABLE_BALE",
        "false"
    ).lower() != "true":

        logger.info(
            "ℹ️ ارسال Media Group به بله "
            "غیرفعال است."
        )

        return True

    if not files:

        logger.warning(
            "⚠️ Media Group خالی است."
        )

        return False

    # -----------------------------------------------------
    # Branding
    # -----------------------------------------------------

    try:

        branding = get_branding(
            user_id
        )

    except Exception as e:

        logger.exception(
            f"❌ خطا در دریافت branding "
            f"برای Media Group: {e}"
        )

        return False

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
            f"⚠️ تنظیمات بله برای "
            f"user={user_id} موجود نیست."
        )

        return False

    # -----------------------------------------------------
    # حداکثر ۱۰ رسانه
    # -----------------------------------------------------

    files = files[:10]

    media_items = []
    upload_files = {}

    # -----------------------------------------------------
    # دانلود همه رسانه‌ها
    # -----------------------------------------------------

    for index, item in enumerate(files):

        media_type = item.get(
            "type"
        )

        file_id = item.get(
            "file_id"
        )

        if not file_id:

            logger.warning(
                f"⚠️ file_id رسانه "
                f"{index + 1} خالی است."
            )

            continue

        if media_type not in (
            "photo",
            "video"
        ):

            logger.warning(
                f"⚠️ نوع رسانه "
                f"{media_type} برای Media Group "
                f"پشتیبانی نمی‌شود."
            )

            continue

        # ---------------------------------------------
        # دانلود از تلگرام
        # ---------------------------------------------

        file_content, filename = (
            download_file_from_telegram(
                file_id
            )
        )

        if file_content is None:

            logger.error(
                f"❌ دانلود رسانه "
                f"{index + 1} ناموفق بود."
            )

            continue

        # ---------------------------------------------
        # نام فیلد upload
        # ---------------------------------------------

        field_name = (
            f"media{len(media_items)}"
        )

        # ---------------------------------------------
        # ساخت Media Object
        # ---------------------------------------------

        media_object = {
            "type": media_type,
            "media": (
                f"attach://{field_name}"
            )
        }

        # ---------------------------------------------
        # Caption فقط برای اولین رسانه
        # ---------------------------------------------

        if (
            len(media_items) == 0
            and caption
        ):

            media_object[
                "caption"
            ] = caption

        media_items.append(
            media_object
        )

        upload_files[
            field_name
        ] = (
            filename,
            file_content
        )

        logger.info(
            f"📦 رسانه {index + 1} "
            f"آماده ارسال به بله | "
            f"type={media_type} | "
            f"name={filename} | "
            f"size={len(file_content)} bytes"
        )

    # -----------------------------------------------------
    # هیچ رسانه‌ای باقی نمانده
    # -----------------------------------------------------

    if not media_items:

        logger.error(
            "❌ هیچ رسانه‌ای برای "
            "ارسال به بله باقی نماند."
        )

        return False

    # -----------------------------------------------------
    # اگر فقط یک رسانه است
    # -----------------------------------------------------

    if len(media_items) == 1:

        media = media_items[0]

        field_name = (
            media["media"]
            .replace(
                "attach://",
                ""
            )
        )

        uploaded = upload_files.get(
            field_name
        )

        if not uploaded:

            return False

        filename, content = uploaded

        if media["type"] == "photo":

            return send_photo_to_bale(
                bale_channel,
                bale_token,
                caption,
                files[0]["file_id"]
            )

        if media["type"] == "video":

            return send_video_to_bale(
                bale_channel,
                bale_token,
                caption,
                files[0]["file_id"]
            )

        return False

    # -----------------------------------------------------
    # Media Group
    # -----------------------------------------------------

    try:

        url = (
            f"{BALE_API_BASE}"
            f"{bale_token}/sendMediaGroup"
        )

        # Bale API انتظار دارد media
        # به صورت JSON string ارسال شود
        data = {
            "chat_id": bale_channel,
            "media": json.dumps(
                media_items,
                ensure_ascii=False
            )
        }

        logger.info(
            f"📤 ارسال Media Group به بله | "
            f"count={len(media_items)}"
        )

        response = requests.post(
            url,
            data=data,
            files=upload_files,
            timeout=300
        )

        if response.status_code == 200:

            logger.info(
                f"🎯 Media Group با "
                f"{len(media_items)} رسانه "
                f"با موفقیت به بله ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال Media Group به بله | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_media_group_to_bale: {e}"
        )

        return False
