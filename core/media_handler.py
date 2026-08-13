import time
import threading
import logging
from collections import defaultdict
import requests

from core.formatter import format_news

logger = logging.getLogger(__name__)

pending_groups = defaultdict(dict)

API_URL = None
CHANNEL_ID = None


# =========================================================
# INITIALIZE
# =========================================================

def initialize(api_url, channel_id):

    global API_URL, CHANNEL_ID

    API_URL = api_url
    CHANNEL_ID = channel_id

    logger.info(
        "✅ Media Handler initialized"
    )


# =========================================================
# MEDIA GROUP
# =========================================================

def is_media_group(message):

    return bool(
        message.get("media_group_id")
    )


# =========================================================
# ADD TO GROUP
# =========================================================

def add_to_pending_group(
    media_group_id,
    file_id,
    media_type,
    caption=""
):

    if media_group_id not in pending_groups:

        pending_groups[media_group_id] = {
            "files": [],
            "caption": "",
            "last_update": time.time(),
            "is_processing": False,
            "scheduled": False,
            "user_id": None
        }

    group = pending_groups[media_group_id]

    # جلوگیری از duplicate
    existing_ids = {
        item["file_id"]
        for item in group["files"]
    }

    if file_id not in existing_ids:

        group["files"].append({
            "type": media_type,
            "file_id": file_id
        })

        logger.info(
            f"📸 رسانه به گروه {media_group_id} اضافه شد | "
            f"type={media_type} | "
            f"total={len(group['files'])}"
        )

    group["last_update"] = time.time()

    # فقط اولین کپشن
    if caption and not group.get("caption"):

        try:
            group["caption"] = format_news(
                caption
            )

        except Exception:

            group["caption"] = caption


# =========================================================
# REMOVE
# =========================================================

def remove_pending_group(
    media_group_id
):

    if media_group_id in pending_groups:

        del pending_groups[
            media_group_id
        ]


# =========================================================
# READY
# =========================================================

def is_group_ready(
    media_group_id,
    timeout=1.5
):

    group = pending_groups.get(
        media_group_id
    )

    if not group:
        return False

    if group.get(
        "is_processing",
        False
    ):
        return False

    return (
        time.time()
        - group["last_update"]
        >= timeout
    )


# =========================================================
# SEND ALBUM TO TELEGRAM
# =========================================================

def send_media_group(
    chat_id,
    files,
    caption=""
):

    if not files:
        return False

    from core.formatter import (
        HASHTAG,
        CHANNEL_TAG
    )

    if caption:

        final_caption = (
            caption
            + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
        )

    else:

        final_caption = (
            f"{HASHTAG}\n{CHANNEL_TAG}"
        )

    media_group = []

    for index, file in enumerate(files):

        media_type = file.get("type")
        file_id = file.get("file_id")

        if media_type == "photo":

            media = {
                "type": "photo",
                "media": file_id
            }

        elif media_type == "video":

            media = {
                "type": "video",
                "media": file_id
            }

        else:

            continue

        if index == 0 and final_caption:

            media["caption"] = final_caption

        media_group.append(media)

    if not media_group:

        return False

    try:

        resp = requests.post(
            f"{API_URL}/sendMediaGroup",
            json={
                "chat_id": chat_id,
                "media": media_group
            },
            timeout=60
        )

        if resp.status_code == 200:

            logger.info(
                f"✅ آلبوم با "
                f"{len(media_group)} رسانه ارسال شد."
            )

            return True

        logger.error(
            f"❌ ارسال آلبوم شکست خورد | "
            f"status={resp.status_code} | "
            f"response={resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در ارسال آلبوم: {e}"
        )

        return False


# =========================================================
# SEND SINGLE MEDIA
# =========================================================

def send_single_media(
    chat_id,
    file,
    caption=""
):

    media_type = file.get("type")
    file_id = file.get("file_id")

    from core.formatter import (
        HASHTAG,
        CHANNEL_TAG
    )

    if caption:

        final_caption = (
            caption
            + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
        )

    else:

        final_caption = (
            f"{HASHTAG}\n{CHANNEL_TAG}"
        )

    try:

        if media_type == "photo":

            resp = requests.post(
                f"{API_URL}/sendPhoto",
                json={
                    "chat_id": chat_id,
                    "photo": file_id,
                    "caption": final_caption
                },
                timeout=60
            )

        elif media_type == "video":

            resp = requests.post(
                f"{API_URL}/sendVideo",
                json={
                    "chat_id": chat_id,
                    "video": file_id,
                    "caption": final_caption
                },
                timeout=60
            )

        else:

            return False

        if resp.status_code == 200:

            return True

        logger.error(
            f"❌ ارسال رسانه شکست خورد | "
            f"{resp.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ خطا در send_single_media: {e}"
        )

        return False


# =========================================================
# SEND ALBUM TO BALE
# =========================================================

def send_media_group_to_bale(
    user_id,
    files,
    caption=""
):

    if not files:
        return False

    from core.bale_forwarder import (
        send_to_bale_for_user
    )

    success = 0
    failed = 0

    logger.info(
        f"📤 شروع ارسال {len(files)} رسانه "
        f"آلبوم به بله."
    )

    for index, file in enumerate(files):

        file_id = file.get("file_id")
        media_type = file.get("type")

        if not file_id:

            failed += 1
            continue

        # کپشن فقط برای اولین رسانه
        media_caption = (
            caption
            if index == 0
            else ""
        )

        logger.info(
            f"📤 Bale media "
            f"{index + 1}/{len(files)} | "
            f"type={media_type}"
        )

        try:

            result = send_to_bale_for_user(
                user_id,
                media_caption,
                file_id,
                media_type
            )

            if result:

                success += 1

            else:

                failed += 1

        except Exception as e:

            failed += 1

            logger.exception(
                f"❌ خطا در ارسال رسانه به بله: {e}"
            )

    logger.info(
        f"📊 Bale album result | "
        f"success={success} | "
        f"failed={failed}"
    )

    return (
        success > 0
        and failed == 0
    )


# =========================================================
# PROCESS GROUP
# =========================================================

def process_media_group(
    media_group_id
):

    group = pending_groups.get(
        media_group_id
    )

    if not group:
        return

    if group.get(
        "is_processing",
        False
    ):
        return

    group["is_processing"] = True

    try:

        files = list(
            group.get("files", [])
        )

        caption = group.get(
            "caption",
            ""
        )

        user_id = group.get(
            "user_id"
        )

        if not files or not user_id:

            return

        logger.info(
            f"🎬 پردازش گروه {media_group_id} | "
            f"files={len(files)}"
        )

        # -----------------------------------------
        # یک رسانه
        # -----------------------------------------

        if len(files) == 1:

            telegram_success = (
                send_single_media(
                    CHANNEL_ID,
                    files[0],
                    caption
                )
            )

        # -----------------------------------------
        # آلبوم
        # -----------------------------------------

        else:

            telegram_success = (
                send_media_group(
                    CHANNEL_ID,
                    files,
                    caption
                )
            )

        # -----------------------------------------
        # Telegram موفق
        # -----------------------------------------

        if telegram_success:

            logger.info(
                "✅ رسانه/آلبوم در تلگرام منتشر شد."
            )

            bale_success = (
                send_media_group_to_bale(
                    user_id,
                    files,
                    caption
                )
            )

            if bale_success:

                logger.info(
                    "✅ رسانه/آلبوم به بله ارسال شد."
                )

            else:

                logger.error(
                    "❌ ارسال رسانه/آلبوم به بله "
                    "کامل نبود."
                )

        else:

            logger.error(
                "❌ انتشار در کانال تلگرام شکست خورد."
            )

    except Exception as e:

        logger.exception(
            f"❌ خطا در process_media_group: {e}"
        )

    finally:

        remove_pending_group(
            media_group_id
        )


# =========================================================
# SCHEDULE
# =========================================================

def schedule_processing(
    media_group_id,
    delay=1.5
):

    group = pending_groups.get(
        media_group_id
    )

    if not group:
        return

    # جلوگیری از Thread تکراری
    if group.get(
        "scheduled",
        False
    ):

        return

    group["scheduled"] = True

    def delayed_process():

        try:

            while True:

                time.sleep(delay)

                group = pending_groups.get(
                    media_group_id
                )

                if not group:
                    return

                elapsed = (
                    time.time()
                    - group["last_update"]
                )

                if elapsed < delay:

                    continue

                if is_group_ready(
                    media_group_id,
                    delay
                ):

                    process_media_group(
                        media_group_id
                    )

                    return

        except Exception as e:

            logger.exception(
                f"❌ خطا در Thread آلبوم: {e}"
            )

    thread = threading.Thread(
        target=delayed_process,
        daemon=True
    )

    thread.start()


# =========================================================
# HANDLE MEDIA GROUP MESSAGE
# =========================================================

def handle_media_group_message(
    message,
    file_id,
    media_type,
    caption=""
):

    media_group_id = message.get(
        "media_group_id"
    )

    if not media_group_id:

        return False

    chat = message.get(
        "chat",
        {}
    )

    user_id = chat.get(
        "id"
    )

    if not user_id:

        return False

    add_to_pending_group(
        media_group_id,
        file_id,
        media_type,
        caption
    )

    group = pending_groups.get(
        media_group_id
    )

    if group:

        group["user_id"] = user_id

    schedule_processing(
        media_group_id,
        1.5
    )

    return True
