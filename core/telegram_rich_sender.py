"""
Telegram Rich Message sender.

Purpose:
    Convert normalized shared media content into Telegram
    Rich Message presentation when explicitly requested by
    PreparedContent.media_presentation.

Architecture:
    PreparedContent
        -> Shared Publication Engine
        -> Telegram executor
        -> telegram_rich_sender.py
        -> sendRichMessage

IMPORTANT:
    This module is Telegram-output-specific.

    It must NOT:
        - perform source cleanup
        - apply branding
        - run editorial review
        - run smart summary
        - perform duplicate detection
        - resolve destinations
        - modify Bale behavior

    It only converts already-prepared Telegram destination
    content into an InputRichMessage payload and sends it.
"""

import logging

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)

from core.content_model import ExecutorResult


logger = logging.getLogger(__name__)


# =========================================================
# SUPPORTED PRESENTATIONS
# =========================================================

SUPPORTED_RICH_PRESENTATIONS = {
    "slideshow",
    "collage",
}


# =========================================================
# SUPPORTED MEDIA TYPES
# =========================================================
#
# Telegram Bot API 10.3 InputRichBlock media types.
#
# Incoming normalized files use:
#
# {
#     "type": "photo",
#     "file_id": "..."
# }
#
# =========================================================

SUPPORTED_RICH_MEDIA_TYPES = {
    "animation",
    "audio",
    "document",
    "photo",
    "video",
    "voice_note",
}


# =========================================================
# MEDIA FIELD MAPPING
# =========================================================

RICH_MEDIA_FIELD_BY_TYPE = {
    "animation": "animation",
    "audio": "audio",
    "document": "document",
    "photo": "photo",
    "video": "video",
    "voice_note": "voice_note",
}


# =========================================================
# INPUT MEDIA TYPE MAPPING
# =========================================================

INPUT_MEDIA_TYPE_BY_RICH_TYPE = {
    "animation": "animation",
    "audio": "audio",
    "document": "document",
    "photo": "photo",
    "video": "video",
    "voice_note": "voice_note",
}


# =========================================================
# NORMALIZE PRESENTATION
# =========================================================

def normalize_media_presentation(
    presentation: Optional[str]
) -> str:
    """
    Normalize and validate semantic media presentation.

    Returns:
        "slideshow"
        "collage"
        ""

    Unknown presentation values are rejected safely by
    returning an empty string.
    """

    value = (
        str(
            presentation
            or ""
        )
        .strip()
        .lower()
    )

    if value in SUPPORTED_RICH_PRESENTATIONS:
        return value

    return ""


# =========================================================
# BUILD INPUT MEDIA
# =========================================================

def build_input_media(
    media_type: str,
    file_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Build Telegram InputMedia object using an existing file_id.

    Rich Message media blocks accept the normal InputMedia
    family such as InputMediaPhoto and InputMediaVideo.
    """

    normalized_type = (
        str(
            media_type
            or ""
        )
        .strip()
        .lower()
    )

    normalized_file_id = (
        str(
            file_id
            or ""
        )
        .strip()
    )

    if (
        not normalized_type
        or normalized_type
        not in SUPPORTED_RICH_MEDIA_TYPES
    ):

        logger.warning(
            "⚠️ Unsupported Telegram Rich media type | "
            f"type={normalized_type or '-'}"
        )

        return None

    if not normalized_file_id:

        logger.warning(
            "⚠️ Telegram Rich media has empty file_id | "
            f"type={normalized_type}"
        )

        return None

    input_media_type = (
        INPUT_MEDIA_TYPE_BY_RICH_TYPE[
            normalized_type
        ]
    )

    return {
        "type": input_media_type,
        "media": normalized_file_id,
    }


# =========================================================
# BUILD MEDIA BLOCK
# =========================================================

def build_media_block(
    file: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Convert one normalized shared media item into one
    Telegram InputRichBlock media block.
    """

    if not isinstance(
        file,
        dict
    ):

        logger.warning(
            "⚠️ Invalid Telegram Rich media item | "
            f"type={type(file).__name__}"
        )

        return None

    media_type = (
        str(
            file.get(
                "type",
                ""
            )
            or ""
        )
        .strip()
        .lower()
    )

    file_id = (
        str(
            file.get(
                "file_id",
                ""
            )
            or ""
        )
        .strip()
    )

    if (
        media_type
        not in SUPPORTED_RICH_MEDIA_TYPES
    ):

        logger.warning(
            "⚠️ Unsupported Telegram Rich block media | "
            f"type={media_type or '-'}"
        )

        return None

    input_media = (
        build_input_media(
            media_type,
            file_id,
        )
    )

    if input_media is None:
        return None

    media_field = (
        RICH_MEDIA_FIELD_BY_TYPE[
            media_type
        ]
    )

    return {
        "type": media_type,
        media_field: input_media,
    }


# =========================================================
# BUILD PRESENTATION BLOCK
# =========================================================

def build_presentation_block(
    files: List[Dict[str, Any]],
    presentation: str,
    caption: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Build InputRichBlockSlideshow or InputRichBlockCollage.

    The destination-formatted caption is attached to the
    presentation block as RichBlockCaption.
    """

    normalized_presentation = (
        normalize_media_presentation(
            presentation
        )
    )

    if not normalized_presentation:

        logger.warning(
            "⚠️ Telegram Rich presentation unsupported | "
            f"presentation={presentation or '-'}"
        )

        return None

    media_blocks: List[
        Dict[str, Any]
    ] = []

    for file in list(
        files
        or []
    ):

        block = (
            build_media_block(
                file
            )
        )

        if block is not None:

            media_blocks.append(
                block
            )

    if not media_blocks:

        logger.error(
            "❌ Telegram Rich presentation has no "
            "supported media blocks"
        )

        return None

    presentation_block: Dict[
        str,
        Any
    ] = {
        "type":
            normalized_presentation,

        "blocks":
            media_blocks,
    }

    normalized_caption = (
        str(
            caption
            or ""
        )
        .strip()
    )

    if normalized_caption:

        presentation_block[
            "caption"
        ] = {
            "text":
                normalized_caption
        }

    return presentation_block


# =========================================================
# BUILD INPUT RICH MESSAGE
# =========================================================

def build_input_rich_message(
    files: List[Dict[str, Any]],
    presentation: str,
    caption: str = "",
    is_rtl: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build Telegram InputRichMessage using explicit blocks.

    Exactly one InputRichMessage representation is used:
        blocks
    """

    presentation_block = (
        build_presentation_block(
            files=files,
            presentation=presentation,
            caption=caption,
        )
    )

    if presentation_block is None:
        return None

    rich_message: Dict[
        str,
        Any
    ] = {
        "blocks": [
            presentation_block
        ]
    }

    if is_rtl is not None:

        rich_message[
            "is_rtl"
        ] = bool(
            is_rtl
        )

    return rich_message


# =========================================================
# RESPONSE JSON
# =========================================================

def _response_json(
    response: Any
) -> Dict[str, Any]:

    if response is None:
        return {}

    try:

        payload = (
            response.json()
        )

        if isinstance(
            payload,
            dict
        ):

            return payload

    except Exception:

        pass

    return {}


# =========================================================
# EXTRACT TELEGRAM ERROR
# =========================================================

def _extract_error(
    response: Any,
    payload: Dict[str, Any],
) -> Tuple[
    Optional[int],
    Optional[int],
    str,
]:

    status_code = None

    if response is not None:

        try:

            status_code = int(
                response.status_code
            )

        except Exception:

            status_code = None

    error_code = (
        payload.get(
            "error_code"
        )
        if isinstance(
            payload,
            dict
        )
        else None
    )

    try:

        if error_code is not None:

            error_code = int(
                error_code
            )

    except Exception:

        error_code = None

    description = ""

    if isinstance(
        payload,
        dict
    ):

        description = (
            str(
                payload.get(
                    "description",
                    ""
                )
                or ""
            )
        )

    if (
        not description
        and response is None
    ):

        description = (
            "Telegram sendRichMessage "
            "returned no response"
        )

    elif (
        not description
        and status_code is not None
    ):

        description = (
            f"Telegram sendRichMessage "
            f"HTTP {status_code}"
        )

    return (
        status_code,
        error_code,
        description,
    )


# =========================================================
# SEND TELEGRAM RICH MEDIA
# =========================================================

def send_rich_media_to_channel(
    files: List[Dict[str, Any]],
    presentation: str,
    caption: str = "",
    channel_id: Optional[str] = None,
    api_url: Optional[str] = None,
    is_rtl: Optional[bool] = None,
) -> ExecutorResult:
    """
    Send slideshow/collage using Telegram sendRichMessage.

    This function performs exactly one outbound Telegram API
    request.

    IMPORTANT:
        No automatic sendMediaGroup fallback happens here.

    Reason:
        A transport timeout may occur after Telegram has
        already accepted the Rich Message. Automatically
        sending a normal album afterward could duplicate the
        publication.

    Controlled fallback, if required, belongs to the shared
    executor/idempotency layer where delivery state is known.
    """

    normalized_presentation = (
        normalize_media_presentation(
            presentation
        )
    )

    if not normalized_presentation:

        return ExecutorResult(
            success=False,
            error=(
                "unsupported rich media presentation"
            ),
            operation=(
                "sendRichMessage"
            ),
        )

    if not files:

        return ExecutorResult(
            success=False,
            error=(
                "rich media files are empty"
            ),
            operation=(
                "sendRichMessage"
            ),
        )

    rich_message = (
        build_input_rich_message(
            files=list(
                files
                or []
            ),
            presentation=(
                normalized_presentation
            ),
            caption=caption,
            is_rtl=is_rtl,
        )
    )

    if rich_message is None:

        return ExecutorResult(
            success=False,
            error=(
                "unable to build rich message payload"
            ),
            operation=(
                "sendRichMessage"
            ),
        )

    try:

        from core import (
            media_handler
        )

        effective_channel_id = (
            channel_id
            or getattr(
                media_handler,
                "CHANNEL_ID",
                None
            )
        )

        if not effective_channel_id:

            logger.error(
                "❌ Telegram Rich destination "
                "channel_id is not configured"
            )

            return ExecutorResult(
                success=False,
                error=(
                    "telegram destination "
                    "channel_id is not configured"
                ),
                operation=(
                    "sendRichMessage"
                ),
            )

        payload = {
            "chat_id":
                effective_channel_id,

            "rich_message":
                rich_message,
        }

        logger.info(
            "🖼️ Telegram Rich Message send | "
            f"presentation="
            f"{normalized_presentation} | "
            f"media={len(files)} | "
            f"caption_length="
            f"{len(caption or '')}"
        )

        response = (
            media_handler.telegram_post(
                "sendRichMessage",
                payload,
                api_url=api_url,
            )
        )

        response_payload = (
            _response_json(
                response
            )
        )

        ok = bool(
            response_payload.get(
                "ok"
            )
        )

        if ok:

            result = (
                response_payload.get(
                    "result"
                )
                or {}
            )

            message_id = None

            if isinstance(
                result,
                dict
            ):

                raw_message_id = (
                    result.get(
                        "message_id"
                    )
                )

                try:

                    if raw_message_id is not None:

                        message_id = int(
                            raw_message_id
                        )

                except Exception:

                    message_id = None

            logger.info(
                "✅ Telegram Rich Message sent | "
                f"presentation="
                f"{normalized_presentation} | "
                f"message_id="
                f"{message_id or '-'}"
            )

            return ExecutorResult(
                success=True,
                primary_message_id=(
                    message_id
                ),
                message_ids=(
                    (message_id,)
                    if message_id is not None
                    else ()
                ),
                status_code=(
                    getattr(
                        response,
                        "status_code",
                        None
                    )
                    if response is not None
                    else None
                ),
                raw_result=(
                    result
                ),
                operation=(
                    "sendRichMessage"
                ),
            )

        (
            status_code,
            error_code,
            error_message,
        ) = (
            _extract_error(
                response,
                response_payload,
            )
        )

        logger.error(
            "❌ Telegram Rich Message failed | "
            f"presentation="
            f"{normalized_presentation} | "
            f"status="
            f"{status_code or '-'} | "
            f"error_code="
            f"{error_code or '-'} | "
            f"error="
            f"{error_message or '-'}"
        )

        return ExecutorResult(
            success=False,
            status_code=(
                status_code
            ),
            error=(
                error_message
            ),
            raw_result=(
                response_payload
            ),
            error_code=(
                error_code
            ),
            operation=(
                "sendRichMessage"
            ),
        )

    except Exception as e:

        logger.exception(
            "❌ Telegram Rich Message exception | "
            f"presentation="
            f"{normalized_presentation} | "
            f"{e}"
        )

        return ExecutorResult(
            success=False,
            error=str(
                e
            ),
            operation=(
                "sendRichMessage"
            ),
        )
