import os
import requests
import logging
from core.database import get_tenant

logger = logging.getLogger(__name__)

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return True

    tenant = get_tenant(user_id)
    if not tenant or not tenant[4] or not tenant[5]:
        return True

    logger.info(f"📤 ارسال به بله: media_type={media_type}, file_id={file_id[:20] if file_id else 'None'}...")

    api_url = f"https://tapi.bale.ai/bot{tenant[5]}/"
    try:
        if file_id and media_type:
            # برای عکس و فیلم، ابتدا سعی کن به‌عنوان sendPhoto یا sendVideo ارسال کنی
            if media_type == "photo":
                endpoint = f"{api_url}sendPhoto"
                payload = {"chat_id": tenant[4], "photo": file_id, "caption": text}
            elif media_type == "video":
                endpoint = f"{api_url}sendVideo"
                payload = {"chat_id": tenant[4], "video": file_id, "caption": text}
            else:
                endpoint = f"{api_url}sendDocument"
                payload = {"chat_id": tenant[4], "document": file_id, "caption": text}
        else:
            endpoint = f"{api_url}sendMessage"
            payload = {"chat_id": tenant[4], "text": text}

        resp = requests.post(endpoint, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"❌ خطا در ارسال به بله: {resp.text}")
            return False
        logger.info(f"✅ به بله برای {user_id} ارسال شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به بله: {e}")
        return False
