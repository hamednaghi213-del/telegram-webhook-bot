import os
import requests
import logging
from core.database import get_tenant

logger = logging.getLogger(__name__)

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    """
    ارسال پیام به کانال بله بر اساس تنظیمات کاربر
    فقط در صورتی کار می‌کند که:
    1. ENABLE_BALE = true باشد
    2. کاربر کانال بله و توکن را تنظیم کرده باشد
    """
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return False  # قابلیت غیرفعال است

    tenant = get_tenant(user_id)
    if not tenant or not tenant[4] or not tenant[5]:
        return False  # کاربر تنظیمات بله را کامل نکرده

    bale_token = tenant[5]
    bale_channel = tenant[4]
    api_url = f"https://tapi.bale.ai/bot{bale_token}/"

    try:
        if file_id and media_type:
            endpoint = f"{api_url}send{media_type.capitalize()}"
            payload = {"chat_id": bale_channel, media_type: file_id, "caption": text}
        else:
            endpoint = f"{api_url}sendMessage"
            payload = {"chat_id": bale_channel, "text": text}

        resp = requests.post(endpoint, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"✅ به بله برای کاربر {user_id} ارسال شد")
            return True
        else:
            logger.error(f"❌ خطا در ارسال به بله: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ استثنا در ارسال به بله: {e}")
        return False
