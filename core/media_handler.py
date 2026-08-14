import time
import threading
import logging
import requests
import json

from typing import (
    Dict,
    Tuple,
    List,
    Optional,
    Any
)

from collections import defaultdict

from core.formatter import (
    format_news
)

from core.content_entities import (
    parse_telegram_entities
)

from core.caption_manager import (
    analyze_content,
    PublicationPlan
)


logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL: Optional[str] = None
CHANNEL_ID: Optional[str] = None


# =========================================================
# MEDIA GROUP STORAGE
# =========================================================

pending_groups: Dict[
    Tuple[int, str],
    Dict[str, Any]
] = defaultdict(dict)


group_timers: Dict[
    Tuple[int, str],
    threading.Timer
] = {}


group_lock = threading.RLock()


# =========================================================
# RESOURCE LIMITS
# =========================================================

MAX_PENDING_GROUPS = 1000

MAX_GROUP_AGE_SECONDS = 900
# 15 minutes

CLEANUP_INTERVAL_SECONDS = 300
# 5 minutes


cleanup_thread: Optional[
    threading.Thread
] = None

cleanup_running = False


# =========================================================
# TELEGRAM LIMITS
# =========================================================

TELEGRAM_MEDIA_GROUP_MIN_ITEMS = 2
TELEGRAM_MEDIA_GROUP_MAX_ITEMS = 10


# =========================================================
# TIMEOUT CONFIG
# =========================================================

TELEGRAM_CONNECT_TIMEOUT = 10
TELEGRAM_READ_TIMEOUT = 60

MEDIA_GROUP_DELAY = 2.5
MEDIA_GROUP_MIN_WAIT = 1.5


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    api_url: str,
    channel_id: str
) -> None:
    """
    مقداردهی Media Handler.
    """

    global API_URL
    global CHANNEL_ID
    global cleanup_thread

    if not api_url:

        raise ValueError(
            "api_url cannot be empty"
        )

    if not channel_id:

        raise ValueError(
            "channel_id cannot be empty"
        )

    API_URL = api_url.rstrip("/")

    CHANNEL_ID = channel_id

    logger.info(
        f"✅ Media Handler initialized | "
        f"channel={CHANNEL_ID}"
    )

    # =====================================================
    # START CLEANUP SCHEDULER
    # =====================================================

    if (
        cleanup_thread is None
        or not cleanup_thread.is_alive()
    ):

        cleanup_thread = threading.Thread(
            target=_cleanup_scheduler,
            daemon=True,
            name="MediaHandlerCleanup"
        )

        cleanup_thread.start()

        logger.info(
            "🧹 Media Handler cleanup scheduler started"
        )


# =========================================================
# CLEANUP SCHEDULER
# =========================================================

def _cleanup_scheduler() -> None:
    """
    پاکسازی دوره‌ای Media Groupهای قدیمی.
    """

    global cleanup_running

    cleanup_running = True

    logger.info(
        f"🧹 Cleanup scheduler running | "
        f"interval={CLEANUP_INTERVAL_SECONDS}s"
    )

    while cleanup_running:

        try:

            time.sleep(
                CLEANUP_INTERVAL_SECONDS
            )

            cleanup_old_groups()

        except Exception as e:

            logger.exception(
                f"❌ Cleanup scheduler error: {e}"
            )


# =========================================================
# CLEANUP OLD GROUPS
# =========================================================

def cleanup_old_groups() -> None:
    """
    حذف Media Groupهای قدیمی یا stuck.
    """

    current_time = time.time()

    groups_to_remove = []

    with group_lock:

        # =================================================
        # OLD GROUPS
        # =================================================

        for group_key, group in list(
            pending_groups.items()
        ):

            last_update = group.get(
                "last_update",
                current_time
            )

            age_seconds = (
                current_time
                - last_update
            )

            if (
                age_seconds
                > MAX_GROUP_AGE_SECONDS
            ):

                groups_to_remove.append(
                    group_key
                )

                logger.warning(
                    f"⚠️ Old Media Group | "
                    f"group={group_key[1]} | "
                    f"age={age_seconds:.1f}s"
                )

        # =================================================
        # TOTAL GROUP LIMIT
        # =================================================

        if (
            len(pending_groups)
            > MAX_PENDING_GROUPS
        ):

            sorted_groups = sorted(
                pending_groups.items(),
                key=lambda item: (
                    item[1].get(
                        "last_update",
                        0
                    )
                )
            )

            excess = (
                len(sorted_groups)
                - MAX_PENDING_GROUPS
            )

            for (
                group_key,
                _
            ) in sorted_groups[:excess]:

                if (
                    group_key
                    not in groups_to_remove
                ):

                    groups_to_remove.append(
                        group_key
                    )

        # =================================================
        # REMOVE GROUPS
        # =================================================

        for group_key in groups_to_remove:

            pending_groups.pop(
                group_key,
                None
            )

            timer = group_timers.pop(
                group_key,
                None
            )

            if timer:

                try:

                    timer.cancel()

                except Exception:

                    pass

    if groups_to_remove:

        logger.info(
            f"🧹 Media Group cleanup | "
            f"removed={len(groups_to_remove)} | "
            f"remaining={len(pending_groups)}"
        )


# =========================================================
# MEDIA GROUP DETECTION
# =========================================================

def is_media_group(
    message: Dict[str, Any]
) -> bool:
    """
    آیا Message بخشی از Media Group است؟
    """

    return bool(
        message.get(
            "media_group_id"
        )
    )


# =========================================================
# ADD MEDIA TO PENDING GROUP
# =========================================================

def add_to_pending_group(
    media_group_id: str,
    chat_id: int,
    file_id: str,
    media_type: str,
    caption: str = "",
    caption_entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> None:
    """
    اضافه کردن Media به Pending Group.

    معماری:

    Telegram raw caption
            +
    caption_entities
            ↓
    parse_telegram_entities()
            ↓
    Content Structure

    Formatter و Caption Manager
    در مرحله process_media_group اجرا می‌شوند.

    فقط اولین Media دارای Caption
    اطلاعات Caption را ثبت می‌کند.
    """

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        # =================================================
        # CREATE GROUP
        # =================================================

        if group_key not in pending_groups:

            pending_groups[
                group_key
            ] = {
                "chat_id": chat_id,

                "media_group_id": (
                    media_group_id
                ),

                "files": [],

                "raw_caption": "",

                "caption_entities": [],

                "main_text": "",

                "expandable_blocks": [],

                "blockquote_blocks": [],

                "other_entities": [],

                "caption_received": False,

                "last_update": (
                    time.time()
                ),

                "is_processing": False
            }

            logger.info(
                f"🆕 New Media Group | "
                f"group={media_group_id}"
            )

        group = pending_groups[
            group_key
        ]

        # =================================================
        # DUPLICATE MEDIA CHECK
        # =================================================

        already_exists = any(
            item.get(
                "file_id"
            ) == file_id

            for item
            in group["files"]
        )

        if not already_exists:

            group["files"].append({
                "type": media_type,
                "file_id": file_id
            })

            logger.info(
                f"📸 Media added | "
                f"group={media_group_id} | "
                f"type={media_type} | "
                f"count={len(group['files'])}"
            )

        else:

            logger.debug(
                f"ℹ️ Duplicate media ignored | "
                f"group={media_group_id}"
            )

        group[
            "last_update"
        ] = time.time()

        # =================================================
        # CAPTION
        # =================================================
        #
        # فقط اولین Caption ثبت می‌شود.
        #
        # caption_received جداگانه داریم چون ممکن است
        # main_text بعد از Entity Parsing خالی شود.
        # =================================================

        if (
            caption
            and not group[
                "caption_received"
            ]
        ):

            entities = list(
                caption_entities
                or []
            )

            group[
                "caption_received"
            ] = True

            group[
                "raw_caption"
            ] = caption

            group[
                "caption_entities"
            ] = entities

            try:

                parsed = (
                    parse_telegram_entities(
                        caption,
                        entities
                    )
                )

                group[
                    "main_text"
                ] = parsed.get(
                    "main_text",
                    ""
                )

                group[
                    "expandable_blocks"
                ] = list(
                    parsed.get(
                        "expandable_blocks",
                        []
                    )
                )

                group[
                    "blockquote_blocks"
                ] = list(
                    parsed.get(
                        "blockquote_blocks",
                        []
                    )
                )

                group[
                    "other_entities"
                ] = list(
                    parsed.get(
                        "other_entities",
                        []
                    )
                )

                logger.info(
                    f"🧩 Media Group entities parsed | "
                    f"group={media_group_id} | "
                    f"entities={len(entities)} | "
                    f"main={len(group['main_text'])} | "
                    f"expandable="
                    f"{len(group['expandable_blocks'])} | "
                    f"blockquote="
                    f"{len(group['blockquote_blocks'])} | "
                    f"other="
                    f"{len(group['other_entities'])}"
                )

            except Exception as e:

                # =========================================
                # BACKWARD SAFE FALLBACK
                # =========================================
                #
                # اگر Entity Parser شکست خورد،
                # متن اصلی از بین نمی‌رود.
                # =========================================

                logger.exception(
                    f"❌ Entity parsing failed | "
                    f"group={media_group_id} | "
                    f"{e}"
                )

                group[
                    "main_text"
                ] = caption

                group[
                    "expandable_blocks"
                ] = []

                group[
                    "blockquote_blocks"
                ] = []

                group[
                    "other_entities"
                ] = []


# =========================================================
# REMOVE GROUP
# =========================================================

def remove_pending_group(
    media_group_id: str,
    chat_id: Optional[int] = None
) -> None:
    """
    حذف Pending Group و Timer.
    """

    with group_lock:

        if chat_id is not None:

            group_key = (
                chat_id,
                media_group_id
            )

            pending_groups.pop(
                group_key,
                None
            )

            timer = group_timers.pop(
                group_key,
                None
            )

            if timer:

                try:

                    timer.cancel()

                except Exception:

                    pass

            return

        keys_to_remove = [
            key
            for key
            in list(
                pending_groups.keys()
            )
            if key[1]
            == media_group_id
        ]

        for key in keys_to_remove:

            pending_groups.pop(
                key,
                None
            )

            timer = group_timers.pop(
                key,
                None
            )

            if timer:

                try:

                    timer.cancel()

                except Exception:

                    pass


# =========================================================
# TELEGRAM POST
# =========================================================

def telegram_post(
    endpoint: str,
    payload: Dict[str, Any]
) -> Optional[requests.Response]:
    """
    ارسال HTTP Request به Telegram Bot API.
    """

    if not API_URL:

        logger.error(
            "❌ API_URL is not configured"
        )

        return None

    url = (
        f"{API_URL}/{endpoint}"
    )

    logger.info(
        f"🌐 Telegram API request | "
        f"endpoint={endpoint}"
    )

    # =====================================================
    # SAFE PAYLOAD LOGGING
    # =====================================================

    try:

        payload_preview = json.dumps(
            payload,
            ensure_ascii=False,
            default=str
        )

        logger.debug(
            f"📨 Telegram payload | "
            f"{payload_preview[:1500]}"
        )

    except Exception as e:

        logger.debug(
            f"Payload logging error: {e}"
        )

    # =====================================================
    # REQUEST
    # =====================================================

    try:

        start_time = time.time()

        response = requests.post(
            url,
            json=payload,
            timeout=(
                TELEGRAM_CONNECT_TIMEOUT,
                TELEGRAM_READ_TIMEOUT
            )
        )

        elapsed = (
            time.time()
            - start_time
        )

        logger.info(
            f"📡 Telegram response | "
            f"endpoint={endpoint} | "
            f"status={response.status_code} | "
            f"time={elapsed:.2f}s"
        )

        return response

    except requests.exceptions.ConnectTimeout as e:

        logger.error(
            f"⏰ Telegram ConnectTimeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.ReadTimeout as e:

        logger.error(
            f"⏰ Telegram ReadTimeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.Timeout as e:

        logger.error(
            f"⏰ Telegram Timeout | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.ConnectionError as e:

        logger.error(
            f"🔌 Telegram ConnectionError | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except requests.exceptions.RequestException as e:

        logger.error(
            f"❌ Telegram RequestException | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None

    except Exception as e:

        logger.exception(
            f"❌ Telegram API error | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return None


# =========================================================
# TELEGRAM RESPONSE CHECK
# =========================================================

def telegram_response_ok(
    response: Optional[
        requests.Response
    ],
    endpoint: str
) -> bool:
    """
    بررسی پاسخ Telegram API.
    """

    if response is None:

        logger.error(
            f"❌ No Telegram response | "
            f"endpoint={endpoint}"
        )

        return False

    if response.status_code != 200:

        logger.error(
            f"❌ Telegram HTTP error | "
            f"endpoint={endpoint} | "
            f"status={response.status_code} | "
            f"response={response.text[:2000]}"
        )

        return False

    try:

        data = response.json()

    except Exception as e:

        logger.error(
            f"❌ Invalid Telegram JSON | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

        return False

    if data.get(
        "ok"
    ) is True:

        return True

    logger.error(
        f"❌ Telegram API returned error | "
        f"endpoint={endpoint} | "
        f"error_code={data.get('error_code')} | "
        f"description={data.get('description')}"
    )

    return False


# =========================================================
# SEND TEXT TO TELEGRAM CHANNEL
# =========================================================

def send_text_to_channel(
    text: str,
    parse_mode: Optional[str] = None
) -> bool:
    """
    ارسال پیام متنی مستقل به Telegram.
    """

    if not text:

        return True

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID not configured"
        )

        return False

    payload: Dict[str, Any] = {
        "chat_id": CHANNEL_ID,
        "text": text
    }

    if parse_mode:

        payload[
            "parse_mode"
        ] = parse_mode

    response = telegram_post(
        "sendMessage",
        payload
    )

    success = telegram_response_ok(
        response,
        "sendMessage"
    )

    if success:

        logger.info(
            f"✅ Telegram text sent | "
            f"length={len(text)} | "
            f"parse_mode={parse_mode or 'NONE'}"
        )

    return success


# =========================================================
# SEND SINGLE MEDIA TO TELEGRAM
# =========================================================

def send_single_media_to_channel(
    file_id: str,
    media_type: str,
    caption: str = ""
) -> bool:
    """
    ارسال Photo یا Video تکی.
    """

    if not API_URL:

        logger.error(
            "❌ API_URL not configured"
        )

        return False

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID not configured"
        )

        return False

    if not file_id:

        logger.error(
            "❌ file_id is empty"
        )

        return False

    if media_type == "photo":

        endpoint = "sendPhoto"

        payload = {
            "chat_id": CHANNEL_ID,
            "photo": file_id
        }

    elif media_type == "video":

        endpoint = "sendVideo"

        payload = {
            "chat_id": CHANNEL_ID,
            "video": file_id
        }

    else:

        logger.error(
            f"❌ Unsupported media type | "
            f"type={media_type}"
        )

        return False

    if caption:

        payload[
            "caption"
        ] = caption

    response = telegram_post(
        endpoint,
        payload
    )

    if telegram_response_ok(
        response,
        endpoint
    ):

        logger.info(
            f"✅ Single Telegram media sent | "
            f"type={media_type}"
        )

        return True

    return False


# =========================================================
# SEND MEDIA GROUP TO TELEGRAM
# =========================================================

def send_media_group_to_channel(
    files: List[
        Dict[str, str]
    ],
    caption: str = ""
) -> bool:
    """
    ارسال Media Group واقعی Telegram.

    قانون قطعی:

    هیچ Fallback به ارسال تکی وجود ندارد.
    """

    file_count = (
        len(files)
        if files
        else 0
    )

    logger.info(
        f"📤 Sending Telegram Media Group | "
        f"count={file_count}"
    )

    if not files:

        logger.error(
            "❌ Media Group files empty"
        )

        return False

    if not API_URL:

        logger.error(
            "❌ API_URL not configured"
        )

        return False

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID not configured"
        )

        return False

    # =====================================================
    # ITEM COUNT VALIDATION
    # =====================================================

    if (
        file_count
        < TELEGRAM_MEDIA_GROUP_MIN_ITEMS
    ):

        logger.error(
            "❌ Media Group requires "
            "at least 2 items"
        )

        return False

    if (
        file_count
        > TELEGRAM_MEDIA_GROUP_MAX_ITEMS
    ):

        # مهم:
        # files[:10] استفاده نمی‌کنیم.
        # هیچ رسانه‌ای silently حذف نمی‌شود.

        logger.error(
            f"❌ Media Group exceeds Telegram limit | "
            f"count={file_count} | "
            f"max={TELEGRAM_MEDIA_GROUP_MAX_ITEMS}"
        )

        return False

    # =====================================================
    # BUILD MEDIA ARRAY
    # =====================================================

    media_group = []

    for index, file in enumerate(
        files
    ):

        media_type = file.get(
            "type"
        )

        file_id = file.get(
            "file_id"
        )

        if media_type not in (
            "photo",
            "video"
        ):

            logger.error(
                f"❌ Invalid Media Group type | "
                f"index={index} | "
                f"type={media_type}"
            )

            return False

        if not file_id:

            logger.error(
                f"❌ Empty file_id | "
                f"index={index}"
            )

            return False

        media_item = {
            "type": media_type,
            "media": file_id
        }

        # =================================================
        # CAPTION ONLY FIRST MEDIA
        # =================================================

        if (
            index == 0
            and caption
        ):

            media_item[
                "caption"
            ] = caption

        media_group.append(
            media_item
        )

    payload = {
        "chat_id": CHANNEL_ID,
        "media": media_group
    }

    response = telegram_post(
        "sendMediaGroup",
        payload
    )

    if telegram_response_ok(
        response,
        "sendMediaGroup"
    ):

        logger.info(
            f"🎯 Telegram Media Group sent | "
            f"count={len(media_group)}"
        )

        return True

    # =====================================================
    # ABSOLUTELY NO FALLBACK
    # =====================================================

    logger.error(
        "❌ Telegram Media Group failed"
    )

    logger.error(
        "🚫 Single-media fallback is disabled"
    )

    return False


# =========================================================
# BUILD BRANDING
# =========================================================

def build_branding_for_user(
    user_id: int
) -> str:
    """
    Branding مخصوص Tenant را می‌سازد.

    اولویت:
    branding_manager

    Fallback:
    Formatter globals
    """

    try:

        from core.branding_manager import (
            get_branding
        )

        branding = get_branding(
            user_id
        )

        parts = []

        hashtag = (
            branding.get(
                "hashtag",
                ""
            )
            or ""
        )

        channel_tag = (
            branding.get(
                "channel_tag",
                ""
            )
            or ""
        )

        if hashtag:

            parts.append(
                hashtag
            )

        if channel_tag:

            parts.append(
                channel_tag
            )

        if parts:

            return "\n".join(
                parts
            )

    except Exception as e:

        logger.warning(
            f"⚠️ Per-user branding unavailable | "
            f"user={user_id} | "
            f"{e}"
        )

    # =====================================================
    # FALLBACK TO FORMATTER GLOBALS
    # =====================================================

    try:

        from core.formatter import (
            HASHTAG,
            CHANNEL_TAG
        )

        parts = []

        if HASHTAG:

            parts.append(
                HASHTAG
            )

        if CHANNEL_TAG:

            parts.append(
                CHANNEL_TAG
            )

        return "\n".join(
            parts
        )

    except Exception as e:

        logger.warning(
            f"⚠️ Formatter branding unavailable | "
            f"{e}"
        )

        return ""


# =========================================================
# SEND ALBUM TO BALE
# =========================================================

def send_album_to_bale(
    user_id: int,
    files: List[
        Dict[str, str]
    ],
    caption: str = ""
) -> bool:
    """
    ارسال Album به Bale.
    """

    if not files:

        logger.error(
            "❌ Bale album files empty"
        )

        return False

    try:

        from core.bale_forwarder import (
            send_media_group_to_bale
        )

        success = (
            send_media_group_to_bale(
                user_id,
                files,
                caption
            )
        )

        if success:

            logger.info(
                f"✅ Bale album sent | "
                f"user={user_id}"
            )

        else:

            logger.warning(
                f"⚠️ Bale album failed | "
                f"user={user_id}"
            )

        return success

    except Exception as e:

        logger.exception(
            f"❌ Bale album exception | "
            f"user={user_id} | "
            f"{e}"
        )

        return False


# =========================================================
# SEND TEXT TO BALE
# =========================================================

def send_text_to_bale(
    user_id: int,
    text: str
) -> bool:
    """
    ارسال پیام متنی مستقل به Bale.
    """

    if not text:

        return True

    try:

        from core.bale_forwarder import (
            send_to_bale_for_user
        )

        success = (
            send_to_bale_for_user(
                user_id,
                text
            )
        )

        if success:

            logger.info(
                f"✅ Bale text sent | "
                f"user={user_id} | "
                f"length={len(text)}"
            )

        else:

            logger.warning(
                f"⚠️ Bale text failed | "
                f"user={user_id}"
            )

        return success

    except Exception as e:

        logger.exception(
            f"❌ Bale text exception | "
            f"user={user_id} | "
            f"{e}"
        )

        return False


# =========================================================
# EXECUTE TELEGRAM PLAN
# =========================================================

def execute_telegram_plan(
    files: List[
        Dict[str, str]
    ],
    plan: Dict[str, Any]
) -> bool:
    """
    اجرای Telegram Publication Plan.

    Caption Manager تصمیم می‌گیرد.
    Media Handler فقط اجرا می‌کند.
    """

    media_caption = (
        plan.get(
            "media_caption",
            ""
        )
        or ""
    )

    followup_messages = list(
        plan.get(
            "followup_messages",
            []
        )
        or []
    )

    blockquote_messages = list(
        plan.get(
            "blockquote_messages",
            []
        )
        or []
    )

    document_fallback = bool(
        plan.get(
            "document_fallback",
            False
        )
    )

    # =====================================================
    # SAFETY FLAG
    # =====================================================
    #
    # طبق تست‌های Caption Manager در شرایط عادی
    # این Flag نباید True شود.
    #
    # اگر True شد، Caption نامعتبر را ارسال نمی‌کنیم.
    # =====================================================

    if document_fallback:

        logger.error(
            "❌ Telegram Publication Plan requested "
            "document fallback"
        )

        logger.error(
            "🚫 Unsafe Telegram media send aborted"
        )

        return False

    # =====================================================
    # STEP 1
    # MEDIA
    # =====================================================

    if len(files) == 1:

        file = files[0]

        media_success = (
            send_single_media_to_channel(
                file.get(
                    "file_id"
                ),
                file.get(
                    "type"
                ),
                media_caption
            )
        )

    else:

        media_success = (
            send_media_group_to_channel(
                files,
                media_caption
            )
        )

    if not media_success:

        logger.error(
            "❌ Telegram media execution failed"
        )

        return False

    # =====================================================
    # STEP 2
    # FOLLOW-UP MESSAGES
    # =====================================================

    for index, message in enumerate(
        followup_messages
    ):

        success = send_text_to_channel(
            message
        )

        if not success:

            logger.error(
                f"❌ Telegram follow-up failed | "
                f"index={index + 1}"
            )

    # =====================================================
    # STEP 3
    # BLOCKQUOTES
    # =====================================================

    for index, html_message in enumerate(
        blockquote_messages
    ):

        success = send_text_to_channel(
            html_message,
            parse_mode="HTML"
        )

        if not success:

            logger.error(
                f"❌ Telegram blockquote failed | "
                f"index={index + 1}"
            )

    # اصل موفقیت:
    # Media اصلی با موفقیت ارسال شده است.

    return True


# =========================================================
# EXECUTE BALE PLAN
# =========================================================

def execute_bale_plan(
    user_id: int,
    files: List[
        Dict[str, str]
    ],
    plan: Dict[str, Any]
) -> bool:
    """
    اجرای Bale Publication Plan.
    """

    media_caption = (
        plan.get(
            "media_caption",
            ""
        )
        or ""
    )

    followup_messages = list(
        plan.get(
            "followup_messages",
            []
        )
        or []
    )

    blockquote_messages = list(
        plan.get(
            "blockquote_messages",
            []
        )
        or []
    )

    document_fallback = bool(
        plan.get(
            "document_fallback",
            False
        )
    )

    if document_fallback:

        logger.error(
            "❌ Bale Publication Plan requested "
            "document fallback"
        )

        return False

    # =====================================================
    # STEP 1
    # MEDIA
    # =====================================================

    media_success = (
        send_album_to_bale(
            user_id,
            files,
            media_caption
        )
    )

    if not media_success:

        logger.warning(
            "⚠️ Bale media execution failed"
        )

        return False

    # =====================================================
    # STEP 2
    # FOLLOW-UP
    # =====================================================

    for index, message in enumerate(
        followup_messages
    ):

        success = send_text_to_bale(
            user_id,
            message
        )

        if not success:

            logger.warning(
                f"⚠️ Bale follow-up failed | "
                f"index={index + 1}"
            )

    # =====================================================
    # STEP 3
    # BLOCKQUOTES
    # =====================================================

    for index, message in enumerate(
        blockquote_messages
    ):

        success = send_text_to_bale(
            user_id,
            message
        )

        if not success:

            logger.warning(
                f"⚠️ Bale blockquote failed | "
                f"index={index + 1}"
            )

    return True


# =========================================================
# PROCESS MEDIA GROUP
# =========================================================

def process_media_group(
    media_group_id: str,
    chat_id: int
) -> bool:
    """
    پردازش نهایی Media Group.

    معماری:

    Parsed Content
        ↓
    Formatter
        ↓
    Branding
        ↓
    Caption Manager
        ↓
    Publication Plan
        ↓
    Telegram
        ↓
    Bale
    """

    group_key = (
        chat_id,
        media_group_id
    )

    logger.info(
        f"🚀 Processing Media Group | "
        f"group={media_group_id} | "
        f"chat={chat_id}"
    )

    # =====================================================
    # SNAPSHOT
    # =====================================================

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.error(
                f"❌ Media Group not found | "
                f"group={media_group_id}"
            )

            return False

        if group.get(
            "is_processing",
            False
        ):

            logger.warning(
                f"⚠️ Media Group already processing | "
                f"group={media_group_id}"
            )

            return False

        group[
            "is_processing"
        ] = True

        files = list(
            group.get(
                "files",
                []
            )
        )

        raw_main_text = (
            group.get(
                "main_text",
                ""
            )
            or ""
        )

        blockquote_blocks = list(
            group.get(
                "blockquote_blocks",
                []
            )
        )

        expandable_blocks = list(
            group.get(
                "expandable_blocks",
                []
            )
        )

        other_entities = list(
            group.get(
                "other_entities",
                []
            )
        )

    logger.info(
        f"📦 Media Group snapshot | "
        f"files={len(files)} | "
        f"main={len(raw_main_text)} | "
        f"blockquote={len(blockquote_blocks)} | "
        f"expandable={len(expandable_blocks)} | "
        f"other={len(other_entities)}"
    )

    if not files:

        logger.error(
            "❌ Media Group contains no files"
        )

        remove_pending_group(
            media_group_id,
            chat_id
        )

        return False

    try:

        # =================================================
        # FORMAT MAIN TEXT
        # =================================================

        formatted_main_text = ""

        if raw_main_text:

            try:

                formatted_main_text = (
                    format_news(
                        raw_main_text
                    )
                )

            except Exception as e:

                logger.exception(
                    f"❌ Formatter failed | "
                    f"group={media_group_id} | "
                    f"{e}"
                )

                # Backward safe fallback
                formatted_main_text = (
                    raw_main_text
                )

        # =================================================
        # BRANDING
        # =================================================

        branding = (
            build_branding_for_user(
                chat_id
            )
        )

        logger.info(
            f"🏷️ Branding prepared | "
            f"length={len(branding)}"
        )

        # =================================================
        # CAPTION MANAGER
        # =================================================

        publication_plan: PublicationPlan = (
            analyze_content(
                main_text=formatted_main_text,
                blockquote_blocks=(
                    blockquote_blocks
                ),
                expandable_blocks=(
                    expandable_blocks
                ),
                other_entities=(
                    other_entities
                ),
                branding=branding
            )
        )

        telegram_plan = (
            publication_plan.telegram
        )

        bale_plan = (
            publication_plan.bale
        )

        logger.info(
            f"📋 Publication Plan received | "
            f"tg_caption="
            f"{len(telegram_plan.get('media_caption', ''))} | "
            f"tg_followup="
            f"{len(telegram_plan.get('followup_messages', []))} | "
            f"tg_blockquote="
            f"{len(telegram_plan.get('blockquote_messages', []))} | "
            f"bale_caption="
            f"{len(bale_plan.get('media_caption', ''))}"
        )

        # =================================================
        # STEP 1
        # TELEGRAM
        # =================================================

        logger.info(
            "📤 Step 1/2 | Execute Telegram Plan"
        )

        telegram_success = (
            execute_telegram_plan(
                files,
                telegram_plan
            )
        )

        if not telegram_success:

            logger.error(
                "❌ Telegram Publication Plan failed"
            )

            # اصل قدیمی حفظ می‌شود:
            # اگر Telegram شکست بخورد Bale اجرا نمی‌شود.

            return False

        logger.info(
            "✅ Telegram Publication Plan completed"
        )

        # =================================================
        # STEP 2
        # BALE
        # =================================================

        logger.info(
            "📤 Step 2/2 | Execute Bale Plan"
        )

        bale_success = (
            execute_bale_plan(
                chat_id,
                files,
                bale_plan
            )
        )

        if bale_success:

            logger.info(
                "✅ Bale Publication Plan completed"
            )

        else:

            logger.warning(
                "⚠️ Telegram succeeded but Bale failed"
            )

        # =================================================
        # SUCCESS POLICY
        # =================================================
        #
        # Telegram Media موفق = عملیات اصلی موفق.
        #
        # Bale failure باعث Fail شدن Telegram نمی‌شود.
        # =================================================

        return True

    except Exception as e:

        logger.exception(
            f"❌ Media Group processing error | "
            f"group={media_group_id} | "
            f"{e}"
        )

        return False

    finally:

        remove_pending_group(
            media_group_id,
            chat_id
        )

        logger.info(
            f"🧹 Media Group cleaned | "
            f"group={media_group_id}"
        )


# =========================================================
# SCHEDULE PROCESSING
# =========================================================

def schedule_processing(
    media_group_id: str,
    chat_id: int,
    delay: float = MEDIA_GROUP_DELAY
) -> None:
    """
    برنامه‌ریزی پردازش Media Group.
    """

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        old_timer = group_timers.get(
            group_key
        )

        if old_timer:

            try:

                old_timer.cancel()

            except Exception:

                pass

        timer = threading.Timer(
            delay,
            _scheduled_process,
            args=(
                media_group_id,
                chat_id
            )
        )

        timer.daemon = True

        group_timers[
            group_key
        ] = timer

        timer.start()

        logger.info(
            f"⏱️ Media Group scheduled | "
            f"group={media_group_id} | "
            f"delay={delay}s"
        )


# =========================================================
# SCHEDULED PROCESS
# =========================================================

def _scheduled_process(
    media_group_id: str,
    chat_id: int
) -> None:
    """
    Timer callback.
    """

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.warning(
                f"⚠️ Media Group not found at timer | "
                f"group={media_group_id}"
            )

            return

        if group.get(
            "is_processing",
            False
        ):

            return

        last_update = group.get(
            "last_update",
            0
        )

        elapsed = (
            time.time()
            - last_update
        )

    if (
        elapsed
        < MEDIA_GROUP_MIN_WAIT
    ):

        remaining = (
            MEDIA_GROUP_MIN_WAIT
            - elapsed
        )

        schedule_processing(
            media_group_id,
            chat_id,
            max(
                remaining,
                0.5
            )
        )

        return

    process_media_group(
        media_group_id,
        chat_id
    )


# =========================================================
# HANDLE MEDIA GROUP MESSAGE
# =========================================================

def handle_media_group_message(
    message: Dict[str, Any],
    file_id: str,
    media_type: str,
    caption: str = "",
    caption_entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> bool:
    """
    دریافت یک بخش از Media Group.

    caption و caption_entities
    هر دو وارد Content Entity Layer می‌شوند.
    """

    media_group_id = message.get(
        "media_group_id"
    )

    if not media_group_id:

        logger.warning(
            "⚠️ media_group_id not found"
        )

        return False

    chat_id = (
        message
        .get(
            "chat",
            {}
        )
        .get(
            "id"
        )
    )

    if chat_id is None:

        logger.error(
            "❌ chat_id not found"
        )

        return False

    # =====================================================
    # CAPTION ENTITIES
    # =====================================================

    if caption_entities is None:

        caption_entities = (
            message.get(
                "caption_entities",
                []
            )
            or []
        )

    logger.info(
        f"🖼️ Media Group message | "
        f"group={media_group_id} | "
        f"type={media_type} | "
        f"caption={bool(caption)} | "
        f"entities={len(caption_entities)}"
    )

    add_to_pending_group(
        media_group_id,
        chat_id,
        file_id,
        media_type,
        caption,
        caption_entities
    )

    schedule_processing(
        media_group_id,
        chat_id,
        delay=MEDIA_GROUP_DELAY
    )

    return True
