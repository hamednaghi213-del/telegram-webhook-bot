"""Telegram delivery helpers for the External Review preview surface.

The preview is one coherent surface:

  - optional media panel (photos; album when more than one)
  - one persistent control message (text + inline keyboard)

State changes edit the control message in place and reconcile the
media panel only when the visible media set changes. No new free
-standing status messages are created.

Every helper here is fail-soft: Telegram delivery problems are
logged and reported as ``False``/``None`` so a preview UI hiccup
can never block or duplicate the publication path.

Preview media display is presentation-only. Publication media
still crosses the existing staging/materialization boundary at
execution time; nothing here changes PreparedContent construction.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from core.external_content_model import (
    ExternalMedia,
)


logger = logging.getLogger(__name__)


# =========================================================
# TYPES
# =========================================================

# Minimal Telegram API caller used by this module:
#   telegram_api("sendMessage", {"chat_id": ..., ...}) -> dict
TelegramApiCaller = Callable[
    [str, Mapping[str, Any]],
    Mapping[str, Any],
]


# =========================================================
# RESPONSE HELPERS
# =========================================================


def _result_ok(
    response: Any,
) -> bool:
    return bool(
        isinstance(
            response,
            Mapping,
        )
        and response.get(
            "ok",
            False,
        )
    )


def _result_payload(
    response: Any,
) -> Mapping[str, Any]:
    if not _result_ok(response):
        return {}

    result = response.get(
        "result"
    )

    if isinstance(
        result,
        Mapping,
    ):
        return result

    return {}


def _message_id_from_result(
    result: Mapping[str, Any],
) -> Optional[int]:
    message_id = result.get(
        "message_id"
    )

    try:
        value = int(
            message_id
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if value <= 0:
        return None

    return value


def _photo_file_id_from_result(
    result: Mapping[str, Any],
) -> str:
    photos = (
        result.get(
            "photo"
        )
        or []
    )

    if not isinstance(
        photos,
        list,
    ):
        return ""

    for item in reversed(
        photos
    ):
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        file_id = str(
            item.get(
                "file_id"
            )
            or ""
        ).strip()

        if file_id:
            return file_id

    return ""


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True)
class MediaPanelResult:
    """Outcome of rendering one preview media panel."""

    message_ids: Tuple[int, ...] = ()

    # file_id per source media position, ready to persist so
    # later toggles can re-display without staging again.
    file_ids_by_position: Mapping[int, str] = field(
        default_factory=dict
    )


# =========================================================
# CONTROL MESSAGE
# =========================================================


def send_control_message(
    *,
    telegram_api: TelegramApiCaller,
    chat_id: int,
    text: str,
    reply_markup: Optional[
        Mapping[str, Any]
    ] = None,
) -> Optional[int]:
    payload: Dict[str, Any] = {
        "chat_id": int(chat_id),
        "text": str(text or ""),
    }

    if reply_markup:
        payload[
            "reply_markup"
        ] = reply_markup

    try:
        response = telegram_api(
            "sendMessage",
            payload,
        )

    except Exception as exc:
        logger.exception(
            "external review control message "
            f"send failed | {exc}"
        )
        return None

    return _message_id_from_result(
        _result_payload(
            response
        )
    )


def edit_control_message(
    *,
    telegram_api: TelegramApiCaller,
    chat_id: int,
    message_id: Optional[int],
    text: str,
    reply_markup: Optional[
        Mapping[str, Any]
    ] = None,
) -> bool:
    if not message_id:
        return False

    payload: Dict[str, Any] = {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "text": str(text or ""),
    }

    if reply_markup is not None:
        payload[
            "reply_markup"
        ] = reply_markup

    try:
        response = telegram_api(
            "editMessageText",
            payload,
        )

    except Exception as exc:
        logger.exception(
            "external review control message "
            f"edit failed | {exc}"
        )
        return False

    if _result_ok(response):
        return True

    logger.warning(
        "external review control message edit "
        f"rejected | {str(response)[:300]}"
    )

    return False


# =========================================================
# MEDIA PANEL
# =========================================================


def _download_image(
    *,
    media: ExternalMedia,
    max_bytes: int,
    fetcher: Any = None,
) -> Optional[bytes]:
    source_url = str(
        getattr(
            media,
            "source_url",
            "",
        )
        or ""
    ).strip()

    if not source_url:
        return None

    try:
        if fetcher is not None:
            fetched = fetcher(
                source_url
            )

        else:
            from core.external_fetcher import (
                FetchPolicy,
                SafeExternalFetcher,
            )

            safe_fetcher = SafeExternalFetcher(
                policy=FetchPolicy(
                    max_bytes=int(
                        max_bytes
                    )
                )
            )

            fetched = safe_fetcher.fetch(
                source_url,
                allowed_content_types=(
                    "image/*",
                ),
                max_bytes=int(
                    max_bytes
                ),
            )

    except Exception as exc:
        logger.warning(
            "external review preview media "
            f"fetch failed | {exc}"
        )
        return None

    if isinstance(
        fetched,
        (bytes, bytearray),
    ):
        body = bytes(fetched)

    else:
        body = getattr(
            fetched,
            "content",
            None,
        )

    if not body:
        return None

    return bytes(body)


def send_media_panel(
    *,
    telegram_api: TelegramApiCaller,
    chat_id: int,
    staging_chat_id: str,
    media: Sequence[ExternalMedia],
    staged_file_ids: Sequence[str] = (),
    max_bytes: int = (
        10 * 1024 * 1024
    ),
    fetcher: Any = None,
) -> MediaPanelResult:
    """
    Display the selected external media as one preview panel.

    Photos are fetched safely, staged once through the configured
    staging chat to obtain a reusable file_id, then shown to the
    user as a photo or an album. The staging messages are deleted
    immediately; nothing is published to a destination.

    ``staged_file_ids`` may contain previously staged file_id
    values aligned with ``content.media`` indexes. Media items that
    already have a staged value are re-displayed directly without
    downloading or staging again.

    Returns displayed message ids plus the file_id used per source
    media position. Non-photo media are skipped for display; they
    remain available for publication through the existing
    materializer.
    """

    normalized_staging = str(
        staging_chat_id
        or ""
    ).strip()

    photos = [
        item
        for item in (
            media
            or ()
        )
        if str(
            getattr(
                item,
                "type",
                "",
            )
            or ""
        ).strip().lower()
        in ("photo", "image")
    ]

    if not photos:
        return MediaPanelResult()

    staged_by_index: Dict[int, str] = {}

    for item in photos:
        position = int(
            getattr(
                item,
                "position",
                0,
            )
            or 0
        )

        candidate = ""

        if 0 <= position < len(
            staged_file_ids
        ):
            candidate = str(
                staged_file_ids[position]
                or ""
            ).strip()

        if candidate:
            staged_by_index[position] = candidate

    file_ids = []
    resolved_by_position: Dict[int, str] = {}

    for item in photos[:10]:
        position = int(
            getattr(
                item,
                "position",
                0,
            )
            or 0
        )

        cached = staged_by_index.get(
            position,
            "",
        )

        if cached:
            file_ids.append(cached)
            resolved_by_position[position] = cached
            continue

        if not normalized_staging:
            continue

        content = _download_image(
            media=item,
            max_bytes=max_bytes,
            fetcher=fetcher,
        )

        if not content:
            continue

        try:
            staging_response = telegram_api(
                "sendPhoto",
                {
                    "chat_id": (
                        normalized_staging
                    ),
                    "photo_bytes": content,
                },
            )

        except Exception as exc:
            logger.warning(
                "external review preview media "
                f"staging failed | {exc}"
            )
            continue

        staging_result = _result_payload(
            staging_response
        )

        file_id = (
            _photo_file_id_from_result(
                staging_result
            )
        )

        staging_message_id = (
            _message_id_from_result(
                staging_result
            )
        )

        if staging_message_id:
            try:
                telegram_api(
                    "deleteMessage",
                    {
                        "chat_id": (
                            normalized_staging
                        ),
                        "message_id": (
                            staging_message_id
                        ),
                    },
                )

            except Exception:
                logger.warning(
                    "external review preview staging "
                    "cleanup failed"
                )

        if file_id:
            file_ids.append(
                file_id
            )
            resolved_by_position[position] = file_id

    if not file_ids:
        return MediaPanelResult(
            file_ids_by_position=(
                resolved_by_position
            ),
        )

    try:
        if len(file_ids) == 1:
            response = telegram_api(
                "sendPhoto",
                {
                    "chat_id": int(chat_id),
                    "photo": file_ids[0],
                },
            )

            result = _result_payload(
                response
            )

            message_id = (
                _message_id_from_result(
                    result
                )
            )

            return MediaPanelResult(
                message_ids=(
                    (message_id,)
                    if message_id
                    else ()
                ),
                file_ids_by_position=(
                    resolved_by_position
                ),
            )

        group_media = [
            {
                "type": "photo",
                "media": file_id,
            }
            for file_id in file_ids[:10]
        ]

        response = telegram_api(
            "sendMediaGroup",
            {
                "chat_id": int(chat_id),
                "media": group_media,
            },
        )

        result = response.get(
            "result"
        )

        message_ids = []

        if isinstance(result, list):
            for item in result:
                if not isinstance(
                    item,
                    Mapping,
                ):
                    continue

                message_id = (
                    _message_id_from_result(
                        item
                    )
                )

                if message_id:
                    message_ids.append(
                        message_id
                    )

        return MediaPanelResult(
            message_ids=tuple(
                message_ids
            ),
            file_ids_by_position=(
                resolved_by_position
            ),
        )

    except Exception as exc:
        logger.exception(
            "external review preview media panel "
            f"send failed | {exc}"
        )
        return MediaPanelResult(
            file_ids_by_position=(
                resolved_by_position
            ),
        )


def delete_media_panel(
    *,
    telegram_api: TelegramApiCaller,
    chat_id: int,
    message_ids: Sequence[int],
) -> None:
    for message_id in (
        message_ids
        or ()
    ):
        try:
            telegram_api(
                "deleteMessage",
                {
                    "chat_id": int(chat_id),
                    "message_id": int(
                        message_id
                    ),
                },
            )

        except Exception:
            logger.warning(
                "external review preview media panel "
                f"delete failed | message_id={message_id}"
            )


def reconcile_media_panel(
    *,
    telegram_api: TelegramApiCaller,
    chat_id: int,
    staging_chat_id: str,
    media: Sequence[ExternalMedia],
    current_message_ids: Sequence[int],
    staged_file_ids: Sequence[str] = (),
    max_bytes: int = (
        10 * 1024 * 1024
    ),
    fetcher: Any = None,
) -> MediaPanelResult:
    """
    Bring the displayed media panel in line with the selected media.

    The panel is rebuilt only when the visible set actually changed;
    callers pass the desired media and the currently displayed
    message ids. Deleting first keeps ordering stable: the control
    message always stays the last message in the chat.

    Previously staged file_id values are reused so unchanged media
    are not downloaded or staged again.
    """

    if not tuple(
        media
        or ()
    ):
        if current_message_ids:
            delete_media_panel(
                telegram_api=telegram_api,
                chat_id=chat_id,
                message_ids=(
                    current_message_ids
                ),
            )

        return MediaPanelResult()

    if current_message_ids:
        delete_media_panel(
            telegram_api=telegram_api,
            chat_id=chat_id,
            message_ids=(
                current_message_ids
            ),
        )

    return send_media_panel(
        telegram_api=telegram_api,
        chat_id=chat_id,
        staging_chat_id=staging_chat_id,
        media=media,
        staged_file_ids=staged_file_ids,
        max_bytes=max_bytes,
        fetcher=fetcher,
    )
