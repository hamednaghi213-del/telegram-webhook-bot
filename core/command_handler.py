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

# Phase 4A — optional setup infrastructure.
# When the database module doesn't expose these functions
# (e.g. during Phase 3 test isolation), the flag is False and
# the old handle_start path is used unchanged.
try:
    from core.workspace_setup import (
        get_or_init_setup_state,
        start_setup,
        advance_to_step,
        is_setup_completed,
        register_channel_destination,
        save_workspace_branding,
        add_member_to_workspace,
        can_complete_setup,
        complete_setup,
    )
    _WORKSPACE_SETUP_ENABLED: bool = True
except (ImportError, AttributeError):
    _WORKSPACE_SETUP_ENABLED = False

# Phase 5 is additive and optional for older/fake database modules.
try:
    from core.database import (
        get_active_workspace_preference,
        list_user_workspaces,
        set_active_workspace,
    )
    _ACTIVE_WORKSPACE_ENABLED: bool = True
except (ImportError, AttributeError):
    _ACTIVE_WORKSPACE_ENABLED = False

# Phase 6 member management is optional for older/fake database modules.
try:
    from core.database import get_user_by_id, list_workspace_members
    from core.workspace_members import authorize_member_action
    _MEMBER_MANAGEMENT_ENABLED: bool = True
except (ImportError, AttributeError):
    _MEMBER_MANAGEMENT_ENABLED = False

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


def send_message_with_keyboard(
    chat_id: int,
    text: str,
    keyboard: list
) -> bool:
    """Send a message with an inline keyboard."""
    if not API_URL:
        return False
    try:
        response = requests.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {"inline_keyboard": keyboard},
            },
            timeout=30,
        )
        return response.status_code == 200
    except Exception:
        logger.exception("Error sending inline keyboard")
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

    Legacy tenant path (get_tenant returns a row): unchanged.
    New workspace path: routes to Phase 4A setup wizard if enabled,
    otherwise falls back to Phase 3 onboarding messages.

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

        onboarding_result = _ensure_onboarding_ready(chat_id)
        workspace = onboarding_result["workspace"]
        user = onboarding_result["user"]
        onboarding_state = onboarding_result["state_before"]

        # ── Phase 4A setup wizard routing ──────────────────────────
        if _WORKSPACE_SETUP_ENABLED:
            setup_state = get_or_init_setup_state(workspace["id"])
            step = setup_state.get("step", "not_started")

            if step == "completed":
                send_message(
                    chat_id,
                    "✅ رسانه شما آماده است.\n\n"
                    "📋 تنظیمات: /settings\n"
                    "❓ راهنما: /help"
                )
            elif step == "in_progress":
                current = setup_state.get("current_step_key", "setup_channel")
                send_message(chat_id, _setup_resume_message(current))
            else:
                # not_started → prompt owner to begin
                send_message(
                    chat_id,
                    "👋 به رسانه‌ساز خوش آمدید!\n\n"
                    "برای شروع راه‌اندازی رسانه خود:\n"
                    "▶️ /setup\n\n"
                    "❓ راهنما: /help"
                )
            logger.info(
                "✅ START (4A) | "
                f"user={chat_id} | "
                f"setup_step={step} | "
                f"workspace_id={workspace['id']}"
            )
            return True

        # ── Phase 3 fallback (legacy compat when setup infra absent) ─
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
            f"workspace_id={workspace['id']}"
        )
        return True

    except Exception:
        logger.exception("❌ Error in handle_start")
        send_message(chat_id, "❌ خطا در راه‌اندازی اولیه حساب")
        return False


# =========================================================
# PHASE 4A — SETUP WIZARD HELPERS
# =========================================================

def _setup_resume_message(current_step_key: str) -> str:
    """Return the contextual resume message for the given setup step."""
    if current_step_key == "setup_channel":
        return (
            "▶️ راه‌اندازی در حال انجام است.\n\n"
            "مرحله ۱: افزودن کانال\n"
            "کانال تلگرام خود را وارد کنید:\n"
            "/addchannel @channel_id\n\n"
            "چند کانال دارید؟ همه را اضافه کنید.\n"
            "وقتی تمام کانال‌ها اضافه شد: /nextsetupstep\n\n"
            "❓ راهنما: /help"
        )
    if current_step_key == "setup_branding":
        return (
            "▶️ مرحله ۲: برندینگ رسانه\n\n"
            "نام رسانه، هشتگ پیش‌فرض و تگ کانال را تنظیم کنید:\n"
            "/setbranding نام_رسانه #هشتگ @تگ_کانال\n\n"
            "مثال:\n"
            "/setbranding دنیا۲۴ #دنیا_۲۴ @Donya24News\n\n"
            "❓ راهنما: /help"
        )
    if current_step_key == "setup_member":
        return (
            "▶️ مرحله ۳: افزودن عضو (اختیاری)\n\n"
            "عضو جدید اضافه کنید:\n"
            "/addmember TELEGRAM_ID نقش\n\n"
            "نقش‌های مجاز: manager, publisher, writer\n\n"
            "وقتی آماده هستید: /finishsetup\n\n"
            "❓ راهنما: /help"
        )
    return (
        "▶️ راه‌اندازی ادامه دارد.\n"
        "برای ادامه: /setup\n"
        "❓ راهنما: /help"
    )


def _get_workspace_for_user(chat_id: int):
    """Return (user, workspace) for a non-legacy workspace user, or (None, None)."""
    user = get_user_by_telegram_id(chat_id)
    if not user:
        return None, None
    if not _ACTIVE_WORKSPACE_ENABLED:
        workspaces = list_owned_workspaces(user["id"], include_inactive=True)
        if not workspaces:
            return user, None
        return user, _select_primary_workspace(workspaces)

    workspaces = list_user_workspaces(user["id"], include_inactive=False)
    if not workspaces:
        return user, None
    preference = get_active_workspace_preference(user["id"]) or {}
    active_workspace_id = preference.get("active_workspace_id")
    for workspace in workspaces:
        if workspace.get("id") == active_workspace_id:
            return user, workspace
    workspace = _select_primary_workspace(workspaces)
    return user, workspace


def handle_workspaces(chat_id: int) -> bool:
    """List accessible workspaces and allow the user to select the active one."""
    if not _ACTIVE_WORKSPACE_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user = get_user_by_telegram_id(chat_id)
        if not user:
            send_message(chat_id, "❌ ابتدا /start را بفرستید.")
            return True

        workspaces = list_user_workspaces(user["id"], include_inactive=False)
        if not workspaces:
            send_message(chat_id, "❌ رسانه فعالی برای شما یافت نشد.")
            return True

        preference = get_active_workspace_preference(user["id"]) or {}
        active_id = preference.get("active_workspace_id")
        if len(workspaces) == 1 and active_id != workspaces[0]["id"]:
            set_active_workspace(user["id"], workspaces[0]["id"])
            active_id = workspaces[0]["id"]

        from core.workspace_publisher import build_workspace_keyboard
        keyboard = build_workspace_keyboard(workspaces, active_id)

        send_message_with_keyboard(
            chat_id,
            "🏢 رسانه‌های شما\n\nرسانه فعال را انتخاب کنید:",
            keyboard,
        )
        return True
    except Exception:
        logger.exception("Error listing workspaces")
        send_message(chat_id, "❌ خطا در نمایش رسانه‌ها")
        return False


def handle_switchworkspace(args: str, chat_id: int) -> bool:
    """Select an active workspace by numeric ID."""
    if not _ACTIVE_WORKSPACE_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    value = (args or "").strip()
    if not value:
        return handle_workspaces(chat_id)
    try:
        workspace_id = int(value)
        user = get_user_by_telegram_id(chat_id)
        if not user:
            send_message(chat_id, "❌ ابتدا /start را بفرستید.")
            return True
        set_active_workspace(user["id"], workspace_id)
        send_message(chat_id, "✅ رسانه فعال با موفقیت تغییر کرد.")
        return True
    except (TypeError, ValueError):
        send_message(
            chat_id,
            "❌ شناسه رسانه معتبر نیست یا به آن دسترسی ندارید.\n"
            "برای مشاهده رسانه‌ها: /workspaces",
        )
        return True
    except Exception:
        logger.exception("Error switching workspace")
        send_message(chat_id, "❌ خطا در تغییر رسانه فعال")
        return False


# =========================================================
# PHASE 4A — SETUP COMMAND HANDLERS
# =========================================================

def handle_setup(chat_id: int) -> bool:
    """
    /setup — شروع یا ادامه راه‌اندازی اولیه رسانه.

    - اگر راه‌اندازی کامل شده: پنل آماده نمایش می‌دهد.
    - اگر در حال انجام: از مرحله‌ای که متوقف شده ادامه می‌دهد.
    - اگر هنوز شروع نشده: مرحله اول را آغاز می‌کند.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        state = start_setup(workspace["id"])
        step = state.get("step", "in_progress")

        if step == "completed":
            send_message(
                chat_id,
                "✅ راه‌اندازی رسانه قبلاً کامل شده است.\n\n"
                "📋 تنظیمات: /settings\n"
                "❓ راهنما: /help"
            )
        else:
            current = state.get("current_step_key", "setup_channel")
            send_message(chat_id, _setup_resume_message(current))

        return True
    except Exception:
        logger.exception("❌ Error in handle_setup")
        send_message(chat_id, "❌ خطا در راه‌اندازی")
        return False


def handle_addchannel(args: str, chat_id: int) -> bool:
    """
    /addchannel @channel_id — افزودن کانال تلگرام در مرحله راه‌اندازی.

    کانال با وضعیت غیر‌فعال (unverified) ذخیره می‌شود.
    تأیید مدیریت کانال (admin verification) در Phase 4B انجام می‌شود.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        if not args:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n/addchannel @channel_id\n\n"
                "مثال: /addchannel @MyChannel"
            )
            return True

        external_id = args.strip()
        is_valid, err = validate_channel(external_id)
        if not is_valid:
            send_message(chat_id, err)
            return True

        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        dest, is_dup = register_channel_destination(
            workspace["id"],
            external_id=external_id,
            name=external_id,
        )

        if is_dup:
            send_message(
                chat_id,
                f"⚠️ کانال {external_id} قبلاً اضافه شده است.\n\n"
                "کانال دیگری دارید؟ /addchannel @channel\n"
                "وقتی تمام کانال‌ها اضافه شد: /nextsetupstep"
            )
        elif dest:
            send_message(
                chat_id,
                f"✅ کانال {external_id} ثبت شد.\n\n"
                "🔍 در حال بررسی دسترسی ادمین ربات...\n\n"
                "کانال دیگری دارید؟ /addchannel @channel\n"
                "وقتی تمام کانال‌ها اضافه شد: /nextsetupstep"
            )
            # Phase 4B: Real Telegram verification
            _verify_and_activate_channel(workspace["id"], dest, chat_id)
        else:
            send_message(chat_id, "❌ خطا در ثبت کانال. دوباره تلاش کنید.")

        return True
    except Exception:
        logger.exception("❌ Error in handle_addchannel")
        send_message(chat_id, "❌ خطا در افزودن کانال")
        return False


# =========================================================
# PHASE 4B — REAL TELEGRAM CHANNEL VERIFICATION
# =========================================================

def _verify_and_activate_channel(
    workspace_id: int,
    dest: Dict[str, Any],
    chat_id: int
) -> None:
    """Run real Telegram admin verification and activate destination if verified."""
    try:
        if not API_URL:
            logger.warning(
                "Skipping channel verification — API_URL not configured"
            )
            return

        from core.telegram_verifier import verify_channel_admin
        from core.database import (
            upsert_destination_verification,
            update_publication_destination_status,
        )

        external_id = dest["external_id"]
        verified, note = verify_channel_admin(API_URL, external_id)

        upsert_destination_verification(
            dest["id"],
            verified=verified,
            verification_note=note,
        )

        if verified:
            update_publication_destination_status(dest["id"], "active")
            send_message(
                chat_id,
                f"✅ کانال با موفقیت متصل شد.\n\n"
                f"کانال {external_id} آماده انتشار است."
            )
        else:
            # A destination that loses Telegram permissions must fail closed.
            update_publication_destination_status(dest["id"], "inactive")
            send_message(
                chat_id,
                f"⚠️ بررسی دسترسی ناموفق بود:\n{note}\n\n"
                f"ابتدا ربات را به عنوان مدیر کانال اضافه کنید،\n"
                f"سپس دوباره تلاش کنید:\n/verifychannel {external_id}"
            )
    except Exception:
        logger.exception("Error in _verify_and_activate_channel")


def handle_verifychannel(args: str, chat_id: int) -> bool:
    """
    /verifychannel @channel_id — بررسی مجدد دسترسی ادمین ربات در کانال.

    اگر تأیید موفق باشد، کانال فعال (active) می‌شود.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        if not args:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n/verifychannel @channel_id\n\n"
                "مثال: /verifychannel @MyChannel"
            )
            return True

        external_id = args.strip()
        is_valid, err = validate_channel(external_id)
        if not is_valid:
            send_message(chat_id, err)
            return True

        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        from core.database import list_workspace_destinations

        destinations = list_workspace_destinations(
            workspace["id"],
            include_removed=False
        )
        target = None
        for destination in destinations:
            if destination.get("external_id") == external_id:
                target = destination
                break

        if not target:
            send_message(
                chat_id,
                f"❌ کانال {external_id} در این رسانه ثبت نشده است.\n\n"
                f"ابتدا آن را اضافه کنید:\n/addchannel {external_id}"
            )
            return True

        _verify_and_activate_channel(workspace["id"], target, chat_id)
        return True
    except Exception:
        logger.exception("❌ Error in handle_verifychannel")
        send_message(chat_id, "❌ خطا در بررسی کانال")
        return False


def handle_nextsetupstep(chat_id: int) -> bool:
    """
    /nextsetupstep — پیشروی به مرحله بعدی راه‌اندازی.
    از مرحله کانال به مرحله برندینگ می‌رود.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        state = get_or_init_setup_state(workspace["id"])
        if state.get("step") == "completed":
            send_message(
                chat_id,
                "✅ راه‌اندازی قبلاً کامل شده است.\n/settings"
            )
            return True

        current = state.get("current_step_key", "setup_channel")
        if current == "setup_channel":
            advance_to_step(workspace["id"], "setup_branding")
            send_message(chat_id, _setup_resume_message("setup_branding"))
        elif current == "setup_branding":
            advance_to_step(workspace["id"], "setup_member")
            send_message(chat_id, _setup_resume_message("setup_member"))
        else:
            send_message(
                chat_id,
                "✅ همه مراحل راه‌اندازی کامل شده‌اند.\n"
                "برای پایان: /finishsetup"
            )
        return True
    except Exception:
        logger.exception("❌ Error in handle_nextsetupstep")
        send_message(chat_id, "❌ خطا در پیشروی مرحله")
        return False


def handle_setbranding(args: str, chat_id: int) -> bool:
    """
    /setbranding نام_رسانه #هشتگ @تگ_کانال — تنظیم برندینگ رسانه.

    مثال: /setbranding دنیا۲۴ #دنیا_۲۴ @Donya24News

    برندینگ متعلق به رسانه است، نه کاربر تلگرام.
    مسیر برندینگ legacy دست‌نخورده می‌ماند.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        parts = (args or "").split()
        if len(parts) < 1:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n"
                "/setbranding نام_رسانه #هشتگ @تگ_کانال\n\n"
                "مثال:\n/setbranding دنیا۲۴ #دنیا_۲۴ @Donya24News\n\n"
                "هشتگ و تگ کانال اختیاری هستند."
            )
            return True

        media_name = parts[0].strip()
        hashtag = parts[1].strip() if len(parts) > 1 else ""
        channel_tag = parts[2].strip() if len(parts) > 2 else ""

        if not media_name:
            send_message(chat_id, "❌ نام رسانه نمی‌تواند خالی باشد.")
            return True

        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        branding = save_workspace_branding(
            workspace["id"],
            media_name=media_name,
            hashtag=hashtag,
            channel_tag=channel_tag,
        )

        if branding:
            send_message(
                chat_id,
                f"✅ برندینگ رسانه ذخیره شد:\n"
                f"نام رسانه: {media_name}\n"
                f"هشتگ: {hashtag or '(تنظیم نشده)'}\n"
                f"تگ کانال: {channel_tag or '(تنظیم نشده)'}\n\n"
                "برای ادامه: /nextsetupstep"
            )
        else:
            send_message(chat_id, "❌ خطا در ذخیره برندینگ.")

        return True
    except Exception:
        logger.exception("❌ Error in handle_setbranding")
        send_message(chat_id, "❌ خطا در تنظیم برندینگ")
        return False


def handle_addmember(args: str, chat_id: int) -> bool:
    """
    /addmember TELEGRAM_ID نقش — افزودن عضو به رسانه.

    نقش‌های مجاز: manager, publisher, writer
    یک کاربر می‌تواند عضو چند رسانه باشد (multi-workspace).
    نقش مالک قابل انتقال نیست.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        parts = (args or "").split()
        if len(parts) < 2:
            send_message(
                chat_id,
                "❌ فرمت صحیح:\n"
                "/addmember TELEGRAM_ID نقش\n\n"
                "نقش‌های مجاز: manager, publisher, writer\n\n"
                "مثال: /addmember 123456789 manager"
            )
            return True

        try:
            target_telegram_id = int(parts[0])
        except ValueError:
            send_message(
                chat_id,
                "❌ شناسه تلگرام باید عدد باشد.\n"
                "مثال: /addmember 123456789 manager"
            )
            return True

        role = parts[1].strip().lower()

        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        actor = get_workspace_member(workspace["id"], user["id"])
        allowed, reason = authorize_member_action(
            (actor or {}).get("role"),
            requested_role=role,
        ) if _MEMBER_MANAGEMENT_ENABLED else (True, "")
        if not allowed:
            send_message(chat_id, f"❌ {reason}")
            return True

        membership, err = add_member_to_workspace(
            workspace["id"],
            target_telegram_id,
            role=role,
        )

        if err == "duplicate":
            send_message(
                chat_id,
                f"⚠️ کاربر {target_telegram_id} قبلاً عضو این رسانه است.\n\n"
                "عضو دیگری: /addmember TELEGRAM_ID نقش\n"
                "پایان: /finishsetup"
            )
        elif membership:
            send_message(
                chat_id,
                f"✅ عضو جدید با نقش {role} اضافه شد.\n\n"
                "عضو دیگری: /addmember TELEGRAM_ID نقش\n"
                "پایان: /finishsetup"
            )
        else:
            send_message(chat_id, f"❌ {err or 'خطا در افزودن عضو'}")

        return True
    except Exception:
        logger.exception("❌ Error in handle_addmember")
        send_message(chat_id, "❌ خطا در افزودن عضو")
        return False


def handle_members(chat_id: int) -> bool:
    """List members of the active workspace."""
    if not _MEMBER_MANAGEMENT_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(chat_id, "❌ رسانه‌ای یافت نشد.")
            return True
        actor = get_workspace_member(workspace["id"], user["id"])
        if (actor or {}).get("role") not in {"owner", "manager"}:
            send_message(chat_id, "❌ فقط مالک یا مدیر می‌تواند فهرست اعضا را ببیند.")
            return True

        lines = [f"👥 اعضای {workspace.get('name') or workspace['id']}"]
        for member in list_workspace_members(workspace["id"], include_inactive=True):
            member_user = get_user_by_id(member["user_id"]) or {}
            telegram_id = member_user.get("telegram_user_id", member["user_id"])
            lines.append(
                f"• {telegram_id} — {member.get('role')} — {member.get('status')}"
            )
        send_long_message(chat_id, "\n".join(lines))
        return True
    except Exception:
        logger.exception("Error listing workspace members")
        send_message(chat_id, "❌ خطا در نمایش اعضا")
        return False


def _find_member_by_telegram_id(workspace_id: int, telegram_id: int):
    target_user = get_user_by_telegram_id(telegram_id)
    if not target_user:
        return None, None
    return target_user, get_workspace_member(workspace_id, target_user["id"])


def handle_setmemberrole(args: str, chat_id: int) -> bool:
    """Change a non-owner member role in the active workspace."""
    if not _MEMBER_MANAGEMENT_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    parts = (args or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        send_message(chat_id, "❌ فرمت صحیح: /setmemberrole TELEGRAM_ID نقش")
        return True
    try:
        telegram_id, role = int(parts[0]), parts[1].lower()
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(chat_id, "❌ رسانه‌ای یافت نشد.")
            return True
        actor = get_workspace_member(workspace["id"], user["id"])
        target_user, target = _find_member_by_telegram_id(workspace["id"], telegram_id)
        if not target:
            send_message(chat_id, "❌ این کاربر عضو رسانه نیست.")
            return True
        allowed, reason = authorize_member_action(
            (actor or {}).get("role"), target.get("role"), role
        )
        if not allowed:
            send_message(chat_id, f"❌ {reason}")
            return True
        update_workspace_member_role(workspace["id"], target_user["id"], role)
        send_message(chat_id, f"✅ نقش کاربر {telegram_id} به {role} تغییر کرد.")
        return True
    except Exception:
        logger.exception("Error changing workspace member role")
        send_message(chat_id, "❌ خطا در تغییر نقش عضو")
        return False


def handle_removemember(args: str, chat_id: int) -> bool:
    """Soft-remove a non-owner member from the active workspace."""
    if not _MEMBER_MANAGEMENT_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    value = (args or "").strip()
    if not value.isdigit():
        send_message(chat_id, "❌ فرمت صحیح: /removemember TELEGRAM_ID")
        return True
    try:
        telegram_id = int(value)
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(chat_id, "❌ رسانه‌ای یافت نشد.")
            return True
        actor = get_workspace_member(workspace["id"], user["id"])
        target_user, target = _find_member_by_telegram_id(workspace["id"], telegram_id)
        if not target:
            send_message(chat_id, "❌ این کاربر عضو رسانه نیست.")
            return True
        allowed, reason = authorize_member_action(
            (actor or {}).get("role"), target.get("role")
        )
        if not allowed:
            send_message(chat_id, f"❌ {reason}")
            return True
        update_workspace_member_status(workspace["id"], target_user["id"], "removed")
        send_message(chat_id, f"✅ کاربر {telegram_id} از رسانه حذف شد.")
        return True
    except Exception:
        logger.exception("Error removing workspace member")
        send_message(chat_id, "❌ خطا در حذف عضو")
        return False


def handle_finishsetup(chat_id: int) -> bool:
    """
    /finishsetup — پایان راه‌اندازی و فعال‌سازی رسانه.

    نیازمندی‌های حداقلی:
    - عضویت فعال مالک
    - برندینگ تنظیم شده (حداقل نام رسانه)
    - حداقل یک کانال ثبت شده
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        if is_setup_completed(workspace["id"]):
            send_message(
                chat_id,
                "✅ راه‌اندازی قبلاً کامل شده است.\n/settings"
            )
            return True

        ok, reason = complete_setup(workspace["id"], user["id"])
        if ok:
            send_message(
                chat_id,
                "🎉 رسانه شما راه‌اندازی شد!\n\n"
                "✅ تنظیمات: /settings\n"
                "❓ راهنما: /help\n\n"
                "⚠️ نکته: کانال‌های ثبت‌شده تا تأیید دسترسی ادمین\n"
                "غیرفعال هستند. (Phase 4B)"
            )
        else:
            send_message(
                chat_id,
                f"❌ راه‌اندازی کامل نشد:\n{reason}\n\n"
                "پس از رفع مشکل دوباره /finishsetup بفرستید."
            )
        return True
    except Exception:
        logger.exception("❌ Error in handle_finishsetup")
        send_message(chat_id, "❌ خطا در پایان راه‌اندازی")
        return False


def handle_settings(chat_id: int) -> bool:
    """
    /settings — منوی تنظیمات پس از راه‌اندازی.

    تنظیمات را می‌توان بارها تغییر داد؛ راه‌اندازی مجدد اتفاق نمی‌افتد.
    """
    if not _WORKSPACE_SETUP_ENABLED:
        send_message(chat_id, "❌ این قابلیت در حال حاضر فعال نیست.")
        return True
    try:
        user, workspace = _get_workspace_for_user(chat_id)
        if not workspace:
            send_message(
                chat_id,
                "❌ رسانه‌ای یافت نشد. ابتدا /start را بفرستید."
            )
            return True

        send_message(
            chat_id,
            "📋 تنظیمات رسانه\n\n"
            "🏢 تغییر رسانه فعال:\n"
            "/workspaces\n\n"
            "🔧 برندینگ:\n"
            "/setbranding نام #هشتگ @تگ\n\n"
            "📡 کانال‌ها:\n"
            "/addchannel @channel\n"
            "/verifychannel @channel\n\n"
            "👥 اعضا:\n"
            "/members\n"
            "/addmember TELEGRAM_ID نقش\n"
            "/setmemberrole TELEGRAM_ID نقش\n"
            "/removemember TELEGRAM_ID\n\n"
            "❓ راهنما:\n"
            "/help"
        )
        return True
    except Exception:
        logger.exception("❌ Error in handle_settings")
        send_message(chat_id, "❌ خطا در نمایش تنظیمات")
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

    except Exception:
        logger.exception("❌ Error in handle_help")
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
    user = get_user_by_telegram_id(chat_id)
    if not user:
        state_before = "not_started"
        user = get_or_create_user_by_telegram_id(
            chat_id,
            status="active"
        )
    else:
        state_before = "in_progress"

    owned_workspaces = list_owned_workspaces(
        user["id"],
        include_inactive=True
    )
    workspace = _select_primary_workspace(owned_workspaces)
    membership = None
    if workspace:
        membership = get_workspace_member(
            workspace["id"],
            user["id"]
        )
        if (
            membership
            and membership.get("role") == "owner"
            and membership.get("status") == "active"
        ):
            state_before = "completed"

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

    if membership and membership.get("role") != "owner":
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
        "state_before": state_before,
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
        logger.warning(
            f"Invalid command format: {normalized_text}"
        )
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
            # Phase 4A setup wizard
            "setup": lambda: handle_setup(chat_id),
            "addchannel": lambda: handle_addchannel(args, chat_id),
            "verifychannel": lambda: handle_verifychannel(args, chat_id),
            "nextsetupstep": lambda: handle_nextsetupstep(chat_id),
            "setbranding": lambda: handle_setbranding(args, chat_id),
            "addmember": lambda: handle_addmember(args, chat_id),
            "members": lambda: handle_members(chat_id),
            "setmemberrole": lambda: handle_setmemberrole(args, chat_id),
            "removemember": lambda: handle_removemember(args, chat_id),
            "finishsetup": lambda: handle_finishsetup(chat_id),
            "settings": lambda: handle_settings(chat_id),
            # Phase 5 active-workspace selection
            "workspaces": lambda: handle_workspaces(chat_id),
            "switchworkspace": lambda: handle_switchworkspace(args, chat_id),
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
