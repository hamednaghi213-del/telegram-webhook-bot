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

    api_url = f"https://tapi.bale.ai/bot{tenant[5]}/"

    try:
        # ارسال متن ساده
        if not file_id or not media_type:
            resp = requests.post(
                f"{api_url}sendMessage",
                json={"chat_id": tenant[4], "text": text},
                timeout=10
            )
        else:
            # ارسال رسانه به‌عنوان Document
            # ابتدا فایل را از تلگرام دانلود می‌کنیم
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

            # ارسال به بله
            files = {"document": (os.path.basename(file_path), file_content)}
            resp = requests.post(
                f"{api_url}sendDocument",
                data={"chat_id": tenant[4], "caption": text},
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
