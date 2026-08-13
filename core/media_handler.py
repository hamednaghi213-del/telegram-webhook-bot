import time
import threading
import logging
import requests
import json

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
# TIMEOUT CONFIG
# =========================================================

TELEGRAM_CONNECT_TIMEOUT = 10
TELEGRAM_READ_TIMEOUT = 30

MEDIA_GROUP_DELAY = 2.0
MEDIA_GROUP_MIN_WAIT = 1.5


# =========================================================
# INITIALIZE
# =========================================================

def initialize(api_url, channel_id):

    global API_URL
    global CHANNEL_ID

    API_URL = api_url
    CHANNEL_ID = channel_id

    logger.info(
        "✅ Media Handler initialized"
    )

    logger.info(
        f"🔧 Media Handler config | "
        f"channel={CHANNEL_ID}"
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

            logger.info(
                f"🆕 گروه جدید ایجاد شد | "
                f"group={media_group_id}"
            )

        group = pending_groups[group_key]

        already_exists = any(
            item.get("file_id") == file_id
            for item in group["files"]
        )

        if not already_exists:

            group["files"].append({
                "type": media_type,
                "file_id": file_id
            })

        else:

            logger.info(
                f"ℹ️ رسانه تکراری نادیده گرفته شد | "
                f"group={media_group_id}"
            )

        group["last_update"] = time.time()

        # -------------------------------------------------
        # Caption
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
                for key in list(
                    pending_groups.keys()
                )
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
# TELEGRAM REQUEST HELPER
# =========================================================

def telegram_post(
    endpoint,
    payload
):

    if not API_URL:

        logger.error(
            "❌ API_URL تنظیم نشده است."
        )

        return None

    url = (
        f"{API_URL}/{endpoint}"
    )

    logger.info(
        f"🌐 Telegram API request | "
        f"endpoint={endpoint}"
    )

    try:

        start_time = time.time()

        response = requests.post(
            url,
            json=payload,
            timeout=(
                TELEGRAM_CONNECT_TIMEOUT,
                TELEGRAM_READ_TIMEOUT
            )
        )

        elapsed = (
            time.time() - start_time
        )

        logger.info(
            f"📡 Telegram API response | "
            f"endpoint={endpoint} | "
            f"status={response.status_code} | "
            f"time={elapsed:.2f}s"
        )

        logger.info(
            f"📨 Telegram response body | "
            f"{response.text[:3000]}"
        )

        return response

    except requests.exceptions.ConnectTimeout as e:

        logger.error(
            f"⏰ Telegram ConnectTimeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.ReadTimeout as e:

        logger.error(
            f"⏰ Telegram ReadTimeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.Timeout as e:

        logger.error(
            f"⏰ Telegram Timeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.RequestException as e:

        logger.error(
            f"❌ Telegram RequestException | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except Exception as e:

        logger.exception(
            f"❌ Telegram API Exception | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None


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

    if not API_URL:

        logger.error(
            "❌ API_URL تنظیم نشده است."
        )

        return False

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID تنظیم نشده است."
        )

        return False

    if not file_id:

        logger.error(
            "❌ file_id خالی است."
        )

        return False

    if media_type == "photo":

        endpoint = "sendPhoto"

        payload = {
            "chat_id": CHANNEL_ID,
            "photo": file_id
        }

    elif media_type == "video":

        endpoint = "sendVideo"

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

    response = telegram_post(
        endpoint,
        payload
    )

    if response is None:

        return False

    if response.status_code == 200:

        try:

            data = response.json()

            if data.get("ok") is True:

                logger.info(
                    "✅ رسانه تکی در تلگرام "
                    "ارسال شد."
                )

                return True

            logger.error(
                f"❌ Telegram returned ok=false | "
                f"{data}"
            )

        except Exception:

            logger.error(
                "❌ پاسخ Telegram قابل پردازش نیست."
            )

        return False

    logger.error(
        f"❌ خطا در ارسال رسانه تکی | "
        f"status={response.status_code}"
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

    if not API_URL:

        logger.error(
            "❌ API_URL تنظیم نشده است."
        )

        return False

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID تنظیم نشده است."
        )

        return False

    # =====================================================
    # ساخت Media Group
    # =====================================================

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
                f"⚠️ نوع رسانه پشتیبانی نمی‌شود | "
                f"type={media_type}"
            )

            continue

        if not file_id:

            logger.warning(
                f"⚠️ file_id رسانه "
                f"{index + 1} خالی است."
            )

            continue

        media_item = {
            "type": media_type,
            "media": file_id
        }

        if (
            len(media_group) == 0
            and caption
        ):

            media_item[
                "caption"
            ] = caption

        media_group.append(
            media_item
        )

        supported_files.append({
            "type": media_type,
            "file_id": file_id
        })

    # =====================================================
    # حداکثر ۱۰ رسانه
    # =====================================================

    media_group = media_group[:10]
    supported_files = supported_files[:10]

    logger.info(
        f"📦 Media Group آماده شد | "
        f"count={len(media_group)}"
    )

    if not media_group:

        logger.error(
            "❌ هیچ رسانه‌ای برای ارسال وجود ندارد."
        )

        return False

    # =====================================================
    # ساخت Payload
    # =====================================================

    payload = {
        "chat_id": CHANNEL_ID,
        "media": media_group
    }

    logger.info(
        f"📨 Telegram Media Group payload آماده شد | "
        f"chat_id={CHANNEL_ID} | "
        f"count={len(media_group)}"
    )

    logger.info(
        f"🧾 Media JSON | "
        f"{json.dumps(media_group, ensure_ascii=False)}"
    )

    # =====================================================
    # ارسال Media Group
    # =====================================================

    response = telegram_post(
        "sendMediaGroup",
        payload
    )

    # =====================================================
    # موفق
    # =====================================================

    if response is not None:

        if response.status_code == 200:

            try:

                data = response.json()

                if data.get("ok") is True:

                    logger.info(
                        f"🎯 آلبوم با "
                        f"{len(media_group)} رسانه "
                        f"در تلگرام منتشر شد."
                    )

                    return True

                logger.error(
                    f"❌ Telegram sendMediaGroup "
                    f"ok=false | {data}"
                )

            except Exception as e:

                logger.error(
                    f"❌ خطا در خواندن پاسخ Telegram: "
                    f"{e}"
                )

        else:

            logger.error(
                f"❌ Telegram Media Group failed | "
                f"status={response.status_code}"
            )

    # =====================================================
    # FALLBACK
    # =====================================================

    logger.warning(
        "🛟 Media Group ناموفق بود."
    )

    logger.warning(
        "🔄 فعال‌سازی Fallback ارسال تکی..."
    )

    return send_media_group_fallback(
        supported_files,
        caption
    )


# =========================================================
# FALLBACK
# =========================================================

def send_media_group_fallback(
    files,
    caption=""
):

    logger.warning(
        f"🛟 شروع Fallback | "
        f"count={len(files) if files else 0}"
    )

    if not files:

        logger.error(
            "❌ Fallback فایل ندارد."
        )

        return False

    success_count = 0

    for index, file in enumerate(files):

        file_id = file.get(
            "file_id"
        )

        media_type = file.get(
            "type"
        )

        if not file_id:

            continue

        item_caption = (
            caption
            if index == 0
            else ""
        )

        logger.info(
            f"🛟 ارسال Fallback رسانه "
            f"{index + 1}/{len(files)} | "
            f"type={media_type}"
        )

        success = (
            send_single_media_to_channel(
                file_id,
                media_type,
                item_caption
            )
        )

        if success:

            success_count += 1

        else:

            logger.error(
                f"❌ Fallback رسانه "
                f"{index + 1} ناموفق بود."
            )

    if success_count == len(files):

        logger.info(
            f"✅ Fallback کامل موفق بود | "
            f"{success_count}/{len(files)}"
        )

        return True

    if success_count > 0:

        logger.warning(
            f"⚠️ Fallback ناقص بود | "
            f"{success_count}/{len(files)}"
        )

        return False

    logger.error(
        "❌ Fallback کاملاً ناموفق بود."
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
    # SNAPSHOT
    # =====================================================

    with group_lock:

        logger.info(
            f"🔒 دریافت Snapshot گروه | "
            f"group={media_group_id}"
        )

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
            f"🔓 Snapshot دریافت شد و Lock آزاد شد | "
            f"group={media_group_id}"
        )

    logger.info(
        f"📦 اطلاعات آلبوم دریافت شد | "
        f"count={len(files)} | "
        f"caption={'YES' if caption else 'NO'}"
    )

    # =====================================================
    # VALIDATE
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
        # CAPTION
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
        # TELEGRAM
        # =================================================

        logger.info(
            "📤 مرحله ۱/۲ | شروع انتشار در تلگرام..."
        )

        if len(files) == 1:

            file = files[0]

            channel_success = (
                send_single_media_to_channel(
                    file.get("file_id"),
                    file.get("type"),
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
        # BALE
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
    delay=MEDIA_GROUP_DELAY
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
            f"برای {delay} ثانیه بعد "
            f"برنامه‌ریزی شد"
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
                f"پیدا نشد | "
                f"group={media_group_id}"
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

    if elapsed < MEDIA_GROUP_MIN_WAIT:

        remaining = (
            MEDIA_GROUP_MIN_WAIT - elapsed
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

    add_to_pending_group(
        media_group_id,
        chat_id,
        file_id,
        media_type,
        caption
    )

    schedule_processing(
        media_group_id,
        chat_id,
        delay=MEDIA_GROUP_DELAY
    )

    return True
