import time
import threading
import logging
import requests

from collections import defaultdict

from core.formatter import format_news

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL = None
CHANNEL_ID = None


# =========================================================
# MEDIA GROUP STORAGE
# =========================================================

pending_groups = defaultdict(dict)

group_timers = {}

group_lock = threading.RLock()


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
# MEDIA GROUP DETECTION
# =========================================================

def is_media_group(message):

    return bool(
        message.get("media_group_id")
    )


# =========================================================
# ADD MEDIA TO GROUP
# =========================================================

def add_to_pending_group(
    media_group_id,
    chat_id,
    file_id,
    media_type,
    caption=""
):

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        if group_key not in pending_groups:

            pending_groups[group_key] = {
                "chat_id": chat_id,
                "media_group_id": media_group_id,
                "files": [],
                "caption": "",
                "last_update": time.time(),
                "is_processing": False
            }

        group = pending_groups[group_key]

        # جلوگیری از اضافه شدن تکراری
        already_exists = any(
            item["file_id"] == file_id
            for item in group["files"]
        )

        if not already_exists:

            group["files"].append({
                "type": media_type,
                "file_id": file_id
            })

        group["last_update"] = time.time()

        # کپشن فقط یک بار و از اولین رسانه دارای کپشن
        if caption and not group["caption"]:

            try:

                formatted = format_news(
                    caption
                )

                group["caption"] = (
                    formatted
                    if formatted
                    else caption
                )

            except Exception as e:

                logger.error(
                    f"❌ خطا در format_news: {e}"
                )

                group["caption"] = caption

        logger.info(
            f"📸 رسانه به گروه {media_group_id} "
            f"اضافه شد | "
            f"تعداد فعلی: {len(group['files'])}"
        )


# =========================================================
# REMOVE GROUP
# =========================================================

def remove_pending_group(
    media_group_id,
    chat_id=None
):

    with group_lock:

        if chat_id is not None:

            group_key = (
                chat_id,
                media_group_id
            )

            pending_groups.pop(
                group_key,
                None
            )

            timer = group_timers.pop(
                group_key,
                None
            )

            if timer:

                try:
                    timer.cancel()
                except Exception:
                    pass

        else:

            # سازگاری با نسخه‌های قبلی
            keys_to_remove = [
                key
                for key in pending_groups
                if key[1] == media_group_id
            ]

            for key in keys_to_remove:

                pending_groups.pop(
                    key,
                    None
                )

                timer = group_timers.pop(
                    key,
                    None
                )

                if timer:

                    try:
                        timer.cancel()
                    except Exception:
                        pass


# =========================================================
# SEND SINGLE MEDIA TO TELEGRAM CHANNEL
# =========================================================

def send_single_media_to_channel(
    file_id,
    media_type,
    caption=""
):

    if media_type == "photo":

        endpoint = (
            f"{API_URL}/sendPhoto"
        )

        payload = {
            "chat_id": CHANNEL_ID,
            "photo": file_id
        }

    elif media_type == "video":

        endpoint = (
            f"{API_URL}/sendVideo"
        )

        payload = {
            "chat_id": CHANNEL_ID,
            "video": file_id
        }

    else:

        logger.warning(
            f"⚠️ نوع رسانه برای آلبوم "
            f"پشتیبانی نمی‌شود: {media_type}"
        )

        return False

    if caption:

        payload["caption"] = caption

    try:

        response = requests.post(
            endpoint,
            json=payload,
            timeout=60
        )

        if response.status_code == 200:

            logger.info(
                f"✅ رسانه تکی ارسال شد | "
                f"type={media_type}"
            )

            return True

        logger.error(
            f"❌ خطا در ارسال رسانه تکی: "
            f"{response.text}"
        )

        return False

    except Exception as e:

        logger.error(
            f"❌ Exception ارسال رسانه تکی: {e}"
        )

        return False


# =========================================================
# SEND MEDIA GROUP TO TELEGRAM
# =========================================================

def send_media_group_to_channel(
    files,
    caption=""
):

    if not files:

        return False

    media_group = []

    supported_files = []

    for file in files:

        media_type = file.get("type")
        file_id = file.get("file_id")

        if media_type not in (
            "photo",
            "video"
        ):

            continue

        if not file_id:

            continue

        media = {
            "type": media_type,
            "media": file_id
        }

        supported_files.append(
            file
        )

        media_group.append(
            media
        )

    if not media_group:

        return False

    # Telegram Media Group حداکثر ۱۰ رسانه
    media_group = media_group[:10]
    supported_files = supported_files[:10]

    if caption:

        media_group[0]["caption"] = caption

    try:

        response = requests.post(
            f"{API_URL}/sendMediaGroup",
            json={
                "chat_id": CHANNEL_ID,
                "media": media_group
            },
            timeout=120
        )

        if response.status_code == 200:

            logger.info(
                f"✅ آلبوم با "
                f"{len(media_group)} رسانه "
                f"در کانال منتشر شد"
            )

            return True

        logger.error(
            f"❌ خطا در ارسال آلبوم "
            f"به کانال: {response.text}"
        )

        return False

    except Exception as e:

        logger.error(
            f"❌ Exception ارسال آلبوم: {e}"
        )

        return False


# =========================================================
# SEND ALBUM TO BALE
# =========================================================

def send_album_to_bale(
    user_id,
    files,
    caption=""
):

    if not files:

        return False

    try:

        from core.bale_forwarder import (
            send_media_group_to_bale
        )

        success = send_media_group_to_bale(
            user_id,
            files,
            caption
        )

        if success:

            logger.info(
                f"✅ آلبوم به بله ارسال شد | "
                f"user={user_id} | "
                f"count={len(files)}"
            )

        else:

            logger.error(
                f"❌ ارسال آلبوم به بله ناموفق بود | "
                f"user={user_id}"
            )

        return success

    except Exception as e:

        logger.error(
            f"❌ خطا در ارسال آلبوم به بله: {e}"
        )

        return False


# =========================================================
# PROCESS MEDIA GROUP
# =========================================================

def process_media_group(
    media_group_id,
    chat_id
):

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.warning(
                f"⚠️ گروه پیدا نشد: "
                f"{media_group_id}"
            )

            return False

        if group.get(
            "is_processing",
            False
        ):

            return False

        group["is_processing"] = True

        files = list(
            group.get(
                "files",
                []
            )
        )

        caption = group.get(
            "caption",
            ""
        )

    if not files:

        remove_pending_group(
            media_group_id,
            chat_id
        )

        return False

    logger.info(
        f"🚀 پردازش آلبوم | "
        f"group={media_group_id} | "
        f"chat={chat_id} | "
        f"count={len(files)}"
    )

    try:

        # -------------------------------------------------
        # ساخت کپشن نهایی
        # -------------------------------------------------

        from core.formatter import (
            HASHTAG,
            CHANNEL_TAG
        )

        if caption:

            final_caption = (
                f"{caption}\n\n"
                f"{HASHTAG}\n"
                f"{CHANNEL_TAG}"
            )

        else:

            final_caption = (
                f"{HASHTAG}\n"
                f"{CHANNEL_TAG}"
            )

        # -------------------------------------------------
        # ارسال به کانال تلگرام
        # -------------------------------------------------

        channel_success = False

        if len(files) == 1:

            file = files[0]

            channel_success = (
                send_single_media_to_channel(
                    file["file_id"],
                    file["type"],
                    final_caption
                )
            )

        else:

            channel_success = (
                send_media_group_to_channel(
                    files,
                    final_caption
                )
            )

        if not channel_success:

            logger.error(
                f"❌ انتشار آلبوم در کانال "
                f"ناموفق بود"
            )

            return False

        # -------------------------------------------------
        # ارسال آلبوم به بله
        # -------------------------------------------------

        bale_success = send_album_to_bale(
            chat_id,
            files,
            final_caption
        )

        if bale_success:

            logger.info(
                f"🎯 آلبوم کامل با موفقیت "
                f"در تلگرام و بله منتشر شد"
            )

        else:

            logger.warning(
                f"⚠️ آلبوم در تلگرام منتشر شد "
                f"اما ارسال آن به بله ناموفق بود"
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطا در پردازش آلبوم "
            f"{media_group_id}: {e}"
        )

        return False

    finally:

        remove_pending_group(
            media_group_id,
            chat_id
        )


# =========================================================
# SCHEDULE PROCESSING
# =========================================================

def schedule_processing(
    media_group_id,
    chat_id,
    delay=2.0
):

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        old_timer = group_timers.get(
            group_key
        )

        if old_timer:

            try:
                old_timer.cancel()
            except Exception:
                pass

        timer = threading.Timer(
            delay,
            _scheduled_process,
            args=(
                media_group_id,
                chat_id
            )
        )

        timer.daemon = True

        group_timers[group_key] = timer

        timer.start()

        logger.info(
            f"⏱️ پردازش گروه "
            f"{media_group_id} "
            f"برای {delay} ثانیه بعد برنامه‌ریزی شد"
        )


# =========================================================
# SCHEDULED PROCESS
# =========================================================

def _scheduled_process(
    media_group_id,
    chat_id
):

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            return

        last_update = group.get(
            "last_update",
            0
        )

        elapsed = (
            time.time() - last_update
        )

    # اگر هنوز رسانه جدیدی وارد گروه شده
    # دوباره کمی صبر می‌کنیم
    if elapsed < 1.2:

        remaining = (
            1.2 - elapsed
        )

        schedule_processing(
            media_group_id,
            chat_id,
            max(
                remaining,
                0.5
            )
        )

        return

    process_media_group(
        media_group_id,
        chat_id
    )


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

    chat_id = (
        message
        .get("chat", {})
        .get("id")
    )

    if not chat_id:

        logger.error(
            "❌ chat_id برای آلبوم پیدا نشد"
        )

        return False

    # -----------------------------------------
    # ذخیره رسانه
    # -----------------------------------------

    add_to_pending_group(
        media_group_id,
        chat_id,
        file_id,
        media_type,
        caption
    )

    # -----------------------------------------
    # هر بار که رسانه جدید می‌رسد
    # تایمر قبلی لغو و دوباره تنظیم می‌شود
    # -----------------------------------------

    schedule_processing(
        media_group_id,
        chat_id,
        delay=2.0
    )

    return True
