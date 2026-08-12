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
    return "reply_to_message" in message

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

def send_simple_message(text: str):
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

def extract_reply_chain(message: dict, chain=None):
    """استخراج زنجیره ریپلای با مدیریت خطا"""
    if chain is None:
        chain = []
    
    # اگر پیام فعلی وجود ندارد، برگرد
    if not message:
        return chain
    
    media_info = get_media_from_message(message)
    chain.append({
        "text": media_info.get("text", ""),
        "media": media_info if media_info["type"] != "text" else None,
        "type": media_info.get("type", "text")
    })
    
    # اگر reply_to_message وجود دارد، بازگشتی برو
    if "reply_to_message" in message and message["reply_to_message"]:
        # بررسی کن که reply_to_message یک دیکشنری معتبر باشد
        try:
            extract_reply_chain(message["reply_to_message"], chain)
        except Exception as e:
            logger.warning(f"⚠️ خطا در استخراج پیام اصلی: {e}")
    
    return chain

def process_deep_reply(msg: dict) -> bool:
    if not msg or "reply_to_message" not in msg:
        return False
    
    # استخراج زنجیره
    chain = extract_reply_chain(msg)
    
    # اگر فقط یک آیتم وجود دارد (یعنی reply_to_message معتبر نبوده)، فقط همان را پردازش کن
    if len(chain) == 1:
        # فقط خود پیام را پردازش کن (مثل حالت عادی)
        item = chain[0]
        if item["text"]:
            formatted = format_news(item["text"])
            if formatted:
                send_long_to_channel(formatted)
        if item["media"]:
            media = item["media"]
            send_media_to_channel(media["file_id"], media["type"], "")
        return True
    
    # معکوس کردن زنجیره (از قدیمی به جدید)
    chain.reverse()
    
    # ساخت متن کامل با چیدمان بهتر
    full_text = ""
    for i, item in enumerate(chain):
        if item["text"]:
            formatted = format_news(item["text"])
            if formatted:
                # حذف فاصله‌های اضافی و خطوط خالی
                formatted = formatted.strip()
                if i == 0:
                    full_text += f"📌 خبر اصلی:\n{formatted}\n\n"
                else:
                    full_text += f"🔄 پاسخ:\n{formatted}\n\n"
    
    # ارسال متن ترکیبی
    if full_text:
        # حذف فضاهای اضافی انتهایی
        full_text = full_text.rstrip()
        send_long_to_channel(full_text)
    
    # ارسال ضمیمه‌ها (به ترتیب)
    for item in chain:
        if item["media"]:
            media = item["media"]
            # برای ضمیمه‌ها، کپشن خالی می‌فرستیم چون قبلاً متن کامل ارسال شده
            send_media_to_channel(media["file_id"], media["type"], "")
    
    return True
