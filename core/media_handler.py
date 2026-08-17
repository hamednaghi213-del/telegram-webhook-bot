import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

API_URL: Optional[str] = None
CHANNEL_ID: Optional[str] = None

MEDIA_GROUP_DELAY = 2.5
MEDIA_GROUP_MIN_WAIT = 1.5

TELEGRAM_CONNECT_TIMEOUT = 10
TELEGRAM_READ_TIMEOUT = 30


# ============================================================
# MEDIA GROUP STATE
# ============================================================

pending_groups: Dict[str, Dict[str, Any]] = {}
group_timers: Dict[str, threading.Timer] = {}

group_lock = threading.RLock()


# ============================================================
# INITIALIZE
# ============================================================

def initialize(
    api_url: str,
    channel_id: str
) -> None:
    """
    Initialize Telegram API URL and destination channel.
    """

    global API_URL
    global CHANNEL_ID

    API_URL = (
        str(api_url).rstrip("/")
        if api_url
        else None
    )

    CHANNEL_ID = (
        str(channel_id)
        if channel_id is not None
        else None
    )

    logger.info(
        "✅ Media Handler initialized | "
        f"channel={CHANNEL_ID} | "
        f"api={'SET' if API_URL else 'NOT_SET'}"
    )


# ============================================================
# TELEGRAM HTTP
# ============================================================

def _telegram_endpoint(
    method: str
) -> str:
    if not API_URL:
        raise RuntimeError(
            "Media Handler API_URL is not initialized"
        )

    return (
        f"{API_URL.rstrip('/')}/"
        f"{method}"
    )


def telegram_post(
    method: str,
    payload: Dict[str, Any],
    *,
    connect_timeout: int = TELEGRAM_CONNECT_TIMEOUT,
    read_timeout: int = TELEGRAM_READ_TIMEOUT
) -> Optional[requests.Response]:
    """
    Send one request to Telegram Bot API.

    IMPORTANT:
    A fresh HTTP connection is intentionally used for every call.
    No persistent requests.Session is used here.

    This is especially important for diagnosing the Render
    sendMediaGroup issue.
    """

    url = _telegram_endpoint(
        method
    )

    started_at = time.monotonic()

    safe_payload = dict(
        payload or {}
    )

    # Never dump the complete caption/media content into logs.
    media_value = safe_payload.get(
        "media"
    )

    media_count = 0

    if isinstance(
        media_value,
        list
    ):
        media_count = len(
            media_value
        )

    logger.info(
        "📡 Telegram API request START | "
        f"method={method} | "
        f"chat_id={safe_payload.get('chat_id')} | "
        f"media_count={media_count} | "
        f"connect_timeout={connect_timeout} | "
        f"read_timeout={read_timeout}"
    )

    try:
        #
        # IMPORTANT:
        # Do not reuse an HTTP session here.
        #
        # Connection: close prevents a stale keep-alive socket
        # from being reused by the Render worker.
        #
        response = requests.post(
            url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Connection": "close"
            },
            timeout=(
                connect_timeout,
                read_timeout
            ),
            allow_redirects=False
        )

        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.info(
            "📥 Telegram API response RECEIVED | "
            f"method={method} | "
            f"status={response.status_code} | "
            f"elapsed={elapsed:.3f}s | "
            f"content_length="
            f"{len(response.content or b'')}"
        )

        return response

    except requests.exceptions.ConnectTimeout:
        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.error(
            "❌ Telegram CONNECT TIMEOUT | "
            f"method={method} | "
            f"elapsed={elapsed:.3f}s | "
            f"timeout={connect_timeout}s"
        )

        return None

    except requests.exceptions.ReadTimeout:
        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.error(
            "❌ Telegram READ TIMEOUT | "
            f"method={method} | "
            f"elapsed={elapsed:.3f}s | "
            f"timeout={read_timeout}s"
        )

        return None

    except requests.exceptions.ConnectionError as exc:
        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.exception(
            "❌ Telegram CONNECTION ERROR | "
            f"method={method} | "
            f"elapsed={elapsed:.3f}s | "
            f"error={exc}"
        )

        return None

    except requests.exceptions.RequestException as exc:
        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.exception(
            "❌ Telegram REQUEST ERROR | "
            f"method={method} | "
            f"elapsed={elapsed:.3f}s | "
            f"error={exc}"
        )

        return None

    except Exception as exc:
        elapsed = (
            time.monotonic()
            - started_at
        )

        logger.exception(
            "❌ Telegram UNEXPECTED HTTP ERROR | "
            f"method={method} | "
            f"elapsed={elapsed:.3f}s | "
            f"error={exc}"
        )

        return None


def telegram_response_ok(
    response: Optional[requests.Response],
    method: str = ""
) -> bool:
    """
    Validate Telegram Bot API response.
    """

    if response is None:
        logger.error(
            "❌ Telegram response missing | "
            f"method={method or 'UNKNOWN'}"
        )

        return False

    try:
        data = response.json()

    except Exception:
        body = (
            response.text[:1000]
            if response.text
            else ""
        )

        logger.error(
            "❌ Telegram invalid JSON response | "
            f"method={method or 'UNKNOWN'} | "
            f"status={response.status_code} | "
            f"body={body}"
        )

        return False

    if (
        response.status_code != 200
        or not data.get("ok")
    ):
        logger.error(
            "❌ Telegram API rejected request | "
            f"method={method or 'UNKNOWN'} | "
            f"status={response.status_code} | "
            f"error_code={data.get('error_code')} | "
            f"description={data.get('description')}"
        )

        return False

    logger.info(
        "✅ Telegram API request successful | "
        f"method={method or 'UNKNOWN'}"
    )

    return True


# ============================================================
# MEDIA NORMALIZATION
# ============================================================

def _normalize_media_info(
    media_info: Any
) -> Optional[Dict[str, str]]:
    """
    Normalize incoming media information.

    Expected:
        {
            "type": "photo",
            "file_id": "..."
        }

    video is also supported.
    """

    if not isinstance(
        media_info,
        dict
    ):
        return None

    media_type = (
        media_info.get("type")
        or media_info.get("media_type")
        or ""
    )

    file_id = (
        media_info.get("file_id")
        or ""
    )

    media_type = str(
        media_type
    ).strip().lower()

    file_id = str(
        file_id
    ).strip()

    if media_type not in (
        "photo",
        "video"
    ):
        logger.warning(
            "⚠️ Unsupported media-group type | "
            f"type={media_type}"
        )

        return None

    if not file_id:
        logger.warning(
            "⚠️ Media Group item has no file_id"
        )

        return None

    return {
        "type": media_type,
        "file_id": file_id
    }


# ============================================================
# CAPTION
# ============================================================

def _build_final_caption(
    caption: str
) -> str:
    """
    Preserve the existing Formatter behavior.

    Branding / advanced entity handling should remain outside
    this transport-level repair unless already supplied in caption.
    """

    caption = (
        caption or ""
    ).strip()

    if not caption:
        return ""

    try:
        from core.formatter import format_news

        formatted = format_news(
            caption
        )

        if formatted:
            return formatted

    except Exception as exc:
        logger.exception(
            "⚠️ Formatter failed inside Media Handler | "
            f"error={exc}"
        )

    return caption


# ============================================================
# SINGLE MEDIA
# ============================================================

def _send_single_media(
    item: Dict[str, str],
    caption: str = "",
    parse_mode: Optional[str] = None,
    caption_entities: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Single item received as a Media Group.
    Uses sendPhoto/sendVideo exactly as before.
    """

    media_type = item[
        "type"
    ]

    file_id = item[
        "file_id"
    ]

    if media_type == "photo":
        method = "sendPhoto"
        media_key = "photo"

    elif media_type == "video":
        method = "sendVideo"
        media_key = "video"

    else:
        logger.error(
            "❌ Unsupported single media type | "
            f"type={media_type}"
        )

        return False

    payload: Dict[str, Any] = {
        "chat_id": CHANNEL_ID,
        media_key: file_id
    }

    if caption:
        payload["caption"] = caption

    if caption_entities:
        payload[
            "caption_entities"
        ] = caption_entities

    elif parse_mode:
        payload[
            "parse_mode"
        ] = parse_mode

    logger.info(
        "📤 Single Media Group item | "
        f"method={method} | "
        f"type={media_type} | "
        f"caption_len={len(caption)}"
    )

    response = telegram_post(
        method,
        payload
    )

    return telegram_response_ok(
        response,
        method
    )


# ============================================================
# MEDIA GROUP PAYLOAD
# ============================================================

def _build_media_group_payload(
    items: List[Dict[str, str]],
    caption: str = "",
    parse_mode: Optional[str] = None,
    caption_entities: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Build Telegram InputMedia array.

    Caption must exist ONLY on the first media item.
    """

    media: List[
        Dict[str, Any]
    ] = []

    for index, item in enumerate(
        items
    ):
        media_type = item.get(
            "type"
        )

        file_id = item.get(
            "file_id"
        )

        if (
            media_type not in (
                "photo",
                "video"
            )
            or not file_id
        ):
            continue

        input_media: Dict[str, Any] = {
            "type": media_type,
            "media": file_id
        }

        if (
            index == 0
            and caption
        ):
            input_media[
                "caption"
            ] = caption

            if caption_entities:
                input_media[
                    "caption_entities"
                ] = caption_entities

            elif parse_mode:
                input_media[
                    "parse_mode"
                ] = parse_mode

        media.append(
            input_media
        )

    return media


# ============================================================
# SEND MEDIA GROUP
# ============================================================

def _send_media_group(
    items: List[Dict[str, str]],
    caption: str = "",
    parse_mode: Optional[str] = None,
    caption_entities: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Send a real Telegram Media Group.

    IMPORTANT:
    There is intentionally NO fallback to individual messages.
    """

    media = _build_media_group_payload(
        items=items,
        caption=caption,
        parse_mode=parse_mode,
        caption_entities=caption_entities
    )

    if len(media) < 2:
        logger.error(
            "❌ sendMediaGroup requires at least 2 valid items | "
            f"valid_items={len(media)}"
        )

        return False

    payload: Dict[
        str,
        Any
    ] = {
        "chat_id": CHANNEL_ID,
        "media": media
    }

    #
    # Serialization probe.
    #
    # This happens BEFORE requests.post.
    # If we see this log in Render, we know JSON serialization
    # itself is not the point where execution stops.
    #
    try:
        serialized_probe = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":")
        )

    except Exception as exc:
        logger.exception(
            "❌ sendMediaGroup payload serialization failed | "
            f"error={exc}"
        )

        return False

    logger.info(
        "🧪 sendMediaGroup payload ready | "
        f"items={len(media)} | "
        f"payload_bytes="
        f"{len(serialized_probe.encode('utf-8'))} | "
        f"caption_len={len(caption)} | "
        f"parse_mode={parse_mode or 'NONE'} | "
        f"caption_entities="
        f"{len(caption_entities or [])}"
    )

    for index, item in enumerate(
        media,
        start=1
    ):
        logger.info(
            "🧩 Media Group item | "
            f"index={index}/{len(media)} | "
            f"type={item.get('type')} | "
            f"has_caption={'caption' in item} | "
            f"caption_len="
            f"{len(item.get('caption', ''))}"
        )

    logger.info(
        "🚀 sendMediaGroup POST about to start | "
        f"items={len(media)}"
    )

    response = telegram_post(
        "sendMediaGroup",
        payload,
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT
    )

    logger.info(
        "🏁 sendMediaGroup POST returned to caller | "
        f"response={'YES' if response is not None else 'NO'}"
    )

    if not telegram_response_ok(
        response,
        "sendMediaGroup"
    ):
        return False

    logger.info(
        "✅ Telegram Media Group published | "
        f"items={len(media)}"
    )

    return True


# ============================================================
# BALE
# ============================================================

def _forward_album_to_bale(
    user_id: Any,
    items: List[Dict[str, str]],
    caption: str
) -> None:
    """
    Preserve Bale as best-effort.

    Telegram success must not be rolled back if Bale fails.
    """

    if user_id is None:
        return

    try:
        from core.bale_forwarder import (
            send_to_bale_for_user
        )

    except Exception as exc:
        logger.warning(
            "⚠️ Bale forwarder unavailable | "
            f"error={exc}"
        )

        return

    try:
        #
        # This call is intentionally isolated.
        #
        # If the existing Bale forwarder uses another signature,
        # the TypeError is logged without affecting Telegram.
        #
        send_to_bale_for_user(
            user_id=user_id,
            media_items=items,
            caption=caption
        )

        logger.info(
            "✅ Media Group forwarded to Bale"
        )

    except TypeError:
        #
        # Compatibility with older project signature.
        #
        try:
            send_to_bale_for_user(
                user_id,
                items,
                caption
            )

            logger.info(
                "✅ Media Group forwarded to Bale "
                "| compatibility signature"
            )

        except Exception as exc:
            logger.exception(
                "⚠️ Bale Media Group forwarding failed | "
                f"error={exc}"
            )

    except Exception as exc:
        logger.exception(
            "⚠️ Bale Media Group forwarding failed | "
            f"error={exc}"
        )


# ============================================================
# PROCESS MEDIA GROUP
# ============================================================

def process_media_group(
    media_group_id: str
) -> bool:
    """
    Process one collected Telegram media group.

    Critical design:
    1. Lock
    2. Mark is_processing
    3. Snapshot
    4. Release lock
    5. Telegram network request
    6. Cleanup in finally
    """

    group_id = str(
        media_group_id
    )

    logger.info(
        "⚙️ process_media_group START | "
        f"group={group_id}"
    )

    snapshot: Optional[
        Dict[str, Any]
    ] = None

    try:
        with group_lock:

            group = pending_groups.get(
                group_id
            )

            if not group:
                logger.warning(
                    "⚠️ Media Group not found | "
                    f"group={group_id}"
                )

                return False

            if group.get(
                "is_processing"
            ):
                logger.info(
                    "ℹ️ Media Group already processing | "
                    f"group={group_id}"
                )

                return False

            age = (
                time.monotonic()
                - group.get(
                    "last_update",
                    time.monotonic()
                )
            )

            if (
                age
                < MEDIA_GROUP_MIN_WAIT
            ):
                remaining = (
                    MEDIA_GROUP_MIN_WAIT
                    - age
                )

                logger.info(
                    "⏳ Media Group minimum wait not reached | "
                    f"group={group_id} | "
                    f"remaining={remaining:.3f}s"
                )

                timer = threading.Timer(
                    remaining,
                    process_media_group,
                    args=(
                        group_id,
                    )
                )

                timer.daemon = True

                old_timer = group_timers.get(
                    group_id
                )

                if old_timer:
                    try:
                        old_timer.cancel()
                    except Exception:
                        pass

                group_timers[
                    group_id
                ] = timer

                timer.start()

                return False

            group[
                "is_processing"
            ] = True

            #
            # Snapshot BEFORE releasing lock.
            #
            snapshot = {
                "items": [
                    dict(item)
                    for item in group.get(
                        "items",
                        []
                    )
                ],
                "caption": (
                    group.get(
                        "caption",
                        ""
                    )
                    or ""
                ),
                "user_id": group.get(
                    "user_id"
                ),
                "parse_mode": group.get(
                    "parse_mode"
                ),
                "caption_entities": [
                    dict(entity)
                    for entity in group.get(
                        "caption_entities",
                        []
                    )
                ]
            }

        #
        # NETWORK OPERATIONS ARE OUTSIDE THE LOCK.
        #
        items = snapshot[
            "items"
        ]

        caption = snapshot[
            "caption"
        ]

        user_id = snapshot[
            "user_id"
        ]

        parse_mode = snapshot[
            "parse_mode"
        ]

        caption_entities = snapshot[
            "caption_entities"
        ]

        logger.info(
            "📸 Media Group snapshot ready | "
            f"group={group_id} | "
            f"items={len(items)} | "
            f"caption_len={len(caption)} | "
            f"entities={len(caption_entities)}"
        )

        if not items:
            logger.error(
                "❌ Empty Media Group | "
                f"group={group_id}"
            )

            return False

        #
        # If advanced caption logic already supplied parse_mode /
        # entities, preserve it.
        #
        # Otherwise use existing formatter behavior.
        #
        final_caption = caption

        if (
            not parse_mode
            and not caption_entities
        ):
            final_caption = (
                _build_final_caption(
                    caption
                )
            )

        #
        # SINGLE ITEM
        #
        if len(items) == 1:

            logger.info(
                "📤 Media Group contains one item | "
                f"group={group_id}"
            )

            success = _send_single_media(
                item=items[0],
                caption=final_caption,
                parse_mode=parse_mode,
                caption_entities=caption_entities
            )

        #
        # REAL MEDIA GROUP
        #
        else:

            logger.info(
                "📤 Real Media Group sending | "
                f"group={group_id} | "
                f"items={len(items)}"
            )

            success = _send_media_group(
                items=items,
                caption=final_caption,
                parse_mode=parse_mode,
                caption_entities=caption_entities
            )

        if not success:
            logger.error(
                "❌ Telegram Media Group failed | "
                f"group={group_id}"
            )

            return False

        logger.info(
            "✅ Telegram Media Group completed | "
            f"group={group_id}"
        )

        #
        # Bale is executed ONLY after Telegram success.
        #
        _forward_album_to_bale(
            user_id=user_id,
            items=items,
            caption=final_caption
        )

        return True

    except Exception as exc:
        logger.exception(
            "❌ process_media_group unexpected error | "
            f"group={group_id} | "
            f"error={exc}"
        )

        return False

    finally:

        with group_lock:

            timer = group_timers.pop(
                group_id,
                None
            )

            if timer:
                try:
                    timer.cancel()
                except Exception:
                    pass

            pending_groups.pop(
                group_id,
                None
            )

        logger.info(
            "🧹 Media Group cleaned | "
            f"group={group_id}"
        )


# ============================================================
# SCHEDULE
# ============================================================

def _schedule_media_group(
    media_group_id: str
) -> None:

    group_id = str(
        media_group_id
    )

    old_timer = group_timers.get(
        group_id
    )

    if old_timer:
        try:
            old_timer.cancel()
        except Exception:
            pass

    timer = threading.Timer(
        MEDIA_GROUP_DELAY,
        process_media_group,
        args=(
            group_id,
        )
    )

    #
    # Do not keep the Gunicorn worker alive solely
    # because a Timer object exists.
    #
    timer.daemon = True

    group_timers[
        group_id
    ] = timer

    timer.start()

    logger.info(
        "⏱️ Media Group scheduled | "
        f"group={group_id} | "
        f"delay={MEDIA_GROUP_DELAY}s"
    )


# ============================================================
# HANDLE MEDIA GROUP
# ============================================================

def handle_media_group_message(
    media_group_id: str,
    media_info: Optional[Dict[str, Any]] = None,
    caption: str = "",
    user_id: Any = None,
    caption_entities: Optional[List[Dict[str, Any]]] = None,
    parse_mode: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Add an item to pending Media Group.

    Current preferred call:

        handle_media_group_message(
            media_group_id=...,
            media_info={
                "type": "photo",
                "file_id": "..."
            },
            caption=...,
            user_id=...,
            caption_entities=...
        )
    """

    if not media_group_id:
        logger.error(
            "❌ media_group_id missing"
        )

        return False

    #
    # Compatibility aliases.
    #
    if media_info is None:

        media_type = (
            kwargs.get(
                "media_type"
            )
            or kwargs.get(
                "type"
            )
        )

        file_id = kwargs.get(
            "file_id"
        )

        if (
            media_type
            and file_id
        ):
            media_info = {
                "type": media_type,
                "file_id": file_id
            }

    if not caption:
        caption = (
            kwargs.get(
                "text"
            )
            or kwargs.get(
                "caption"
            )
            or ""
        )

    if user_id is None:
        user_id = (
            kwargs.get(
                "telegram_user_id"
            )
            or kwargs.get(
                "chat_id"
            )
            or kwargs.get(
                "user_id"
            )
        )

    if caption_entities is None:
        caption_entities = (
            kwargs.get(
                "entities"
            )
            or kwargs.get(
                "caption_entities"
            )
            or []
        )

    if parse_mode is None:
        parse_mode = kwargs.get(
            "parse_mode"
        )

    normalized = (
        _normalize_media_info(
            media_info
        )
    )

    if not normalized:
        logger.error(
            "❌ Invalid Media Group item | "
            f"group={media_group_id}"
        )

        return False

    group_id = str(
        media_group_id
    )

    file_id = normalized[
        "file_id"
    ]

    now = time.monotonic()

    with group_lock:

        group = pending_groups.get(
            group_id
        )

        if group is None:

            group = {
                "items": [],
                "caption": "",
                "user_id": user_id,
                "caption_entities": [],
                "parse_mode": parse_mode,
                "last_update": now,
                "is_processing": False
            }

            pending_groups[
                group_id
            ] = group

            logger.info(
                "🆕 Media Group created | "
                f"group={group_id}"
            )

        if group.get(
            "is_processing"
        ):
            logger.warning(
                "⚠️ Media arrived after processing started | "
                f"group={group_id}"
            )

            return False

        #
        # Prevent duplicate file_id.
        #
        duplicate = any(
            item.get(
                "file_id"
            )
            == file_id

            for item
            in group[
                "items"
            ]
        )

        if duplicate:
            logger.info(
                "ℹ️ Duplicate Media Group item ignored | "
                f"group={group_id} | "
                f"file_id={file_id[:16]}..."
            )

            group[
                "last_update"
            ] = now

            _schedule_media_group(
                group_id
            )

            return True

        group[
            "items"
        ].append(
            normalized
        )

        #
        # Telegram normally includes caption only on
        # one item of an album.
        #
        if (
            caption
            and not group.get(
                "caption"
            )
        ):
            group[
                "caption"
            ] = caption

            group[
                "caption_entities"
            ] = list(
                caption_entities
                or []
            )

            group[
                "parse_mode"
            ] = parse_mode

        if (
            user_id is not None
            and group.get(
                "user_id"
            ) is None
        ):
            group[
                "user_id"
            ] = user_id

        group[
            "last_update"
        ] = now

        item_count = len(
            group[
                "items"
            ]
        )

        logger.info(
            "➕ Media Group item added | "
            f"group={group_id} | "
            f"items={item_count} | "
            f"type={normalized['type']} | "
            f"has_caption={bool(caption)}"
        )

        #
        # Schedule AFTER the most recent media item.
        #
        _schedule_media_group(
            group_id
        )

    return True


# ============================================================
# DEBUG STATE
# ============================================================

def get_pending_groups_count() -> int:

    with group_lock:
        return len(
            pending_groups
        )


def get_pending_group_snapshot(
    media_group_id: str
) -> Optional[Dict[str, Any]]:

    group_id = str(
        media_group_id
    )

    with group_lock:

        group = pending_groups.get(
            group_id
        )

        if not group:
            return None

        return {
            "items": [
                dict(item)
                for item in group.get(
                    "items",
                    []
                )
            ],
            "caption": group.get(
                "caption",
                ""
            ),
            "user_id": group.get(
                "user_id"
            ),
            "caption_entities": [
                dict(entity)
                for entity in group.get(
                    "caption_entities",
                    []
                )
            ],
            "parse_mode": group.get(
                "parse_mode"
            ),
            "last_update": group.get(
                "last_update"
            ),
            "is_processing": group.get(
                "is_processing",
                False
            )
        }
