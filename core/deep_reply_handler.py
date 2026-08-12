import logging
import requests
from core.formatter import format_news

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

def send_simple_message(text: str, reply_to_id=None):
    try:
        payload = {"chat_id": CHANNEL_ID, "text": text}
        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id
        resp = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال پیام: {e}")
        return None

def send_media_to_channel(file_id: str, media_type: str, caption: str = "", reply_to_id=None):
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
            return None
        payload = {"chat_id": CHANNEL_ID, media_type: file_id, "caption": caption}
        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id
        resp = requests.post(endpoint, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال {media_type}: {e}")
        return None

def send_long_to_channel(text: str):
    from core.formatter import HASHTAG, CHANNEL_TAG
    text = text + f"\n\n{HASHTAG}\n{CHANNEL_TAG}"
    max_len = 4096
    if len(text) <= max_len:
        send_simple_message(text)
        return
    parts = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        if end < len(text):
            last_newline = text.rfind('\n', start, end)
            last_space = text.rfind(' ', start, end)
            cut_at = max(last_newline, last_space)
            if cut_at > start:
                end = cut_at + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    for i, part in enumerate(parts):
        if len(parts) > 1:
            part = f"({i+1}/{len(parts)})\n{part}"
        send_simple_message(part)
        import time
        time.sleep(0.5)

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

def process_deep_reply(msg: dict, chat_id: int) -> bool:
    if not msg or "reply_to_message" not in msg:
        return False

    chain = extract_reply_chain(msg)

    if len(chain) == 1:
        item = chain[0]
        if item["text"]:
            formatted = format_news(item["text"])
            if formatted:
                send_long_to_channel(formatted)
        if item["media"]:
            media = item["media"]
            send_media_to_channel(media["file_id"], media["type"], "")
        return True

    chain.reverse()

    for item in chain:
        if item["text"]:
            formatted = format_news(item["text"])
            if formatted:
                send_long_to_channel(formatted)
        if item["media"]:
            media = item["media"]
            send_media_to_channel(media["file_id"], media["type"], "")

    return True
