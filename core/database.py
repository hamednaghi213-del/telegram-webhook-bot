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
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
)

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

    # Privileged client is intentionally separate.
    # Normal bot/database operations continue using the regular client.
    # Only explicitly authorized server-side operations may use this client.
    service_supabase = (
        create_client(
            SUPABASE_URL,
            SUPABASE_SERVICE_ROLE_KEY,
        )
        if SUPABASE_SERVICE_ROLE_KEY
        else None
    )

    if service_supabase is None:
        logger.warning(
            "⚠️ SUPABASE_SERVICE_ROLE_KEY is not configured | "
            "privileged workspace operations are unavailable"
        )

except Exception as e:
    logger.exception(f"❌ Failed to initialize DB: {e}")
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

WORKSPACE_PENDING_ACTIONS = {
    "create_workspace_name",
    "rename_workspace",
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
def _delete_workspace_by_id(
    workspace_id: int
) -> None:
    """حذف workspace برای rollback داخلی"""
    (
        supabase
        .table("workspaces")
        .delete()
        .eq("id", workspace_id)
        .execute()
    )


@with_retry
def get_user_by_telegram_id(
    telegram_user_id: int
) -> Optional[Dict[str, Any]]:
    """دریافت کاربر بر اساس شناسه تلگرام"""
    result = (
        supabase
        .table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )

    return _first_row(result)


@with_retry
def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """دریافت کاربر workspace بر اساس شناسه داخلی"""
    result = (
        supabase
        .table("users")
        .select("*")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


@with_retry
def set_user_pending_workspace_action(
    user_id: int,
    action: Optional[str],
    workspace_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Persist the short-lived Create/Rename workspace input state."""
    if action is not None and action not in WORKSPACE_PENDING_ACTIONS:
        raise ValueError("Invalid pending workspace action")
    if action == "rename_workspace" and workspace_id is None:
        raise ValueError("Rename action requires a workspace")
    if action != "rename_workspace":
        workspace_id = None

    result = (
        supabase.table("users")
        .update({
            "pending_workspace_action": action,
            "pending_workspace_id": workspace_id,
            "updated_at": time.time(),
        })
        .eq("id", user_id)
        .execute()
    )
    return _first_row(result)


def clear_user_pending_workspace_action(user_id: int) -> Optional[Dict[str, Any]]:
    return set_user_pending_workspace_action(user_id, None, None)


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

    try:
        add_workspace_member(
            workspace_id=workspace["id"],
            user_id=owner_user_id,
            role="owner",
            status="active"
        )
    except Exception:
        _delete_workspace_by_id(
            workspace["id"]
        )
        raise

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
def update_workspace_name(
    workspace_id: int,
    name: str
) -> Optional[Dict[str, Any]]:
    """همگام‌سازی نام workspace با نام واقعی رسانه"""
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Workspace name is required")

    result = (
        supabase
        .table("workspaces")
        .update({
            "name": normalized_name,
            "updated_at": time.time()
        })
        .eq("id", workspace_id)
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
        .select(
            "id, workspace_id, role, status, "
            "workspaces(id, name, owner_user_id, status, created_at, updated_at)"
        )
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
        workspace = membership.get("workspaces")
        # Older PostgREST/test adapters may not support embedded relations.
        # Production uses the embedded row, keeping the common path to one query.
        if not workspace:
            workspace = get_workspace(membership["workspace_id"])
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
def list_workspace_destination_counts(
    workspace_ids: List[int],
) -> Dict[int, Dict[str, int]]:
    """Return channel counts for many workspaces in one PostgREST query."""
    normalized_ids = sorted({int(value) for value in (workspace_ids or [])})
    if not normalized_ids:
        return {}

    if canonical_media_enabled():
        rows = list_canonical_destinations_for_workspaces(normalized_ids)
        counts = {
            workspace_id: {"total": 0, "active_verified": 0}
            for workspace_id in normalized_ids
        }
        destination_ids = sorted({int(row["id"]) for row in rows})
        verifications = (
            supabase.table("destination_verification").select("destination_id,verified")
            .in_("destination_id", destination_ids).execute().data or []
        ) if destination_ids else []
        verified_ids = {
            int(row["destination_id"]) for row in verifications if row.get("verified")
        }
        for destination in rows:
            workspace_id = int(destination["workspace_id"])
            counts[workspace_id]["total"] += 1
            if destination.get("status") == "active" and int(destination["id"]) in verified_ids:
                counts[workspace_id]["active_verified"] += 1
        return counts

    result = (
        supabase.table("publication_destinations")
        .select("workspace_id, status, destination_verification(verified)")
        .in_("workspace_id", normalized_ids)
        .neq("status", "removed")
        .execute()
    )
    counts = {
        workspace_id: {"total": 0, "active_verified": 0}
        for workspace_id in normalized_ids
    }
    for destination in result.data or []:
        workspace_id = int(destination["workspace_id"])
        counts.setdefault(workspace_id, {"total": 0, "active_verified": 0})
        counts[workspace_id]["total"] += 1
        verification = destination.get("destination_verification") or {}
        if isinstance(verification, list):
            verification = verification[0] if verification else {}
        if destination.get("status") == "active" and verification.get("verified"):
            counts[workspace_id]["active_verified"] += 1
    return counts


def canonical_media_enabled() -> bool:
    """Explicit cutover gate: never query additive tables on an old schema."""
    return os.getenv("ENABLE_CANONICAL_MEDIA", "false").strip().lower() == "true"


@with_retry
def list_canonical_destinations_for_workspaces(
    workspace_ids: List[int],
) -> List[Dict[str, Any]]:
    """Bulk-load physical destinations through their group associations."""
    ids = sorted({int(value) for value in (workspace_ids or [])})
    if not ids:
        return []
    associations = (
        supabase.table("workspace_destinations")
        .select("workspace_id,destination_id,status")
        .in_("workspace_id", ids)
        .eq("status", "active")
        .execute().data or []
    )
    destination_ids = sorted({int(row["destination_id"]) for row in associations})
    if not destination_ids:
        return []
    destinations = (
        supabase.table("publication_destinations")
        .select("*").in_("id", destination_ids).neq("status", "removed")
        .execute().data or []
    )
    by_id = {int(row["id"]): row for row in destinations}
    rows = []
    for association in associations:
        destination = by_id.get(int(association["destination_id"]))
        if not destination:
            continue
        rows.append({
            **destination,
            "workspace_id": int(association["workspace_id"]),
            "association_status": association.get("status"),
        })
    return sorted(rows, key=lambda row: (int(row["workspace_id"]), int(row["id"])))


@with_retry
def list_canonical_publication_destinations(
    user_id: int,
    workspace_ids: List[int],
) -> List[Dict[str, Any]]:
    """Resolve ready canonical rows with media access in bulk (no N+1)."""
    rows = [
        row for row in list_canonical_destinations_for_workspaces(workspace_ids)
        if row.get("media_identity_id") is not None
    ]
    destination_ids = sorted({int(row["id"]) for row in rows})
    media_ids = sorted({int(row["media_identity_id"]) for row in rows if row.get("media_identity_id")})
    if not destination_ids or not media_ids:
        return []
    verifications = (
        supabase.table("destination_verification").select("*")
        .in_("destination_id", destination_ids).execute().data or []
    )
    overrides = (
        supabase.table("destination_branding").select("*")
        .in_("destination_id", destination_ids).execute().data or []
    )
    identities = (
        supabase.table("media_identities").select("*")
        .in_("id", media_ids).execute().data or []
    )
    memberships = (
        supabase.table("media_identity_members").select("*")
        .eq("user_id", int(user_id)).in_("media_identity_id", media_ids)
        .eq("status", "active").execute().data or []
    )
    verification_by_destination = {int(row["destination_id"]): row for row in verifications}
    override_by_destination = {int(row["destination_id"]): row for row in overrides}
    identity_by_id = {int(row["id"]): row for row in identities}
    membership_by_media = {int(row["media_identity_id"]): row for row in memberships}
    resolved = []
    for row in rows:
        media_id = int(row["media_identity_id"])
        resolved.append({
            **row,
            "verification": verification_by_destination.get(int(row["id"]), {}),
            "destination_branding": override_by_destination.get(int(row["id"]), {}),
            "media_identity": identity_by_id.get(media_id, {}),
            "media_member": membership_by_media.get(media_id, {}),
            "media_status": identity_by_id.get(media_id, {}).get("status"),
        })
    return resolved


@with_retry
def move_canonical_destination_associations(
    user_id: int,
    destination_ids: List[int],
    target_workspace_id: int,
) -> List[Dict[str, Any]]:
    """
    Atomically move canonical destination associations.

    This operation is privileged:
    - normal database traffic continues through the regular Supabase client
    - this RPC uses the service-role client
    - the RPC independently verifies workspace and media permissions
    """
    ids = sorted({int(value) for value in destination_ids})

    if not ids:
        return []

    if service_supabase is None:
        raise RuntimeError(
            "Secure workspace destination move is not configured"
        )

    result = service_supabase.rpc(
        "move_workspace_destination_memberships_authorized",
        {
            "p_user_id": int(user_id),
            "p_destination_ids": ids,
            "p_target_workspace_id": int(target_workspace_id),
        },
    ).execute()

    rows = result.data or []

    if {int(row["destination_id"]) for row in rows} != set(ids):
        raise RuntimeError(
            "Canonical association move was incomplete"
        )

    return rows


@with_retry
def claim_legacy_destination_canonical(
    user_id: int,
    workspace_id: int,
    identity_key: str,
    platform: str,
    external_id: str,
    media_name: str,
    hashtag: str = "",
    channel_tag: str = "",
) -> Dict[str, Any]:
    """Call the transaction-scoped canonical claim primitive."""
    result = supabase.rpc("claim_legacy_destination_canonical", {
        "p_user_id": int(user_id),
        "p_workspace_id": int(workspace_id),
        "p_identity_key": str(identity_key),
        "p_platform": str(platform),
        "p_external_id": str(external_id),
        "p_media_name": str(media_name),
        "p_hashtag": str(hashtag or ""),
        "p_channel_tag": str(channel_tag or ""),
    }).execute()
    row = _first_row(result)
    if not row:
        raise RuntimeError("Canonical Legacy claim returned no destination")
    return row


@with_retry
def list_owned_workspaces(
    owner_user_id: int,
    include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """لیست workspaceهایی که کاربر مالک آن‌هاست"""
    query = (
        supabase
        .table("workspaces")
        .select("*")
        .eq("owner_user_id", owner_user_id)
    )

    if not include_inactive:
        query = query.eq(
            "status",
            "active"
        )

    workspaces = query.execute().data or []
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


# =========================================================
# PUBLICATION DESTINATIONS FOUNDATION
# =========================================================


PUBLICATION_DESTINATION_PLATFORMS = {
    "telegram",
    "bale"
}

PUBLICATION_DESTINATION_TYPES = {
    "channel"
}

PUBLICATION_DESTINATION_STATUSES = {
    "active",
    "inactive",
    "removed"
}


def _validate_destination_name(name: str) -> str:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Publication destination name is required")
    return normalized_name


def _validate_external_id(external_id: str) -> str:
    normalized_external_id = str(external_id or "").strip()
    if not normalized_external_id:
        raise ValueError("Publication destination external_id is required")
    return normalized_external_id


@with_retry
def create_publication_destination(
    workspace_id: int,
    platform: str,
    destination_type: str,
    name: str,
    external_id: str,
    status: str = "active",
    is_default: bool = False
) -> Dict[str, Any]:
    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError(f"Workspace not found: {workspace_id}")

    validated_platform = _validate_enum(
        platform,
        PUBLICATION_DESTINATION_PLATFORMS,
        "publication destination platform"
    )
    validated_destination_type = _validate_enum(
        destination_type,
        PUBLICATION_DESTINATION_TYPES,
        "publication destination type"
    )
    validated_status = _validate_enum(
        status,
        PUBLICATION_DESTINATION_STATUSES,
        "publication destination status"
    )
    validated_name = _validate_destination_name(name)
    validated_external_id = _validate_external_id(external_id)

    if is_default and validated_status != "active":
        raise ValueError(
            "Default publication destination must be active"
        )

    existing_result = (
        supabase
        .table("publication_destinations")
        .select("*")
        .eq("workspace_id", workspace_id)
        .eq("platform", validated_platform)
        .eq("external_id", validated_external_id)
        .execute()
    )

    existing_destination = next(
        (
            row for row in (existing_result.data or [])
            if row.get("status") != "removed"
        ),
        None
    )
    if existing_destination:
        if is_default and existing_destination.get("status") != "active":
            raise ValueError(
                "Default publication destination must be active"
            )
        if is_default and not existing_destination.get("is_default"):
            set_default_publication_destination(
                workspace_id,
                existing_destination["id"]
            )
            return get_publication_destination(
                existing_destination["id"]
            ) or existing_destination
        return existing_destination

    now = time.time()
    insert_result = (
        supabase
        .table("publication_destinations")
        .insert({
            "workspace_id": workspace_id,
            "platform": validated_platform,
            "destination_type": validated_destination_type,
            "name": validated_name,
            "external_id": validated_external_id,
            "status": validated_status,
            "is_default": bool(is_default),
            "created_at": now,
            "updated_at": now
        })
        .execute()
    )

    destination = _first_row(insert_result)
    if not destination:
        raise RuntimeError(
            "Failed to create publication destination"
        )

    if is_default:
        set_default_publication_destination(
            workspace_id,
            destination["id"]
        )
        destination = get_publication_destination(
            destination["id"]
        ) or destination

    return destination


@with_retry
def get_publication_destination(
    destination_id: int
) -> Optional[Dict[str, Any]]:
    result = (
        supabase
        .table("publication_destinations")
        .select("*")
        .eq("id", destination_id)
        .limit(1)
        .execute()
    )

    return _first_row(result)


@with_retry
def list_workspace_destinations(
    workspace_id: int,
    include_removed: bool = False
) -> List[Dict[str, Any]]:
    if canonical_media_enabled():
        rows = list_canonical_destinations_for_workspaces([workspace_id])
        if include_removed:
            return rows
        return [row for row in rows if row.get("status") != "removed"]

    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError(f"Workspace not found: {workspace_id}")

    destinations = (
        supabase
        .table("publication_destinations")
        .select("*")
        .eq("workspace_id", workspace_id)
        .execute()
        .data
        or []
    )

    if not include_removed:
        destinations = [
            destination
            for destination in destinations
            if destination.get("status") != "removed"
        ]

    return sorted(
        destinations,
        key=lambda item: item.get("id", 0)
    )


@with_retry
def list_publication_destinations_for_workspaces(
    workspace_ids: List[int],
    include_removed: bool = False,
) -> List[Dict[str, Any]]:
    """Bulk-load destinations for workspace management without N+1 queries."""
    ids = sorted({int(workspace_id) for workspace_id in workspace_ids})
    if not ids:
        return []
    query = (
        supabase.table("publication_destinations")
        .select("*")
        .in_("workspace_id", ids)
    )
    if not include_removed:
        query = query.neq("status", "removed")
    return sorted(query.execute().data or [], key=lambda item: item.get("id", 0))


@with_retry
def move_publication_destinations(
    destination_ids: List[int],
    target_workspace_id: int,
) -> List[Dict[str, Any]]:
    """Move an already-authorized batch in one database statement."""
    ids = sorted({int(destination_id) for destination_id in destination_ids})
    if not ids:
        return []
    result = (
        supabase.table("publication_destinations")
        .update({
            "workspace_id": int(target_workspace_id),
            "is_default": False,
            "updated_at": time.time(),
        })
        .in_("id", ids)
        .execute()
    )
    rows = result.data or []
    if {int(row["id"]) for row in rows} != set(ids):
        raise RuntimeError("Destination move did not update the complete batch")
    return sorted(rows, key=lambda item: item.get("id", 0))


@with_retry
def update_publication_destination(
    destination_id: int,
    **fields
) -> Optional[Dict[str, Any]]:
    existing_destination = get_publication_destination(
        destination_id
    )
    if not existing_destination:
        return None

    update_data = {}

    if "name" in fields:
        update_data["name"] = _validate_destination_name(
            fields["name"]
        )

    if "external_id" in fields:
        update_data["external_id"] = _validate_external_id(
            fields["external_id"]
        )

    if "platform" in fields:
        update_data["platform"] = _validate_enum(
            fields["platform"],
            PUBLICATION_DESTINATION_PLATFORMS,
            "publication destination platform"
        )

    if "destination_type" in fields:
        update_data["destination_type"] = _validate_enum(
            fields["destination_type"],
            PUBLICATION_DESTINATION_TYPES,
            "publication destination type"
        )

    if "status" in fields:
        update_data["status"] = _validate_enum(
            fields["status"],
            PUBLICATION_DESTINATION_STATUSES,
            "publication destination status"
        )

    if "is_default" in fields:
        update_data["is_default"] = bool(fields["is_default"])

    if (
        update_data.get("is_default") is True
        and update_data.get("status", existing_destination.get("status")) != "active"
    ):
        raise ValueError(
            "Default publication destination must be active"
        )

    if not update_data:
        return existing_destination

    update_data["updated_at"] = time.time()
    result = (
        supabase
        .table("publication_destinations")
        .update(update_data)
        .eq("id", destination_id)
        .execute()
    )

    updated_destination = _first_row(result)
    if (
        updated_destination
        and updated_destination.get("is_default")
        and updated_destination.get("status") == "active"
    ):
        set_default_publication_destination(
            updated_destination["workspace_id"],
            updated_destination["id"]
        )
        return get_publication_destination(
            updated_destination["id"]
        ) or updated_destination

    return updated_destination


@with_retry
def update_publication_destination_status(
    destination_id: int,
    status: str
) -> Optional[Dict[str, Any]]:
    validated_status = _validate_enum(
        status,
        PUBLICATION_DESTINATION_STATUSES,
        "publication destination status"
    )

    destination = get_publication_destination(
        destination_id
    )
    if not destination:
        return None

    update_fields = {
        "status": validated_status
    }
    if validated_status != "active" and destination.get("is_default"):
        update_fields["is_default"] = False

    return update_publication_destination(
        destination_id,
        **update_fields
    )


@with_retry
def set_default_publication_destination(
    workspace_id: int,
    destination_id: int
) -> Dict[str, Any]:
    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError(f"Workspace not found: {workspace_id}")

    destination = get_publication_destination(destination_id)
    if not destination:
        raise ValueError(
            f"Publication destination not found: {destination_id}"
        )
    if destination.get("workspace_id") != workspace_id:
        raise ValueError(
            "Destination does not belong to workspace"
        )
    if destination.get("status") != "active":
        raise ValueError(
            "Default publication destination must be active"
        )

    now = time.time()
    (
        supabase
        .table("publication_destinations")
        .update({
            "is_default": False,
            "updated_at": now
        })
        .eq("workspace_id", workspace_id)
        .eq("status", "active")
        .execute()
    )

    updated_result = (
        supabase
        .table("publication_destinations")
        .update({
            "is_default": True,
            "updated_at": now
        })
        .eq("id", destination_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )

    default_destination = _first_row(updated_result)
    if default_destination:
        return default_destination

    raise RuntimeError(
        "Failed to set default publication destination"
    )


@with_retry
def get_default_publication_destination(
    workspace_id: int
) -> Optional[Dict[str, Any]]:
    result = (
        supabase
        .table("publication_destinations")
        .select("*")
        .eq("workspace_id", workspace_id)
        .eq("status", "active")
        .eq("is_default", True)
        .limit(1)
        .execute()
    )

    return _first_row(result)


# =========================================================
# PHASE 4A — WORKSPACE SETUP STATE
# =========================================================

def get_workspace_setup_state(
    workspace_id: int
) -> Optional[Dict[str, Any]]:
    """Fetch the setup state for a workspace (one row, keyed by workspace_id)."""
    result = (
        supabase
        .table("workspace_setup_state")
        .select("*")
        .eq("workspace_id", workspace_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


def upsert_workspace_setup_state(
    workspace_id: int,
    step: str,
    current_step_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Create or update workspace setup state.  Safe to call repeatedly."""
    payload: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "step": step,
        "current_step_key": current_step_key,
        "updated_at": time.time(),
    }
    result = (
        supabase
        .table("workspace_setup_state")
        .upsert(payload, on_conflict="workspace_id")
        .execute()
    )
    return _first_row(result)


@with_retry
def update_workspace_branding_sample(
    workspace_id: int,
    sample_text: str,
    sample_icons: List[str],
    status: str,
    bale_url: Optional[str] = None,
    bale_channel: Optional[str] = None,
    bale_status: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Persist a branding sample draft or its confirmation status."""
    allowed_statuses = {"not_started", "pending_confirmation", "confirmed"}
    if status not in allowed_statuses:
        raise ValueError(f"Invalid branding sample status: {status}")
    payload = {
        "branding_sample_text": (sample_text or "").strip(),
        "branding_sample_icons": list(sample_icons or []),
        "branding_sample_status": status,
        "updated_at": time.time(),
    }
    if bale_url is not None:
        payload["branding_sample_bale_url"] = (bale_url or "").strip()
    if bale_channel is not None:
        payload["branding_sample_bale_channel"] = (bale_channel or "").strip()
    if bale_status is not None:
        if bale_status not in {"none", "pending", "connected", "ignored"}:
            raise ValueError(f"Invalid Bale suggestion status: {bale_status}")
        payload["branding_sample_bale_status"] = bale_status
    if profile is not None:
        payload["branding_sample_profile"] = dict(profile or {})
    result = (
        supabase
        .table("workspace_setup_state")
        .update(payload)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _first_row(result)


# =========================================================
# PHASE 4A — WORKSPACE BRANDING
# =========================================================

def get_workspace_branding(
    workspace_id: int
) -> Optional[Dict[str, Any]]:
    """Fetch workspace branding record (media_name, hashtag, channel_tag)."""
    result = (
        supabase
        .table("workspace_branding")
        .select("*")
        .eq("workspace_id", workspace_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


def upsert_workspace_branding(
    workspace_id: int,
    media_name: str,
    hashtag: str,
    channel_tag: str
) -> Optional[Dict[str, Any]]:
    """Create or update workspace branding.  Belongs to workspace, not user."""
    payload: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "media_name": (media_name or "").strip(),
        "hashtag": (hashtag or "").strip(),
        "channel_tag": (channel_tag or "").strip(),
        "updated_at": time.time(),
    }
    result = (
        supabase
        .table("workspace_branding")
        .upsert(payload, on_conflict="workspace_id")
        .execute()
    )
    return _first_row(result)


@with_retry
def update_workspace_branding_icons(
    workspace_id: int,
    icons: List[str],
    enabled: bool = True,
) -> Optional[Dict[str, Any]]:
    """Update the ordered Unicode icon list without changing other branding."""
    result = (
        supabase
        .table("workspace_branding")
        .update({
            "publication_icons": list(icons or []),
            "icons_enabled": bool(enabled and icons),
            "updated_at": time.time(),
        })
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _first_row(result)


# =========================================================
# PHASE 4A — DESTINATION VERIFICATION
# =========================================================

def get_destination_verification(
    destination_id: int
) -> Optional[Dict[str, Any]]:
    """Fetch verification record for a publication destination."""
    result = (
        supabase
        .table("destination_verification")
        .select("*")
        .eq("destination_id", destination_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


def upsert_destination_verification(
    destination_id: int,
    verified: bool = False,
    verification_note: str = ""
) -> Optional[Dict[str, Any]]:
    """Create or update destination verification record."""
    payload: Dict[str, Any] = {
        "destination_id": destination_id,
        "verified": verified,
        "verification_note": (verification_note or "").strip(),
        "updated_at": time.time(),
    }
    result = (
        supabase
        .table("destination_verification")
        .upsert(payload, on_conflict="destination_id")
        .execute()
    )
    return _first_row(result)


# =========================================================
# PHASE 4A — DESTINATION BRANDING
# =========================================================

def get_destination_branding(
    destination_id: int
) -> Optional[Dict[str, Any]]:
    """Fetch per-destination branding record (hashtag, channel_tag, custom_footer)."""
    result = (
        supabase
        .table("destination_branding")
        .select("*")
        .eq("destination_id", destination_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


def upsert_destination_branding(
    destination_id: int,
    hashtag: str = "",
    channel_tag: str = "",
    custom_footer: Optional[str] = None,
    footer_enabled: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Create or update per-destination branding.

    custom_footer is optional — pass None to leave it unset/cleared.
    footer_enabled controls whether the footer is active regardless of
    whether custom_footer has a value.
    Does NOT touch workspace_branding or legacy tenant columns.
    """
    payload: Dict[str, Any] = {
        "destination_id": destination_id,
        "hashtag": (hashtag or "").strip(),
        "channel_tag": (channel_tag or "").strip(),
        "custom_footer": custom_footer,
        "footer_enabled": bool(footer_enabled),
        "updated_at": time.time(),
    }
    result = (
        supabase
        .table("destination_branding")
        .upsert(payload, on_conflict="destination_id")
        .execute()
    )
    return _first_row(result)


# =========================================================
# PHASE 4B — PUBLISHABLE DESTINATIONS & MEMBERSHIPS
# =========================================================

def list_verified_active_destinations(
    workspace_id: int
) -> List[Dict[str, Any]]:
    """
    Return publication_destinations that are:
    - status = 'active'
    - platform is supported ('telegram' or 'bale')
    - have a matching destination_verification with verified = True

    Reuses existing helper functions — no new Supabase calls introduced beyond what
    list_workspace_destinations and get_destination_verification already do.
    """
    try:
        all_active = list_workspace_destinations(
            workspace_id, include_removed=False
        )
        verified = []
        for dest in all_active:
            if dest.get("status") != "active":
                continue
            if dest.get("platform") not in {"telegram", "bale"}:
                continue
            verif = get_destination_verification(dest["id"])
            if verif and verif.get("verified"):
                verified.append(dest)
        return verified
    except Exception as e:
        logger.exception(
            f"list_verified_active_destinations failed | "
            f"workspace={workspace_id} | {e}"
        )
        return []


def create_publication_message_link(**payload) -> Optional[Dict[str, Any]]:
    """Store the message IDs needed to mirror Telegram edits to Bale."""
    payload = dict(payload)
    payload["updated_at"] = time.time()
    result = (
        supabase.table("publication_message_links")
        .upsert(payload, on_conflict="telegram_chat_id,telegram_message_id")
        .execute()
    )
    return _first_row(result)


@with_retry
def update_workspace_branding_profile(
    workspace_id: int,
    profile: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Persist the complete confirmed sample pattern, not only a flat icon list."""
    result = (
        supabase.table("workspace_branding")
        .update({
            "publication_profile": dict(profile or {}),
            "updated_at": time.time(),
        })
        .eq("workspace_id", workspace_id)
        .execute()
    )
    return _first_row(result)


def get_publication_message_link(
    telegram_chat_id: Any,
    telegram_message_id: int,
) -> Optional[Dict[str, Any]]:
    result = (
        supabase.table("publication_message_links")
        .select("*")
        .eq("telegram_chat_id", str(telegram_chat_id))
        .eq("telegram_message_id", int(telegram_message_id))
        .limit(1)
        .execute()
    )
    return _first_row(result)


def list_user_workspace_memberships(
    user_id: int
) -> List[Dict[str, Any]]:
    """
    Return all workspaces where user has an active membership.
    Returns list of workspace rows (joined from workspace_members + workspaces).
    """
    try:
        result = (
            supabase
            .table("workspace_members")
            .select(
                "workspace_id, role, status, "
                "workspaces(id, name, status, owner_user_id)"
            )
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        rows = result.data or []
        workspaces = []
        for row in rows:
            ws = row.get("workspaces")
            if ws and ws.get("status") == "active":
                ws = dict(ws)
                ws["member_role"] = row.get("role")
                workspaces.append(ws)
        return workspaces
    except Exception as e:
        logger.exception(
            f"list_user_workspace_memberships failed | user={user_id} | {e}"
        )
        return []


# =========================================================
# PHASE 5 — ACTIVE WORKSPACE PREFERENCE
# =========================================================

@with_retry
def get_active_workspace_preference(
    user_id: int
) -> Optional[Dict[str, Any]]:
    """Return the user's persisted active-workspace preference, if any."""
    result = (
        supabase
        .table("user_workspace_preferences")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


@with_retry
def list_selected_workspace_ids(user_id: int) -> List[int]:
    """Return the user's explicitly selected workspace IDs."""
    result = (
        supabase.table("user_selected_workspaces")
        .select("workspace_id").eq("user_id", user_id).execute()
    )
    return [int(row["workspace_id"]) for row in (result.data or [])]


@with_retry
def set_legacy_workspace_selected(user_id: int, selected: bool) -> Dict[str, Any]:
    """Persist whether the legacy tenant is a publication target."""
    existing = get_active_workspace_preference(user_id)
    if not existing:
        raise ValueError("Workspace preference does not exist")
    result = (
        supabase.table("user_workspace_preferences")
        .update({"legacy_selected": bool(selected), "updated_at": time.time()})
        .eq("user_id", user_id)
        .execute()
    )
    preference = _first_row(result)
    if not preference:
        raise RuntimeError("Failed to persist legacy publication selection")
    return preference


@with_retry
def select_workspace(user_id: int, workspace_id: int) -> Dict[str, Any]:
    """Add an active membership to the simultaneous publication set."""
    preference = set_active_workspace(user_id, workspace_id)
    result = (
        supabase.table("user_selected_workspaces")
        .upsert(
            {"user_id": user_id, "workspace_id": workspace_id},
            on_conflict="user_id,workspace_id",
        ).execute()
    )
    if not _first_row(result):
        raise RuntimeError("Failed to select workspace")
    return preference


@with_retry
def deselect_workspace(user_id: int, workspace_id: int) -> None:
    """Remove a workspace from the simultaneous publication set."""
    result = (
        supabase.table("user_selected_workspaces").delete()
        .eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    )
    return result.data


@with_retry
def set_active_workspace(
    user_id: int,
    workspace_id: int
) -> Dict[str, Any]:
    """Persist an active workspace only when membership and workspace are active."""
    membership = get_workspace_member(workspace_id, user_id)
    if not membership or membership.get("status") != "active":
        raise ValueError("User is not an active member of this workspace")

    workspace = get_workspace(workspace_id)
    if not workspace or workspace.get("status") != "active":
        raise ValueError("Workspace is not active")

    now = time.time()
    existing = get_active_workspace_preference(user_id)
    payload = {
        "user_id": user_id,
        "active_workspace_id": workspace_id,
        "context_type": "workspace",
        # PostgreSQL validates NOT NULL columns on the proposed INSERT row
        # before resolving ON CONFLICT.  Therefore an upsert must include
        # created_at even when this user already has a preference row.
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }

    result = (
        supabase
        .table("user_workspace_preferences")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )
    preference = _first_row(result)
    if not preference:
        raise RuntimeError("Failed to persist active workspace")
    return preference


@with_retry
def set_active_legacy_context(user_id: int) -> Dict[str, Any]:
    """Persist the legacy tenant as the user's active media context."""
    existing = get_active_workspace_preference(user_id)
    now = time.time()
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "active_workspace_id": None,
        "context_type": "legacy",
        "legacy_selected": True,
        # Keep the original creation timestamp while still supplying the
        # required column for PostgREST's INSERT ... ON CONFLICT statement.
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    result = (
        supabase
        .table("user_workspace_preferences")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )
    preference = _first_row(result)
    if not preference:
        raise RuntimeError("Failed to persist legacy context")
    return preference
