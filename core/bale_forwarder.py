import os
import requests
import logging
from core.branding_manager import get_branding

logger = logging.getLogger(__name__)

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    """
    ارسال پیام به کانال بله بر اساس تنظیمات ذخیره‌شده در دیتابیس
    """
    # بررسی فعال بودن بله
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return True

    # دریافت تنظیمات بله از دیتابیس
    branding = get_branding(user_id)
    bale_channel = branding.get("bale_channel", "")
    bale_token = branding.get("bale_token", "")

    if not bale_channel or not bale_token:
        logger.info(f"⏳ بله برای کاربر {user_id} تنظیم نشده است.")
        return False

    api_url = f"https://tapi.bale.ai/bot{bale_token}/"

    try:
        # ارسال متن ساده
        if not file_id or not media_type:
            resp = requests.post(
                f"{api_url}sendMessage",
                json={"chat_id": bale_channel, "text": text},
                timeout=10
            )
        else:
            # ارسال رسانه به‌عنوان Document
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            file_info = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}",
                timeout=10
            ).json()
            if not file_info.get("ok"):
                logger.error(f"❌ خطا در دریافت اطلاعات فایل: {file_info}")
                return False

            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            file_content = requests.get(file_url, timeout=30).content

            files = {"document": (os.path.basename(file_path), file_content)}
            resp = requests.post(
                f"{api_url}sendDocument",
                data={"chat_id": bale_channel, "caption": text},
                files=files,
                timeout=30
            )

        if resp.status_code == 200:
            logger.info(f"✅ به بله برای {user_id} ارسال شد")
            return True
        else:
            logger.error(f"❌ خطا در ارسال به بله: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به بله: {e}")
        return False
