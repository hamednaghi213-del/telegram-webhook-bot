"""
Phase 4B — Real Telegram Channel Verification
Uses getChatMember to confirm bot is administrator with post rights.
"""
import logging
import requests
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_BOT_ID_CACHE: Dict[str, int] = {}


def reset_bot_id_cache() -> None:
    """Reset the cached bot ID (for testing)."""
    _BOT_ID_CACHE.clear()


def get_bot_id(api_url: str) -> Optional[int]:
    """Return the bot's own Telegram user ID, cached after first call."""
    cached_bot_id = _BOT_ID_CACHE.get(api_url)
    if cached_bot_id is not None:
        return cached_bot_id
    try:
        r = requests.get(f"{api_url}/getMe", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("result", {}).get("id"):
                bot_id = int(data["result"]["id"])
                _BOT_ID_CACHE[api_url] = bot_id
                logger.info(f"Bot ID cached: {bot_id}")
                return bot_id
        logger.error(f"getMe failed: status={r.status_code}")
        return None
    except Exception as e:
        logger.exception(f"getMe exception: {e}")
        return None


def verify_channel_admin(api_url: str, external_id: str) -> Tuple[bool, str]:
    """
    Verify that the bot is an administrator with can_post_messages in the channel.

    Returns (verified: bool, note: str).
    note is a Persian explanation for the user on failure.

    Never raises; errors are caught and returned as (False, message).
    """
    try:
        bot_id = get_bot_id(api_url)
        if not bot_id:
            return False, "نمی‌توان اطلاعات ربات را دریافت کرد"

        params = {"chat_id": external_id, "user_id": bot_id}
        r = requests.get(f"{api_url}/getChatMember", params=params, timeout=10)

        if r.status_code != 200:
            logger.warning(f"getChatMember HTTP {r.status_code} for {external_id}")
            data = {}
            try:
                data = r.json() or {}
            except Exception:
                data = {}
            desc = (data.get("description") or "").lower()
            if "chat not found" in desc or "invalid" in desc:
                return False, "کانال یافت نشد یا نامعتبر است"
            return False, "خطا در بررسی دسترسی کانال"

        data = r.json()
        if not data.get("ok"):
            desc = (data.get("description") or "").lower()
            logger.warning(f"getChatMember not ok: {desc}")
            if "chat not found" in desc or "invalid" in desc:
                return False, "کانال یافت نشد یا نامعتبر است"
            return False, "خطا در دریافت اطلاعات عضویت ربات"

        member = data.get("result", {}) or {}
        status = member.get("status", "")

        if status not in ("administrator", "creator"):
            logger.info(f"Bot status={status} in {external_id} — not admin")
            return False, "ربات مدیر (ادمین) کانال نیست"

        if status == "administrator":
            if not member.get("can_post_messages", False):
                logger.info(f"Bot lacks can_post_messages in {external_id}")
                return False, "ربات مجوز ارسال پیام در کانال را ندارد"

        logger.info(f"Channel verified: {external_id} status={status}")
        return True, "تأیید شد"

    except requests.RequestException as e:
        logger.warning(f"Network error verifying {external_id}: {e}")
        return False, "خطای شبکه در بررسی دسترسی"
    except Exception as e:
        logger.exception(f"Unexpected error verifying {external_id}: {e}")
        return False, "خطای داخلی در بررسی دسترسی"
