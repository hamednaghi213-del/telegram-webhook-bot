import time
import threading
import logging
from collections import defaultdict
import requests

logger = logging.getLogger(__name__)

pending_groups = defaultdict(dict)
API_URL = None
CHANNEL_ID = None

def initialize(api_url, channel_id):
    global API_URL, CHANNEL_ID
    API_URL = api_url
    CHANNEL_ID = channel_id

def is_media_group(message):
    return "media_group_id" in message

def add_to_pending_group(media_group_id, file_id, media_type, caption=""):
    if media_group_id not in pending_groups:
        pending_groups[media_group_id] = {
            "files": [],
            "caption": "",
            "last_update": time.time(),
            "is_processing": False
        }
    pending_groups[media_group_id]["files"].append({
        "type": media_type,
        "file_id": file_id
    })
    pending_groups[media_group_id]["last_update"] = time.time()
    if caption:
        pending_groups[media_group_id]["caption"] = caption
    logger.info(f"📸 رسانه به گروه {media_group_id} اضافه شد (تعداد: {len(pending_groups[media_group_id]['files'])})")

def remove_pending_group(media_group_id):
    if media_group_id in pending_groups:
        del pending_groups[media_group_id]
        logger.info(f"🗑️ گروه {media_group_id} از حافظه حذف شد")

def is_group_ready(media_group_id, timeout=1.5):
    group = pending_groups.get(media_group_id)
    if not group:
        return False
    if group.get("is_processing", False):
        return False
    if time.time() - group["last_update"] > timeout:
        return True
    return False

def clean_mentions_from_text(text):
    """حذف تمام @ها (به جز @Donya24News) از کپشن"""
    if not text:
        return text
    import re
    pattern = re.compile(r'@[a-zA-Z0-9_]+')
    def replace_at(match):
        return match.group(0) if match.group(0) == "@Donya24News" else ""
    return pattern.sub(replace_at, text)

def send_media_group(chat_id, files, caption=""):
    """ارسال آلبوم با متد sendMediaGroup"""
    if not files:
        return False
    
    caption = clean_mentions_from_text(caption)
    
    media_group = []
    for i, file in enumerate(files):
        if file["type"] == "photo":
            media = {"type": "photo", "media": file["file_id"]}
        elif file["type"] == "video":
            media = {"type": "video", "media": file["file_id"]}
        else:
            continue
        if i == 0 and caption:
            media["caption"] = caption
        media_group.append(media)
    
    if not media_group:
        return False
    
    try:
        resp = requests.post(
            f"{API_URL}/sendMediaGroup",
            json={"chat_id": chat_id, "media": media_group},
            timeout=30
        )
        resp.raise_for_status()
        logger.info(f"✅ آلبوم با {len(media_group)} رسانه ارسال شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال آلبوم: {e}")
        # در صورت خطا، به صورت جداگانه ارسال کن
        for i, file in enumerate(files):
            try:
                if file["type"] == "photo":
                    requests.post(
                        f"{API_URL}/sendPhoto",
                        json={"chat_id": chat_id, "photo": file["file_id"], "caption": caption if i == 0 else ""},
                        timeout=30
                    )
                elif file["type"] == "video":
                    requests.post(
                        f"{API_URL}/sendVideo",
                        json={"chat_id": chat_id, "video": file["file_id"], "caption": caption if i == 0 else ""},
                        timeout=30
                    )
            except Exception as e2:
                logger.error(f"❌ خطا در ارسال تکی {file['type']}: {e2}")
        return False

def process_media_group(media_group_id):
    group = pending_groups.get(media_group_id)
    if not group:
        return
    
    group["is_processing"] = True
    
    try:
        files = group["files"]
        caption = group.get("caption", "")
        
        if not files:
            return
        
        if len(files) == 1:
            file = files[0]
            caption = clean_mentions_from_text(caption)
            if file["type"] == "photo":
                requests.post(
                    f"{API_URL}/sendPhoto",
                    json={"chat_id": CHANNEL_ID, "photo": file["file_id"], "caption": caption},
                    timeout=30
                )
            elif file["type"] == "video":
                requests.post(
                    f"{API_URL}/sendVideo",
                    json={"chat_id": CHANNEL_ID, "video": file["file_id"], "caption": caption},
                    timeout=30
                )
            logger.info(f"✅ رسانه تکی ارسال شد")
        else:
            send_media_group(CHANNEL_ID, files, caption)
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش آلبوم {media_group_id}: {e}")
    finally:
        remove_pending_group(media_group_id)

def schedule_processing(media_group_id, delay=1.5):
    def delayed_process():
        time.sleep(delay)
        if is_group_ready(media_group_id, timeout=0):
            process_media_group(media_group_id)
        else:
            schedule_processing(media_group_id, delay)
    
    thread = threading.Thread(target=delayed_process)
    thread.daemon = True
    thread.start()

def handle_media_group_message(message, file_id, media_type, caption=""):
    media_group_id = message.get("media_group_id")
    if not media_group_id:
        return False
    
    add_to_pending_group(media_group_id, file_id, media_type, caption)
    schedule_processing(media_group_id, 1.5)
    return True
