import logging
import requests
import re
from typing import Optional, Dict, Any, Tuple

from core.database import (
    get_tenant,
    save_tenant,
    update_bale_settings,
    get_user_by_telegram_id,
    get_or_create_user_by_telegram_id,
    create_workspace,
    list_owned_workspaces,
    get_workspace_member,
    add_workspace_member,
    update_workspace_member_role,
    update_workspace_member_status
)

logger = logging.getLogger(__name__)

# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL: Optional[str] = None
COMMAND_HANDLER_INITIALIZED: bool = False

# Validation Constants
CHANNEL_PATTERN = re.compile(r"^@[a-zA-Z0-9_]{5,32}$")
TOKEN_MIN_LENGTH = 10
TOKEN_MAX_LENGTH = 255
CHANNEL_MIN_LENGTH = 6
CHANNEL_MAX_LENGTH = 33
DEFAULT_WORKSPACE_NAME = "رسانه من"


# =========================================================
# INITIALIZE
# =========================================================

def initialize(api_url: str) -> None:
    """
    مقداردهی Command Handler
    
    Args:
        api_url: آدرس API تلگرام
        
    Raises:
        ValueError: اگر api_url خالی باشد
    """
    global API_URL, COMMAND_HANDLER_INITIALIZED
    
    if not api_url:
        raise ValueError("❌ api_url cannot be empty")
    
    API_URL = api_url.rstrip("/")
    COMMAND_HANDLER_INITIALIZED = True
    
    logger.info("✅ Command Handler initialized")


# =========================================================
# VALIDATION FUNCTIONS
# =========================================================

def validate_channel(channel: str) -> Tuple[bool, str]:
    """
    اعتبارسنجی نام کانال
    
    Args:
        channel: نام کانال (مثل @mychannel)
        
    Returns:
        (is_valid, error_message)
    """
    if not channel:
        return False, "❌ کانال نمی‌تواند خالی باشد"
    
    channel = channel.strip()
    
    if len(channel) < CHANNEL_MIN_LENGTH:
        return False, f"❌ کانال باید حداقل {CHANNEL_MIN_LENGTH} کاراکتر باشد"
    
    if len(channel) > CHANNEL_MAX_LENGTH:
        return False, f"❌ کانال نمی‌تواند از {CHANNEL_MAX_LENGTH} کاراکتر بیشتر باشد"
    
    if not channel.startswith("@"):
        return False, "❌ کانال باید با @ شروع شود"
    
    if not CHANNEL_PATTERN.match(channel):
        return (
            False,
            "❌ کانال فقط می‌تواند حاوی حروف، اعداد و _ باشد"
        )
    
    logger.debug(f"✅ Channel validated: {channel}")
    return True, ""


def validate_bale_token(token: str) -> Tuple[bool, str]:
    """
    اعتبارسنجی توکن بله
    
    Args:
        token: توکن ربات بله
        
    Returns:
        (is_valid, error_message)
    """
    if not token:
        return False, "❌ توکن نمی‌تواند خالی باشد"
    
    token = token.strip()
    
    if len(token) < TOKEN_MIN_LENGTH:
        return (
            False,
            f"❌ توکن باید حداقل {TOKEN_MIN_LENGTH} کاراکتر باشد"
        )
    
    if len(token) > TOKEN_MAX_LENGTH:
        return (
            False,
            f"❌ توکن نمی‌تواند از {TOKEN_MAX_LENGTH} کاراکتر بیشتر باشد"
        )
    
    # توکن‌های بله معمولاً alphanumeric + _ هستند
    if not re.match(r"^[a-zA-Z0-9_\-]+$", token):
        return False, "❌ توکن فرمت نامعتبری دارد"
    
    logger.debug(f"✅ Token validated (length={len(token)})")
    return True, ""


def parse_command(text: str) -> Tuple[str, str]:
    """
    Parse کردن دستور و استخراج نام دستور
    
    Args:
        text: متن دستور (مثل /settelegram @channel)
        
    Returns:
        (command_name, remaining_args)
        
    Examples:
        >>> parse_command("/register")
        ('register', '')
        >>> parse_command("/settelegram @mychannel")
        ('settelegram', '@mychannel')
    """
    if not text or not text.startswith("/"):
        return "", text
    
    # حذف @BotName (مثل /register@mybot)
    command_part = text.split()[0]  # اول بخش
    command_part = command_part.split("@")[0]  # قبل از @
    command_name = command_part[1:].lower()  # بدون /
    
    # بقیه متن
    remaining = text[len(command_part):].strip()
    
    return command_name, remaining


# =========================================================
# SEND MESSAGE
# =========================================================

def send_message(
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = None
) -> bool:
    """
    ار��ال پیام به کاربر
    
    Args:
        chat_id: شناسه چت کاربر
        text: متن پیام
        parse_mode: نوع فرمت (HTML, Markdown, etc.)
        
    Returns:
        True اگر ارسال موفق باشد
    """
    if not API_URL:
        logger.error("❌ API_URL در Command Handler تنظیم نشده است")
        return False
    
    if not text:
        logger.warning("⚠️ Empty message to send")
        return False
    
    try:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        response = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            logger.debug(f"✅ Message sent to {chat_id}")
            return True
        
        logger.error(
            f"❌ Telegram sendMessage error: "
            f"status={response.status_code} | "
            f"response={response.text[:200]}"
        )
        return False
        
    except Exception as e:
        logger.exception(f"❌ خطا در ارسال پیام: {e}")
        return False


# =========================================================
# SEND LONG MESSAGE (SPLIT)
# =========================================================

def send_long_message(
    chat_id: int,
    text: str,
    max_len: int = 4096
) -> bool:
    """
    ارسال پیام‌های بلند (تقسیم کردن اگر > 4096 کاراکتر)
    
    Telegram max message length = 4096
    این تابع پیام را تقسیم می‌کند اگر بیشتر باشد
    
    Args:
        chat_id: شناسه چت کاربر
        text: متن پیام
        max_len: حداکثر طول (default: 4096)
        
    Returns:
        True اگر تمام قسمت‌ها ارسال شود
    """
    if not text:
        return False
    
    # اگر خیلی کوتاه است، بفرست
    if len(text) <= max_len:
        return send_message(chat_id, text)
    
    # تقسیم کردن
    parts = []
    current = ""
    
    for line in text.split("\n"):
        # اگر سطر جدید جا دارد
        if len(current) + len(line) + 1 <= max_len:
            current += line + "\n"
        else:
            # ذخیره قسمت فعلی
            if current:
                parts.append(current.strip())
            # شروع قسمت جدید
            current = line + "\n"
    
    # قسمت آخر
    if current:
        parts.append(current.strip())
    
    # ارسال تمام قسمت‌ها
    logger.info(f"📤 Sending long message in {len(parts)} parts")
    for i, part in enumerate(parts, 1):
        if not send_message(chat_id, part):
            logger.error(f"❌ Failed to send part {i}/{len(parts)}")
            return False
        logger.debug(f"✅ Part {i}/{len(parts)} sent")
    
    return True


# =========================================================
# COMMAND HANDLERS
# =========================================================

def handle_start(chat_id: int) -> bool:
    """
    پردازش دستور /start
    
    Args:
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        tenant = get_tenant(chat_id)
        if tenant:
            send_message(
                chat_id,
                "👋 به ربات خبری خوش آمدید.\n\n"
                "برای شروع از /register استفاده کنید."
            )
            return True

        onboarding_state = _get_onboarding_state(chat_id)
        onboarding_result = _ensure_onboarding_ready(chat_id)

        if onboarding_state == "not_started":
            text = (
                "👋 به ربات مدیریت انتشار خوش آمدید.\n\n"
                "حساب شما آماده شد ✅\n"
                "حالا مقصد انتشار خود را اضافه کنید:\n"
                "افزودن مقصد انتشار: /adddestination\n\n"
                "برای راهنمای بیشتر: /help"
            )
        elif onboarding_state == "in_progress":
            text = (
                "✅ تنظیمات اولیه شما کامل شد.\n\n"
                "حالا مقصد انتشار خود را اضافه کنید:\n"
                "افزودن مقصد انتشار: /adddestination\n\n"
                "اگر نیاز به راهنما دارید: /help"
            )
        else:
            text = (
                "✅ حساب شما آماده است.\n\n"
                "برای ادامه تنظیم مقصد انتشار:\n"
                "افزودن مقصد انتشار: /adddestination\n\n"
                "برای راهنما: /help"
            )

        send_message(chat_id, text)
        logger.info(
            "✅ ONBOARDING READY | "
            f"user={chat_id} | "
            f"state_before={onboarding_state} | "
            f"workspace_id={onboarding_result['workspace']['id']}"
        )
        return True

    except Exception as e:
        logger.exception(f"❌ Error in handle_start: {e}")
        send_message(chat_id, "❌ خطا در راه‌اندازی اولیه حساب")
        return False


def handle_help(chat_id: int) -> bool:
    """
    پردازش دستور /help
    
    Args:
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        tenant = get_tenant(chat_id)
        if tenant:
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
            send_long_message(chat_id, text)
            return True

        onboarding_state = _get_onboarding_state(chat_id)
        if onboarding_state == "not_started":
            text = (
                "📚 راهنمای شروع\n\n"
                "۱) /start را بفرستید تا حساب شما آماده شود.\n"
                "۲) سپس مقصد انتشار را اضافه کنید.\n\n"
                "برای تنظیم مقصد تلگرام:\n"
                "/settelegram @channel"
            )
        elif onboarding_state == "in_progress":
            text = (
                "📚 راهنمای تکمیل تنظیمات\n\n"
                "تنظیمات اولیه در حال تکمیل است.\n"
                "یک بار /start را بفرستید.\n\n"
                "بعد از آن مقصد انتشار را اضافه کنید:\n"
                "/adddestination"
            )
        else:
            text = (
                "📚 راهنمای مقصد انتشار\n\n"
                "مقصد انتشار خود را وصل کنید:\n"
                "/settelegram @channel\n"
                "/setbale @channel (اختیاری)\n"
                "/setbaletoken TOKEN (اختیاری)\n\n"
                "برای وضعیت فعلی: /status"
            )

        send_long_message(chat_id, text)
        return True

    except Exception as e:
        logger.exception(f"❌ Error in handle_help: {e}")
        send_message(chat_id, "❌ خطا در نمایش راهنما")
        return False


def handle_adddestination(chat_id: int) -> bool:
    """راهنمای اولیه افزودن مقصد انتشار"""
    text = (
        "➕ افزودن مقصد انتشار\n\n"
        "برای شروع، مقصد تلگرام را تنظیم کنید:\n"
        "/settelegram @channel\n\n"
        "در صورت نیاز می‌توانید مقصد بله را هم اضافه کنید:\n"
        "/setbale @channel\n"
        "/setbaletoken TOKEN"
    )
    send_long_message(chat_id, text)
    return True


def _select_primary_workspace(workspaces):
    """انتخاب workspace اصلی برای onboarding"""
    if not workspaces:
        return None

    active_workspaces = [
        workspace
        for workspace in workspaces
        if workspace.get("status") == "active"
    ]
    candidates = active_workspaces or workspaces
    return sorted(
        candidates,
        key=lambda item: item.get("id", 0)
    )[0]


def _get_onboarding_state(chat_id: int) -> str:
    """
    وضعیت onboarding کاربر:
    - not_started
    - in_progress
    - completed
    """
    user = get_user_by_telegram_id(chat_id)
    if not user:
        return "not_started"

    workspaces = list_owned_workspaces(
        user["id"],
        include_inactive=True
    )
    if not workspaces:
        return "in_progress"

    workspace = _select_primary_workspace(workspaces)
    membership = get_workspace_member(
        workspace["id"],
        user["id"]
    )
    if not membership:
        return "in_progress"

    if (
        membership.get("role") == "owner"
        and membership.get("status") == "active"
    ):
        return "completed"

    return "in_progress"


def _ensure_onboarding_ready(chat_id: int) -> Dict[str, Any]:
    """ایجاد/تکمیل idempotent onboarding برای کاربر جدید"""
    user = get_or_create_user_by_telegram_id(
        chat_id,
        status="active"
    )

    owned_workspaces = list_owned_workspaces(
        user["id"],
        include_inactive=True
    )
    workspace = _select_primary_workspace(owned_workspaces)
    if not workspace:
        workspace = create_workspace(
            name=DEFAULT_WORKSPACE_NAME,
            owner_user_id=user["id"],
            status="active"
        )

    membership = get_workspace_member(
        workspace["id"],
        user["id"]
    )
    if not membership:
        membership = add_workspace_member(
            workspace_id=workspace["id"],
            user_id=user["id"],
            role="owner",
            status="active"
        )

    if membership.get("role") != "owner":
        membership = update_workspace_member_role(
            workspace["id"],
            user["id"],
            "owner"
        )

    if membership and membership.get("status") != "active":
        membership = update_workspace_member_status(
            workspace["id"],
            user["id"],
            "active"
        )

    if not membership:
        raise RuntimeError(
            "Failed to ensure owner membership for onboarding"
        )

    return {
        "user": user,
        "workspace": workspace,
        "membership": membership
    }


def handle_register(chat_id: int) -> bool:
    """
    پردازش دستور /register
    
    Args:
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        tenant = get_tenant(chat_id)
        
        if tenant:
            send_message(
                chat_id,
                "✅ شما قبلاً ثبت‌نام کرده‌اید.\n\n"
                "برای مشاهده وضعیت تنظیمات از /status استفاده کنید."
            )
            return True
        
        # ایجاد tenant جدید
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
            send_long_message(
                chat_id,
                "✅ ثبت‌نام شما با موفقیت انجام شد.\n\n"
                "⚠️ توجه: تنظیمات موقتی هستند!\n\n"
                "ابتدا کانال تلگرام را تنظیم کنید:\n"
                "/settelegram @channel\n\n"
                "سپس در صورت نیاز کانال بله را تنظیم کنید:\n"
                "/setbale @channel\n\n"
                "و توکن ربات بله را وارد کنید:\n"
                "/setbaletoken TOKEN"
            )
            logger.info(f"✅ USER REGISTERED | user={chat_id}")
        else:
            send_message(
                chat_id,
                "❌ ثبت‌نام انجام نشد. لطفاً دوباره تلاش کنید."
            )
        
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error in handle_register: {e}")
        send_message(chat_id, "❌ خطا در پردازش ثبت‌نام")
        return False


def handle_settelegram(args: str, chat_id: int) -> bool:
    """
    پردازش دستور /settelegram @channel
    
    Args:
        args: آرگومان‌ها (نام کانال)
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        if not args:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n\n"
                "/settelegram @channel"
            )
            return True
        
        channel = args.strip()
        
        # Validate channel
        is_valid, error_msg = validate_channel(channel)
        if not is_valid:
            send_message(chat_id, error_msg)
            return True
        
        # Get tenant
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(
                chat_id,
                "❌ ابتدا با /register ثبت‌نام کنید."
            )
            return True
        
        # Save channel
        success = save_tenant(
            user_id=chat_id,
            bot_token=tenant.get("bot_token") or "TOKEN_TEMP",
            telegram_channel=channel,
            bale_channel=tenant.get("bale_channel") or "",
            bale_token=tenant.get("bale_token") or "",
            hashtag=tenant.get("hashtag") or "#دنیا_۲۴_نیوز",
            channel_tag=tenant.get("channel_tag") or "@Donya24News"
        )
        
        if success:
            send_message(
                chat_id,
                f"✅ کانال تلگرام با موفقیت تنظیم شد:\n{channel}"
            )
            logger.info(
                f"✅ TELEGRAM CHANNEL SET | "
                f"user={chat_id} | channel={channel}"
            )
        else:
            send_message(
                chat_id,
                "❌ ذخیره کانال تلگرام انجام نشد."
            )
        
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error in handle_settelegram: {e}")
        send_message(chat_id, "❌ خطا در تنظیم کانال تلگرام")
        return False


def handle_setbale(args: str, chat_id: int) -> bool:
    """
    پردازش دستور /setbale @channel
    
    Args:
        args: آرگومان‌ها (نام کانال)
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        if not args:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n\n"
                "/setbale @channel"
            )
            return True
        
        bale_channel = args.strip()
        
        # Validate channel
        is_valid, error_msg = validate_channel(bale_channel)
        if not is_valid:
            send_message(chat_id, error_msg)
            return True
        
        # Get tenant
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(
                chat_id,
                "❌ ابتدا با /register ثبت‌نام کنید."
            )
            return True
        
        # Update bale settings
        success = update_bale_settings(
            chat_id,
            bale_channel,
            tenant.get("bale_token", "") or ""
        )
        
        if success:
            send_message(
                chat_id,
                f"✅ کانال بله با موفقیت تنظیم شد:\n{bale_channel}"
            )
            logger.info(
                f"✅ BALE CHANNEL SET | "
                f"user={chat_id} | channel={bale_channel}"
            )
        else:
            send_message(
                chat_id,
                "❌ ذخیره کانال بله انجام نشد."
            )
        
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error in handle_setbale: {e}")
        send_message(chat_id, "❌ خطا در تنظیم کانال بله")
        return False


def handle_setbaletoken(args: str, chat_id: int) -> bool:
    """
    پردازش دستور /setbaletoken TOKEN
    
    Args:
        args: آرگومان‌ها (توکن)
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        if not args:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n\n"
                "/setbaletoken TOKEN"
            )
            return True
        
        bale_token = args.strip()
        
        # Validate token
        is_valid, error_msg = validate_bale_token(bale_token)
        if not is_valid:
            send_message(chat_id, error_msg)
            return True
        
        # Get tenant
        tenant = get_tenant(chat_id)
        if not tenant:
            send_message(
                chat_id,
                "❌ ابتدا با /register ثبت‌نام کنید."
            )
            return True
        
        # Update bale token
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
        
    except Exception as e:
        logger.exception(f"❌ Error in handle_setbaletoken: {e}")
        send_message(chat_id, "❌ خطا در تنظیم توکن بله")
        return False


def handle_status(chat_id: int) -> bool:
    """
    پردازش دستور /status
    
    Args:
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    try:
        tenant = get_tenant(chat_id)
        
        if not tenant:
            send_message(
                chat_id,
                "❌ شما هنوز ثبت‌نام نکرده‌اید.\n\n"
                "/register"
            )
            return True
        
        telegram_channel = (
            tenant.get("telegram_channel") or "تنظیم نشده"
        )
        
        bale_channel = (
            tenant.get("bale_channel") or "تنظیم نشده"
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
        
        send_message(chat_id, status_text)
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error in handle_status: {e}")
        send_message(chat_id, "❌ خطا در بازیابی وضعیت")
        return False


# =========================================================
# COMMAND DETECTION
# =========================================================

def is_command(text: str) -> bool:
    """
    بررسی اینکه متن یک دستور است یا نه
    
    Args:
        text: متن برای بررسی
        
    Returns:
        True اگر شروع شود به /
    """
    if not text:
        return False
    return text.strip().startswith("/")


# =========================================================
# MAIN COMMAND HANDLER
# =========================================================

def handle_command(text: str, chat_id: int) -> bool:
    """
    پردازش اصلی دستور
    
    Args:
        text: متن دستور (مثل /register @channel)
        chat_id: شناسه کاربر
        
    Returns:
        True اگر پردازش موفق باشد
    """
    normalized_text = (text or "").strip()
    if normalized_text == "راهنما":
        return handle_help(chat_id)

    if not normalized_text.startswith("/"):
        logger.warning(f"Invalid command format: {text}")
        return False
    
    try:
        # Parse command
        command, args = parse_command(text)
        
        if not command:
            logger.warning(f"Empty command for: {text}")
            return False
        
        logger.info(
            f"📌 COMMAND | user={chat_id} | command=/{command} | "
            f"args_len={len(args)}"
        )
        
        # Command routing
        commands = {
            "start": lambda: handle_start(chat_id),
            "help": lambda: handle_help(chat_id),
            "register": lambda: handle_register(chat_id),
            "settelegram": lambda: handle_settelegram(args, chat_id),
            "setbale": lambda: handle_setbale(args, chat_id),
            "setbaletoken": lambda: handle_setbaletoken(args, chat_id),
            "status": lambda: handle_status(chat_id),
            "adddestination": lambda: handle_adddestination(chat_id),
        }
        
        if command in commands:
            return commands[command]()
        
        # Unknown command
        send_message(
            chat_id,
            f"❌ دستور /{command} شناسایی نشد.\n\n"
            "برای مشاهده دستورات:\n"
            "/help"
        )
        logger.warning(f"Unknown command: /{command}")
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error handling command '{text}': {e}")
        send_message(
            chat_id,
            "❌ خطا در پردازش دستور"
        )
        return False
