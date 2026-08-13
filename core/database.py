import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL و SUPABASE_KEY تنظیم نشده‌اند.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    print("✅ دیتابیس مقداردهی شد")

def get_tenant(user_id):
    try:
        result = supabase.table("tenants").select("*").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"❌ get_tenant: {e}")
        return None

def save_tenant(user_id, bot_token, telegram_channel, bale_channel=None, bale_token=None, hashtag=None, channel_tag=None):
    try:
        existing = get_tenant(user_id)
        data = {
            "bot_token": bot_token,
            "telegram_channel": telegram_channel,
            "bale_channel": bale_channel or "",
            "bale_token": bale_token or "",
            "hashtag": hashtag or "#دنیا_۲۴_نیوز",
            "channel_tag": channel_tag or "@Donya24News"
        }
        if existing:
            supabase.table("tenants").update(data).eq("user_id", user_id).execute()
        else:
            supabase.table("tenants").insert({
                "user_id": user_id,
                **data
            }).execute()
        return True
    except Exception as e:
        print(f"❌ save_tenant: {e}")
        return False
