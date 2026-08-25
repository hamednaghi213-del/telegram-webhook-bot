import logging
import os

from core.database import (
    get_tenant,
    save_tenant,
    update_bale_settings
)

logger = logging.getLogger(__name__)

DEFAULT_HASHTAG = "#دنیا_۲۴_نیوز"
DEFAULT_CHANNEL_TAG = "@Donya24News"


# =========================================================
# GET BRANDING
# =========================================================

def get_branding(user_id):

    tenant = get_tenant(user_id)

    if not tenant:

        return {
            "hashtag": DEFAULT_HASHTAG,
            "channel_tag": DEFAULT_CHANNEL_TAG,
            "bale_channel": "",
            "bale_token": ""
        }

    return {
        "hashtag": (
            tenant.get("hashtag")
            or DEFAULT_HASHTAG
        ),

        "channel_tag": (
            tenant.get("channel_tag")
            or DEFAULT_CHANNEL_TAG
        ),

        "bale_channel": (
            tenant.get("bale_channel")
            or ""
        ),

        "bale_token": (
            os.getenv("BALE_BOT_TOKEN", "").strip()
            or tenant.get("bale_token")
            or ""
        )
    }


# =========================================================
# SET BRANDING
# =========================================================

def set_branding(
    user_id,
    hashtag=None,
    channel_tag=None
):

    tenant = get_tenant(user_id)

    if tenant:

        bot_token = (
            tenant.get("bot_token")
            or "TOKEN_TEMP"
        )

        telegram_channel = (
            tenant.get("telegram_channel")
            or "@channel"
        )

        bale_channel = (
            tenant.get("bale_channel")
            or ""
        )

        bale_token = (
            tenant.get("bale_token")
            or ""
        )

    else:

        bot_token = "TOKEN_TEMP"
        telegram_channel = "@channel"
        bale_channel = ""
        bale_token = ""

    success = save_tenant(
        user_id=user_id,
        bot_token=bot_token,
        telegram_channel=telegram_channel,
        bale_channel=bale_channel,
        bale_token=bale_token,
        hashtag=hashtag or DEFAULT_HASHTAG,
        channel_tag=channel_tag or DEFAULT_CHANNEL_TAG
    )

    if success:

        logger.info(
            f"✅ Branding برای کاربر {user_id} ذخیره شد."
        )

    else:

        logger.error(
            f"❌ ذخیره Branding برای کاربر {user_id} ناموفق بود."
        )

    return success


# =========================================================
# SET BALE
# =========================================================

def set_bale(
    user_id,
    bale_channel,
    bale_token
):

    if not bale_channel or not bale_token:

        logger.warning(
            f"⚠️ اطلاعات بله برای کاربر {user_id} ناقص است."
        )

        return False

    success = update_bale_settings(
        user_id,
        bale_channel,
        bale_token
    )

    if success:

        logger.info(
            f"✅ تنظیمات بله برای کاربر {user_id} ذخیره شد."
        )

    else:

        logger.error(
            f"❌ ذخیره تنظیمات بله برای کاربر {user_id} ناموفق بود."
        )

    return success


# =========================================================
# GET BALE
# =========================================================

def get_bale(user_id):

    branding = get_branding(user_id)

    return {
        "bale_channel": branding.get(
            "bale_channel",
            ""
        ),

        "bale_token": branding.get(
            "bale_token",
            ""
        )
    }


# =========================================================
# DISABLE BALE
# =========================================================

def disable_bale(user_id):

    success = update_bale_settings(
        user_id,
        "",
        ""
    )

    if success:

        logger.info(
            f"🛑 بله برای کاربر {user_id} غیرفعال شد."
        )

    return success
