import logging
import uuid
import requests
import os
import traceback

from flask import request

from core.database import get_tenant
from core.formatter import format_news
from core.media_sender import send_media_to_channel
from core.branding_manager import get_branding
from core.media_handler import (
    is_media_group,
    handle_media_group_message
)
from core.bale_forwarder import send_to_bale_for_user
from core.command_handler import (
    is_command,
    handle_command
)


logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL = (
    f"https://api.telegram.org/"
    f"bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
)

CHANNEL_ID = "@Donya24News"


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    api_url,
    channel_id,
    secret_token
):

    global API_URL
    global CHANNEL_ID

    API_URL = api_url
    CHANNEL_ID = channel_id

    logger.info(
        "✅ Webhook Handler initialized"
    )


# =========================================================
# SEND MESSAGE TO USER
# =========================================================

def send_message(
    chat_id,
    text
):

    try:

        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=30
        )

        if resp.status_code != 200:

            logger.error(
                f"❌ send_message failed | "
                f"status={resp.status_code} | "
                f"response={resp.text}"
            )

            return False

        return True

    except Exception as e:

        logger.exception(
            f"❌ send_message error: {e}"
        )

        return False


# =========================================================
# SPLIT LONG MESSAGE
# =========================================================

def split_long_message(
    text,
    max_len=4096
):

    if not text:

        return [""]

    if len(text) <= max_len:

        return [text]

    parts = []

    lines = text.split("\n")

    current_part = ""

    for line in lines:

        # -----------------------------------------
        # خط معمولی
        # -----------------------------------------

        if (
            len(current_part)
            + len(line)
            + 1
            <= max_len
        ):

            current_part += (
                line + "\n"
            )

        else:

            if current_part:

                parts.append(
                    current_part.strip()
                )

            # -------------------------------------
            # اگر خود خط خیلی بزرگ است
            # -------------------------------------

            if len(line) > max_len:

                for i in range(
                    0,
                    len(line),
                    max_len
                ):

                    parts.append(
                        line[
                            i:i + max_len
                        ]
                    )

                current_part = ""

            else:

                current_part = (
                    line + "\n"
                )

    if current_part:

        parts.append(
            current_part.strip()
        )

    return parts


# =========================================================
# SEND TEXT TO MAIN TELEGRAM CHANNEL
# =========================================================

def send_to_channel(
    text
):

    try:

        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": CHANNEL_ID,
                "text": text
            },
            timeout=30
        )

        if resp.status_code == 200:

            logger.info(
                "✅ متن به کانال اصلی ارسال شد."
            )

            return True

        logger.error(
            f"❌ ارسال متن به کانال شکست خورد | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ send_to_channel error: {e}"
        )

        return False


# =========================================================
# SEND LONG TEXT TO TELEGRAM + BALE
# =========================================================

def send_long_to_channel(
    text,
    chat_id
):

    try:

        branding = get_branding(
            chat_id
        )

        hashtag = branding.get(
            "hashtag",
            ""
        )

        channel_tag = branding.get(
            "channel_tag",
            ""
        )

        # -----------------------------------------
        # Branding
        # -----------------------------------------

        if hashtag:

            text += (
                f"\n\n{hashtag}"
            )

        if channel_tag:

            text += (
                f"\n{channel_tag}"
            )

        # -----------------------------------------
        # Split
        # -----------------------------------------

        parts = split_long_message(
            text
        )

        telegram_success = True

        for part in parts:

            if not send_to_channel(
                part
            ):

                telegram_success = False

                break

        # -----------------------------------------
        # Telegram موفق
        # -----------------------------------------

        if telegram_success:

            bale_success = (
                send_to_bale_for_user(
                    chat_id,
                    text,
                    None,
                    None
                )
            )

            if bale_success:

                logger.info(
                    "✅ متن به بله ارسال شد."
                )

            else:

                logger.error(
                    "❌ ارسال متن به بله ناموفق بود."
                )

        return telegram_success

    except Exception as e:

        logger.exception(
            f"❌ send_long_to_channel error: {e}"
        )

        return False


# =========================================================
# GET MESSAGE TEXT
# =========================================================

def get_message_text(
    msg
):

    # caption برای عکس / ویدئو / فایل
    if msg.get("caption"):

        return msg["caption"]

    # text برای پیام معمولی
    if msg.get("text"):

        return msg["text"]

    return ""


# =========================================================
# GET MEDIA FROM MESSAGE
# =========================================================

def get_media_from_message(
    msg
):

    result = {
        "type": None,
        "file_id": None,
        "caption": ""
    }

    # =====================================================
    # VIDEO
    # =====================================================

    if "video" in msg:

        video = msg["video"]

        result["type"] = "video"

        result["file_id"] = (
            video.get("file_id")
        )

        result["caption"] = (
            msg.get("caption", "")
        )

        return result

    # =====================================================
    # PHOTO
    # =====================================================

    if "photo" in msg:

        photos = msg["photo"]

        if photos:

            # آخرین مورد = بالاترین کیفیت
            result["type"] = "photo"

            result["file_id"] = (
                photos[-1].get(
                    "file_id"
                )
            )

            result["caption"] = (
                msg.get(
                    "caption",
                    ""
                )
            )

        return result

    # =====================================================
    # DOCUMENT
    # =====================================================

    if "document" in msg:

        document = msg["document"]

        result["type"] = "document"

        result["file_id"] = (
            document.get("file_id")
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
        )

        return result

    # =====================================================
    # AUDIO
    # =====================================================

    if "audio" in msg:

        audio = msg["audio"]

        result["type"] = "audio"

        result["file_id"] = (
            audio.get("file_id")
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
        )

        return result

    # =====================================================
    # VOICE
    # =====================================================

    if "voice" in msg:

        voice = msg["voice"]

        result["type"] = "voice"

        result["file_id"] = (
            voice.get("file_id")
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
        )

        return result

    return result


# =========================================================
# LOG MEDIA
# =========================================================

def log_media_info(
    req_id,
    media_info
):

    file_id = media_info.get(
        "file_id"
    )

    logger.info(
        f"[{req_id}] 📦 MEDIA DETECTED | "
        f"type={media_info.get('type')} | "
        f"has_file_id={bool(file_id)} | "
        f"file_id="
        f"{str(file_id)[:30] if file_id else None}"
    )


# =========================================================
# WEBHOOK HANDLER
# =========================================================

def handle_webhook():

    req_id = str(
        uuid.uuid4()
    )[:8]

    logger.info(
        f"[{req_id}] 📥 دریافت درخواست Webhook"
    )

    try:

        # =================================================
        # GET JSON
        # =================================================

        data = request.get_json(
            silent=True
        )

        if not data:

            logger.warning(
                f"[{req_id}] ⚠️ Webhook بدون JSON"
            )

            return {
                "ok": True
            }

        # =================================================
        # CHECK MESSAGE
        # =================================================

        if "message" not in data:

            logger.info(
                f"[{req_id}] ℹ️ Update فاقد message است."
            )

            return {
                "ok": True
            }

        msg = data["message"]

        # =================================================
        # CHAT ID
        # =================================================

        chat = msg.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        if not chat_id:

            logger.error(
                f"[{req_id}] ❌ chat_id پیدا نشد."
            )

            return {
                "ok": True
            }

        # =================================================
        # TEXT / CAPTION
        # =================================================

        text = get_message_text(
            msg
        )

        logger.info(
            f"[{req_id}] 📩 پیام از "
            f"chat_id={chat_id}"
        )

        # =================================================
        # COMMAND
        # =================================================

        if text and is_command(
            text
        ):

            logger.info(
                f"[{req_id}] ⚙️ Command: {text}"
            )

            handle_command(
                text,
                chat_id
            )

            return {
                "ok": True
            }

        # =================================================
        # TENANT
        # =================================================

        tenant = get_tenant(
            chat_id
        )

        if (
            not tenant
            or not tenant.get(
                "telegram_channel"
            )
        ):

            logger.warning(
                f"[{req_id}] ⚠️ "
                f"Telegram channel تنظیم نشده."
            )

            send_message(
                chat_id,
                "❌ ابتدا با /register ثبت‌نام "
                "و کانال را تنظیم کنید."
            )

            return {
                "ok": True
            }

        # =================================================
        # MEDIA DETECTION
        # =================================================

        media_info = (
            get_media_from_message(
                msg
            )
        )

        log_media_info(
            req_id,
            media_info
        )

        # =================================================
        # MEDIA GROUP
        # =================================================

        if (
            media_info["type"]
            and is_media_group(msg)
        ):

            logger.info(
                f"[{req_id}] 🖼️ Media Group detected | "
                f"type={media_info['type']} | "
                f"group_id="
                f"{msg.get('media_group_id')}"
            )

            # ---------------------------------------------
            # اضافه کردن رسانه به Media Handler
            # ---------------------------------------------

            handle_media_group_message(
                msg,
                media_info["file_id"],
                media_info["type"],
                media_info["caption"]
            )

            # ---------------------------------------------
            # توجه:
            # ارسال به بله اینجا انجام نمی‌شود.
            #
            # Media Handler بعد از کامل شدن آلبوم
            # تمام رسانه‌ها را به بله می‌فرستد.
            # ---------------------------------------------

            send_message(
                chat_id,
                "✅ آلبوم شما در حال پردازش است..."
            )

            return {
                "ok": True
            }

        # =================================================
        # SINGLE MEDIA
        # =================================================

        elif media_info["type"]:

            media_type = (
                media_info["type"]
            )

            file_id = (
                media_info["file_id"]
            )

            logger.info(
                f"[{req_id}] 🎞️ Single Media | "
                f"type={media_type} | "
                f"file_id="
                f"{str(file_id)[:30]}"
            )

            # ---------------------------------------------
            # Caption
            # ---------------------------------------------

            caption = (
                text
                if text
                else media_info.get(
                    "caption",
                    ""
                )
            )

            # ---------------------------------------------
            # Branding
            # ---------------------------------------------

            branding = get_branding(
                chat_id
            )

            hashtag = branding.get(
                "hashtag",
                ""
            )

            channel_tag = branding.get(
                "channel_tag",
                ""
            )

            # ---------------------------------------------
            # Format caption
            # ---------------------------------------------

            if caption:

                formatted_caption = (
                    format_news(
                        caption
                    )
                )

                if not formatted_caption:

                    formatted_caption = (
                        caption
                    )

            else:

                formatted_caption = ""

            # ---------------------------------------------
            # Branding
            # ---------------------------------------------

            branding_parts = []

            if hashtag:

                branding_parts.append(
                    hashtag
                )

            if channel_tag:

                branding_parts.append(
                    channel_tag
                )

            if branding_parts:

                if formatted_caption:

                    formatted_caption += (
                        "\n\n"
                        + "\n".join(
                            branding_parts
                        )
                    )

                else:

                    formatted_caption = (
                        "\n".join(
                            branding_parts
                        )
                    )

            # =================================================
            # SEND MEDIA TO TELEGRAM CHANNEL
            # =================================================

            logger.info(
                f"[{req_id}] 📤 "
                f"ارسال رسانه به کانال اصلی..."
            )

            telegram_success = (
                send_media_to_channel(
                    API_URL,
                    CHANNEL_ID,
                    file_id,
                    media_type,
                    formatted_caption
                )
            )

            # ---------------------------------------------
            # Telegram Failed
            # ---------------------------------------------

            if not telegram_success:

                logger.error(
                    f"[{req_id}] ❌ "
                    f"ارسال رسانه به کانال اصلی شکست خورد."
                )

                send_message(
                    chat_id,
                    "❌ ارسال رسانه با مشکل روبرو شد."
                )

                return {
                    "ok": True
                }

            # ---------------------------------------------
            # Telegram Success
            # ---------------------------------------------

            logger.info(
                f"[{req_id}] ✅ "
                f"رسانه در کانال اصلی منتشر شد."
            )

            send_message(
                chat_id,
                "✅ خبر تصویری/ویدیویی شما "
                "در کانال منتشر شد."
            )

            # =================================================
            # SEND MEDIA TO BALE
            # =================================================

            logger.info(
                f"[{req_id}] 📤 "
                f"شروع ارسال رسانه به بله | "
                f"type={media_type}"
            )

            bale_success = (
                send_to_bale_for_user(
                    chat_id,
                    formatted_caption,
                    file_id,
                    media_type
                )
            )

            # ---------------------------------------------
            # Bale Result
            # ---------------------------------------------

            if bale_success:

                logger.info(
                    f"[{req_id}] ✅ "
                    f"رسانه با موفقیت به بله ارسال شد."
                )

            else:

                logger.error(
                    f"[{req_id}] ❌ "
                    f"ارسال رسانه به بله ناموفق بود."
                )

            return {
                "ok": True
            }

        # =================================================
        # TEXT MESSAGE
        # =================================================

        else:

            if text and text.strip():

                logger.info(
                    f"[{req_id}] 📝 "
                    f"پیام متنی دریافت شد."
                )

                formatted = format_news(
                    text
                )

                if formatted:

                    telegram_success = (
                        send_long_to_channel(
                            formatted,
                            chat_id
                        )
                    )

                    if telegram_success:

                        send_message(
                            chat_id,
                            "✅ خبر شما در کانال منتشر شد."
                        )

                    else:

                        send_message(
                            chat_id,
                            "❌ ارسال خبر به کانال "
                            "با مشکل روبرو شد."
                        )

                else:

                    send_message(
                        chat_id,
                        "❌ خبر قابل پردازش نیست."
                    )

            else:

                logger.warning(
                    f"[{req_id}] ⚠️ "
                    f"پیام خالی است."
                )

                send_message(
                    chat_id,
                    "❌ پیام خالی است."
                )

            return {
                "ok": True
            }

    # =====================================================
    # EXCEPTION
    # =====================================================

    except Exception as e:

        logger.error(
            f"[{req_id}] ❌ "
            f"خطا در Webhook Handler: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return {
            "ok": False,
            "error": str(e)
        }, 500
