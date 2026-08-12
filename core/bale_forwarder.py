import os
import requests
import logging
from core.database import get_tenant

logger = logging.getLogger(__name__)

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return False
    tenant = get_tenant(user_id)
    if not tenant or not tenant[4] or not tenant[5]:
        return False

    api_url = f"https://tapi.bale.ai/bot{tenant[5]}/"
    try:
        if file_id and media_type:
            endpoint = f"{api_url}send{media_type.capitalize()}"
            payload = {"chat_id": tenant[4], media_type: file_id, "caption": text}
        else:
            endpoint = f"{api_url}sendMessage"
            payload = {"chat_id": tenant[4], "text": text}
        requests.post(endpoint, json=payload, timeout=10)
        logger.info(f"✅ به بله برای {user_id} ارسال شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به بله: {e}")
        return False
