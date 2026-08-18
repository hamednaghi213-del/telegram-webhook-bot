import os
import logging
import time
import uuid
import sqlite3
from typing import Optional, Dict, Any, List, Tuple
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
# PHASE 1 — WORKSPACE FOUNDATION
# =========================================================
# These functions operate on the new ws_users, ws_workspaces,
# and ws_workspace_members tables.  The legacy tenant system
# and all existing publication routes are UNTOUCHED.
#
# Valid roles:    owner | manager | publisher | writer
# Valid statuses: active | suspended | removed
# =========================================================

_WS_ROLES: frozenset = frozenset({"owner", "manager", "publisher", "writer"})
_WS_MEMBER_STATUSES: frozenset = frozenset({"active", "suspended", "removed"})


# ---------------------------------------------------------
# USERS
# ---------------------------------------------------------

@with_retry
def get_or_create_user_by_telegram_id(
    telegram_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the ws_users row for *telegram_id*, creating it if absent.

    Idempotent: calling twice with the same telegram_id returns the same
    record.  Profile fields are updated on each call to keep them fresh.

    Returns:
        Dict representing the ws_users row.
    """
    try:
        logger.debug(
            f"👤 get_or_create_user telegram_id={telegram_id}"
        )

        existing = (
            supabase
            .table("ws_users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )

        now = time.time()

        if existing.data:
            user = existing.data[0]
            update_payload: Dict[str, Any] = {"updated_at": now}
            if first_name is not None:
                update_payload["first_name"] = first_name
            if last_name is not None:
                update_payload["last_name"] = last_name
            if username is not None:
                update_payload["username"] = username

            updated = (
                supabase
                .table("ws_users")
                .update(update_payload)
                .eq("id", user["id"])
                .execute()
            )
            return updated.data[0] if updated.data else user

        payload: Dict[str, Any] = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "created_at": now,
            "updated_at": now,
        }
        created = (
            supabase
            .table("ws_users")
            .insert(payload)
            .execute()
        )
        logger.info(
            f"✅ New ws_user created telegram_id={telegram_id}"
        )
        return created.data[0]

    except Exception as e:
        logger.exception(
            f"❌ get_or_create_user_by_telegram_id({telegram_id}): {e}"
        )
        raise


# ---------------------------------------------------------
# WORKSPACES
# ---------------------------------------------------------

@with_retry
def create_workspace(
    name: str,
    owner_user_id: str,
) -> Dict[str, Any]:
    """
    Create a new workspace and automatically add the owner as a member
    with role='owner' and status='active'.

    Returns:
        Dict representing the new ws_workspaces row.

    Raises:
        ValueError: if name is empty or owner_user_id is missing.
    """
    if not name or not name.strip():
        raise ValueError("Workspace name must not be empty.")
    if not owner_user_id:
        raise ValueError("owner_user_id is required.")

    try:
        now = time.time()
        workspace_payload: Dict[str, Any] = {
            "name": name.strip(),
            "owner_user_id": owner_user_id,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        result = (
            supabase
            .table("ws_workspaces")
            .insert(workspace_payload)
            .execute()
        )
        workspace = result.data[0]
        logger.info(
            f"✅ Workspace created id={workspace['id']} "
            f"name={name!r} owner={owner_user_id}"
        )

        # Automatically enrol the owner as a member
        add_workspace_member(
            workspace_id=workspace["id"],
            user_id=owner_user_id,
            role="owner",
        )

        return workspace

    except Exception as e:
        logger.exception(f"❌ create_workspace({name!r}): {e}")
        raise


@with_retry
def get_workspace(workspace_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single workspace by its UUID.

    Returns:
        Dict representing the ws_workspaces row, or None if not found.
    """
    try:
        result = (
            supabase
            .table("ws_workspaces")
            .select("*")
            .eq("id", workspace_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        logger.debug(f"ℹ️ Workspace {workspace_id} not found.")
        return None

    except Exception as e:
        logger.exception(f"❌ get_workspace({workspace_id}): {e}")
        raise


@with_retry
def list_user_workspaces(user_id: str) -> List[Dict[str, Any]]:
    """
    Return all workspaces where *user_id* has an active membership.

    Returns:
        List of ws_workspaces rows.
    """
    try:
        members = (
            supabase
            .table("ws_workspace_members")
            .select("workspace_id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        workspace_ids = [m["workspace_id"] for m in (members.data or [])]
        if not workspace_ids:
            return []

        workspaces = (
            supabase
            .table("ws_workspaces")
            .select("*")
            .in_("id", workspace_ids)
            .execute()
        )
        return workspaces.data or []

    except Exception as e:
        logger.exception(f"❌ list_user_workspaces({user_id}): {e}")
        raise


# ---------------------------------------------------------
# WORKSPACE MEMBERS
# ---------------------------------------------------------

@with_retry
def add_workspace_member(
    workspace_id: str,
    user_id: str,
    role: str = "writer",
) -> Dict[str, Any]:
    """
    Add *user_id* to *workspace_id* with the given *role*.

    Raises:
        ValueError: if role is invalid.
        Exception:  if the (workspace_id, user_id) pair already exists
                    (enforced by the unique constraint in the database).

    Returns:
        Dict representing the new ws_workspace_members row.
    """
    if role not in _WS_ROLES:
        raise ValueError(
            f"Invalid role {role!r}. Must be one of {sorted(_WS_ROLES)}."
        )
    try:
        now = time.time()
        payload: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": role,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        result = (
            supabase
            .table("ws_workspace_members")
            .insert(payload)
            .execute()
        )
        logger.info(
            f"✅ Member added workspace={workspace_id} "
            f"user={user_id} role={role}"
        )
        return result.data[0]

    except Exception as e:
        logger.exception(
            f"❌ add_workspace_member({workspace_id}, {user_id}): {e}"
        )
        raise


@with_retry
def get_workspace_member(
    workspace_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the membership record for (workspace_id, user_id).

    Returns:
        Dict representing the ws_workspace_members row, or None.
    """
    try:
        result = (
            supabase
            .table("ws_workspace_members")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        logger.exception(
            f"❌ get_workspace_member({workspace_id}, {user_id}): {e}"
        )
        raise


@with_retry
def list_workspace_members(
    workspace_id: str,
) -> List[Dict[str, Any]]:
    """
    Return all member records for *workspace_id* (any status).

    Returns:
        List of ws_workspace_members rows.
    """
    try:
        result = (
            supabase
            .table("ws_workspace_members")
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        return result.data or []

    except Exception as e:
        logger.exception(
            f"❌ list_workspace_members({workspace_id}): {e}"
        )
        raise


@with_retry
def update_workspace_member_role(
    workspace_id: str,
    user_id: str,
    new_role: str,
) -> Optional[Dict[str, Any]]:
    """
    Change the role for an existing membership.

    Raises:
        ValueError: if new_role is not a valid role string.

    Returns:
        Updated ws_workspace_members row, or None if not found.
    """
    if new_role not in _WS_ROLES:
        raise ValueError(
            f"Invalid role {new_role!r}. Must be one of "
            f"{sorted(_WS_ROLES)}."
        )
    try:
        result = (
            supabase
            .table("ws_workspace_members")
            .update({"role": new_role, "updated_at": time.time()})
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        logger.exception(
            f"❌ update_workspace_member_role({workspace_id}, "
            f"{user_id}, {new_role}): {e}"
        )
        raise


@with_retry
def update_workspace_member_status(
    workspace_id: str,
    user_id: str,
    new_status: str,
) -> Optional[Dict[str, Any]]:
    """
    Change the status for an existing membership.

    Raises:
        ValueError: if new_status is not active/suspended/removed.

    Returns:
        Updated ws_workspace_members row, or None if not found.
    """
    if new_status not in _WS_MEMBER_STATUSES:
        raise ValueError(
            f"Invalid status {new_status!r}. Must be one of "
            f"{sorted(_WS_MEMBER_STATUSES)}."
        )
    try:
        result = (
            supabase
            .table("ws_workspace_members")
            .update({"status": new_status, "updated_at": time.time()})
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        logger.exception(
            f"❌ update_workspace_member_status({workspace_id}, "
            f"{user_id}, {new_status}): {e}"
        )
        raise
