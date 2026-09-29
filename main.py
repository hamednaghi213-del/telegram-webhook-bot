import os
import time
import logging
import threading
import requests

from flask import (
    Flask,
    request,
    jsonify
)

from logging.handlers import (
    RotatingFileHandler
)

from core.webhook_handler import (
    initialize as init_webhook,
    handle_webhook
)

from core.cleaner import (
    initialize as init_cleaner
)

from core.formatter import (
    initialize as init_formatter
)

from core.media_handler import (
    initialize as init_media_handler
)

from core.command_handler import (
    initialize as init_commands
)

from core.deep_reply_handler import (
    initialize as init_deep_reply
)

from core.database import (
    init_db
)

from core.smart_summarizer import (
    summarize_text_safely
)

from core.ai_summarizer_provider import (
    summarize_with_gemini
)
from core.release_readiness import parse_bool


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

if not TOKEN:

    raise ValueError(
        "❌ توکن در متغیر محیطی "
        "TELEGRAM_BOT_TOKEN تنظیم نشده."
    )


SECRET_TOKEN = os.getenv(
    "TELEGRAM_SECRET_TOKEN"
)

if not SECRET_TOKEN:
    raise ValueError(
        "❌ متغیر محیطی TELEGRAM_SECRET_TOKEN تنظیم نشده است."
    )


GEMINI_TEST_SECRET = os.getenv(
    "GEMINI_TEST_SECRET",
    ""
)


API = (
    f"https://api.telegram.org/"
    f"bot{TOKEN}"
)


CHANNEL_ID = os.getenv(
    "TELEGRAM_CHANNEL_ID",
    "@Donya24News"
)


HASHTAG = os.getenv(
    "CHANNEL_HASHTAG",
    "#دنیا_۲۴_نیوز"
)


CHANNEL_TAG = os.getenv(
    "CHANNEL_TAG",
    "@Donya24News"
)

ENABLE_SELF_PING = parse_bool(
    os.getenv("ENABLE_SELF_PING", "false")
)

APPLICATION_READY = False


# =========================================================
# LOGGING
# =========================================================

def setup_logging():

    logger = logging.getLogger()

    logger.setLevel(
        logging.INFO
    )

    # جلوگیری از اضافه شدن چند Handler
    if logger.handlers:

        return logger

    console_handler = (
        logging.StreamHandler()
    )

    console_handler.setLevel(
        logging.INFO
    )

    console_format = (
        logging.Formatter(
            "%(asctime)s - "
            "%(levelname)s - "
            "%(message)s"
        )
    )

    console_handler.setFormatter(
        console_format
    )

    logger.addHandler(
        console_handler
    )

    # -----------------------------------------
    # File Log
    # -----------------------------------------

    try:

        file_handler = (
            RotatingFileHandler(
                "bot.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8"
            )
        )

        file_handler.setLevel(
            logging.INFO
        )

        file_handler.setFormatter(
            console_format
        )

        logger.addHandler(
            file_handler
        )

    except Exception as e:

        print(
            f"⚠️ فعال‌سازی فایل لاگ "
            f"ناموفق بود: {e}"
        )

    return logger


logger = setup_logging()


# =========================================================
# INITIALIZE ALL MODULES
# =========================================================

def initialize_modules():

    global APPLICATION_READY

    logger.info(
        "🚀 شروع مقداردهی اولیه ماژول‌ها..."
    )

    # -----------------------------------------
    # Database
    # -----------------------------------------

    init_db()

    logger.info(
        "✅ Database initialized"
    )

    # -----------------------------------------
    # Persistence Recovery (B5-B8)
    #
    # Restore unfinished in-memory-backed state
    # (media groups, editorial pending reviews)
    # from Supabase after restart/deploy.
    # Each hook is flag-gated and no-ops when
    # its persistence flag is disabled.
    # -----------------------------------------

    try:

        from core.media_handler import (
            rehydrate_media_groups
        )

        restored_groups = (
            rehydrate_media_groups()
        )

        logger.info(
            "♻️ Media groups rehydrated | "
            f"count={restored_groups}"
        )

    except Exception as e:

        logger.exception(
            f"❌ Media group rehydration failed | {e}"
        )

    try:

        from core.editorial_pending import (
            rehydrate_editorial_reviews
        )

        restored_reviews = (
            rehydrate_editorial_reviews()
        )

        logger.info(
            "♻️ Editorial reviews rehydrated | "
            f"count={restored_reviews}"
        )

    except Exception as e:

        logger.exception(
            f"❌ Editorial review rehydration failed | {e}"
        )

    # -----------------------------------------
    # Cleaner
    # -----------------------------------------

    init_cleaner(
        CHANNEL_TAG,
        HASHTAG
    )

    logger.info(
        "✅ Cleaner initialized"
    )

    # -----------------------------------------
    # Formatter
    # -----------------------------------------

    init_formatter(
        CHANNEL_TAG,
        HASHTAG
    )

    logger.info(
        "✅ Formatter initialized"
    )

    # -----------------------------------------
    # Media Handler
    # -----------------------------------------

    init_media_handler(
        API,
        CHANNEL_ID
    )

    logger.info(
        "✅ Media Handler initialized"
    )

    # -----------------------------------------
    # Command Handler
    # -----------------------------------------

    init_commands(
        API
    )

    logger.info(
        "✅ Command Handler initialized"
    )

    # -----------------------------------------
    # Deep Reply Handler
    # -----------------------------------------

    init_deep_reply(
        API,
        CHANNEL_ID
    )

    logger.info(
        "✅ Deep Reply Handler initialized"
    )

    # -----------------------------------------
    # Webhook Handler
    # -----------------------------------------

    init_webhook(
        API,
        CHANNEL_ID,
        SECRET_TOKEN
    )

    logger.info(
        "✅ Webhook Handler initialized"
    )

    # -----------------------------------------
    # Bale Adapter (Bale Full Bot Parity)
    # -----------------------------------------

    from core.bale_adapter import initialize as init_bale_adapter

    init_bale_adapter(
        os.getenv("BALE_WEBHOOK_SECRET_TOKEN", "").strip()
    )

    logger.info(
        "✅ Bale Adapter initialized"
    )

    logger.info(
        "🎯 تمام ماژول‌ها با موفقیت "
        "مقداردهی شدند."
    )

    APPLICATION_READY = True


# =========================================================
# SELF PING
# =========================================================

def self_ping():

    url = os.getenv(
        "SELF_PING_URL",
        "https://telegram-webhook-bot-onyd.onrender.com/"
    )

    interval = int(
        os.getenv(
            "SELF_PING_INTERVAL",
            "420"
        )
    )

    logger.info(
        f"🔄 Self-ping فعال شد | "
        f"interval={interval}s"
    )

    while True:

        try:

            response = requests.get(
                url,
                timeout=15
            )

            logger.info(
                f"🔄 Self-ping | "
                f"status={response.status_code}"
            )

        except Exception as e:

            logger.error(
                f"❌ Self-ping خطا: {e}"
            )

        time.sleep(
            interval
        )


# =========================================================
# START SELF PING
# =========================================================

def start_self_ping():

    thread = threading.Thread(
        target=self_ping,
        name="SelfPingThread",
        daemon=True
    )

    thread.start()

    return thread


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def health_check():

    return (
        "🤖 ربات خبری هوشمند - "
        "نسخه نهایی"
    )


@app.route("/healthz", methods=["GET"])
def liveness_check():
    return jsonify({"ok": True, "status": "alive"}), 200


@app.route("/readyz", methods=["GET"])
def readiness_check():
    status_code = 200 if APPLICATION_READY else 503
    return jsonify({
        "ok": APPLICATION_READY,
        "status": "ready" if APPLICATION_READY else "starting",
    }), status_code


# =========================================================
# GEMINI LIVE TEST
# =========================================================

@app.route(
    "/test-gemini",
    methods=["GET"]
)
def test_gemini():

    # -----------------------------------------
    # Security
    # -----------------------------------------

    configured_secret = (
        GEMINI_TEST_SECRET
        or ""
    )

    supplied_secret = (
        request.args.get(
            "secret",
            ""
        )
        or ""
    )

    if not configured_secret:

        logger.error(
            "❌ GEMINI_TEST_SECRET "
            "is not configured"
        )

        return jsonify({
            "ok": False,
            "error": (
                "GEMINI_TEST_SECRET "
                "is not configured"
            )
        }), 503

    if supplied_secret != configured_secret:

        logger.warning(
            "⚠️ Unauthorized Gemini "
            "test request"
        )

        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 403

    # -----------------------------------------
    # Test Text
    # -----------------------------------------

    original_text = (
        "وزیر خارجه اعلام کرد احتمال دارد "
        "مذاکرات در هفته آینده آغاز شود. "
        "او گفت رایزنی‌های دیپلماتیک در "
        "روزهای اخیر ادامه داشته و طرف‌ها "
        "در حال بررسی پیشنهادهای مطرح شده "
        "هستند. مقام‌های مسئول هنوز زمان "
        "قطعی آغاز مذاکرات را اعلام نکرده‌اند. "
        "بر اساس این گزارش، رایزنی‌ها برای "
        "رسیدن به چارچوب اولیه همچنان "
        "ادامه دارد."
    )

    target_length = 220

    logger.info(
        "🧠 Gemini live test started | "
        f"original_length={len(original_text)} | "
        f"target_length={target_length}"
    )

    # -----------------------------------------
    # Smart Summarizer
    # -----------------------------------------

    try:

        result = summarize_text_safely(
            original_text=original_text,
            target_length=target_length,
            summarizer=summarize_with_gemini
        )

    except Exception as e:

        logger.exception(
            f"❌ Gemini live test crashed | "
            f"{e}"
        )

        return jsonify({
            "ok": False,
            "error": "test_execution_failed",
            "detail": str(e)
        }), 500

    # -----------------------------------------
    # Result
    # -----------------------------------------

    logger.info(
        "🧠 Gemini live test completed | "
        f"success={result.success} | "
        f"reason={result.reason} | "
        f"validation="
        f"{result.validation_passed} | "
        f"original_length="
        f"{result.original_length} | "
        f"summary_length="
        f"{result.summary_length}"
    )

    return jsonify({

        "ok": True,

        "summary_success":
            result.success,

        "reason":
            result.reason,

        "validation_passed":
            result.validation_passed,

        "original_length":
            result.original_length,

        "summary_length":
            result.summary_length,

        "reduction_ratio":
            result.reduction_ratio,

        "original_text":
            result.original_text,

        "summary_text":
            result.summary_text,

        "metadata":
            result.metadata
    })


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route(
    "/",
    methods=["POST"]
)
def webhook():

    return handle_webhook()


# =========================================================
# BALE WEBHOOK (Bale Full Bot Parity)
# =========================================================

@app.route(
    "/bale/webhook",
    methods=["POST"]
)
def bale_webhook():
    """Inbound Bale bot updates, routed into the shared application core."""
    from core.bale_adapter import (
        handle_bale_update,
        validate_bale_webhook_token,
    )

    if not validate_bale_webhook_token(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    data = request.get_json(silent=True) or {}

    response, status_code = handle_bale_update(data)

    return jsonify(response), status_code


# =========================================================
# X OAUTH CALLBACK
# =========================================================

@app.route(
    "/oauth/x/callback",
    methods=["GET"]
)
def x_oauth_callback():
    """Complete X OAuth and bind the authenticated account to its Workspace."""

    error = str(
        request.args.get("error")
        or ""
    ).strip()

    if error:
        logger.warning(
            "X OAuth denied or failed | error=%s",
            error,
        )
        return (
            "❌ اتصال حساب X انجام نشد. "
            "می‌توانید این صفحه را ببندید و دوباره از ربات تلاش کنید.",
            400,
        )

    state = str(
        request.args.get("state")
        or ""
    ).strip()

    code = str(
        request.args.get("code")
        or ""
    ).strip()

    if not state or not code:
        return (
            "❌ اطلاعات callback حساب X ناقص است.",
            400,
        )

    try:
        from core.x_oauth import (
            complete_x_oauth_callback,
        )
        from core.database import (
            get_workspace_member,
            register_setup_destination_canonical,
            update_publication_destination_status,
            upsert_x_oauth_connection,
        )
        from core.workspace_destinations import (
            can_manage_destinations,
        )

        result = complete_x_oauth_callback(
            state=state,
            code=code,
        )

        if result.requested_by_user_id is None:
            raise PermissionError(
                "X OAuth session has no requesting user"
            )

        member = get_workspace_member(
            result.workspace_id,
            result.requested_by_user_id,
        )

        allowed, _reason = can_manage_destinations(
            (member or {}).get("role")
        )

        if (
            not member
            or member.get("status") != "active"
            or not allowed
        ):
            raise PermissionError(
                "User can no longer manage Workspace destinations"
            )

        display_name = (
            result.x_display_name
            or (
                f"@{result.x_username}"
                if result.x_username
                else f"X {result.x_user_id}"
            )
        )

        # Use the immutable X user ID as the physical destination identity.
        external_id = f"x:{result.x_user_id}"

        destination, association_status = (
            register_setup_destination_canonical(
                workspace_id=result.workspace_id,
                platform="x",
                external_id=external_id,
                name=display_name,
            )
        )

        if not destination:
            raise RuntimeError(
                "X destination could not be created"
            )

        if association_status == "owned_elsewhere":
            raise PermissionError(
                "This X account is already connected to another Workspace"
            )

        destination_id = int(
            destination["id"]
        )

        connection = upsert_x_oauth_connection(
            destination_id=destination_id,
            workspace_id=result.workspace_id,
            connected_by_user_id=(
                result.requested_by_user_id
            ),
            x_user_id=result.x_user_id,
            x_username=result.x_username,
            x_display_name=result.x_display_name,
            access_token_ciphertext=(
                result.access_token_ciphertext
            ),
            refresh_token_ciphertext=(
                result.refresh_token_ciphertext
            ),
            token_expires_at=(
                result.token_expires_at
            ),
            granted_scopes=(
                result.granted_scopes
            ),
            connection_status="connected",
            last_error=None,
        )

        if not connection:
            raise RuntimeError(
                "X OAuth connection could not be persisted"
            )

        activated = (
            update_publication_destination_status(
                destination_id,
                "active",
            )
        )

        if not activated:
            raise RuntimeError(
                "X destination could not be activated"
            )

        logger.info(
            "X OAuth connected | "
            "workspace=%s | destination=%s | x_user=%s",
            result.workspace_id,
            destination_id,
            result.x_user_id,
        )

        return (
            "✅ حساب X با موفقیت به رسانه متصل شد. "
            "می‌توانید این صفحه را ببندید و به ربات برگردید.",
            200,
        )

    except PermissionError as exc:
        logger.warning(
            "X OAuth callback permission rejected | %s",
            exc,
        )
        return (
            "❌ اجازه اتصال این حساب X به رسانه وجود ندارد.",
            403,
        )

    except Exception as exc:
        logger.exception(
            "X OAuth callback failed | %s",
            exc,
        )
        return (
            "❌ اتصال حساب X کامل نشد. "
            "لطفاً از داخل ربات دوباره تلاش کنید.",
            500,
        )


# =========================================================
# STARTUP
# =========================================================

initialize_modules()

if ENABLE_SELF_PING:
    start_self_ping()
else:
    logger.info("ℹ️ Self-ping disabled")


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            10000
        )
    )

    logger.info(
        f"🚀 ربات روی پورت "
        f"{port} در حال اجراست..."
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
