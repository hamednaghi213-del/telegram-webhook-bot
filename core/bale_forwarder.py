import os
import requests
import logging
import threading
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

    if file_id and media_type:
        threading.Thread(
            target=send_media_to_bale_async,
            args=(user_id, bale_channel, bale_token, text, file_id, media_type)
        ).start()
        logger.info(f"📤 ارسال فایل به بله در پس‌زمینه (کاربر {user_id})")
        return True

    return send_text_to_bale(bale_channel, bale_token, text)

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

def send_media_to_bale_async(user_id, channel, token, caption, file_id, media_type):
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        file_info = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}",
            timeout=30
        ).json()
        if not file_info.get("ok"):
            logger.error(f"❌ خطا در دریافت اطلاعات فایل: {file_info}")
            return

        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        file_content = requests.get(file_url, timeout=60).content

        files = {"document": (os.path.basename(file_path), file_content)}
        resp = requests.post(
            f"https://tapi.bale.ai/bot{token}/sendDocument",
            data={"chat_id": channel, "caption": caption},
            files=files,
            timeout=60
        )

        if resp.status_code == 200:
            logger.info(f"✅ فایل به بله برای کاربر {user_id} ارسال شد")
        else:
            logger.error(f"❌ خطا در ارسال فایل به بله: {resp.text}")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال فایل به بله: {e}")
