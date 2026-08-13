from core.database import get_tenant, save_tenant

def get_branding(user_id):
    """
    دریافت هشتگ، آیدی کانال و اطلاعات بله برای یک کاربر
    """
    tenant = get_tenant(user_id)
    if tenant:
        return {
            "hashtag": tenant.get("hashtag", "#دنیا_۲۴_نیوز"),
            "channel_tag": tenant.get("channel_tag", "@Donya24News"),
            "bale_channel": tenant.get("bale_channel", ""),
            "bale_token": tenant.get("bale_token", "")
        }
    return {
        "hashtag": "#دنیا_۲۴_نیوز",
        "channel_tag": "@Donya24News",
        "bale_channel": "",
        "bale_token": ""
    }

def set_branding(user_id, hashtag=None, channel_tag=None):
    tenant = get_tenant(user_id)
    if tenant:
        save_tenant(
            user_id,
            tenant.get("bot_token", "TOKEN_TEMP"),
            tenant.get("telegram_channel", "@channel"),
            tenant.get("bale_channel", ""),
            tenant.get("bale_token", ""),
            hashtag or tenant.get("hashtag", "#دنیا_۲۴_نیوز"),
            channel_tag or tenant.get("channel_tag", "@Donya24News")
        )
    else:
        save_tenant(
            user_id,
            "TOKEN_TEMP",
            "@channel",
            "",
            "",
            hashtag or "#دنیا_۲۴_نیوز",
            channel_tag or "@Donya24News"
        )
