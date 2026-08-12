import os
import requests
import logging
from core.database import get_tenant

logger = logging.getLogger(__name__)

# توکن تلگرام برای دانلود فایل
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FILE_URL = f"https://api.telegram.org/file/bot{BOT_TOKEN}/"

def send_to_bale_for_user(user_id, text, file_id=None, media_type=None):
    if os.getenv("ENABLE_BALE", "false").lower() != "true":
        return True

    tenant = get_tenant(user_id)
    if not tenant or not tenant[4] or not tenant[5]:
        return True

    # اگر رسانه وجود دارد، فایل را دانلود کن و به بله بفرست
    if file_id and media_type:
        try:
            # 1. دریافت مسیر فایل از تلگرام
            file_info = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}",
                timeout=10
            ).json()
            if not file_info.get("ok"):
                logger.error(f"❌ خطا در دریافت اطلاعات فایل: {file_info}")
                return False

            file_path = file_info["result"]["file_path"]
            download_url = TELEGRAM_FILE_URL + file_path

            # 2. دانلود فایل
            file_resp = requests.get(download_url, timeout=30)
            if file_resp.status_code != 200:
                logger.error(f"❌ خطا در دانلود فایل: {file_resp.status_code}")
                return False

            file_content = file_resp.content
            filename = os.path.basename(file_path)

            # 3. ارسال به بله به‌عنوان Document
            api_url = f"https://tapi.bale.ai/bot{tenant[5]}/sendDocument"
            files = {
                "document": (filename, file_content, "application/octet-stream")
            }
            data = {"chat_id": tenant[4], "caption": text}
            resp = requests.post(api_url, data=data, files=files, timeout=30)

            if resp.status_code != 200:
                logger.error(f"❌ خطا در ارسال فایل به بله: {resp.text}")
                return False

            logger.info(f"✅ فایل به بله برای {user_id} ارسال شد")
            return True

        except Exception as e:
            logger.error(f"❌ خطا در پردازش فایل: {e}")
            return False

    # ارسال متن ساده
    else:
        api_url = f"https://tapi.bale.ai/bot{tenant[5]}/sendMessage"
        payload = {"chat_id": tenant[4], "text": text}
        try:
            resp = requests.post(api_url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error(f"❌ خطا در ارسال متن به بله: {resp.text}")
                return False
            logger.info(f"✅ متن به بله برای {user_id} ارسال شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در ارسال متن به بله: {e}")
            return False
