import os
import requests
import logging
from core.branding_manager import get_branding

logger = logging.getLogger(__name__)

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return True

    branding = get_branding(user_id)
    bale_channel = branding.get("bale_channel", "")
    bale_token = branding.get("bale_token", "")

    if not bale_channel or not bale_token:
        logger.info(f"⏳ بله برای کاربر {user_id} تنظیم نشده است.")
        return False

    # ارسال متن ساده
    if not file_id or not media_type:
        return send_text_to_bale(bale_channel, bale_token, text)

    # ارسال فایل (همزمان با timeout بالا)
    return send_media_to_bale(bale_channel, bale_token, text, file_id, media_type)

def send_text_to_bale(channel, token, text):
    try:
        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendMessage",
            json={"chat_id": channel, "text": text},
            timeout=30
        )
        if resp.status_code == 200:
            logger.info("✅ متن به بله ارسال شد")
            return True
        else:
            logger.error(f"❌ خطا در ارسال متن به بله: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ خطا در ارسال متن به بله: {e}")
        return False

def send_media_to_bale(channel, token, caption, file_id, media_type):
    try:
        logger.info(f"📥 دریافت اطلاعات فایل از تلگرام (ID: {file_id[:20]}...)")
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

        file_info = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}",
            timeout=30
        ).json()
        if not file_info.get("ok"):
            logger.error(f"❌ خطا در دریافت اطلاعات فایل: {file_info}")
            return False

        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        logger.info(f"📥 دانلود فایل از: {file_url}")

        file_content = requests.get(file_url, timeout=120).content
        logger.info(f"📤 ارسال فایل به بله (حجم: {len(file_content)} بایت)")

        files = {"document": (os.path.basename(file_path), file_content)}
        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendDocument",
            data={"chat_id": channel, "caption": caption},
            files=files,
            timeout=120
        )

        if resp.status_code == 200:
            logger.info("✅ فایل به بله ارسال شد")
            return True
        else:
            logger.error(f"❌ خطا در ارسال فایل به بله: {resp.text}")
            return False

    except Exception as e:
        logger.error(f"❌ خطا در ارسال فایل به بله: {e}")
        return False
