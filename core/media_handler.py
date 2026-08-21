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
# THREAD-LOCAL TELEGRAM SEND STATE
# =========================================================

telegram_send_state = threading.local()


def set_last_media_message_id(
    message_id: Optional[int]
) -> None:

    telegram_send_state.last_media_message_id = (
        message_id
    )


def get_last_media_message_id() -> Optional[int]:

    value = getattr(
        telegram_send_state,
        "last_media_message_id",
        None
    )

    if (
        isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return value

    return None


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
CLEANUP_INTERVAL_SECONDS = 300


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
MEDIA_GROUP_INCOMPLETE_RETRY_DELAY = 1.0


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    api_url: str,
    channel_id: str
) -> None:

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

    current_time = time.time()
    groups_to_remove = []

    with group_lock:

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
    ] = None,
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> None:

    group_key = (
        chat_id,
        media_group_id
    )

    with group_lock:

        if group_key not in pending_groups:

            pending_groups[
                group_key
            ] = {
                "chat_id":
                    chat_id,

                "media_group_id":
                    media_group_id,

                "files":
                    [],

                "raw_caption":
                    "",

                "caption_entities":
                    [],

                "main_text":
                    "",

                "expandable_blocks":
                    [],

                "blockquote_blocks":
                    [],

                "other_entities":
                    [],

                "forward_source":
                    {},

                "caption_received":
                    False,

                "last_update":
                    time.time(),

                "is_processing":
                    False,

                "timer_generation":
                    0
            }

            logger.info(
                f"🆕 New Media Group | "
                f"group={media_group_id}"
            )

        group = pending_groups[
            group_key
        ]

        if (
            forward_source
            and forward_source.get(
                "is_forwarded"
            )
            and not group.get(
                "forward_source"
            )
        ):

            group[
                "forward_source"
            ] = dict(
                forward_source
            )

            logger.info(
                f"🔗 Media Group source stored | "
                f"group={media_group_id} | "
                f"title="
                f"{forward_source.get('source_title') or '-'} | "
                f"username="
                f"{forward_source.get('source_username') or '-'}"
            )

        already_exists = any(
            item.get(
                "file_id"
            ) == file_id

            for item
            in group["files"]
        )

        if not already_exists:

            group["files"].append({
                "type":
                    media_type,

                "file_id":
                    file_id
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
                    or []
                )

                group[
                    "blockquote_blocks"
                ] = list(
                    parsed.get(
                        "blockquote_blocks",
                        []
                    )
                    or []
                )

                group[
                    "other_entities"
                ] = list(
                    parsed.get(
                        "other_entities",
                        []
                    )
                    or []
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
#
# DIAGNOSTIC VERSION FOR RENDER / SENDMEDIAGROUP
# =========================================================

def telegram_post(
    endpoint: str,
    payload: Dict[str, Any]
) -> Optional[requests.Response]:

    if not API_URL:

        logger.error(
            "❌ API_URL is not configured"
        )

        return None

    url = (
        f"{API_URL}/{endpoint}"
    )

    request_started = (
        time.monotonic()
    )

    payload_bytes = 0
    media_count = 0

    # =====================================================
    # PAYLOAD DIAGNOSTIC
    # =====================================================

    try:

        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            separators=(",", ":")
        )

        payload_bytes = len(
            serialized_payload.encode(
                "utf-8"
            )
        )

        media_value = payload.get(
            "media"
        )

        if isinstance(
            media_value,
            list
        ):

            media_count = len(
                media_value
            )

        logger.info(
            f"🌐 Telegram API request | "
            f"endpoint={endpoint} | "
            f"media_count={media_count} | "
            f"payload_bytes={payload_bytes}"
        )

        logger.debug(
            f"📨 Telegram payload | "
            f"{serialized_payload[:1500]}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ Telegram payload diagnostic failed | "
            f"endpoint={endpoint} | "
            f"{e}"
        )

    # =====================================================
    # SENDMEDIAGROUP ITEM DIAGNOSTIC
    # =====================================================

    if endpoint == "sendMediaGroup":

        media_value = payload.get(
            "media",
            []
        )

        if isinstance(
            media_value,
            list
        ):

            logger.info(
                f"🧪 sendMediaGroup prepared | "
                f"items={len(media_value)} | "
                f"payload_bytes={payload_bytes}"
            )

            for index, item in enumerate(
                media_value
            ):

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                logger.info(
                    f"🧩 sendMediaGroup item | "
                    f"index={index + 1}/"
                    f"{len(media_value)} | "
                    f"type={item.get('type')} | "
                    f"has_media="
                    f"{bool(item.get('media'))} | "
                    f"has_caption="
                    f"{bool(item.get('caption'))} | "
                    f"caption_length="
                    f"{len(item.get('caption', '') or '')} | "
                    f"caption_entities="
                    f"{len(item.get('caption_entities', []) or [])} | "
                    f"parse_mode="
                    f"{item.get('parse_mode') or 'NONE'}"
                )

    # =====================================================
    # REQUEST WATCHDOG
    #
    # این Thread درخواست را تغییر نمی‌دهد.
    # فقط مشخص می‌کند requests.post چند ثانیه
    # بدون Response مانده است.
    # =====================================================

    watchdog_cancelled = (
        threading.Event()
    )

    def request_watchdog() -> None:

        checkpoints = (
            10,
            30,
            55
        )

        previous_checkpoint = 0

        for checkpoint in checkpoints:

            wait_seconds = (
                checkpoint
                - previous_checkpoint
            )

            previous_checkpoint = (
                checkpoint
            )

            if watchdog_cancelled.wait(
                wait_seconds
            ):
                return

            elapsed = (
                time.monotonic()
                - request_started
            )

            logger.warning(
                f"⏳ Telegram request still waiting | "
                f"endpoint={endpoint} | "
                f"elapsed={elapsed:.2f}s"
            )

    watchdog_thread = (
        threading.Thread(
            target=request_watchdog,
            daemon=True,
            name=(
                f"TelegramWatchdog-"
                f"{endpoint}"
            )
        )
    )

    watchdog_thread.start()

    # =====================================================
    # ACTUAL TELEGRAM REQUEST
    # =====================================================

    try:

        logger.info(
            f"➡️ requests.post ENTER | "
            f"endpoint={endpoint} | "
            f"connect_timeout="
            f"{TELEGRAM_CONNECT_TIMEOUT}s | "
            f"read_timeout="
            f"{TELEGRAM_READ_TIMEOUT}s"
        )

        response = requests.post(
            url,
            json=payload,
            timeout=(
                TELEGRAM_CONNECT_TIMEOUT,
                TELEGRAM_READ_TIMEOUT
            )
        )

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.info(
            f"⬅️ requests.post RETURNED | "
            f"endpoint={endpoint} | "
            f"status={response.status_code} | "
            f"time={elapsed:.2f}s | "
            f"response_bytes="
            f"{len(response.content or b'')}"
        )

        logger.info(
            f"📡 Telegram response | "
            f"endpoint={endpoint} | "
            f"status={response.status_code} | "
            f"time={elapsed:.2f}s"
        )

        return response

    except requests.exceptions.ConnectTimeout as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.error(
            f"⏰ Telegram ConnectTimeout | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    except requests.exceptions.ReadTimeout as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.error(
            f"⏰ Telegram ReadTimeout | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    except requests.exceptions.Timeout as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.error(
            f"⏰ Telegram Timeout | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    except requests.exceptions.ConnectionError as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.error(
            f"🔌 Telegram ConnectionError | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    except requests.exceptions.RequestException as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.error(
            f"❌ Telegram RequestException | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    except Exception as e:

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.exception(
            f"❌ Telegram API error | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s | "
            f"{e}"
        )

        return None

    finally:

        watchdog_cancelled.set()

        elapsed = (
            time.monotonic()
            - request_started
        )

        logger.info(
            f"🏁 Telegram request EXIT | "
            f"endpoint={endpoint} | "
            f"time={elapsed:.2f}s"
        )


# =========================================================
# TELEGRAM RESPONSE CHECK
# =========================================================

def telegram_response_ok(
    response: Optional[
        requests.Response
    ],
    endpoint: str
) -> bool:

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
# DEBUG TELEGRAM RETURNED CAPTION ENTITIES
# =========================================================

def debug_telegram_returned_caption_entities(
    response: Optional[
        requests.Response
    ],
    endpoint: str
) -> None:

    if response is None:
        return

    try:

        data = response.json()

        if data.get(
            "ok"
        ) is not True:
            return

        result = data.get(
            "result"
        )

        if isinstance(
            result,
            list
        ):

            messages = result

        elif isinstance(
            result,
            dict
        ):

            messages = [
                result
            ]

        else:

            return

        for index, message in enumerate(
            messages
        ):

            if not isinstance(
                message,
                dict
            ):
                continue

            caption = (
                message.get(
                    "caption",
                    ""
                )
                or ""
            )

            caption_entities = (
                message.get(
                    "caption_entities",
                    []
                )
                or []
            )

            logger.warning(
                "🔬 TELEGRAM RETURN DEBUG | "
                f"endpoint={endpoint} | "
                f"item={index + 1} | "
                f"message_id="
                f"{message.get('message_id')} | "
                f"caption_repr="
                f"{repr(caption)} | "
                f"caption_entities="
                f"{json.dumps(caption_entities, ensure_ascii=False)}"
            )

    except Exception as e:

        logger.exception(
            "❌ Telegram return debug failed | "
            f"endpoint={endpoint} | "
            f"{e}"
        )


# =========================================================
# EXTRACT SINGLE MESSAGE ID
# =========================================================

def extract_single_message_id(
    response: Optional[
        requests.Response
    ]
) -> Optional[int]:

    if response is None:
        return None

    try:

        data = response.json()

        result = data.get(
            "result"
        )

        if not isinstance(
            result,
            dict
        ):

            return None

        message_id = result.get(
            "message_id"
        )

        if (
            isinstance(message_id, int)
            and not isinstance(message_id, bool)
        ):

            return message_id

    except Exception as e:

        logger.warning(
            f"⚠️ Cannot extract Telegram message_id | "
            f"{e}"
        )

    return None


# =========================================================
# EXTRACT MEDIA GROUP ANCHOR
# =========================================================

def extract_media_group_message_id(
    response: Optional[
        requests.Response
    ]
) -> Optional[int]:

    if response is None:
        return None

    try:

        data = response.json()

        result = data.get(
            "result"
        )

        if not isinstance(
            result,
            list
        ):

            return None

        if not result:
            return None

        first_message = result[0]

        if not isinstance(
            first_message,
            dict
        ):

            return None

        message_id = first_message.get(
            "message_id"
        )

        if (
            isinstance(message_id, int)
            and not isinstance(message_id, bool)
        ):

            return message_id

    except Exception as e:

        logger.warning(
            f"⚠️ Cannot extract Media Group message_id | "
            f"{e}"
        )

    return None


# =========================================================
# SEND TEXT TO TELEGRAM CHANNEL
# =========================================================

def send_text_to_channel(
    text: str,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None
) -> bool:

    if not text:
        return True

    if not CHANNEL_ID:

        logger.error(
            "❌ CHANNEL_ID not configured"
        )

        return False

    payload: Dict[str, Any] = {
        "chat_id":
            CHANNEL_ID,

        "text":
            text
    }

    if parse_mode:

        payload[
            "parse_mode"
        ] = parse_mode

    if (
        isinstance(
            reply_to_message_id,
            int
        )
        and not isinstance(
            reply_to_message_id,
            bool
        )
    ):

        payload[
            "reply_parameters"
        ] = {
            "message_id":
                reply_to_message_id
        }

        logger.info(
            f"↩️ Telegram reply prepared | "
            f"reply_to={reply_to_message_id}"
        )

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
            f"parse_mode={parse_mode or 'NONE'} | "
            f"reply_to="
            f"{reply_to_message_id or '-'}"
        )

    return success


# =========================================================
# SEND SINGLE MEDIA TO TELEGRAM
# =========================================================

def send_single_media_to_channel(
    file_id: str,
    media_type: str,
    caption: str = "",
    parse_mode: Optional[str] = None,
    caption_entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> bool:

    set_last_media_message_id(
        None
    )

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

    endpoint_map = {
        "photo": "sendPhoto",
        "video": "sendVideo",
        "document": "sendDocument",
        "voice": "sendVoice",
        "audio": "sendAudio"
    }

    endpoint = endpoint_map.get(
        media_type
    )

    if not endpoint:

        logger.error(
            f"❌ Unsupported media type | "
            f"type={media_type}"
        )

        return False

    payload: Dict[str, Any] = {
        "chat_id": CHANNEL_ID,
        media_type: file_id
    }

    if caption:

        payload[
            "caption"
        ] = caption

        if caption_entities:

            payload[
                "caption_entities"
            ] = caption_entities

        elif parse_mode:

            payload[
                "parse_mode"
            ] = parse_mode

    response = telegram_post(
        endpoint,
        payload
    )

    if telegram_response_ok(
        response,
        endpoint
    ):

        debug_telegram_returned_caption_entities(
            response,
            endpoint
        )

        message_id = (
            extract_single_message_id(
                response
            )
        )

        set_last_media_message_id(
            message_id
        )

        logger.info(
            f"✅ Single Telegram media sent | "
            f"type={media_type} | "
            f"parse_mode="
            f"{parse_mode or 'NONE'} | "
            f"caption_entities="
            f"{len(caption_entities or [])} | "
            f"message_id="
            f"{message_id or '-'}"
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
    caption: str = "",
    parse_mode: Optional[str] = None,
    caption_entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> bool:

    set_last_media_message_id(
        None
    )

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

    if (
        file_count
        < TELEGRAM_MEDIA_GROUP_MIN_ITEMS
    ):

        logger.error(
            f"❌ Media Group requires at least "
            f"{TELEGRAM_MEDIA_GROUP_MIN_ITEMS} items | "
            f"received={file_count}"
        )

        return False

    if (
        file_count
        > TELEGRAM_MEDIA_GROUP_MAX_ITEMS
    ):

        logger.error(
            f"❌ Media Group exceeds Telegram limit | "
            f"count={file_count} | "
            f"max={TELEGRAM_MEDIA_GROUP_MAX_ITEMS}"
        )

        return False

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

        media_item: Dict[str, Any] = {
            "type":
                media_type,

            "media":
                file_id
        }

        if (
            index == 0
            and caption
        ):

            media_item[
                "caption"
            ] = caption

            if caption_entities:

                media_item[
                    "caption_entities"
                ] = caption_entities

            elif parse_mode:

                media_item[
                    "parse_mode"
                ] = parse_mode

        media_group.append(
            media_item
        )

    payload = {
        "chat_id":
            CHANNEL_ID,

        "media":
            media_group
    }

    response = telegram_post(
        "sendMediaGroup",
        payload
    )

    if telegram_response_ok(
        response,
        "sendMediaGroup"
    ):

        debug_telegram_returned_caption_entities(
            response,
            "sendMediaGroup"
        )

        message_id = (
            extract_media_group_message_id(
                response
            )
        )

        set_last_media_message_id(
            message_id
        )

        logger.info(
            f"🎯 Telegram Media Group sent | "
            f"count={len(media_group)} | "
            f"parse_mode="
            f"{parse_mode or 'NONE'} | "
            f"caption_entities="
            f"{len(caption_entities or [])} | "
            f"anchor_message_id="
            f"{message_id or '-'}"
        )

        return True

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

    media_caption = (
        plan.get(
            "media_caption",
            ""
        )
        or ""
    )

    media_parse_mode = (
        plan.get(
            "media_parse_mode"
        )
        or None
    )

    media_caption_entities = list(
        plan.get(
            "media_caption_entities",
            []
        )
        or []
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
            "❌ Telegram Publication Plan requested "
            "document fallback"
        )

        logger.error(
            "🚫 Unsafe Telegram media send aborted"
        )

        return False

    if not files:

        logger.error(
            "❌ Telegram plan has no media files"
        )

        return False

    set_last_media_message_id(
        None
    )

    if len(files) == 1:

        file = files[0]

        if media_caption_entities:

            media_success = (
                send_single_media_to_channel(
                    file.get(
                        "file_id"
                    ),
                    file.get(
                        "type"
                    ),
                    media_caption,
                    caption_entities=(
                        media_caption_entities
                    )
                )
            )

        elif media_parse_mode:

            media_success = (
                send_single_media_to_channel(
                    file.get(
                        "file_id"
                    ),
                    file.get(
                        "type"
                    ),
                    media_caption,
                    parse_mode=(
                        media_parse_mode
                    )
                )
            )

        else:

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

        if media_caption_entities:

            media_success = (
                send_media_group_to_channel(
                    files,
                    media_caption,
                    caption_entities=(
                        media_caption_entities
                    )
                )
            )

        elif media_parse_mode:

            media_success = (
                send_media_group_to_channel(
                    files,
                    media_caption,
                    parse_mode=(
                        media_parse_mode
                    )
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

    media_message_id = (
        get_last_media_message_id()
    )

    logger.info(
        f"🔗 Telegram media anchor | "
        f"message_id={media_message_id or '-'} | "
        f"blockquote_replies="
        f"{len(blockquote_messages)} | "
        f"followups="
        f"{len(followup_messages)}"
    )

    for index, html_message in enumerate(
        blockquote_messages
    ):

        if media_message_id:

            logger.info(
                f"🧩 Telegram blockquote reply | "
                f"index={index + 1} | "
                f"reply_to={media_message_id}"
            )

            success = (
                send_text_to_channel(
                    html_message,
                    parse_mode="HTML",
                    reply_to_message_id=(
                        media_message_id
                    )
                )
            )

        else:

            logger.warning(
                f"⚠️ Media message_id unavailable | "
                f"blockquote will be sent normally | "
                f"index={index + 1}"
            )

            success = (
                send_text_to_channel(
                    html_message,
                    parse_mode="HTML"
                )
            )

        if not success:

            logger.error(
                f"❌ Telegram blockquote reply failed | "
                f"index={index + 1}"
            )

    for index, message in enumerate(
        followup_messages
    ):

        if media_message_id:

            logger.info(
                f"🏷️ Telegram follow-up reply | "
                f"index={index + 1} | "
                f"reply_to={media_message_id}"
            )

            success = (
                send_text_to_channel(
                    message,
                    reply_to_message_id=(
                        media_message_id
                    )
                )
            )

        else:

            logger.warning(
                f"⚠️ Media message_id unavailable | "
                f"follow-up will be sent normally | "
                f"index={index + 1}"
            )

            success = (
                send_text_to_channel(
                    message
                )
            )

        if not success:

            logger.error(
                f"❌ Telegram follow-up failed | "
                f"index={index + 1}"
            )

    logger.info(
        f"✅ Telegram reply chain completed | "
        f"media={media_message_id or '-'} | "
        f"blockquote_replies="
        f"{len(blockquote_messages)} | "
        f"followup_replies="
        f"{len(followup_messages)}"
    )

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

    group_key = (
        chat_id,
        media_group_id
    )

    logger.info(
        f"🚀 Processing Media Group | "
        f"group={media_group_id} | "
        f"chat={chat_id}"
    )

    with group_lock:

        group = pending_groups.get(
            group_key
        )

        if not group:

            logger.warning(
                f"⚠️ Media Group not found | "
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

        files = list(
            group.get(
                "files",
                []
            )
            or []
        )

        if (
            len(files)
            < TELEGRAM_MEDIA_GROUP_MIN_ITEMS
        ):

            logger.warning(
                f"⏳ Media Group incomplete | "
                f"group={media_group_id} | "
                f"files={len(files)} | "
                f"minimum="
                f"{TELEGRAM_MEDIA_GROUP_MIN_ITEMS}"
            )

            return False

        group[
            "is_processing"
        ] = True

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
            or []
        )

        expandable_blocks = list(
            group.get(
                "expandable_blocks",
                []
            )
            or []
        )

        other_entities = list(
            group.get(
                "other_entities",
                []
            )
            or []
        )

        forward_source = dict(
            group.get(
                "forward_source",
                {}
            )
            or {}
        )

    logger.info(
        f"📦 Media Group snapshot | "
        f"files={len(files)} | "
        f"main={len(raw_main_text)} | "
        f"blockquote={len(blockquote_blocks)} | "
        f"expandable={len(expandable_blocks)} | "
        f"other={len(other_entities)} | "
        f"forwarded="
        f"{bool(forward_source.get('is_forwarded'))}"
    )

    try:

        formatted_main_text = ""

        if raw_main_text:

            try:

                source_title = (
                    forward_source.get(
                        "source_title",
                        ""
                    )
                    or ""
                )

                source_username = (
                    forward_source.get(
                        "source_username",
                        ""
                    )
                    or ""
                )

                if (
                    forward_source.get(
                        "is_forwarded"
                    )
                    and (
                        source_title
                        or source_username
                    )
                ):

                    logger.info(
                        f"🧹 Media Group source cleanup | "
                        f"group={media_group_id} | "
                        f"title={source_title or '-'} | "
                        f"username="
                        f"{source_username or '-'}"
                    )

                    formatted_main_text = (
                        format_news(
                            raw_main_text,
                            source_title=source_title,
                            source_username=source_username
                        )
                    )

                else:

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

                formatted_main_text = (
                    raw_main_text
                )

        branding = (
            build_branding_for_user(
                chat_id
            )
        )

        logger.info(
            f"🏷️ Branding prepared | "
            f"length={len(branding)}"
        )

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
            f"tg_parse_mode="
            f"{telegram_plan.get('media_parse_mode') or 'NONE'} | "
            f"tg_entities="
            f"{len(telegram_plan.get('media_caption_entities', []))} | "
            f"tg_followup="
            f"{len(telegram_plan.get('followup_messages', []))} | "
            f"tg_blockquote="
            f"{len(telegram_plan.get('blockquote_messages', []))} | "
            f"bale_caption="
            f"{len(bale_plan.get('media_caption', ''))}"
        )

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

            return False

        logger.info(
            "✅ Telegram Publication Plan completed"
        )

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
                f"⚠️ Cannot schedule missing Media Group | "
                f"group={media_group_id}"
            )

            return

        if group.get(
            "is_processing",
            False
        ):

            logger.debug(
                f"ℹ️ Media Group already processing | "
                f"group={media_group_id}"
            )

            return

        old_timer = group_timers.get(
            group_key
        )

        if old_timer:

            try:
                old_timer.cancel()
            except Exception:
                pass

        current_generation = (
            int(
                group.get(
                    "timer_generation",
                    0
                )
                or 0
            )
            + 1
        )

        group[
            "timer_generation"
        ] = current_generation

        timer = threading.Timer(
            delay,
            _scheduled_process,
            args=(
                media_group_id,
                chat_id,
                current_generation
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
            f"delay={delay:.2f}s | "
            f"generation={current_generation} | "
            f"files={len(group.get('files', []))}"
        )


# =========================================================
# SCHEDULED PROCESS
# =========================================================

def _scheduled_process(
    media_group_id: str,
    chat_id: int,
    timer_generation: Optional[int] = None
) -> None:

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

            logger.debug(
                f"ℹ️ Media Group already processing "
                f"at timer | "
                f"group={media_group_id}"
            )

            return

        current_generation = int(
            group.get(
                "timer_generation",
                0
            )
            or 0
        )

        if (
            timer_generation is not None
            and timer_generation
            != current_generation
        ):

            logger.info(
                f"🛑 Stale Media Group timer ignored | "
                f"group={media_group_id} | "
                f"timer_generation="
                f"{timer_generation} | "
                f"current_generation="
                f"{current_generation}"
            )

            return

        last_update = float(
            group.get(
                "last_update",
                0
            )
            or 0
        )

        elapsed = (
            time.time()
            - last_update
        )

        file_count = len(
            group.get(
                "files",
                []
            )
            or []
        )

    if (
        elapsed
        < MEDIA_GROUP_DELAY
    ):

        remaining = (
            MEDIA_GROUP_DELAY
            - elapsed
        )

        next_delay = max(
            remaining,
            0.5
        )

        logger.info(
            f"⏳ Media Group still receiving | "
            f"group={media_group_id} | "
            f"elapsed={elapsed:.2f}s | "
            f"wait_more={next_delay:.2f}s | "
            f"files={file_count}"
        )

        schedule_processing(
            media_group_id,
            chat_id,
            delay=next_delay
        )

        return

    if (
        file_count
        < TELEGRAM_MEDIA_GROUP_MIN_ITEMS
    ):

        logger.warning(
            f"⏳ Media Group waiting for more items | "
            f"group={media_group_id} | "
            f"files={file_count} | "
            f"minimum="
            f"{TELEGRAM_MEDIA_GROUP_MIN_ITEMS}"
        )

        schedule_processing(
            media_group_id,
            chat_id,
            delay=(
                MEDIA_GROUP_INCOMPLETE_RETRY_DELAY
            )
        )

        return

    logger.info(
        f"✅ Media Group settled | "
        f"group={media_group_id} | "
        f"files={file_count} | "
        f"elapsed={elapsed:.2f}s"
    )

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

    if not file_id:

        logger.error(
            f"❌ Media Group file_id missing | "
            f"group={media_group_id}"
        )

        return False

    if media_type not in (
        "photo",
        "video"
    ):

        logger.error(
            f"❌ Unsupported Media Group type | "
            f"group={media_group_id} | "
            f"type={media_type}"
        )

        return False

    if caption_entities is None:

        caption_entities = (
            message.get(
                "caption_entities",
                []
            )
            or []
        )

    forward_source = (
        message.get(
            "_forward_source"
        )
        or {}
    )

    logger.info(
        f"🖼️ Media Group message | "
        f"group={media_group_id} | "
        f"type={media_type} | "
        f"caption={bool(caption)} | "
        f"entities={len(caption_entities)} | "
        f"forwarded="
        f"{bool(forward_source.get('is_forwarded'))}"
    )

    if (
        forward_source
        and forward_source.get(
            "is_forwarded"
        )
    ):

        add_to_pending_group(
            media_group_id,
            chat_id,
            file_id,
            media_type,
            caption,
            caption_entities,
            forward_source=(
                forward_source
            )
        )

    else:

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
