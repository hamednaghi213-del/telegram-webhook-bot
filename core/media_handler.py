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

        # -------------------------------------------------
        # کپشن
        # -------------------------------------------------

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

                logger.exception(
                    f"❌ خطا در format_news: {e}"
                )

                group["caption"] = caption

        logger.info(
            f"📸 رسانه به گروه {media_group_id} "
            f"اضافه شد | تعداد فعلی: "
            f"{len(group['files'])}"
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
# SEND SINGLE MEDIA TO TELEGRAM
# =========================================================

def send_single_media_to_channel(
    file_id,
    media_type,
    caption=""
):

    logger.info(
        f"📤 شروع ارسال رسانه تکی به تلگرام | "
        f"type={media_type}"
    )

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
            f"⚠️ نوع رسانه پشتیبانی نمی‌شود: "
            f"{media_type}"
        )

        return False

    if caption:

        payload["caption"] = caption

    try:

        response = requests.post(
            endpoint,
            json=payload,
            timeout=120
        )

        logger.info(
            f"📡 Telegram single media response | "
            f"status={response.status_code}"
        )

        if response.status_code == 200:

            logger.info(
                "✅ رسانه تکی در تلگرام ارسال شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال رسانه تکی به تلگرام | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
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

    logger.info(
        f"📤 شروع ارسال Media Group به تلگرام | "
        f"input_count={len(files) if files else 0}"
    )

    if not files:

        logger.error(
            "❌ لیست فایل‌های آلبوم خالی است."
        )

        return False

    media_group = []

    supported_files = []

    for index, file in enumerate(files):

        media_type = file.get(
            "type"
        )

        file_id = file.get(
            "file_id"
        )

        logger.info(
            f"🔎 بررسی رسانه {index + 1} | "
            f"type={media_type} | "
            f"has_file_id={bool(file_id)}"
        )

        if media_type not in (
            "photo",
            "video"
        ):

            logger.warning(
                f"⚠️ رسانه {index + 1} "
                f"نوع پشتیبانی‌نشده دارد: "
                f"{media_type}"
            )

            continue

        if not file_id:

            logger.warning(
                f"⚠️ file_id رسانه "
                f"{index + 1} خالی است."
            )

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

    # -------------------------------------------------
    # حداکثر ۱۰ رسانه
    # -------------------------------------------------

    media_group = media_group[:10]
    supported_files = supported_files[:10]

    logger.info(
        f"📦 Media Group آماده ارسال به تلگرام | "
        f"count={len(media_group)}"
    )

    if not media_group:

        logger.error(
            "❌ هیچ رسانه قابل پشتیبانی "
            "برای ارسال به تلگرام وجود ندارد."
        )

        return False

    # -------------------------------------------------
    # کپشن فقط روی اولین رسانه
    # -------------------------------------------------

    if caption:

        media_group[0]["caption"] = caption

        logger.info(
            "📝 کپشن روی اولین رسانه قرار گرفت."
        )

    # -------------------------------------------------
    # ارسال
    # -------------------------------------------------

    try:

        logger.info(
            "🚀 درخواست sendMediaGroup به Telegram API..."
        )

        response = requests.post(
            f"{API_URL}/sendMediaGroup",
            json={
                "chat_id": CHANNEL_ID,
                "media": media_group
            },
            timeout=180
        )

        logger.info(
            f"📡 Telegram Media Group response | "
            f"status={response.status_code}"
        )

        if response.status_code == 200:

            logger.info(
                f"✅ آلبوم با "
                f"{len(media_group)} رسانه "
                f"در کانال تلگرام منتشر شد."
            )

            return True

        logger.error(
            f"❌ خطا در ارسال آلبوم به تلگرام | "
            f"status={response.status_code} | "
            f"response={response.text}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ Exception ارسال آلبوم به تلگرام: {e}"
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

    logger.info(
        f"📤 شروع ارسال آلبوم به بله | "
        f"user={user_id} | "
        f"count={len(files) if files else 0}"
    )

    if not files:

        logger.error(
            "❌ فایل‌های آلبوم برای بله خالی هستند."
        )

        return False

    try:

        from core.bale_forwarder import (
            send_media_group_to_bale
        )

        logger.info(
            "🔗 اتصال به bale_forwarder برقرار شد."
        )

        success = send_media_group_to_bale(
            user_id,
            files,
            caption
        )

        if success:

            logger.info(
                f"✅ آلبوم با موفقیت "
                f"به بله ارسال شد | "
                f"user={user_id}"
            )

        else:

            logger.error(
                f"❌ ارسال آلبوم به بله ناموفق بود | "
                f"user={user_id}"
            )

        return success

    except Exception as e:

        logger.exception(
            f"❌ Exception در ارسال آلبوم به بله: {e}"
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

    logger.info(
        f"🚀 پردازش آلبوم | "
        f"group={media_group_id} | "
        f"chat={chat_id}"
    )

    # =====================================================
    # دریافت گروه
    # =====================================================

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.error(
                f"❌ گروه پیدا نشد | "
                f"group={media_group_id}"
            )

            return False

        if group.get(
            "is_processing",
            False
        ):

            logger.warning(
                f"⚠️ گروه قبلاً در حال پردازش است | "
                f"group={media_group_id}"
            )

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

    logger.info(
        f"📦 اطلاعات آلبوم دریافت شد | "
        f"count={len(files)} | "
        f"caption={'YES' if caption else 'NO'}"
    )

    # =====================================================
    # بررسی فایل‌ها
    # =====================================================

    if not files:

        logger.error(
            "❌ آلبوم هیچ فایلی ندارد."
        )

        remove_pending_group(
            media_group_id,
            chat_id
        )

        return False

    for index, file in enumerate(files):

        logger.info(
            f"📋 فایل {index + 1}/{len(files)} | "
            f"type={file.get('type')} | "
            f"file_id="
            f"{str(file.get('file_id'))[:25]}..."
        )

    try:

        # =================================================
        # ساخت کپشن
        # =================================================

        logger.info(
            "📝 شروع ساخت کپشن نهایی..."
        )

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

        logger.info(
            "✅ کپشن نهایی ساخته شد."
        )

        # =================================================
        # ارسال به تلگرام
        # =================================================

        logger.info(
            "📤 مرحله ۱/۲ | شروع انتشار در تلگرام..."
        )

        channel_success = False

        if len(files) == 1:

            logger.info(
                "📦 آلبوم فقط یک رسانه دارد."
            )

            file = files[0]

            channel_success = (
                send_single_media_to_channel(
                    file["file_id"],
                    file["type"],
                    final_caption
                )
            )

        else:

            logger.info(
                f"📦 ارسال آلبوم "
                f"{len(files)} رسانه‌ای به تلگرام..."
            )

            channel_success = (
                send_media_group_to_channel(
                    files,
                    final_caption
                )
            )

        logger.info(
            f"📡 نتیجه ارسال به تلگرام | "
            f"success={channel_success}"
        )

        if not channel_success:

            logger.error(
                "❌ انتشار آلبوم در تلگرام ناموفق بود."
            )

            return False

        logger.info(
            "🎯 مرحله ۱/۲ با موفقیت انجام شد."
        )

        # =================================================
        # ارسال به بله
        # =================================================

        logger.info(
            "📤 مرحله ۲/۲ | شروع انتشار در بله..."
        )

        bale_success = send_album_to_bale(
            chat_id,
            files,
            final_caption
        )

        logger.info(
            f"📡 نتیجه ارسال به بله | "
            f"success={bale_success}"
        )

        if bale_success:

            logger.info(
                "🎯 آلبوم کامل با موفقیت "
                "در تلگرام و بله منتشر شد."
            )

        else:

            logger.warning(
                "⚠️ آلبوم در تلگرام منتشر شد "
                "اما ارسال آن به بله ناموفق بود."
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطای اصلی در process_media_group | "
            f"group={media_group_id}: {e}"
        )

        return False

    finally:

        logger.info(
            f"🧹 پاک‌سازی گروه | "
            f"group={media_group_id}"
        )

        remove_pending_group(
            media_group_id,
            chat_id
        )

        logger.info(
            f"✅ پردازش گروه پایان یافت | "
            f"group={media_group_id}"
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

    logger.info(
        f"⏰ Timer اجرا شد | "
        f"group={media_group_id}"
    )

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.warning(
                f"⚠️ گروه در زمان اجرای Timer "
                f"پیدا نشد | group={media_group_id}"
            )

            return

        last_update = group.get(
            "last_update",
            0
        )

        elapsed = (
            time.time() - last_update
        )

    logger.info(
        f"⏱️ زمان گذشته از آخرین رسانه: "
        f"{elapsed:.2f}s"
    )

    if elapsed < 1.2:

        remaining = (
            1.2 - elapsed
        )

        logger.info(
            f"⏳ هنوز رسانه جدید ممکن است برسد | "
            f"remaining={remaining:.2f}s"
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

    logger.info(
        f"🚀 ارسال گروه به process_media_group | "
        f"group={media_group_id}"
    )

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

        logger.warning(
            "⚠️ media_group_id وجود ندارد."
        )

        return False

    chat_id = (
        message
        .get("chat", {})
        .get("id")
    )

    if not chat_id:

        logger.error(
            "❌ chat_id برای آلبوم پیدا نشد."
        )

        return False

    logger.info(
        f"🖼️ Media Group detected | "
        f"type={media_type} | "
        f"group_id={media_group_id}"
    )

    # =====================================================
    # ذخیره رسانه
    # =====================================================

    add_to_pending_group(
        media_group_id,
        chat_id,
        file_id,
        media_type,
        caption
    )

    # =====================================================
    # تنظیم Timer
    # =====================================================

    schedule_processing(
        media_group_id,
        chat_id,
        delay=2.0
    )

    return True
