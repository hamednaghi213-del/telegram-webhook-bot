import os
import logging
import time
from typing import Optional, Dict, Any, List
from supabase import create_client

logger = logging.getLogger(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# Retry Configuration
MAX_RETRIES: int = 3
RETRY_DELAY: float = 1.0  # seconds
RETRY_BACKOFF: float = 2.0  # exponential backoff multiplier

# Default Values
DEFAULT_HASHTAG: str = "#دنیا_۲۴_نیوز"
DEFAULT_CHANNEL_TAG: str = "@Donya24News"

# =========================================================
# VALIDATION
# =========================================================

if not SUPABASE_URL:
    raise ValueError(
        "❌ متغیر محیطی SUPABASE_URL تنظیم نشده است."
    )

if not SUPABASE_KEY:
    raise ValueError(
        "❌ متغیر محیطی SUPABASE_KEY تنظیم نشده است."
    )

# =========================================================
# DATABASE CLIENT
# =========================================================

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase client initialized")
except Exception as e:
    logger.exception(f"❌ Failed to initialize Supabase: {e}")
    raise


# =========================================================
# RETRY DECORATOR
# =========================================================

def with_retry(func):
    """
    Decorator برای retry logic با exponential backoff
    
    Args:
        func: تابعی که نیاز به retry دارد
        
    Returns:
        Wrapped function with retry capability
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(
                    f"🔄 Attempt {attempt + 1}/{MAX_RETRIES} "
                    f"for {func.__name__}"
                )
                return func(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                
                # اگر آخرین تلاش است، error throw کن
                if attempt == MAX_RETRIES - 1:
                    logger.error(
                        f"❌ All {MAX_RETRIES} attempts failed "
                        f"for {func.__name__}: {e}"
                    )
                    raise
                
                # Exponential backoff
                delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(
                    f"⚠️ Attempt {attempt + 1} failed: {e} | "
                    f"Retrying in {delay:.2f}s..."
                )
                time.sleep(delay)
        
        # Fallback (shouldn't reach here)
        if last_exception:
            raise last_exception
    
    return wrapper


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db() -> bool:
    """
    مقداردهی دیتابیس
    
    Returns:
        True اگر مقداردهی موفق باشد
    """
    try:
        logger.info("✅ دیتابیس Supabase مقداردهی شد")
        return True
    except Exception as e:
        logger.exception(f"❌ Failed to initialize DB: {e}")
        return False


# =========================================================
# GET TENANT
# =========================================================

@with_retry
def get_tenant(user_id: int) -> Optional[Dict[str, Any]]:
    """
    دریافت اطلاعات tenant برای کاربر
    
    Args:
        user_id: شناسه کاربر
        
    Returns:
        Dict حاوی تنظیمات کاربر یا None
    """
    try:
        logger.debug(f"📖 Getting tenant for user_id={user_id}")
        
        result = (
            supabase
            .table("tenants")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        
        if result.data and len(result.data) > 0:
            tenant = result.data[0]
            logger.debug(
                f"✅ Tenant found for user_id={user_id} | "
                f"telegram_channel={tenant.get('telegram_channel')}"
            )
            return tenant
        
        logger.info(
            f"ℹ️ tenant برای کاربر {user_id} پیدا نشد."
        )
        return None
        
    except Exception as e:
        logger.exception(
            f"❌ get_tenant({user_id}): {e}"
        )
        raise


# =========================================================
# UPSERT TENANT (INSERT OR UPDATE)
# =========================================================

@with_retry
def upsert_tenant(
    user_id: int,
    bot_token: str,
    telegram_channel: str,
    bale_channel: str = "",
    bale_token: str = "",
    hashtag: Optional[str] = None,
    channel_tag: Optional[str] = None
) -> bool:
    """
    ایجاد یا بروزرسانی tenant (UPSERT)
    
    این تابع به جای دو query جداگانه، یک query واحد استفاده می‌کند
    
    Args:
        user_id: شناسه کاربر
        bot_token: توکن ربات
        telegram_channel: کانال تلگرام
        bale_channel: کانال بله (اختیاری)
        bale_token: توکن بله (اختیاری)
        hashtag: هشتگ (اختیاری)
        channel_tag: تگ کانال (اختیاری)
        
    Returns:
        True اگر موفق باشد
    """
    try:
        logger.debug(
            f"📝 Upserting tenant for user_id={user_id} | "
            f"channel={telegram_channel}"
        )
        
        data = {
            "user_id": user_id,
            "bot_token": bot_token or "",
            "telegram_channel": telegram_channel or "",
            "bale_channel": bale_channel or "",
            "bale_token": bale_token or "",
            "hashtag": hashtag or DEFAULT_HASHTAG,
            "channel_tag": channel_tag or DEFAULT_CHANNEL_TAG,
            "updated_at": time.time()
        }
        
        # Supabase upsert (on_conflict with primary key)
        result = (
            supabase
            .table("tenants")
            .upsert(data, on_conflict="user_id")
            .execute()
        )
        
        if result.data:
            logger.info(
                f"✅ Tenant upserted for user_id={user_id} | "
                f"channel={telegram_channel}"
            )
            return True
        
        logger.warning(
            f"⚠️ No result from upsert for user_id={user_id}"
        )
        return False
        
    except Exception as e:
        logger.exception(
            f"❌ upsert_tenant({user_id}): {e}"
        )
        raise


# =========================================================
# SAVE TENANT (WRAPPER FOR BACKWARD COMPATIBILITY)
# =========================================================

def save_tenant(
    user_id: int,
    bot_token: str,
    telegram_channel: str,
    bale_channel: str = "",
    bale_token: str = "",
    hashtag: Optional[str] = None,
    channel_tag: Optional[str] = None
) -> bool:
    """
    ذخیره tenant (compatibility wrapper)
    
    این تابع برای backward compatibility نگاه داشته شده است.
    داخلی، upsert_tenant() را صدا می‌زند
    
    Args:
        user_id: شناسه کاربر
        bot_token: توکن ربات
        telegram_channel: کانال تلگرام
        bale_channel: کانال بله (اختیاری)
        bale_token: توکن بله (اختیاری)
        hashtag: هشتگ (اختیاری)
        channel_tag: تگ کانال (اختیاری)
        
    Returns:
        True اگر موفق باشد
    """
    try:
        return upsert_tenant(
            user_id=user_id,
            bot_token=bot_token,
            telegram_channel=telegram_channel,
            bale_channel=bale_channel,
            bale_token=bale_token,
            hashtag=hashtag,
            channel_tag=channel_tag
        )
    except Exception as e:
        logger.exception(f"❌ save_tenant({user_id}): {e}")
        return False


# =========================================================
# UPDATE BALE SETTINGS
# =========================================================

@with_retry
def update_bale_settings(
    user_id: int,
    bale_channel: str,
    bale_token: str
) -> bool:
    """
    بروزرسانی تنطیمات بله برای کاربر
    
    Args:
        user_id: شناسه کاربر
        bale_channel: کانال بله
        bale_token: توکن بله
        
    Returns:
        True اگر موفق باشد
    """
    try:
        logger.debug(
            f"🔵 Updating Bale settings for user_id={user_id} | "
            f"channel={bale_channel}"
        )
        
        data = {
            "bale_channel": bale_channel or "",
            "bale_token": bale_token or "",
            "updated_at": time.time()
        }
        
        result = (
            supabase
            .table("tenants")
            .update(data)
            .eq("user_id", user_id)
            .execute()
        )
        
        if result.data and len(result.data) > 0:
            logger.info(
                f"✅ Bale settings updated for user_id={user_id} | "
                f"channel={bale_channel}"
            )
            return True
        
        logger.warning(
            f"⚠️ No tenant found to update for user_id={user_id}"
        )
        return False
        
    except Exception as e:
        logger.exception(
            f"❌ update_bale_settings({user_id}): {e}"
        )
        raise


# =========================================================
# GET BALE SETTINGS
# =========================================================

def get_bale_settings(user_id: int) -> Dict[str, str]:
    """
    دریافت تنطیمات بله برای کاربر
    
    Args:
        user_id: شناسه کاربر
        
    Returns:
        Dict حاوی bale_channel و bale_token
    """
    try:
        logger.debug(f"📖 Getting Bale settings for user_id={user_id}")
        
        tenant = get_tenant(user_id)
        
        if not tenant:
            logger.debug(f"ℹ️ No tenant found for user_id={user_id}")
            return {
                "bale_channel": "",
                "bale_token": ""
            }
        
        settings = {
            "bale_channel": tenant.get("bale_channel", "") or "",
            "bale_token": tenant.get("bale_token", "") or ""
        }
        
        logger.debug(
            f"✅ Bale settings retrieved for user_id={user_id} | "
            f"has_channel={bool(settings['bale_channel'])}"
        )
        
        return settings
        
    except Exception as e:
        logger.exception(
            f"❌ get_bale_settings({user_id}): {e}"
        )
        # Fallback
        return {
            "bale_channel": "",
            "bale_token": ""
        }


# =========================================================
# DISABLE BALE
# =========================================================

@with_retry
def disable_bale(user_id: int) -> bool:
    """
    غیرفعال کردن تنطیمات بله برای کاربر
    
    Args:
        user_id: شناسه کاربر
        
    Returns:
        True اگر موفق باشد
    """
    try:
        logger.debug(f"🛑 Disabling Bale for user_id={user_id}")
        
        result = (
            supabase
            .table("tenants")
            .update({
                "bale_channel": "",
                "bale_token": "",
                "updated_at": time.time()
            })
            .eq("user_id", user_id)
            .execute()
        )
        
        if result.data and len(result.data) > 0:
            logger.info(
                f"🛑 Bale settings disabled for user_id={user_id}"
            )
            return True
        
        logger.warning(
            f"⚠️ No tenant found to disable Bale for user_id={user_id}"
        )
        return False
        
    except Exception as e:
        logger.exception(
            f"❌ disable_bale({user_id}): {e}"
        )
        raise


# =========================================================
# GET ALL TENANTS (ADMIN)
# =========================================================

@with_retry
def get_all_tenants() -> List[Dict[str, Any]]:
    """
    دریافت تمام tenants (برای admin)
    
    Returns:
        لیست تمام tenants
    """
    try:
        logger.debug("📊 Fetching all tenants")
        
        result = (
            supabase
            .table("tenants")
            .select("*")
            .execute()
        )
        
        tenants = result.data or []
        logger.info(f"✅ Retrieved {len(tenants)} tenants")
        
        return tenants
        
    except Exception as e:
        logger.exception(f"❌ get_all_tenants(): {e}")
        raise


# =========================================================
# DELETE TENANT
# =========================================================

@with_retry
def delete_tenant(user_id: int) -> bool:
    """
    حذف tenant برای کاربر
    
    Args:
        user_id: شناسه کاربر
        
    Returns:
        True اگر موفق باشد
    """
    try:
        logger.warning(f"🗑️ Deleting tenant for user_id={user_id}")
        
        result = (
            supabase
            .table("tenants")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
        
        logger.info(f"✅ Tenant deleted for user_id={user_id}")
        return True
        
    except Exception as e:
        logger.exception(
            f"❌ delete_tenant({user_id}): {e}"
        )
        raise


# =========================================================
# BATCH OPERATIONS
# =========================================================

@with_retry
def batch_update_tenants(
    updates: List[Dict[str, Any]]
) -> bool:
    """
    بروزرسانی گروهی tenants
    
    Args:
        updates: لیست dictionaries شامل user_id و fields برای تغییر
        
    Returns:
        True اگر موفق باشد
        
    Example:
        >>> updates = [
        ...     {"user_id": 1, "hashtag": "#new_tag"},
        ...     {"user_id": 2, "hashtag": "#other_tag"}
        ... ]
        >>> batch_update_tenants(updates)
    """
    try:
        logger.info(f"📦 Batch updating {len(updates)} tenants")
        
        for update in updates:
            update["updated_at"] = time.time()
        
        result = (
            supabase
            .table("tenants")
            .upsert(updates, on_conflict="user_id")
            .execute()
        )
        
        logger.info(
            f"✅ Batch update completed for {len(updates)} tenants"
        )
        return bool(result.data)
        
    except Exception as e:
        logger.exception(f"❌ batch_update_tenants(): {e}")
        raise


# =========================================================
# MULTI-WORKSPACE FOUNDATION
# =========================================================


USER_STATUSES = {
    "active",
    "inactive"
}

WORKSPACE_STATUSES = {
    "active",
    "inactive"
}

WORKSPACE_MEMBER_ROLES = {
    "owner",
    "manager",
    "publisher",
    "writer"
}

WORKSPACE_MEMBER_STATUSES = {
    "active",
    "suspended",
    "removed"
}


def _validate_enum(
    value: str,
    allowed_values,
    field_name: str
) -> str:
    """اعتبارسنجی مقادیر enum-like برای جداول جدید"""
    normalized_value = (
        (value or "")
        .strip()
        .lower()
    )

    if normalized_value not in allowed_values:
        raise ValueError(
            f"Invalid {field_name}: {value}"
        )

    return normalized_value


def _first_row(result) -> Optional[Dict[str, Any]]:
    """اولین رکورد Supabase result را برمی‌گرداند"""
    if result.data and len(result.data) > 0:
        return result.data[0]

    return None


@with_retry
def get_or_create_user_by_telegram_id(
    telegram_user_id: int,
    status: str = "active"
) -> Dict[str, Any]:
    """دریافت یا ایجاد کاربر بر اساس شناسه تلگرام"""
    validated_status = _validate_enum(
        status,
        USER_STATUSES,
        "user status"
    )

    logger.debug(
        f"👤 Get or create user | telegram_user_id={telegram_user_id}"
    )

    existing_result = (
        supabase
        .table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )

    existing_user = _first_row(existing_result)
    if existing_user:
        return existing_user

    now = time.time()
    user_data = {
        "telegram_user_id": telegram_user_id,
        "status": validated_status,
        "created_at": now,
        "updated_at": now
    }

    insert_result = (
        supabase
        .table("users")
        .insert(user_data)
        .execute()
    )

    created_user = _first_row(insert_result)
    if created_user:
        return created_user

    raise RuntimeError(
        "Failed to create user record"
    )


@with_retry
def create_workspace(
    name: str,
    owner_user_id: int,
    status: str = "active"
) -> Dict[str, Any]:
    """ایجاد workspace جدید به همراه عضویت owner"""
    if not (name or "").strip():
        raise ValueError(
            "Workspace name is required"
        )

    validated_status = _validate_enum(
        status,
        WORKSPACE_STATUSES,
        "workspace status"
    )

    now = time.time()
    workspace_result = (
        supabase
        .table("workspaces")
        .insert({
            "name": name.strip(),
            "owner_user_id": owner_user_id,
            "status": validated_status,
            "created_at": now,
            "updated_at": now
        })
        .execute()
    )

    workspace = _first_row(workspace_result)
    if not workspace:
        raise RuntimeError(
            "Failed to create workspace"
        )

    owner_membership = add_workspace_member(
        workspace_id=workspace["id"],
        user_id=owner_user_id,
        role="owner",
        status="active"
    )

    workspace["owner_membership"] = owner_membership
    return workspace


@with_retry
def get_workspace(
    workspace_id: int
) -> Optional[Dict[str, Any]]:
    """دریافت workspace بر اساس شناسه"""
    result = (
        supabase
        .table("workspaces")
        .select("*")
        .eq("id", workspace_id)
        .limit(1)
        .execute()
    )

    return _first_row(result)


@with_retry
def list_user_workspaces(
    user_id: int,
    include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """لیست workspaceهای کاربر"""
    membership_query = (
        supabase
        .table("workspace_members")
        .select("*")
        .eq("user_id", user_id)
    )

    if not include_inactive:
        membership_query = membership_query.eq(
            "status",
            "active"
        )

    memberships = (
        membership_query
        .execute()
        .data
        or []
    )

    workspaces = []
    for membership in memberships:
        workspace = get_workspace(
            membership["workspace_id"]
        )
        if not workspace:
            continue

        if (
            not include_inactive
            and workspace.get("status") != "active"
        ):
            continue

        workspace_data = dict(workspace)
        workspace_data["membership_id"] = membership.get("id")
        workspace_data["membership_role"] = membership.get("role")
        workspace_data["membership_status"] = membership.get("status")
        workspaces.append(workspace_data)

    return sorted(
        workspaces,
        key=lambda item: item.get("id", 0)
    )


@with_retry
def add_workspace_member(
    workspace_id: int,
    user_id: int,
    role: str = "writer",
    status: str = "active"
) -> Dict[str, Any]:
    """افزودن عضو به workspace با رفتار idempotent"""
    validated_role = _validate_enum(
        role,
        WORKSPACE_MEMBER_ROLES,
        "workspace member role"
    )
    validated_status = _validate_enum(
        status,
        WORKSPACE_MEMBER_STATUSES,
        "workspace member status"
    )

    existing_membership = get_workspace_member(
        workspace_id,
        user_id
    )
    if existing_membership:
        return existing_membership

    now = time.time()
    result = (
        supabase
        .table("workspace_members")
        .insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": validated_role,
            "status": validated_status,
            "created_at": now,
            "updated_at": now
        })
        .execute()
    )

    membership = _first_row(result)
    if membership:
        return membership

    raise RuntimeError(
        "Failed to create workspace membership"
    )


@with_retry
def get_workspace_member(
    workspace_id: int,
    user_id: int
) -> Optional[Dict[str, Any]]:
    """دریافت membership بر اساس workspace و user"""
    result = (
        supabase
        .table("workspace_members")
        .select("*")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    return _first_row(result)


@with_retry
def list_workspace_members(
    workspace_id: int,
    include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """لیست اعضای workspace"""
    query = (
        supabase
        .table("workspace_members")
        .select("*")
        .eq("workspace_id", workspace_id)
    )

    if not include_inactive:
        query = query.eq(
            "status",
            "active"
        )

    members = query.execute().data or []
    return sorted(
        members,
        key=lambda item: item.get("id", 0)
    )


@with_retry
def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    role: str
) -> Optional[Dict[str, Any]]:
    """بروزرسانی نقش عضو workspace"""
    validated_role = _validate_enum(
        role,
        WORKSPACE_MEMBER_ROLES,
        "workspace member role"
    )

    result = (
        supabase
        .table("workspace_members")
        .update({
            "role": validated_role,
            "updated_at": time.time()
        })
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .execute()
    )

    return _first_row(result)


@with_retry
def update_workspace_member_status(
    workspace_id: int,
    user_id: int,
    status: str
) -> Optional[Dict[str, Any]]:
    """بروزرسانی وضعیت عضو workspace"""
    validated_status = _validate_enum(
        status,
        WORKSPACE_MEMBER_STATUSES,
        "workspace member status"
    )

    result = (
        supabase
        .table("workspace_members")
        .update({
            "status": validated_status,
            "updated_at": time.time()
        })
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .execute()
    )

    return _first_row(result)
