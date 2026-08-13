import logging
import requests

from core.database import (
    get_tenant,
    save_tenant,
    update_bale_settings
)

logger = logging.getLogger(__name__)

API_URL = None


# =========================================================
# INITIALIZE
# =========================================================

def initialize(api_url):
    global API_URL

    API_URL = api_url

    logger.info(
        "✅ Command Handler initialized"
    )


# =========================================================
# COMMAND DETECTION
# =========================================================

def is_command(text):

    if not text:
        return False

    return text.strip().startswith("/")


# =========================================================
# SEND MESSAGE
# =========================================================

def send_message(chat_id, text):

    if not API_URL:
        logger.error(
            "❌ API_URL در Command Handler تنظیم نشده است."
        )
        return False

    try:

        response = requests.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=30
        )

        if response.status_code != 200:

            logger.error(
                f"❌ Telegram sendMessage error: "
                f"{response.text}"
            )

            return False

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطا در ارسال پیام Command Handler: {e}"
        )

        return False


# =========================================================
# REGISTER
# =========================================================

def handle_register(chat_id):

    tenant = get_tenant(chat_id)

    if tenant:

        send_message(
            chat_id,
            "✅ شما قبلاً ثبت‌نام کرده‌اید.\n\n"
            "برای مشاهده وضعیت تنظیمات از /status استفاده کنید."
        )

        return True

    success = save_tenant(
        user_id=chat_id,
        bot_token="TOKEN_TEMP",
        telegram_channel="@channel",
        bale_channel="",
        bale_token="",
        hashtag="#دنیا_۲۴_نیوز",
        channel_tag="@Donya24News"
    )

    if success:

        send_message(
            chat_id,
            "✅ ثبت‌نام شما با موفقیت انجام شد.\n\n"
            "ابتدا کانال تلگرام را تنظیم کنید:\n"
            "/settelegram @channel\n\n"
            "سپس در صورت نیاز کانال بله را تنظیم کنید:\n"
            "/setbale @channel\n\n"
            "و توکن ربات بله را وارد کنید:\n"
            "/setbaletoken TOKEN"
        )

    else:

        send_message(
            chat_id,
            "❌ ثبت‌نام انجام نشد. لطفاً دوباره تلاش کنید."
        )

    return True


# =========================================================
# SET TELEGRAM CHANNEL
# =========================================================

def handle_settelegram(text, chat_id):

    parts = text.split()

    if len(parts) < 2:

        send_message(
            chat_id,
            "❌ فرمت صحیح:\n\n"
            "/settelegram @channel"
        )

        return True

    channel = parts[1].strip()

    tenant = get_tenant(chat_id)

    if not tenant:

        send_message(
            chat_id,
            "❌ ابتدا با /register ثبت‌نام کنید."
        )

        return True

    success = save_tenant(
        user_id=chat_id,

        bot_token=(
            tenant.get("bot_token")
            or "TOKEN_TEMP"
        ),

        telegram_channel=channel,

        bale_channel=(
            tenant.get("bale_channel")
            or ""
        ),

        bale_token=(
            tenant.get("bale_token")
            or ""
        ),

        hashtag=(
            tenant.get("hashtag")
            or "#دنیا_۲۴_نیوز"
        ),

        channel_tag=(
            tenant.get("channel_tag")
            or "@Donya24News"
        )
    )

    if success:

        send_message(
            chat_id,
            f"✅ کانال تلگرام با موفقیت تنظیم شد:\n"
            f"{channel}"
        )

    else:

        send_message(
            chat_id,
            "❌ ذخیره کانال تلگرام انجام نشد."
        )

    return True


# =========================================================
# SET BALE CHANNEL
# =========================================================

def handle_setbale(text, chat_id):

    parts = text.split()

    if len(parts) < 2:

        send_message(
            chat_id,
            "❌ فرمت صحیح:\n\n"
            "/setbale @channel"
        )

        return True

    bale_channel = parts[1].strip()

    tenant = get_tenant(chat_id)

    if not tenant:

        send_message(
            chat_id,
            "❌ ابتدا با /register ثبت‌نام کنید."
        )

        return True

    # فقط تنظیمات بله را تغییر می‌دهیم
    success = update_bale_settings(
        chat_id,
        bale_channel,
        tenant.get("bale_token", "") or ""
    )

    if success:

        send_message(
            chat_id,
            f"✅ کانال بله با موفقیت تنظیم شد:\n"
            f"{bale_channel}"
        )

        logger.info(
            f"✅ BALE CHANNEL SET | "
            f"user={chat_id} | "
            f"channel={bale_channel}"
        )

    else:

        send_message(
            chat_id,
            "❌ ذخیره کانال بله انجام نشد."
        )

    return True


# =========================================================
# SET BALE TOKEN
# =========================================================

def handle_setbaletoken(text, chat_id):

    parts = text.split()

    if len(parts) < 2:

        send_message(
            chat_id,
            "❌ فرمت صحیح:\n\n"
            "/setbaletoken TOKEN"
        )

        return True

    bale_token = parts[1].strip()

    tenant = get_tenant(chat_id)

    if not tenant:

        send_message(
            chat_id,
            "❌ ابتدا با /register ثبت‌نام کنید."
        )

        return True

    success = update_bale_settings(
        chat_id,
        tenant.get("bale_channel", "") or "",
        bale_token
    )

    if success:

        send_message(
            chat_id,
            "✅ توکن بله با موفقیت ذخیره شد."
        )

        logger.info(
            f"✅ BALE TOKEN SET | user={chat_id}"
        )

    else:

        send_message(
            chat_id,
            "❌ ذخیره توکن بله انجام نشد."
        )

    return True


# =========================================================
# STATUS
# =========================================================

def handle_status(chat_id):

    tenant = get_tenant(chat_id)

    if not tenant:

        send_message(
            chat_id,
            "❌ شما هنوز ثبت‌نام نکرده‌اید.\n\n"
            "/register"
        )

        return True

    telegram_channel = (
        tenant.get("telegram_channel")
        or "تنظیم نشده"
    )

    bale_channel = (
        tenant.get("bale_channel")
        or "تنظیم نشده"
    )

    bale_token_exists = bool(
        tenant.get("bale_token")
    )

    status_text = (
        "📊 وضعیت ربات\n\n"
        f"کانال تلگرام: {telegram_channel}\n"
        f"کانال بله: {bale_channel}\n"
        f"توکن بله: "
        f"{'✅ تنظیم شده' if bale_token_exists else '❌ تنظیم نشده'}"
    )

    send_message(
        chat_id,
        status_text
    )

    return True


# =========================================================
# HELP
# =========================================================

def handle_help(chat_id):

    text = (
        "📚 راهنمای ربات\n\n"

        "/register\n"
        "ثبت‌نام در ربات\n\n"

        "/settelegram @channel\n"
        "تنظیم کانال تلگرام\n\n"

        "/setbale @channel\n"
        "تنظیم کانال بله\n\n"

        "/setbaletoken TOKEN\n"
        "تنظیم توکن ربات بله\n\n"

        "/status\n"
        "مشاهده وضعیت تنظیمات\n\n"

        "/help\n"
        "نمایش راهنما"
    )

    send_message(
        chat_id,
        text
    )

    return True


# =========================================================
# START
# =========================================================

def handle_start(chat_id):

    send_message(
        chat_id,
        "👋 به ربات خبری خوش آمدید.\n\n"
        "برای شروع از /register استفاده کنید."
    )

    return True


# =========================================================
# MAIN COMMAND HANDLER
# =========================================================

def handle_command(text, chat_id):

    if not text:
        return False

    text = text.strip()

    if not text.startswith("/"):
        return False

    # حذف @BotName از دستور
    command_part = text.split()[0]

    command_part = command_part.split("@")[0]

    command = command_part[1:].lower()

    logger.info(
        f"📌 COMMAND | user={chat_id} | command=/{command}"
    )

    # -------------------------
    # REGISTER
    # -------------------------

    if command == "register":

        return handle_register(
            chat_id
        )

    # -------------------------
    # SET TELEGRAM
    # -------------------------

    elif command == "settelegram":

        return handle_settelegram(
            text,
            chat_id
        )

    # -------------------------
    # SET BALE CHANNEL
    # -------------------------

    elif command == "setbale":

        return handle_setbale(
            text,
            chat_id
        )

    # -------------------------
    # SET BALE TOKEN
    # -------------------------

    elif command == "setbaletoken":

        return handle_setbaletoken(
            text,
            chat_id
        )

    # -------------------------
    # STATUS
    # -------------------------

    elif command == "status":

        return handle_status(
            chat_id
        )

    # -------------------------
    # HELP
    # -------------------------

    elif command == "help":

        return handle_help(
            chat_id
        )

    # -------------------------
    # START
    # -------------------------

    elif command == "start":

        return handle_start(
            chat_id
        )

    # -------------------------
    # UNKNOWN COMMAND
    # -------------------------

    else:

        send_message(
            chat_id,
            f"❌ دستور /{command} شناسایی نشد.\n\n"
            "برای مشاهده دستورات:\n"
            "/help"
        )

        return True
