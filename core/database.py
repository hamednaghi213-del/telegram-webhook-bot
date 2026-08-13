import os
import logging
from supabase import create_client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise ValueError(
        "❌ متغیر محیطی SUPABASE_URL تنظیم نشده است."
    )

if not SUPABASE_KEY:
    raise ValueError(
        "❌ متغیر محیطی SUPABASE_KEY تنظیم نشده است."
    )

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():
    logger.info("✅ دیتابیس Supabase مقداردهی شد")
    return True


# =========================================================
# GET TENANT
# =========================================================

def get_tenant(user_id):

    try:

        result = (
            supabase
            .table("tenants")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]

        logger.info(
            f"ℹ️ tenant برای کاربر {user_id} پیدا نشد."
        )

        return None

    except Exception as e:

        logger.exception(
            f"❌ get_tenant({user_id}): {e}"
        )

        return None


# =========================================================
# SAVE TENANT
# =========================================================

def save_tenant(
    user_id,
    bot_token,
    telegram_channel,
    bale_channel=None,
    bale_token=None,
    hashtag=None,
    channel_tag=None
):

    try:

        data = {
            "bot_token": bot_token or "",
            "telegram_channel": telegram_channel or "",
            "bale_channel": bale_channel or "",
            "bale_token": bale_token or "",
            "hashtag": hashtag or "#دنیا_۲۴_نیوز",
            "channel_tag": channel_tag or "@Donya24News"
        }

        existing = get_tenant(user_id)

        if existing:

            result = (
                supabase
                .table("tenants")
                .update(data)
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(
                f"✅ تنظیمات کاربر {user_id} به‌روزرسانی شد."
            )

        else:

            insert_data = {
                "user_id": user_id,
                **data
            }

            result = (
                supabase
                .table("tenants")
                .insert(insert_data)
                .execute()
            )

            logger.info(
                f"✅ tenant جدید برای کاربر {user_id} ایجاد شد."
            )

        return bool(result.data)

    except Exception as e:

        logger.exception(
            f"❌ save_tenant({user_id}): {e}"
        )

        return False


# =========================================================
# UPDATE BALE SETTINGS
# =========================================================

def update_bale_settings(
    user_id,
    bale_channel,
    bale_token
):

    try:

        data = {
            "bale_channel": bale_channel or "",
            "bale_token": bale_token or ""
        }

        result = (
            supabase
            .table("tenants")
            .update(data)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:

            logger.info(
                f"✅ تنظیمات بله برای کاربر {user_id} ذخیره شد."
            )

            return True

        logger.warning(
            f"⚠️ tenant برای کاربر {user_id} پیدا نشد."
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ update_bale_settings({user_id}): {e}"
        )

        return False


# =========================================================
# GET BALE SETTINGS
# =========================================================

def get_bale_settings(user_id):

    tenant = get_tenant(user_id)

    if not tenant:
        return {
            "bale_channel": "",
            "bale_token": ""
        }

    return {
        "bale_channel": tenant.get(
            "bale_channel",
            ""
        ) or "",
        "bale_token": tenant.get(
            "bale_token",
            ""
        ) or ""
    }


# =========================================================
# DELETE BALE SETTINGS
# =========================================================

def disable_bale(user_id):

    try:

        result = (
            supabase
            .table("tenants")
            .update({
                "bale_channel": "",
                "bale_token": ""
            })
            .eq("user_id", user_id)
            .execute()
        )

        logger.info(
            f"🛑 تنظیمات بله برای کاربر {user_id} غیرفعال شد."
        )

        return bool(result.data)

    except Exception as e:

        logger.exception(
            f"❌ disable_bale({user_id}): {e}"
        )

        return False
