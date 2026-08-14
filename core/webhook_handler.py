import logging
import uuid
import secrets
import requests
from typing import Dict, Tuple, Optional, Any
from flask import request

logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL: Optional[str] = None
CHANNEL_ID: Optional[str] = None
SECRET_TOKEN: Optional[str] = None
WEBHOOK_INITIALIZED: bool = False


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    api_url: str,
    channel_id: str,
    secret_token: str
) -> None:
    """
    مقداردهی Webhook Handler
    
    Args:
        api_url: آدرس API تلگرام (مثل https://api.telegram.org/bot<TOKEN>)
        channel_id: آیدی کانال مقصد
        secret_token: رمز مخفی برای اعتبارسنجی Webhook
    
    Raises:
        ValueError: اگر هر یک از پارامترها خالی باشند
        
    Example:
        >>> initialize(
        ...     "https://api.telegram.org/bot123",
        ...     "@mychannel",
        ...     "my_secret_token_123"
        ... )
    """
    global API_URL, CHANNEL_ID, SECRET_TOKEN, WEBHOOK_INITIALIZED
    
    if not api_url:
        raise ValueError("❌ api_url cannot be empty")
    
    if not channel_id:
        raise ValueError("❌ channel_id cannot be empty")
    
    if not secret_token:
        raise ValueError(
            "❌ secret_token cannot be empty (SECURITY REQUIRED)"
        )
    
    API_URL = api_url.rstrip("/")
    CHANNEL_ID = channel_id
    SECRET_TOKEN = secret_token
    WEBHOOK_INITIALIZED = True
    
    logger.info(
        f"✅ Webhook Handler initialized | "
        f"channel={CHANNEL_ID}"
    )


# =========================================================
# VALIDATE SECRET TOKEN
# =========================================================

def validate_webhook_token() -> bool:
    """
    اعتبارسنجی Secret Token از HTTP Header
    
    از secrets.compare_digest برای جلوگیری از Timing Attack استفاده می‌کند.
    
    Returns:
        True اگر توکن معتبر باشد
        False اگر توکن missing یا نامعتبر باشد
    """
    if not WEBHOOK_INITIALIZED:
        logger.error(
            "❌ Webhook Handler not initialized! "
            "Call initialize() first"
        )
        return False
    
    if not SECRET_TOKEN:
        logger.error(
            "❌ SECRET_TOKEN is not configured! "
            "This is a SECURITY risk!"
        )
        return False
    
    request_token = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )
    
    if not request_token:
        logger.warning(
            "⚠️ Missing X-Telegram-Bot-Api-Secret-Token header"
        )
        return False
    
    # مقایسه امن (constant-time)
    is_valid = secrets.compare_digest(request_token, SECRET_TOKEN)
    
    if not is_valid:
        logger.error(
            f"❌ Invalid secret token | "
            f"expected_length={len(SECRET_TOKEN)} | "
            f"received_length={len(request_token)}"
        )
        return False
    
    logger.debug("✅ Secret token validated")
    return True


# =========================================================
# GET MESSAGE TEXT
# =========================================================

def get_message_text(msg: Dict[str, Any]) -> str:
    """
    استخراج متن یا کپشن از پیام تلگرام
    
    Args:
        msg: Message object از Telegram
        
    Returns:
        متن پیام یا کپشن، یا خالی
    """
    if msg.get("caption"):
        return msg["caption"]
    if msg.get("text"):
        return msg["text"]
    return ""


# =========================================================
# GET MEDIA FROM MESSAGE
# =========================================================

def get_media_from_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    استخراج اطلاعات رسانه از پیام تلگرام
    
    Args:
        msg: Message object از Telegram
    
    Returns:
        {
            "type": "photo" | "video" | "document" | "voice" | "audio" | None,
            "file_id": str | None,
            "caption": str
        }
    """
    result: Dict[str, Any] = {
        "type": None,
        "file_id": None,
        "caption": ""
    }
    
    if "video" in msg:
        result["type"] = "video"
        result["file_id"] = msg["video"].get("file_id")
        result["caption"] = msg.get("caption", "")
    elif "photo" in msg:
        photos = msg["photo"]
        if photos:
            result["type"] = "photo"
            result["file_id"] = photos[-1].get("file_id")
            result["caption"] = msg.get("caption", "")
    elif "document" in msg:
        result["type"] = "document"
        result["file_id"] = msg["document"].get("file_id")
        result["caption"] = msg.get("caption", "")
    elif "voice" in msg:
        result["type"] = "voice"
        result["file_id"] = msg["voice"].get("file_id")
        result["caption"] = msg.get("caption", "")
    elif "audio" in msg:
        result["type"] = "audio"
        result["file_id"] = msg["audio"].get("file_id")
        result["caption"] = msg.get("caption", "")
    
    return result


# =========================================================
# SEND MESSAGE TO USER
# =========================================================

def send_message(
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = None
) -> bool:
    """
    ارسال پیام به کاربر (چت خصوصی)
    
    Args:
        chat_id: شناسه چت کاربر
        text: متن پیام
        parse_mode: نوع فرمت (HTML, Markdown, etc.)
        
    Returns:
        True اگر ارسال موفق باشد
    """
    if not API_URL:
        logger.error("❌ API_URL not configured")
        return False
    
    try:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )
        
        if resp.status_code == 200:
            logger.debug(f"✅ Message sent to {chat_id}")
            return True
        
        logger.error(
            f"❌ send_message failed | "
            f"status={resp.status_code} | "
            f"response={resp.text[:200]}"
        )
        return False
        
    except Exception as e:
        logger.exception(f"❌ send_message error: {e}")
        return False


# =========================================================
# SEND TO CHANNEL (TEXT)
# =========================================================

def send_to_channel(
    text: str,
    parse_mode: Optional[str] = None
) -> bool:
    """
    ارسال متن به کانال اصلی
    
    Args:
        text: متن برای ارسال
        parse_mode: نوع فرمت (HTML, Markdown, etc.)
        
    Returns:
        True اگر ارسال موفق باشد
    """
    if not API_URL or not CHANNEL_ID:
        logger.error("❌ API_URL or CHANNEL_ID not configured")
        return False
    
    try:
        payload: Dict[str, Any] = {
            "chat_id": CHANNEL_ID,
            "text": text
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )
        
        if resp.status_code == 200:
            logger.info(
                f"✅ متن به کانال اصلی ارسال شد ({len(text)} chars)"
            )
            return True
        
        logger.error(
            f"❌ send_to_channel failed | "
            f"status={resp.status_code} | "
            f"response={resp.text[:200]}"
        )
        return False
        
    except Exception as e:
        logger.exception(f"❌ send_to_channel error: {e}")
        return False


# =========================================================
# WEBHOOK HANDLER
# =========================================================

def handle_webhook() -> Tuple[Dict[str, Any], int]:
    """
    پردازش اصلی Webhook با اعتبارسنجی امنیتی
    
    Returns:
        Tuple[response_dict, status_code]
    """
    req_id = str(uuid.uuid4())[:8]
    logger.info(f"[{req_id}] 📥 دریافت درخواست Webhook")
    
    try:
        # ================================================
        # SECURITY: Validate Secret Token
        # ================================================
        
        if not validate_webhook_token():
            logger.error(
                f"[{req_id}] 🔒 Webhook validation failed - "
                "rejecting request"
            )
            return {"ok": False}, 403
        
        logger.info(f"[{req_id}] 🔓 Webhook token validated ✅")
        
        # ================================================
        # GET JSON DATA
        # ================================================
        
        data = request.get_json(silent=True)
        
        if not data:
            logger.warning(f"[{req_id}] ⚠️ Webhook بدون JSON")
            return {"ok": True}, 200
        
        if "message" not in data:
            logger.info(f"[{req_id}] ℹ️ Update فاقد message است.")
            return {"ok": True}, 200
        
        msg = data["message"]
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        
        if not chat_id:
            logger.error(f"[{req_id}] ❌ chat_id پیدا نشد.")
            return {"ok": True}, 200
        
        # ================================================
        # EXTRACT TEXT / CAPTION & ENTITIES
        # ================================================
        
        text = get_message_text(msg)
        caption_entities = msg.get("caption_entities", [])
        entities = msg.get("entities", [])
        
        logger.info(f"[{req_id}] 📩 پیام از chat_id={chat_id}")
        
        if text:
            logger.debug(
                f"[{req_id}] متن: {text[:50]}... | "
                f"entities={len(entities)} | "
                f"caption_entities={len(caption_entities)}"
            )
        
        # ================================================
        # COMMAND DETECTION
        # ================================================
        
        if text and text.startswith("/"):
            logger.info(f"[{req_id}] ⚙️ Command: {text}")
            
            try:
                from core.command_handler import handle_command
                handle_command(text, chat_id)
            except Exception as e:
                logger.exception(
                    f"[{req_id}] ❌ Error handling command: {e}"
                )
            
            return {"ok": True}, 200
        
        # ================================================
        # TENANT VALIDATION
        # ================================================
        
        try:
            from core.database import get_tenant
            tenant = get_tenant(chat_id)
        except Exception as e:
            logger.exception(f"[{req_id}] ❌ Error getting tenant: {e}")
            send_message(
                chat_id,
                "❌ خطای دیتابیسی. لطفاً بعداً تلاش کنید."
            )
            return {"ok": True}, 200
        
        if not tenant or not tenant.get("telegram_channel"):
            logger.warning(
                f"[{req_id}] ⚠️ Telegram channel تنظیم نشده."
            )
            send_message(
                chat_id,
                "❌ ابتدا با /register ثبت‌نام و کانال را تنظیم کنید."
            )
            return {"ok": True}, 200
        
        # ================================================
        # MEDIA DETECTION
        # ================================================
        
        media_info = get_media_from_message(msg)
        media_type = media_info.get("type")
        file_id = media_info.get("file_id")
        caption = text if text else media_info.get("caption", "")
        
        # ================================================
        # MEDIA GROUP (ALBUM)
        # ================================================
        
        if media_type and msg.get("media_group_id"):
            logger.info(
                f"[{req_id}] 🖼️ Media Group detected | "
                f"type={media_type} | "
                f"group_id={msg.get('media_group_id')}"
            )
            
            try:
                from core.media_handler import (
                    handle_media_group_message
                )
                
                handle_media_group_message(
                    msg,
                    file_id,
                    media_type,
                    caption
                )
                
                send_message(
                    chat_id,
                    "✅ آلبوم شما در حال پردازش است..."
                )
                
            except Exception as e:
                logger.exception(
                    f"[{req_id}] ❌ Error handling media group: {e}"
                )
                send_message(
                    chat_id,
                    "❌ خطا در پردازش آلبوم"
                )
            
            return {"ok": True}, 200
        
        # ================================================
        # SINGLE MEDIA
        # ================================================
        
        if media_type and file_id:
            logger.info(
                f"[{req_id}] 🎞️ Single Media | "
                f"type={media_type}"
            )
            
            try:
                from core.media_sender import send_media_to_channel
                from core.formatter import format_news
                from core.branding_manager import get_branding
                
                # Format caption with branding
                formatted_caption = (
                    format_news(caption) if caption else ""
                )
                
                branding = get_branding(chat_id)
                hashtag = branding.get("hashtag", "")
                channel_tag = branding.get("channel_tag", "")
                
                if hashtag or channel_tag:
                    branding_text = ""
                    if hashtag:
                        branding_text += f"\n\n{hashtag}"
                    if channel_tag:
                        branding_text += f"\n{channel_tag}"
                    formatted_caption += branding_text
                
                # Send to Telegram
                success = send_media_to_channel(
                    API_URL,
                    CHANNEL_ID,
                    file_id,
                    media_type,
                    formatted_caption
                )
                
                if success:
                    logger.info(
                        f"[{req_id}] ✅ رسانه به کانال ارسال شد"
                    )
                    send_message(
                        chat_id,
                        "✅ خبر تصویری/ویدیویی شما "
                        "در کانال منتشر شد."
                    )
                    
                    # Send to Bale
                    try:
                        from core.bale_forwarder import (
                            send_to_bale_for_user
                        )
                        send_to_bale_for_user(
                            chat_id,
                            formatted_caption,
                            file_id,
                            media_type
                        )
                    except Exception as e:
                        logger.error(
                            f"[{req_id}] ❌ Error sending to Bale: {e}"
                        )
                else:
                    logger.error(
                        f"[{req_id}] ❌ رسانه ارسال نشد"
                    )
                    send_message(
                        chat_id,
                        "❌ ارسال رسانه با مشکل روبرو شد."
                    )
                
            except Exception as e:
                logger.exception(
                    f"[{req_id}] ❌ Error sending media: {e}"
                )
                send_message(
                    chat_id,
                    "❌ خطا در ارسال رسانه"
                )
            
            return {"ok": True}, 200
        
        # ================================================
        # TEXT MESSAGE
        # ================================================
        
        if text and text.strip():
            logger.info(f"[{req_id}] 📝 پیام متنی دریافت شد")
            
            try:
                from core.formatter import format_news
                from core.bale_forwarder import send_to_bale_for_user
                from core.content_entities import build_full_html
                
                # Format text
                formatted = format_news(text)
                
                if formatted:
                    # اگر entities موجود است، build_full_html استفاده کن
                    if entities or caption_entities:
                        try:
                            html_content = build_full_html(
                                text,
                                entities or caption_entities
                            )
                            logger.info(
                                f"[{req_id}] Built HTML with entities"
                            )
                            success = send_to_channel(
                                html_content,
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[{req_id}] Fallback to plain text: {e}"
                            )
                            success = send_to_channel(formatted)
                    else:
                        success = send_to_channel(formatted)
                    
                    if success:
                        logger.info(
                            f"[{req_id}] ✅ متن به کانال ارسال شد"
                        )
                        send_message(
                            chat_id,
                            "✅ خبر شما در کانال منتشر شد."
                        )
                        
                        # Send to Bale
                        try:
                            send_to_bale_for_user(
                                chat_id,
                                formatted
                            )
                        except Exception as e:
                            logger.error(
                                f"[{req_id}] ❌ Error sending to Bale: {e}"
                            )
                    else:
                        logger.error(
                            f"[{req_id}] ❌ متن ارسال نشد"
                        )
                        send_message(
                            chat_id,
                            "❌ ارسال خبر به کانال "
                            "با مشکل روبرو شد."
                        )
                else:
                    logger.warning(
                        f"[{req_id}] متن قابل پردازش نیست"
                    )
                    send_message(
                        chat_id,
                        "❌ خبر قابل پردازش نیست."
                    )
                
            except Exception as e:
                logger.exception(
                    f"[{req_id}] ❌ Error processing text: {e}"
                )
                send_message(
                    chat_id,
                    "❌ خطا در پردازش پیام"
                )
        
        else:
            logger.warning(f"[{req_id}] ⚠️ پیام خالی است")
            send_message(chat_id, "❌ پیام خالی است.")
        
        return {"ok": True}, 200
    
    except Exception as e:
        logger.exception(
            f"[{req_id}] ❌ خطا در Webhook Handler: {e}"
        )
        return {
            "ok": False,
            "error": str(e)
        }, 500
