"""Telegram staging transport for external media materialization."""

from __future__ import annotations

import mimetypes
import os
import re

from typing import (
    Any,
    Dict,
    Optional,
)
from urllib.parse import urlsplit

import requests

from core.external_media_materializer import (
    AcquiredExternalMedia,
    ExternalMediaUploadError,
    MaterializedExternalMedia,
)


# =========================================================
# CONFIG
# =========================================================


EXTERNAL_MEDIA_STAGING_CHAT_ENV = (
    "EXTERNAL_MEDIA_STAGING_CHAT_ID"
)


# =========================================================
# HELPERS
# =========================================================


def _safe_filename(
    media: AcquiredExternalMedia,
) -> str:
    """
    Build a harmless filename for multipart upload.

    The external URL never becomes a local filesystem path.
    """

    parsed = urlsplit(
        media.final_url
        or media.source_url
        or ""
    )

    basename = os.path.basename(
        parsed.path
        or ""
    ).strip()

    basename = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        basename,
    ).strip(
        "._"
    )

    if basename:
        return basename[:120]

    extension = (
        mimetypes.guess_extension(
            media.mime_type
            or ""
        )
        or ""
    )

    if media.type == "photo":
        base = "external_image"

    elif media.type == "video":
        base = "external_video"

    elif media.type == "audio":
        base = "external_audio"

    else:
        base = "external_document"

    return (
        f"{base}{extension}"
    )


def _telegram_method(
    media_type: str,
) -> tuple[str, str]:
    normalized = str(
        media_type
        or ""
    ).strip().lower()

    if normalized == "photo":
        return (
            "sendPhoto",
            "photo",
        )

    if normalized == "video":
        return (
            "sendVideo",
            "video",
        )

    if normalized == "audio":
        return (
            "sendAudio",
            "audio",
        )

    if normalized == "document":
        return (
            "sendDocument",
            "document",
        )

    raise ExternalMediaUploadError(
        f"unsupported Telegram staging media type: {normalized}"
    )


def _extract_file_id(
    *,
    media_type: str,
    result: Dict[str, Any],
) -> str:
    """
    Extract the reusable Telegram file_id from the staging message.
    """

    if media_type == "photo":
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
                dict,
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

    payload = result.get(
        media_type
    )

    if not isinstance(
        payload,
        dict,
    ):
        return ""

    return str(
        payload.get(
            "file_id"
        )
        or ""
    ).strip()


# =========================================================
# TELEGRAM TRANSPORT MATERIALIZER
# =========================================================


class TelegramExternalMediaMaterializer:
    """
    Materialize external media into reusable Telegram file_id values.

    Media bytes are uploaded to a controlled staging chat. The resulting
    staging message is deleted after the file_id is captured.

    No destination publication happens here.
    """

    name = "telegram_staging"

    def __init__(
        self,
        *,
        api_url: str,
        staging_chat_id: Optional[
            str
        ] = None,
        timeout_seconds: int = 300,
        session: Any = None,
    ) -> None:
        normalized_api_url = str(
            api_url
            or ""
        ).strip().rstrip(
            "/"
        )

        if not normalized_api_url:
            raise ValueError(
                "api_url is required"
            )

        configured_chat = (
            staging_chat_id
            if staging_chat_id is not None
            else os.getenv(
                EXTERNAL_MEDIA_STAGING_CHAT_ENV,
                "",
            )
        )

        normalized_chat = str(
            configured_chat
            or ""
        ).strip()

        if not normalized_chat:
            raise ValueError(
                "external media staging chat is not configured"
            )

        timeout = int(
            timeout_seconds
        )

        if timeout <= 0:
            raise ValueError(
                "timeout_seconds must be > 0"
            )

        self.api_url = (
            normalized_api_url
        )

        self.staging_chat_id = (
            normalized_chat
        )

        self.timeout_seconds = timeout

        self.session = (
            session
            or requests
        )

    # -----------------------------------------------------
    # SUPPORT
    # -----------------------------------------------------

    def supports(
        self,
        media: AcquiredExternalMedia,
    ) -> bool:
        if not isinstance(
            media,
            AcquiredExternalMedia,
        ):
            return False

        return (
            media.type
            in {
                "photo",
                "video",
                "audio",
                "document",
            }
            and bool(
                media.content
            )
        )

    # -----------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------

    def _delete_staging_message(
        self,
        message_id: Any,
    ) -> None:
        """
        Best-effort cleanup.

        Cleanup failure must not invalidate a file_id that was already
        successfully materialized.
        """

        if message_id is None:
            return

        try:
            self.session.post(
                (
                    f"{self.api_url}"
                    "/deleteMessage"
                ),
                json={
                    "chat_id": (
                        self.staging_chat_id
                    ),
                    "message_id": (
                        message_id
                    ),
                },
                timeout=30,
            )

        except Exception:
            # Staging cleanup is intentionally non-fatal.
            pass

    # -----------------------------------------------------
    # MATERIALIZE
    # -----------------------------------------------------

    def materialize(
        self,
        media: AcquiredExternalMedia,
    ) -> MaterializedExternalMedia:
        if not isinstance(
            media,
            AcquiredExternalMedia,
        ):
            raise TypeError(
                "media must be AcquiredExternalMedia"
            )

        if not self.supports(
            media
        ):
            raise ExternalMediaUploadError(
                "Telegram staging does not support this media"
            )

        method, field = (
            _telegram_method(
                media.type
            )
        )

        filename = _safe_filename(
            media
        )

        request_url = (
            f"{self.api_url}/{method}"
        )

        data = {
            "chat_id": (
                self.staging_chat_id
            )
        }

        file_tuple = (
            filename,
            media.content,
        )

        if media.mime_type:
            file_tuple = (
                filename,
                media.content,
                media.mime_type,
            )

        files = {
            field: file_tuple
        }

        try:
            response = (
                self.session.post(
                    request_url,
                    data=data,
                    files=files,
                    timeout=(
                        self.timeout_seconds
                    ),
                )
            )

        except Exception as exc:
            raise ExternalMediaUploadError(
                "Telegram staging upload failed"
            ) from exc

        try:
            payload = (
                response.json()
                or {}
            )

        except Exception as exc:
            raise ExternalMediaUploadError(
                "Telegram staging returned invalid JSON"
            ) from exc

        if (
            response.status_code
            != 200
            or not payload.get(
                "ok"
            )
        ):
            raise ExternalMediaUploadError(
                (
                    "Telegram staging rejected media "
                    f"with status={response.status_code}"
                )
            )

        result = payload.get(
            "result"
        )

        if not isinstance(
            result,
            dict,
        ):
            raise ExternalMediaUploadError(
                "Telegram staging returned no message result"
            )

        message_id = (
            result.get(
                "message_id"
            )
        )

        file_id = (
            _extract_file_id(
                media_type=media.type,
                result=result,
            )
        )

        if not file_id:
            raise ExternalMediaUploadError(
                "Telegram staging returned no reusable file_id"
            )

        self._delete_staging_message(
            message_id
        )

        return MaterializedExternalMedia(
            type=media.type,
            file_id=file_id,
            position=media.position,
            presentation=(
                media.presentation
            ),
            source_url=(
                media.source_url
            ),
            metadata={
                "transport": (
                    self.name
                ),
                "telegram_staging_message_id": (
                    message_id
                ),
                "mime_type": (
                    media.mime_type
                ),
                "final_url": (
                    media.final_url
                ),
                "source_metadata": dict(
                    media.metadata
                    or {}
                ),
            },
        )
