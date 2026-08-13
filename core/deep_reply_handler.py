import logging
import time
import requests

from core.formatter import format_news
from core.bale_forwarder import send_to_bale_for_user

logger = logging.getLogger(__name__)

API_URL = None
CHANNEL_ID = None


def initialize(api_url, channel_id):
    global API_URL, CHANNEL_ID

    API_URL = api_url
    CHANNEL_ID = channel_id

    logger.info("✅ Deep Reply Handler initialized")


# =========================================================
# REPLY DETECTION
# =========================================================

def has_reply(message: dict) -> bool:
    return (
        isinstance(message, dict)
        and message.get("reply_to_message") is not None
    )


# =========================================================
# MEDIA EXTRACTION
# =========================================================

def get_media_from_message(msg: dict) -> dict:

    result = {
        "type": None,
        "file_id": None,
        "caption": "",
        "text": ""
    }

    if not msg:
        return result

    # -------------------------
    # Video
    # -------------------------

    if "video" in msg:

        result["type"] = "video"
        result["file_id"] = msg["video"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")

    # -------------------------
    # Photo
    # -------------------------

    elif "photo" in msg:

        result["type"] = "photo"
        result["file_id"] = msg["photo"][-1]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")

    # -------------------------
    # Document
    # -------------------------

    elif "document" in msg:

        result["type"] = "document"
        result["file_id"] = msg["document"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")

    # -------------------------
    # Voice
    # -------------------------

    elif "voice" in msg:

        result["type"] = "voice"
        result["file_id"] = msg["voice"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")

    # -------------------------
    # Audio
    # -------------------------

    elif "audio" in msg:

        result["type"] = "audio"
        result["file_id"] = msg["audio"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")

    # -------------------------
    # Text
    # -------------------------

    elif "text" in msg:

        result["type"] = "text"
        result["text"] = msg.get("text", "")

    return result


# =========================================================
# SEND TEXT TO TELEGRAM
# =========================================================

def send_simple_message(text: str, reply_to_id=None):

    if not text:
        return None

    try:

        payload = {
            "chat_id": CHANNEL_ID,
            "text": text
        }

        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id

        response = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram sendMessage error | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return None

        result = response.json()

        if not result.get("ok"):

            logger.error(
                f"❌ Telegram sendMessage API error | "
                f"{result}"
            )

            return None

        message_id = (
            result
            .get("result", {})
            .get("message_id")
        )

        logger.info(
            f"✅ Reply text sent | "
            f"message_id={message_id}"
        )

        return message_id

    except Exception as e:

        logger.exception(
            f"❌ خطا در ارسال پیام Reply: {e}"
        )

        return None


# =========================================================
# SEND MEDIA TO TELEGRAM
# =========================================================

def send_media_to_channel(
    file_id: str,
    media_type: str,
    caption: str = "",
    reply_to_id=None
):

    if not file_id:
        return None

    try:

        if media_type == "photo":

            endpoint = f"{API_URL}/sendPhoto"

        elif media_type == "video":

            endpoint = f"{API_URL}/sendVideo"

        elif media_type == "document":

            endpoint = f"{API_URL}/sendDocument"

        elif media_type == "voice":

            endpoint = f"{API_URL}/sendVoice"

        elif media_type == "audio":

            endpoint = f"{API_URL}/sendAudio"

        else:

            logger.warning(
                f"⚠️ نوع رسانه Reply پشتیبانی نمی‌شود: "
                f"{media_type}"
            )

            return None

        payload = {
            "chat_id": CHANNEL_ID,
            media_type: file_id
        }

        if caption:
            payload["caption"] = caption

        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id

        response = requests.post(
            endpoint,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram media error | "
                f"type={media_type} | "
                f"status={response.status_code} | "
                f"response={response.text}"
            )

            return None

        result = response.json()

        if not result.get("ok"):

            logger.error(
                f"❌ Telegram media API error | "
                f"{result}"
            )

            return None

        message_id = (
            result
            .get("result", {})
            .get("message_id")
        )

        logger.info(
            f"✅ Reply {media_type} sent | "
            f"message_id={message_id}"
        )

        return message_id

    except Exception as e:

        logger.exception(
            f"❌ خطا در ارسال {media_type} Reply: {e}"
        )

        return None


# =========================================================
# SEND LONG TEXT
# =========================================================

def send_long_to_channel(text: str):

    if not text:
        return False

    from core.formatter import HASHTAG, CHANNEL_TAG

    footer = ""

    if HASHTAG:
        footer += HASHTAG

    if CHANNEL_TAG:
        footer += f"\n{CHANNEL_TAG}"

    if footer:
        text = text.rstrip() + "\n\n" + footer

    max_len = 4096

    if len(text) <= max_len:

        return send_simple_message(text) is not None

    parts = []

    start = 0

    while start < len(text):

        end = min(
            start + max_len,
            len(text)
        )

        if end < len(text):

            last_newline = text.rfind(
                "\n",
                start,
                end
            )

            last_space = text.rfind(
                " ",
                start,
                end
            )

            cut_at = max(
                last_newline,
                last_space
            )

            if cut_at > start:

                end = cut_at + 1

        part = text[start:end].strip()

        if part:
            parts.append(part)

        start = end

    total = len(parts)

    success = True

    for index, part in enumerate(parts, 1):

        if total > 1:

            part = (
                f"({index}/{total})\n"
                f"{part}"
            )

        if send_simple_message(part) is None:
            success = False
            break

        if index < total:
            time.sleep(0.5)

    return success


# =========================================================
# EXTRACT REPLY CHAIN
# =========================================================

def extract_reply_chain(
    message: dict,
    chain=None,
    visited=None
):

    if chain is None:
        chain = []

    if visited is None:
        visited = set()

    if not message:
        return chain

    # جلوگیری از حلقه احتمالی
    message_id = message.get("message_id")

    if message_id is not None:

        if message_id in visited:
            return chain

        visited.add(message_id)

    media_info = get_media_from_message(message)

    chain.append({
        "text": media_info.get(
            "text",
            ""
        ),
        "media": (
            media_info
            if media_info.get("type") != "text"
            else None
        ),
        "type": media_info.get(
            "type",
            "text"
        )
    })

    parent = message.get(
        "reply_to_message"
    )

    if parent:

        try:

            extract_reply_chain(
                parent,
                chain,
                visited
            )

        except Exception as e:

            logger.warning(
                f"⚠️ خطا در استخراج زنجیره Reply: {e}"
            )

    return chain


# =========================================================
# PROCESS SINGLE ITEM
# =========================================================

def process_reply_item(
    item: dict,
    chat_id: int
):

    if not item:
        return True

    text = item.get(
        "text",
        ""
    )

    media = item.get(
        "media"
    )

    # -----------------------------------------
    # Text
    # -----------------------------------------

    if text:

        formatted = format_news(
            text
        )

        if formatted:

            telegram_ok = send_long_to_channel(
                formatted
            )

            if not telegram_ok:

                logger.error(
                    "❌ ارسال متن Reply به Telegram شکست خورد."
                )

            # ارسال متن به Bale
            try:

                send_to_bale_for_user(
                    chat_id,
                    formatted
                )

            except Exception as e:

                logger.exception(
                    f"❌ خطا در ارسال Reply text به Bale: {e}"
                )

    # -----------------------------------------
    # Media
    # -----------------------------------------

    if media:

        file_id = media.get(
            "file_id"
        )

        media_type = media.get(
            "type"
        )

        caption = media.get(
            "caption",
            ""
        )

        if not file_id:
            return True

        # Caption را برای Telegram قالب‌بندی می‌کنیم
        formatted_caption = ""

        if caption:

            formatted_caption = format_news(
                caption
            )

        # ارسال به Telegram
        telegram_message_id = send_media_to_channel(
            file_id,
            media_type,
            formatted_caption
        )

        if telegram_message_id is None:

            logger.error(
                f"❌ ارسال {media_type} Reply "
                f"به Telegram شکست خورد."
            )

        # ارسال به Bale
        try:

            send_to_bale_for_user(
                chat_id,
                formatted_caption,
                file_id,
                media_type
            )

        except Exception as e:

            logger.exception(
                f"❌ خطا در ارسال {media_type} Reply به Bale: {e}"
            )

    return True


# =========================================================
# MAIN DEEP REPLY PROCESSOR
# =========================================================

def process_deep_reply(
    msg: dict,
    chat_id: int
) -> bool:

    if not msg:
        return False

    if not has_reply(msg):
        return False

    logger.info(
        f"🔗 شروع پردازش Deep Reply | "
        f"chat_id={chat_id}"
    )

    try:

        chain = extract_reply_chain(msg)

        if not chain:

            logger.warning(
                "⚠️ زنجیره Reply خالی است."
            )

            return False

        # -----------------------------------------
        # زنجیره از پیام اصلی به پیام جدید
        # -----------------------------------------

        chain.reverse()

        logger.info(
            f"🔗 تعداد پیام‌های زنجیره Reply: "
            f"{len(chain)}"
        )

        for item in chain:

            process_reply_item(
                item,
                chat_id
            )

            time.sleep(0.3)

        logger.info(
            "✅ Deep Reply با موفقیت پردازش شد."
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطا در process_deep_reply: {e}"
        )

        return False
