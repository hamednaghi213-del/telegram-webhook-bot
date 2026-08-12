import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL و SUPABASE_KEY در متغیرهای محیطی تنظیم نشده‌اند.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    pass

def get_tenant(user_id):
    try:
        result = supabase.table("tenants").select("*").eq("user_id", user_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"❌ خطا در get_tenant: {e}")
        return None

def save_tenant(user_id, bot_token, telegram_channel, bale_channel=None, bale_token=None):
    try:
        existing = get_tenant(user_id)
        if existing:
            supabase.table("tenants").update({
                "bot_token": bot_token,
                "telegram_channel": telegram_channel,
                "bale_channel": bale_channel,
                "bale_token": bale_token
            }).eq("user_id", user_id).execute()
        else:
            supabase.table("tenants").insert({
                "user_id": user_id,
                "bot_token": bot_token,
                "telegram_channel": telegram_channel,
                "bale_channel": bale_channel,
                "bale_token": bale_token
            }).execute()
        return True
    except Exception as e:
        print(f"❌ خطا در save_tenant: {e}")
        return False
