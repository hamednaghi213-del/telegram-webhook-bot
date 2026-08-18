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
# PHASE 1 — WORKSPACE FOUNDATION HELPERS
#
# These functions are purely additive and operate on the
# new users / workspaces / workspace_members tables.
# They do NOT touch the existing tenants table or any
# legacy routing / publication behaviour.
# =========================================================

# ---------------------------------------------------------
# Users
# ---------------------------------------------------------

@with_retry
def get_or_create_user_by_telegram_id(
    telegram_user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the users row for telegram_user_id, creating it if absent.

    Returns:
        Dict with user record fields.
    """
    try:
        result = (
            supabase
            .table("users")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]

        insert_data: Dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
        }
        if username is not None:
            insert_data["username"] = username
        if first_name is not None:
            insert_data["first_name"] = first_name
        if last_name is not None:
            insert_data["last_name"] = last_name

        created = (
            supabase
            .table("users")
            .insert(insert_data)
            .execute()
        )
        return created.data[0]

    except Exception as e:
        logger.exception(
            f"❌ get_or_create_user_by_telegram_id({telegram_user_id}): {e}"
        )
        raise


# ---------------------------------------------------------
# Workspaces
# ---------------------------------------------------------

@with_retry
def create_workspace(
    name: str,
    owner_user_id: int,
) -> Dict[str, Any]:
    """
    Create a new workspace owned by owner_user_id (users.id).

    Automatically adds the owner as a member with role='owner'.

    Returns:
        Dict with workspace record fields.
    """
    try:
        ws = (
            supabase
            .table("workspaces")
            .insert({"name": name, "owner_user_id": owner_user_id})
            .execute()
        )
        workspace = ws.data[0]

        # Auto-add owner as workspace member
        supabase.table("workspace_members").insert({
            "workspace_id": workspace["id"],
            "user_id": owner_user_id,
            "role": "owner",
            "status": "active",
        }).execute()

        return workspace

    except Exception as e:
        logger.exception(f"❌ create_workspace({name!r}): {e}")
        raise


@with_retry
def get_workspace(workspace_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch a workspace by its primary key.

    Returns:
        Dict with workspace fields, or None if not found.
    """
    try:
        result = (
            supabase
            .table("workspaces")
            .select("*")
            .eq("id", workspace_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    except Exception as e:
        logger.exception(f"❌ get_workspace({workspace_id}): {e}")
        raise


@with_retry
def list_user_workspaces(user_id: int) -> List[Dict[str, Any]]:
    """
    Return all workspaces where user_id has an active membership.

    Args:
        user_id: users.id (not telegram_user_id)

    Returns:
        List of workspace dicts.
    """
    try:
        memberships = (
            supabase
            .table("workspace_members")
            .select("workspace_id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        workspace_ids = [m["workspace_id"] for m in (memberships.data or [])]
        if not workspace_ids:
            return []

        result = (
            supabase
            .table("workspaces")
            .select("*")
            .in_("id", workspace_ids)
            .execute()
        )
        return result.data or []

    except Exception as e:
        logger.exception(f"❌ list_user_workspaces({user_id}): {e}")
        raise


# ---------------------------------------------------------
# Workspace Members
# ---------------------------------------------------------

@with_retry
def add_workspace_member(
    workspace_id: int,
    user_id: int,
    role: str,
) -> Dict[str, Any]:
    """
    Add user_id to workspace_id with the given role.

    Raises an exception on duplicate (workspace_id, user_id).

    Returns:
        Dict with workspace_members record fields.
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .insert({
                "workspace_id": workspace_id,
                "user_id": user_id,
                "role": role,
                "status": "active",
            })
            .execute()
        )
        return result.data[0]

    except Exception as e:
        logger.exception(
            f"❌ add_workspace_member(ws={workspace_id}, user={user_id}): {e}"
        )
        raise


@with_retry
def get_workspace_member(
    workspace_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a single workspace_members row.

    Returns:
        Dict or None if not found.
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    except Exception as e:
        logger.exception(
            f"❌ get_workspace_member(ws={workspace_id}, user={user_id}): {e}"
        )
        raise


@with_retry
def list_workspace_members(
    workspace_id: int,
) -> List[Dict[str, Any]]:
    """
    Return all workspace_members rows for a workspace.

    Returns:
        List of workspace_members dicts.
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        return result.data or []

    except Exception as e:
        logger.exception(f"❌ list_workspace_members({workspace_id}): {e}")
        raise


@with_retry
def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    new_role: str,
) -> bool:
    """
    Change the role of an existing workspace member.

    Returns:
        True if a row was updated.
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .update({"role": new_role})
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)

    except Exception as e:
        logger.exception(
            f"❌ update_workspace_member_role(ws={workspace_id}, user={user_id}): {e}"
        )
        raise


@with_retry
def update_workspace_member_status(
    workspace_id: int,
    user_id: int,
    new_status: str,
) -> bool:
    """
    Change the status of an existing workspace member.

    Valid statuses: active, suspended, removed

    Returns:
        True if a row was updated.
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .update({"status": new_status})
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)

    except Exception as e:
        logger.exception(
            f"❌ update_workspace_member_status(ws={workspace_id}, user={user_id}): {e}"
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
