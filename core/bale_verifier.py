"""Verify that the centrally managed Bale bot can publish to a channel."""

import requests
from typing import Tuple

BALE_API_BASE = "https://tapi.bale.ai/bot"


def verify_bale_channel_admin(token: str, channel_id: str, request_post=None) -> Tuple[bool, str]:
    """Fail closed unless Bale confirms an admin/creator bot membership."""
    if not token:
        return False, "توکن مرکزی ربات بله تنظیم نشده است."
    post = request_post or requests.post
    base_url = f"{BALE_API_BASE}{token}"
    try:
        me_response = post(f"{base_url}/getMe", timeout=15)
        me_payload = me_response.json()
        if not me_response.ok or not me_payload.get("ok"):
            return False, "دریافت شناسه ربات بله ناموفق بود."
        bot_id = (me_payload.get("result") or {}).get("id")
        if bot_id is None:
            return False, "شناسه ربات بله دریافت نشد."
        member_response = post(
            f"{base_url}/getChatMember",
            json={"chat_id": channel_id, "user_id": bot_id},
            timeout=15,
        )
        payload = member_response.json()
        if not member_response.ok or not payload.get("ok"):
            return False, "کانال بله پیدا نشد یا ربات دسترسی ندارد."
        member = payload.get("result") or {}
        if member.get("status") not in {"administrator", "creator"}:
            return False, "ربات مرکزی بله باید مدیر کانال باشد."
        if member.get("can_post_messages") is False:
            return False, "مجوز ارسال پیام برای ربات بله فعال نیست."
        return True, "دسترسی انتشار ربات بله تأیید شد."
    except Exception as exc:
        return False, f"خطا در ارتباط با بله: {exc}"
