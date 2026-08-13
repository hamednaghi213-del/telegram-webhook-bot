import logging
import requests

logger = logging.getLogger(__name__)


# =========================================================
# SEND SINGLE MEDIA TO TELEGRAM CHANNEL
# =========================================================

def send_media_to_channel(
    api_url,
    channel_id,
    file_id,
    media_type,
    caption=""
):
    """
    ارسال یک رسانه به کانال تلگرام
    """

    try:

        if not file_id:
            logger.error(
                "❌ file_id برای ارسال رسانه خالی است."
            )
            return False

        # -------------------------------------------------
        # انتخاب Endpoint
        # -------------------------------------------------

        if media_type == "photo":

            endpoint = f"{api_url}/sendPhoto"

        elif media_type == "video":

            endpoint = f"{api_url}/sendVideo"

        elif media_type == "document":

            endpoint = f"{api_url}/sendDocument"

        elif media_type == "voice":

            endpoint = f"{api_url}/sendVoice"

        elif media_type == "audio":

            endpoint = f"{api_url}/sendAudio"

        else:

            logger.error(
                f"❌ نوع رسانه پشتیبانی نمی‌شود: "
                f"{media_type}"
            )

            return False

        # -------------------------------------------------
        # Payload
        # -------------------------------------------------

        payload = {
            "chat_id": channel_id,
            media_type: file_id
        }

        if caption:
            payload["caption"] = caption

        logger.info(
            f"📤 ارسال {media_type} به کانال | "
            f"channel={channel_id}"
        )

        # -------------------------------------------------
        # Request
        # -------------------------------------------------

        response = requests.post(
            endpoint,
            json=payload,
            timeout=60
        )

        # -------------------------------------------------
        # بررسی پاسخ
        # -------------------------------------------------

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram media error | "
                f"type={media_type} | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return False

        try:

            result = response.json()

        except Exception:

            logger.error(
                "❌ پاسخ Telegram JSON معتبر نیست."
            )

            return False

        if not result.get("ok"):

            logger.error(
                f"❌ Telegram API خطا داد | "
                f"{result}"
            )

            return False

        logger.info(
            f"✅ {media_type} با موفقیت "
            f"در کانال منتشر شد."
        )

        return True

    except requests.Timeout:

        logger.error(
            f"❌ Timeout در ارسال {media_type} "
            f"به کانال."
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_media_to_channel: {e}"
        )

        return False


# =========================================================
# SEND MEDIA GROUP TO TELEGRAM
# =========================================================

def send_media_group(
    api_url,
    channel_id,
    files,
    caption=""
):
    """
    ارسال آلبوم واقعی به کانال تلگرام.

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

    try:

        if not files:

            logger.warning(
                "⚠️ لیست آلبوم خالی است."
            )

            return False

        logger.info(
            f"📦 شروع ارسال آلبوم | "
            f"تعداد رسانه: {len(files)}"
        )

        media_group = []

        # -------------------------------------------------
        # Telegram Media Group حداکثر ۱۰ رسانه
        # -------------------------------------------------

        files = files[:10]

        for index, file in enumerate(files):

            media_type = file.get(
                "type"
            )

            file_id = file.get(
                "file_id"
            )

            if not file_id:

                logger.warning(
                    f"⚠️ file_id رسانه "
                    f"{index + 1} خالی است."
                )

                continue

            # ---------------------------------------------
            # Photo
            # ---------------------------------------------

            if media_type == "photo":

                media = {
                    "type": "photo",
                    "media": file_id
                }

            # ---------------------------------------------
            # Video
            # ---------------------------------------------

            elif media_type == "video":

                media = {
                    "type": "video",
                    "media": file_id
                }

            # ---------------------------------------------
            # Unsupported
            # ---------------------------------------------

            else:

                logger.warning(
                    f"⚠️ رسانه {index + 1} "
                    f"با نوع {media_type} "
                    f"در آلبوم پشتیبانی نمی‌شود."
                )

                continue

            # ---------------------------------------------
            # Caption فقط روی اولین رسانه
            # ---------------------------------------------

            if (
                len(media_group) == 0
                and caption
            ):

                media["caption"] = caption

            media_group.append(
                media
            )

        # -------------------------------------------------
        # بررسی نتیجه
        # -------------------------------------------------

        if not media_group:

            logger.error(
                "❌ هیچ رسانه قابل ارسالی "
                "در آلبوم وجود ندارد."
            )

            return False

        # -------------------------------------------------
        # ارسال به Telegram
        # -------------------------------------------------

        endpoint = (
            f"{api_url}/sendMediaGroup"
        )

        payload = {
            "chat_id": channel_id,
            "media": media_group
        }

        logger.info(
            f"📤 ارسال Media Group به تلگرام | "
            f"count={len(media_group)}"
        )

        response = requests.post(
            endpoint,
            json=payload,
            timeout=90
        )

        # -------------------------------------------------
        # بررسی HTTP
        # -------------------------------------------------

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram Media Group HTTP error | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return False

        # -------------------------------------------------
        # بررسی JSON
        # -------------------------------------------------

        try:

            result = response.json()

        except Exception:

            logger.error(
                "❌ پاسخ Media Group "
                "قابل تبدیل به JSON نیست."
            )

            return False

        if not result.get("ok"):

            logger.error(
                f"❌ Telegram Media Group API error | "
                f"{result}"
            )

            return False

        logger.info(
            f"✅ آلبوم با موفقیت در کانال منتشر شد | "
            f"count={len(media_group)}"
        )

        return True

    except requests.Timeout:

        logger.error(
            "❌ Timeout در ارسال آلبوم."
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception در "
            f"send_media_group: {e}"
        )

        return False
