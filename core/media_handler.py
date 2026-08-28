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


def _destination_kwargs(channel_id=None, api_url=None) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if channel_id is not None:
        kwargs["channel_id"] = channel_id
    if api_url is not None:
        kwargs["api_url"] = api_url
    return kwargs


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
MEDIA_GROUP_RECOVERY_WINDOW_SECONDS = 15.0
MEDIA_GROUP_MAX_RETRIES = 5


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

            protected = group.get("state") in {"leased", "publishing", "retry_pending", "editorial_pending"}
            terminal = group.get("state") == "failed_terminal"
            has_unpublished = bool(group.get("files"))
            if (
                age_seconds
                > MAX_GROUP_AGE_SECONDS
                and not protected
                and not group.get("is_processing")
                and (not has_unpublished or terminal)
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

            removable_groups = [
                item for item in pending_groups.items()
                if item[1].get("state") not in {"leased", "publishing", "retry_pending", "editorial_pending"}
                and not item[1].get("is_processing")
                and (not item[1].get("files") or item[1].get("state") == "failed_terminal")
            ]
            sorted_groups = sorted(
                removable_groups,
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
    ] = None,
    message_id: Optional[int] = None,
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

                "generation":
                    0,

                "published_generation":
                    None,

                "timer_generation":
                    0,

                "state":
                    "collecting",

                "leased_generation":
                    None,

                "delivery_generation":
                    1,

                "recovery_started_at":
                    time.time(),

                "attempt_count":
                    0,

                "last_error":
                    None,
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
            (
                message_id is not None
                and item.get("message_id") == message_id
            )
            or (
                message_id is None
                and item.get("file_id") == file_id
            )

            for item
            in group["files"]
        )

        if not already_exists:

            group["files"].append({
                "type":
                    media_type,

                "file_id":
                    file_id,

                "message_id":
                    message_id,
            })

            group["files"].sort(
                key=lambda item: (
                    item.get("message_id") is None,
                    item.get("message_id") or 0,
                )
            )

            group["generation"] = int(group.get("generation", 0) or 0) + 1
            # A late member invalidates an uncommitted snapshot.  The active
            # processor re-checks this generation immediately before send.
            if group.get("is_processing"):
                if group.get("state") == "publishing":
                    group["state"] = "retry_pending"
                logger.info(
                    f"🔄 Media Group snapshot invalidated | "
                    f"group={media_group_id} | generation={group['generation']}"
                )

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


def lease_editorial_group_for_publication(
    media_group_id: str,
    chat_id: int,
    fallback_files: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Lease the latest editorial album generation for an approved publish."""
    group_key = (chat_id, str(media_group_id))
    with group_lock:
        group = pending_groups.get(group_key)
        if not group:
            files = list(fallback_files or [])
            return {
                "files": files, "generation": None, "delivery_generation": 1,
                "source_key": f"tg:{chat_id}:album:{media_group_id}:generation:1",
                "managed": False,
            }
        retry_files = group.get("editorial_retry_files")
        files = list(
            retry_files if retry_files is not None else (group.get("files", []) or [])
        )[:TELEGRAM_MEDIA_GROUP_MAX_ITEMS]
        generation = int(group.get("generation", 0) or 0)
        delivery_generation = int(group.get("delivery_generation", 1) or 1)
        group["is_processing"] = True
        group["state"] = "publishing"
        group["leased_generation"] = generation
        return {
            "files": files, "generation": generation,
            "delivery_generation": delivery_generation,
            "source_key": f"tg:{chat_id}:album:{media_group_id}:generation:{delivery_generation}",
            "managed": True,
        }


def finish_editorial_group_publication(
    media_group_id: str,
    chat_id: int,
    lease: Dict[str, Any],
    success: bool,
    approved_text: Optional[str] = None,
) -> None:
    """Complete only the leased editorial batch and retain every late member."""
    if not lease.get("managed"):
        return
    group_key = (chat_id, str(media_group_id))
    should_remove = False
    should_schedule = False
    timer_to_cancel = None
    with group_lock:
        group = pending_groups.get(group_key)
        if not group:
            return
        group["editorial_finalized"] = True
        if approved_text is not None:
            group["editorial_approved_text"] = str(approved_text)
        if not success:
            group["is_processing"] = False
            group["state"] = "editorial_pending"
            group["last_error"] = "approved editorial publication failed"
            group["editorial_retry_files"] = list(lease.get("files", []))
        else:
            group.pop("editorial_retry_files", None)
            snapshot_ids = {
                item.get("message_id") if item.get("message_id") is not None
                else ("file", item.get("file_id"))
                for item in lease.get("files", [])
            }
            group["files"] = [
                item for item in group.get("files", [])
                if (
                    item.get("message_id") if item.get("message_id") is not None
                    else ("file", item.get("file_id"))
                ) not in snapshot_ids
            ]
            group["published_generation"] = lease.get("generation")
            group["is_processing"] = False
            if group["files"]:
                group["state"] = "retry_pending"
                group["delivery_generation"] = int(lease.get("delivery_generation", 1)) + 1
                group["recovery_started_at"] = time.time()
                group["attempt_count"] = 0
                group["last_error"] = None
                should_schedule = True
            else:
                group["state"] = "published"
                # Removal must be atomic with the empty-state check. Otherwise
                # a webhook can add a late member between unlock and pop.
                pending_groups.pop(group_key, None)
                timer_to_cancel = group_timers.pop(group_key, None)
    if timer_to_cancel:
        try:
            timer_to_cancel.cancel()
        except Exception:
            pass
    if should_schedule:
        schedule_processing(
            str(media_group_id), chat_id,
            delay=MEDIA_GROUP_INCOMPLETE_RETRY_DELAY,
        )


# =========================================================
# TELEGRAM POST
#
# DIAGNOSTIC VERSION FOR RENDER / SENDMEDIAGROUP
# =========================================================

def telegram_post(
    endpoint: str,
    payload: Dict[str, Any],
    api_url: Optional[str] = None,
) -> Optional[requests.Response]:

    effective_api_url = (api_url or API_URL or "").rstrip("/")

    if not effective_api_url:

        logger.error(
            "❌ API_URL is not configured"
        )

        return None

    url = (
        f"{effective_api_url}/{endpoint}"
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
    reply_to_message_id: Optional[int] = None,
    channel_id: Optional[str] = None,
    api_url: Optional[str] = None,
) -> bool:

    if not text:
        return True

    effective_channel_id = channel_id or CHANNEL_ID

    if not effective_channel_id:

        logger.error(
            "❌ CHANNEL_ID not configured"
        )

        return False

    payload: Dict[str, Any] = {
        "chat_id":
            effective_channel_id,

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

    response = (
        telegram_post("sendMessage", payload, api_url=api_url)
        if api_url is not None
        else telegram_post("sendMessage", payload)
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
    ] = None,
    channel_id: Optional[str] = None,
    api_url: Optional[str] = None,
    return_result: bool = False,
):

    set_last_media_message_id(
        None
    )

    effective_api_url = api_url or API_URL
    effective_channel_id = channel_id or CHANNEL_ID

    if not effective_api_url:

        logger.error(
            "❌ API_URL not configured"
        )

        return False

    if not effective_channel_id:

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
        "chat_id": effective_channel_id,
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

    response = (
        telegram_post(endpoint, payload, api_url=effective_api_url)
        if api_url is not None
        else telegram_post(endpoint, payload)
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

        if return_result:
            data = response.json() or {}
            result = data.get("result") or {}
            return {
                "ok": True,
                "result": result,
                "message_id": result.get("message_id"),
                "status_code": response.status_code,
                "operation": endpoint,
            }
        return True

    if return_result:
        try:
            data = response.json() if response is not None else {}
        except Exception:
            data = {}
        return {
            "ok": False,
            "status_code": getattr(response, "status_code", None),
            "error_code": data.get("error_code"),
            "error": data.get("description") or "Telegram media request failed",
            "operation": endpoint,
        }
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
    ] = None,
    channel_id: Optional[str] = None,
    api_url: Optional[str] = None,
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

    effective_api_url = api_url or API_URL
    effective_channel_id = channel_id or CHANNEL_ID

    if not effective_api_url:

        logger.error(
            "❌ API_URL not configured"
        )

        return False

    if not effective_channel_id:

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
            effective_channel_id,

        "media":
            media_group
    }

    response = (
        telegram_post("sendMediaGroup", payload, api_url=effective_api_url)
        if api_url is not None
        else telegram_post("sendMediaGroup", payload)
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
    caption: str = "",
    return_result: bool = False,
):

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
                caption,
                return_result=return_result,
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
    plan: Dict[str, Any],
    channel_id: Optional[str] = None,
    api_url: Optional[str] = None,
    return_result: bool = False,
):

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
                    ),
                    **_destination_kwargs(channel_id, api_url),
                    **({"return_result": True} if return_result else {}),
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
                    ),
                    **_destination_kwargs(channel_id, api_url),
                    **({"return_result": True} if return_result else {}),
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
                    media_caption,
                    **_destination_kwargs(channel_id, api_url),
                    **({"return_result": True} if return_result else {}),
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
                    ),
                    **_destination_kwargs(channel_id, api_url),
                )
            )

        elif media_parse_mode:

            media_success = (
                send_media_group_to_channel(
                    files,
                    media_caption,
                    parse_mode=(
                        media_parse_mode
                    ),
                    **_destination_kwargs(channel_id, api_url),
                )
            )

        else:

            media_success = (
                send_media_group_to_channel(
                    files,
                    media_caption,
                    **_destination_kwargs(channel_id, api_url),
                )
            )

    media_ok = bool(media_success.get("ok")) if isinstance(media_success, dict) else bool(media_success)
    if not media_ok:

        logger.error(
            "❌ Telegram media execution failed"
        )

        return media_success if return_result else False

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
                    ),
                    **_destination_kwargs(channel_id, api_url),
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
                    parse_mode="HTML",
                    **_destination_kwargs(channel_id, api_url),
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
                    ),
                    **_destination_kwargs(channel_id, api_url),
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
                    message,
                    **_destination_kwargs(channel_id, api_url),
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

    return media_success if return_result and isinstance(media_success, dict) else True


# =========================================================
# EXECUTE BALE PLAN
# =========================================================

def execute_bale_plan(
    user_id: int,
    files: List[
        Dict[str, str]
    ],
    plan: Dict[str, Any],
    return_result: bool = False,
):

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
            media_caption,
            return_result=return_result,
        )
    )

    media_ok = bool(media_success.get("ok")) if isinstance(media_success, dict) else bool(media_success)
    if not media_ok:

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

    return media_success if return_result else True


# =========================================================
# PROCESS MEDIA GROUP
# =========================================================

def process_media_group(
    media_group_id: str,
    chat_id: int,
    expected_generation: Optional[int] = None,
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

        current_generation = int(group.get("generation", 0) or 0)
        if expected_generation is not None and expected_generation != current_generation:
            logger.info(
                f"🛑 Media Group generation changed before snapshot | "
                f"group={media_group_id} | expected={expected_generation} | "
                f"current={current_generation}"
            )
            return False

        all_files = list(
            group.get(
                "files",
                []
            )
            or []
        )

        recovery_age = time.time() - float(group.get("recovery_started_at", group.get("last_update", time.time())))
        allow_single = len(all_files) == 1 and recovery_age >= MEDIA_GROUP_RECOVERY_WINDOW_SECONDS

        if (
            len(all_files)
            < TELEGRAM_MEDIA_GROUP_MIN_ITEMS
            and not allow_single
        ):

            logger.warning(
                f"⏳ Media Group incomplete | "
                f"group={media_group_id} | "
                f"files={len(all_files)} | "
                f"minimum="
                f"{TELEGRAM_MEDIA_GROUP_MIN_ITEMS}"
            )

            return False

        files = all_files[:TELEGRAM_MEDIA_GROUP_MAX_ITEMS]
        delivery_generation = int(group.get("delivery_generation", 1) or 1)

        group["is_processing"] = True
        group["state"] = "leased"
        group["leased_generation"] = current_generation
        snapshot_generation = current_generation

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

        editorial_finalized = bool(group.get("editorial_finalized", False))
        if editorial_finalized:
            raw_main_text = str(group.get("editorial_approved_text", raw_main_text) or "")

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
        forced_content_type = None
        if raw_main_text and not editorial_finalized:
            try:
                from core.webhook_handler import detect_editorial_admin_tag
                forced_content_type, raw_main_text, _removed = detect_editorial_admin_tag(
                    raw_main_text
                )
            except Exception:
                forced_content_type = None

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

        from core.content_model import PreparedContent
        from core.publication_engine import publish_prepared_content

        # Albums and single messages must share the same established Legacy
        # content-processing result. Destination-specific formatting strips
        # these Legacy icons and applies the selected Workspace profile later.
        neutral_main_text = formatted_main_text or raw_main_text

        with group_lock:
            live_group = pending_groups.get(group_key)
            live_generation = int((live_group or {}).get("generation", -1) or -1)
            if not live_group or live_generation != snapshot_generation:
                if live_group:
                    live_group["is_processing"] = False
                logger.info(
                    f"🛑 Media Group send postponed for late member | "
                    f"group={media_group_id} | snapshot={snapshot_generation} | "
                    f"current={live_generation}"
                )
                schedule_processing(media_group_id, chat_id, delay=MEDIA_GROUP_DELAY)
                return False
            live_group["state"] = "publishing"

        if forced_content_type:
            from core.webhook_handler import try_queue_editorial_text_review
            queued = try_queue_editorial_text_review(
                chat_id=chat_id,
                text=raw_main_text,
                entities=[],
                forward_source=forward_source or None,
                forced_content_type=forced_content_type,
                media_files=files,
                source_key=f"tg:{chat_id}:album:{media_group_id}:generation:{delivery_generation}",
                media_group_id=media_group_id,
            )
            if queued:
                with group_lock:
                    live_group = pending_groups.get(group_key)
                    if live_group:
                        live_group["state"] = "editorial_pending"
                        live_group["is_processing"] = False
                return True

        shared_result = publish_prepared_content(
            chat_id,
            API_URL,
            PreparedContent(
                main_text=formatted_main_text,
                neutral_text=neutral_main_text,
                blockquote_blocks=blockquote_blocks,
                expandable_blocks=expandable_blocks,
                other_entities=other_entities,
                files=files,
                editorial_finalized=editorial_finalized,
                source_key=f"tg:{chat_id}:album:{media_group_id}:generation:{delivery_generation}",
            ),
        )
        if shared_result.get("ok"):
            timer_to_cancel = None
            should_schedule = False
            with group_lock:
                live_group = pending_groups.get(group_key)
                if live_group:
                    live_group["published_generation"] = snapshot_generation
                    snapshot_ids = {
                        item.get("message_id") if item.get("message_id") is not None
                        else ("file", item.get("file_id"))
                        for item in files
                    }
                    live_group["files"] = [
                        item for item in live_group.get("files", [])
                        if (
                            item.get("message_id") if item.get("message_id") is not None
                            else ("file", item.get("file_id"))
                        ) not in snapshot_ids
                    ]
                    if live_group["files"]:
                        live_group["state"] = "retry_pending"
                        live_group["is_processing"] = False
                        live_group["delivery_generation"] = delivery_generation + 1
                        live_group["recovery_started_at"] = time.time()
                        live_group["attempt_count"] = 0
                        live_group["last_error"] = None
                        should_schedule = True
                    else:
                        live_group["state"] = "published"
                        # Keep the empty check and removal in one critical
                        # section so a newly arriving member cannot be popped.
                        pending_groups.pop(group_key, None)
                        timer_to_cancel = group_timers.pop(group_key, None)
            if timer_to_cancel:
                try:
                    timer_to_cancel.cancel()
                except Exception:
                    pass
            if not should_schedule:
                logger.info(f"🧹 Media Group cleaned after success | group={media_group_id}")
            else:
                schedule_processing(
                    media_group_id, chat_id,
                    delay=MEDIA_GROUP_INCOMPLETE_RETRY_DELAY,
                )
            return True
        logger.error("❌ Shared Media Group publication failed | group=%s", media_group_id)
        with group_lock:
            live_group = pending_groups.get(group_key)
            if live_group:
                live_group["attempt_count"] = int(live_group.get("attempt_count", 0) or 0) + 1
                live_group["last_error"] = "shared publication failed"
                if live_group["attempt_count"] >= MEDIA_GROUP_MAX_RETRIES:
                    live_group["state"] = "failed_terminal"
        return False

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

        # No network side effect is allowed from a stale snapshot.
        with group_lock:
            live_group = pending_groups.get(group_key)
            live_generation = int((live_group or {}).get("generation", -1) or -1)
            if not live_group or live_generation != snapshot_generation:
                if live_group:
                    live_group["is_processing"] = False
                logger.info(
                    f"🛑 Media Group send postponed for late member | "
                    f"group={media_group_id} | snapshot={snapshot_generation} | "
                    f"current={live_generation}"
                )
                schedule_processing(media_group_id, chat_id, delay=MEDIA_GROUP_DELAY)
                return False

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

        with group_lock:
            live_group = pending_groups.get(group_key)
            if live_group:
                live_group["published_generation"] = snapshot_generation
        remove_pending_group(media_group_id, chat_id)
        logger.info(f"🧹 Media Group cleaned after success | group={media_group_id}")
        return True

    except Exception as e:

        logger.exception(
            f"❌ Media Group processing error | "
            f"group={media_group_id} | "
            f"{e}"
        )

        with group_lock:
            live_group = pending_groups.get(group_key)
            if live_group:
                live_group["attempt_count"] = int(live_group.get("attempt_count", 0) or 0) + 1
                live_group["last_error"] = str(e)
                if live_group["attempt_count"] >= MEDIA_GROUP_MAX_RETRIES:
                    live_group["state"] = "failed_terminal"
        return False

    finally:
        # Keep failed/stale groups for retry.  Successful groups are removed
        # explicitly only after every configured publication step completes.
        retry_required = False
        with group_lock:
            live_group = pending_groups.get(group_key)
            if live_group:
                if live_group.get("state") == "editorial_pending":
                    live_group["is_processing"] = False
                else:
                    live_group["is_processing"] = False
                    if live_group.get("state") not in {"published", "failed_terminal"}:
                        live_group["state"] = "retry_pending"
                    retry_required = live_group.get("state") != "failed_terminal"
        if retry_required:
            schedule_processing(
                media_group_id,
                chat_id,
                delay=MEDIA_GROUP_INCOMPLETE_RETRY_DELAY,
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

        if group.get("state") == "editorial_pending":
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

    if file_count < TELEGRAM_MEDIA_GROUP_MIN_ITEMS:
        with group_lock:
            current = pending_groups.get(group_key) or {}
            recovery_age = time.time() - float(current.get("recovery_started_at", last_update) or last_update)
        if file_count == 1 and recovery_age >= MEDIA_GROUP_RECOVERY_WINDOW_SECONDS:
            logger.info("♻️ Single late media reached recovery deadline | group=%s", media_group_id)
            process_media_group(media_group_id, chat_id, expected_generation=int(current.get("generation", 0) or 0))
            return

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
                min(MEDIA_GROUP_INCOMPLETE_RETRY_DELAY,
                    max(0.1, MEDIA_GROUP_RECOVERY_WINDOW_SECONDS - recovery_age))
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
        chat_id,
        expected_generation=current_generation,
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
            ),
            message_id=message.get("message_id"),
        )

    else:

        add_to_pending_group(
            media_group_id,
            chat_id,
            file_id,
            media_type,
            caption,
            caption_entities,
            message_id=message.get("message_id"),
        )

    schedule_processing(
        media_group_id,
        chat_id,
        delay=MEDIA_GROUP_DELAY
    )

    return True
