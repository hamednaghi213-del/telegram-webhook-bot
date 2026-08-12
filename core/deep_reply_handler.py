import logging
import requests
import re

logger = logging.getLogger(__name__)

API_URL = None
CHANNEL_ID = None

def initialize(api_url, channel_id):
    global API_URL, CHANNEL_ID
    API_URL = api_url
    CHANNEL_ID = channel_id
    logger.info("✅ Deep Reply Handler initialized")

def has_reply(message: dict) -> bool:
    return "reply_to_message" in message and message["reply_to_message"] is not None

def get_media_from_message(msg: dict) -> dict:
    result = {"type": None, "file_id": None, "caption": "", "text": ""}
    if "video" in msg:
        result["type"] = "video"
        result["file_id"] = msg["video"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")
    elif "photo" in msg:
        result["type"] = "photo"
        result["file_id"] = msg["photo"][-1]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")
    elif "document" in msg:
        result["type"] = "document"
        result["file_id"] = msg["document"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")
    elif "voice" in msg:
        result["type"] = "voice"
        result["file_id"] = msg["voice"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")
    elif "audio" in msg:
        result["type"] = "audio"
        result["file_id"] = msg["audio"]["file_id"]
        result["caption"] = msg.get("caption", "")
        result["text"] = msg.get("caption", "")
    elif "text" in msg:
        result["type"] = "text"
        result["text"] = msg["text"]
    return result

def send_media_to_channel(file_id: str, media_type: str, caption: str = ""):
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
            return False
        resp = requests.post(
            endpoint,
            json={"chat_id": CHANNEL_ID, media_type: file_id, "caption": caption},
            timeout=30
        )
        resp.raise_for_status()
        logger.info(f"✅ {media_type} در کانال منتشر شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال {media_type} به کانال: {e}")
        return False

def send_simple_message(text: str):
    """ارسال یک پیام ساده به کانال"""
    try:
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": text},
            timeout=10
        )
        resp.raise_for_status()
        logger.info(f"✅ پیام در کانال منتشر شد (طول: {len(text)})")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال پیام: {e}")

def format_news_with_tag(text: str) -> str:
    """
    قالب‌بندی خبر با ❇️ و 🔹 و اضافه کردن هشتگ و آیدی کانال در انتها
    """
    from core.formatter import HASHTAG, CHANNEL_TAG

    if not text:
        return ""

    lines = text.splitlines()
    lines = [line.strip() for line in lines if line.strip()]
    if not lines:
        return ""

    title = lines[0]
    body = lines[1:]

    result = f"❇️ {title}\n"
    for line in body:
        result += f"🔹 {line}\n"

    # اضافه کردن هشتگ و آیدی کانال در انتهای هر خبر
    result += f"\n{HASHTAG}\n{CHANNEL_TAG}"
    return result

def extract_reply_chain(message: dict, chain=None):
    if chain is None:
        chain = []
    if not message:
        return chain
    media_info = get_media_from_message(message)
    chain.append({
        "text": media_info.get("text", ""),
        "media": media_info if media_info["type"] != "text" else None,
        "type": media_info.get("type", "text")
    })
    if "reply_to_message" in message and message["reply_to_message"]:
        try:
            extract_reply_chain(message["reply_to_message"], chain)
        except Exception as e:
            logger.warning(f"⚠️ خطا در استخراج پیام اصلی: {e}")
    return chain

def process_deep_reply(msg: dict) -> bool:
    if not msg or "reply_to_message" not in msg:
        return False

    chain = extract_reply_chain(msg)

    # اگر فقط یک آیتم وجود دارد (پیام اصلی در دسترس نبوده)
    if len(chain) == 1:
        item = chain[0]
        if item["text"]:
            formatted = format_news_with_tag(item["text"])
            if formatted:
                send_simple_message(formatted)
        if item["media"]:
            media = item["media"]
            send_media_to_channel(media["file_id"], media["type"], "")
        return True

    # معکوس کردن زنجیره (از قدیمی به جدید)
    chain.reverse()

    # ارسال هر خبر به صورت جداگانه با هشتگ و آیدی مخصوص خودش
    for item in chain:
        if item["text"]:
            formatted = format_news_with_tag(item["text"])
            if formatted:
                send_simple_message(formatted)

        if item["media"]:
            media = item["media"]
            send_media_to_channel(media["file_id"], media["type"], "")

    return True
