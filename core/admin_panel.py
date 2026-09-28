"""Private Admin Control command surface.

This module is intentionally isolated from content algorithms.
It manages registration approvals, destination administration,
and audit views only.
"""

import importlib
from typing import Callable

from core.admin_control import is_admin_identity


SendMessage = Callable[[int, str], bool]


def _platform(origin: str) -> str:
    return (
        "bale"
        if (origin or "").strip().lower() == "bale"
        else "telegram"
    )


def _require_admin(
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    platform = _platform(origin)

    if not is_admin_identity(
        platform,
        chat_id,
    ):
        send_message(
            chat_id,
            "❌ دسترسی ادمین ندارید.",
        )
        return False

    return True


def _database():
    return importlib.import_module(
        "core.database"
    )


def _parse_id_and_reason(args: str):
    value = (args or "").strip()

    if not value:
        return None, ""

    parts = value.split(
        maxsplit=1,
    )

    try:
        item_id = int(parts[0])
    except (TypeError, ValueError):
        return None, ""

    if item_id <= 0:
        return None, ""

    reason = (
        parts[1].strip()
        if len(parts) > 1
        else ""
    )

    return item_id, reason


def _find_pending_registration(
    database,
    request_id: int,
):
    for row in (
        database
        .list_pending_admin_registration_requests()
        or []
    ):
        try:
            if int(row.get("id")) == int(
                request_id
            ):
                return row
        except (TypeError, ValueError):
            continue

    return None


def _find_destination(
    database,
    destination_id: int,
):
    for row in (
        database
        .list_admin_destination_inventory()
        or []
    ):
        try:
            if int(row.get("id")) == int(
                destination_id
            ):
                return row
        except (TypeError, ValueError):
            continue

    return None


def handle_admin_root(
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    send_message(
        chat_id,
        "🛡 پنل مدیریت\n\n"
        "👤 ثبت‌نام کاربران\n"
        "/adminregistrations\n\n"
        "📥 درخواست‌های افزودن کانال\n"
        "/adminrequests\n\n"
        "📡 کانال‌ها و مقصدها\n"
        "/admindestinations\n\n"
        "📜 گزارش فعالیت‌ها\n"
        "/adminaudit",
    )

    return True


def handle_admin_registrations(
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    database = _database()

    rows = (
        database
        .list_pending_admin_registration_requests()
        or []
    )

    if not rows:
        send_message(
            chat_id,
            "✅ درخواست ثبت‌نام در انتظار بررسی وجود ندارد.",
        )
        return True

    lines = [
        (
            "👤 درخواست‌های ثبت‌نام "
            f"در انتظار بررسی: {len(rows)}"
        ),
        "",
    ]

    for row in rows[:30]:
        request_id = row.get("id")
        user_id = row.get("user_id")

        requested_platform = (
            row.get("requested_platform")
            or "?"
        )

        external_user_id = (
            row.get(
                "requested_external_user_id"
            )
            or "?"
        )

        lines.extend([
            f"#{request_id}",
            f"User DB ID: {user_id}",
            f"Platform: {requested_platform}",
            (
                "External ID: "
                f"{external_user_id}"
            ),
            (
                "✅ /adminregapprove "
                f"{request_id}"
            ),
            (
                "❌ /adminregreject "
                f"{request_id}"
            ),
            "",
        ])

    if len(rows) > 30:
        lines.append(
            f"… و {len(rows) - 30} درخواست دیگر"
        )

    send_message(
        chat_id,
        "\n".join(lines),
    )

    return True


def handle_admin_registration_approve(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    request_id, reason = (
        _parse_id_and_reason(args)
    )

    if request_id is None:
        send_message(
            chat_id,
            "❌ فرمت صحیح:\n"
            "/adminregapprove REQUEST_ID [reason]",
        )
        return True

    database = _database()

    request_row = (
        _find_pending_registration(
            database,
            request_id,
        )
    )

    if not request_row:
        send_message(
            chat_id,
            "❌ درخواست pending با این شناسه پیدا نشد.",
        )
        return True

    platform = _platform(origin)

    reviewed = (
        database
        .review_admin_registration_request(
            request_id,
            "approved",
            review_reason=(
                reason
                or "approved by admin"
            ),
            reviewed_by_platform=platform,
            reviewed_by_external_user_id=(
                chat_id
            ),
        )
    )

    if not reviewed:
        send_message(
            chat_id,
            "❌ ثبت نتیجه تأیید در دیتابیس انجام نشد.",
        )
        return True

    user_id = int(
        request_row["user_id"]
    )

    updated_user = (
        database.update_user_status(
            user_id,
            "active",
        )
    )

    if not updated_user:
        send_message(
            chat_id,
            "⚠️ درخواست تأیید شد اما فعال‌سازی کاربر کامل نشد.",
        )
        return True

    database.record_admin_audit_log(
        "approve_registration",
        platform,
        actor_external_user_id=chat_id,
        target_type="user",
        target_id=user_id,
        details={
            "request_id": request_id,
            "reason": (
                reason
                or "approved by admin"
            ),
        },
    )

    send_message(
        chat_id,
        "✅ ثبت‌نام تأیید شد.\n"
        f"Request: {request_id}\n"
        f"User: {user_id}",
    )

    return True


def handle_admin_registration_reject(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    request_id, reason = (
        _parse_id_and_reason(args)
    )

    if request_id is None:
        send_message(
            chat_id,
            "❌ فرمت صحیح:\n"
            "/adminregreject REQUEST_ID [reason]",
        )
        return True

    database = _database()

    request_row = (
        _find_pending_registration(
            database,
            request_id,
        )
    )

    if not request_row:
        send_message(
            chat_id,
            "❌ درخواست pending با این شناسه پیدا نشد.",
        )
        return True

    platform = _platform(origin)

    reviewed = (
        database
        .review_admin_registration_request(
            request_id,
            "rejected",
            review_reason=(
                reason
                or "rejected by admin"
            ),
            reviewed_by_platform=platform,
            reviewed_by_external_user_id=(
                chat_id
            ),
        )
    )

    if not reviewed:
        send_message(
            chat_id,
            "❌ ثبت نتیجه رد درخواست در دیتابیس انجام نشد.",
        )
        return True

    user_id = int(
        request_row["user_id"]
    )

    database.update_user_status(
        user_id,
        "inactive",
    )

    database.record_admin_audit_log(
        "reject_registration",
        platform,
        actor_external_user_id=chat_id,
        target_type="user",
        target_id=user_id,
        details={
            "request_id": request_id,
            "reason": (
                reason
                or "rejected by admin"
            ),
        },
    )

    send_message(
        chat_id,
        "❌ درخواست ثبت‌نام رد شد.\n"
        f"Request: {request_id}\n"
        f"User: {user_id}",
    )

    return True


def handle_admin_destinations(
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    database = _database()

    rows = (
        database
        .list_admin_destination_inventory()
        or []
    )

    total = len(rows)

    active = sum(
        1
        for row in rows
        if (
            (
                row.get("admin_state")
                or "active"
            )
            == "active"
            and row.get("status")
            != "removed"
        )
    )

    paused = sum(
        1
        for row in rows
        if (
            row.get("admin_state")
            == "paused"
        )
    )

    blocked = sum(
        1
        for row in rows
        if (
            row.get("admin_state")
            == "blocked"
        )
    )

    lines = [
        "📡 مدیریت کانال‌ها و مقصدها",
        "",
        f"کل مقصدهای متصل: {total}",
        f"🟢 فعال مدیریتی: {active}",
        f"⏸ متوقف موقت: {paused}",
        f"⛔ بلاک: {blocked}",
        "",
    ]

    if not rows:
        lines.append(
            "مقصدی ثبت نشده است."
        )

        send_message(
            chat_id,
            "\n".join(lines),
        )

        return True

    for row in rows[:25]:
        destination_id = row.get("id")

        platform = (
            row.get("platform")
            or "?"
        )

        external_id = (
            row.get("external_id")
            or row.get("name")
            or "?"
        )

        workspace_id = (
            row.get("workspace_id")
            or "?"
        )

        workspace_name = (
            row.get("workspace_name")
            or workspace_id
        )

        destination_status = (
            row.get("status")
            or "?"
        )

        admin_state = (
            row.get("admin_state")
            or "active"
        )

        lines.extend([
            (
                f"#{destination_id} | "
                f"{platform} | "
                f"{external_id}"
            ),
            (
                "Workspace: "
                f"{workspace_name} "
                f"({workspace_id})"
            ),
            (
                "Destination: "
                f"{destination_status}"
            ),
            (
                "Admin: "
                f"{admin_state}"
            ),
            "",
        ])

    if len(rows) > 25:
        lines.append(
            f"… و {len(rows) - 25} مقصد دیگر"
        )

    lines.extend([
        "",
        "کنترل مقصد:",
        "/adminpause ID [reason]",
        "/adminresume ID [reason]",
        "/adminblock ID [reason]",
        "/adminunblock ID [reason]",
    ])

    send_message(
        chat_id,
        "\n".join(lines),
    )

    return True


def _set_destination_state(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
    *,
    state: str,
    action: str,
    usage: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    destination_id, reason = (
        _parse_id_and_reason(args)
    )

    if destination_id is None:
        send_message(
            chat_id,
            f"❌ فرمت صحیح:\n{usage}",
        )
        return True

    database = _database()

    destination = _find_destination(
        database,
        destination_id,
    )

    if not destination:
        send_message(
            chat_id,
            "❌ مقصدی با این شناسه پیدا نشد.",
        )
        return True

    platform = _platform(origin)

    changed = (
        database
        .upsert_admin_destination_control(
            destination_id,
            state,
            reason=(
                reason
                or action
            ),
            changed_by_platform=platform,
            changed_by_external_user_id=(
                chat_id
            ),
        )
    )

    if not changed:
        send_message(
            chat_id,
            "❌ تغییر وضعیت مدیریتی مقصد ثبت نشد.",
        )
        return True

    database.record_admin_audit_log(
        action,
        platform,
        actor_external_user_id=chat_id,
        target_type="destination",
        target_id=destination_id,
        details={
            "admin_state": state,
            "reason": (
                reason
                or action
            ),
            "platform": (
                destination.get(
                    "platform"
                )
            ),
            "external_id": (
                destination.get(
                    "external_id"
                )
            ),
            "workspace_id": (
                destination.get(
                    "workspace_id"
                )
            ),
        },
    )

    state_text = {
        "active": "🟢 فعال",
        "paused": "⏸ متوقف موقت",
        "blocked": "⛔ بلاک",
    }.get(
        state,
        state,
    )

    send_message(
        chat_id,
        (
            f"✅ وضعیت مقصد #{destination_id} "
            "تغییر کرد.\n"
            f"وضعیت: {state_text}"
        ),
    )

    return True


def handle_admin_pause(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    return _set_destination_state(
        args,
        chat_id,
        send_message,
        origin,
        state="paused",
        action="pause_destination",
        usage=(
            "/adminpause "
            "DESTINATION_ID [reason]"
        ),
    )


def handle_admin_resume(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    return _set_destination_state(
        args,
        chat_id,
        send_message,
        origin,
        state="active",
        action="resume_destination",
        usage=(
            "/adminresume "
            "DESTINATION_ID [reason]"
        ),
    )


def handle_admin_block(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    return _set_destination_state(
        args,
        chat_id,
        send_message,
        origin,
        state="blocked",
        action="block_destination",
        usage=(
            "/adminblock "
            "DESTINATION_ID [reason]"
        ),
    )


def handle_admin_unblock(
    args: str,
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    return _set_destination_state(
        args,
        chat_id,
        send_message,
        origin,
        state="active",
        action="unblock_destination",
        usage=(
            "/adminunblock "
            "DESTINATION_ID [reason]"
        ),
    )


def handle_admin_audit(
    chat_id: int,
    send_message: SendMessage,
    origin: str,
) -> bool:
    if not _require_admin(
        chat_id,
        send_message,
        origin,
    ):
        return True

    database = _database()

    rows = (
        database
        .list_admin_audit_log(
            limit=20
        )
        or []
    )

    if not rows:
        send_message(
            chat_id,
            "📜 هنوز رویداد مدیریتی ثبت نشده است.",
        )
        return True

    lines = [
        "📜 آخرین فعالیت‌های مدیریتی",
        "",
    ]

    for row in rows:
        actor = (
            f"{row.get('actor_platform')} "
            f"{row.get('actor_external_user_id') or ''}"
        ).rstrip()

        target = (
            f"{row.get('target_type')} "
            f"{row.get('target_id') or ''}"
        ).rstrip()

        lines.extend([
            (
                f"#{row.get('id')} | "
                f"{row.get('action')}"
            ),
            f"Actor: {actor}",
            f"Target: {target}",
            (
                "Time: "
                f"{row.get('created_at') or '?'}"
            ),
            "",
        ])

    send_message(
        chat_id,
        "\n".join(lines),
    )

    return True
