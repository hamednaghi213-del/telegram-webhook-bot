import logging
import os
import uuid
import secrets
import requests

from typing import (
    Dict,
    Tuple,
    Optional,
    Any,
    List
)

from flask import request


logger = logging.getLogger(__name__)


# =========================================================
# GLOBAL CONFIG
# =========================================================

API_URL: Optional[str] = None
CHANNEL_ID: Optional[str] = None
SECRET_TOKEN: Optional[str] = None

WEBHOOK_INITIALIZED: bool = False


# =========================================================
# EDITORIAL REVIEW CONFIG
# =========================================================

EDITORIAL_REVIEW_ENV = (
    "ENABLE_EDITORIAL_REVIEW"
)


def editorial_review_enabled() -> bool:

    value = (
        os.getenv(
            EDITORIAL_REVIEW_ENV,
            "false"
        )
        or ""
    )

    return (
        value
        .strip()
        .lower()
        in (
            "1",
            "true",
            "yes",
            "on"
        )
    )


# =========================================================
# INITIALIZE
# =========================================================

def initialize(
    api_url: str,
    channel_id: str,
    secret_token: str
) -> None:

    global API_URL
    global CHANNEL_ID
    global SECRET_TOKEN
    global WEBHOOK_INITIALIZED

    if not api_url:
        raise ValueError(
            "❌ api_url cannot be empty"
        )

    if not channel_id:
        raise ValueError(
            "❌ channel_id cannot be empty"
        )

    if not secret_token:
        raise ValueError(
            "❌ secret_token cannot be empty "
            "(SECURITY REQUIRED)"
        )

    API_URL = api_url.rstrip("/")
    CHANNEL_ID = channel_id
    SECRET_TOKEN = secret_token

    WEBHOOK_INITIALIZED = True

    logger.info(
        f"✅ Webhook Handler initialized | "
        f"channel={CHANNEL_ID} | "
        f"editorial_review="
        f"{editorial_review_enabled()}"
    )


# =========================================================
# VALIDATE SECRET TOKEN
# =========================================================

def validate_webhook_token() -> bool:

    if not WEBHOOK_INITIALIZED:

        logger.error(
            "❌ Webhook Handler not initialized"
        )

        return False

    if not SECRET_TOKEN:

        logger.error(
            "❌ SECRET_TOKEN is not configured"
        )

        return False

    request_token = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    if not request_token:

        logger.warning(
            "⚠️ Missing Telegram webhook secret header"
        )

        return False

    if not secrets.compare_digest(
        request_token,
        SECRET_TOKEN
    ):

        logger.error(
            "❌ Invalid Telegram webhook secret token"
        )

        return False

    return True


# =========================================================
# GET MESSAGE TEXT
# =========================================================

def get_message_text(
    msg: Dict[str, Any]
) -> str:

    caption = msg.get(
        "caption"
    )

    if caption:
        return caption

    text = msg.get(
        "text"
    )

    if text:
        return text

    return ""


# =========================================================
# GET MESSAGE ENTITIES
# =========================================================

def get_message_entities(
    msg: Dict[str, Any]
) -> List[Dict[str, Any]]:

    if msg.get(
        "caption"
    ) is not None:

        return list(
            msg.get(
                "caption_entities",
                []
            )
            or []
        )

    return list(
        msg.get(
            "entities",
            []
        )
        or []
    )


# =========================================================
# FORWARD SOURCE METADATA
# =========================================================

def extract_forward_source_metadata(
    msg: Dict[str, Any]
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "is_forwarded": False,
        "origin_type": "",
        "source_chat_id": None,
        "source_title": "",
        "source_username": "",
        "source_message_id": None,
        "sender_name": ""
    }

    try:

        forward_origin = msg.get(
            "forward_origin"
        )

        if isinstance(
            forward_origin,
            dict
        ):

            result[
                "is_forwarded"
            ] = True

            result[
                "origin_type"
            ] = (
                forward_origin.get(
                    "type",
                    ""
                )
                or ""
            )

            origin_chat = (
                forward_origin.get(
                    "chat"
                )
                or {}
            )

            if isinstance(
                origin_chat,
                dict
            ):

                result[
                    "source_chat_id"
                ] = origin_chat.get(
                    "id"
                )

                result[
                    "source_title"
                ] = (
                    origin_chat.get(
                        "title",
                        ""
                    )
                    or ""
                )

                result[
                    "source_username"
                ] = (
                    origin_chat.get(
                        "username",
                        ""
                    )
                    or ""
                )

            result[
                "source_message_id"
            ] = forward_origin.get(
                "message_id"
            )

            result[
                "sender_name"
            ] = (
                forward_origin.get(
                    "sender_user_name",
                    ""
                )
                or ""
            )

        forward_from_chat = (
            msg.get(
                "forward_from_chat"
            )
            or {}
        )

        if isinstance(
            forward_from_chat,
            dict
        ) and forward_from_chat:

            result[
                "is_forwarded"
            ] = True

            if not result[
                "source_chat_id"
            ]:

                result[
                    "source_chat_id"
                ] = (
                    forward_from_chat.get(
                        "id"
                    )
                )

            if not result[
                "source_title"
            ]:

                result[
                    "source_title"
                ] = (
                    forward_from_chat.get(
                        "title",
                        ""
                    )
                    or ""
                )

            if not result[
                "source_username"
            ]:

                result[
                    "source_username"
                ] = (
                    forward_from_chat.get(
                        "username",
                        ""
                    )
                    or ""
                )

        if not result[
            "source_message_id"
        ]:

            result[
                "source_message_id"
            ] = msg.get(
                "forward_from_message_id"
            )

        if (
            not result[
                "sender_name"
            ]
            and msg.get(
                "forward_sender_name"
            )
        ):

            result[
                "sender_name"
            ] = (
                msg.get(
                    "forward_sender_name"
                )
                or ""
            )

        return result

    except Exception as e:

        logger.exception(
            f"❌ Forward source extraction failed | "
            f"{e}"
        )

        return result


# =========================================================
# MESSAGE DIAGNOSTICS
# =========================================================

def log_message_diagnostics(
    req_id: str,
    msg: Dict[str, Any]
) -> None:

    try:

        raw_text = (
            msg.get(
                "text",
                ""
            )
            or ""
        )

        raw_caption = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        entities = list(
            msg.get(
                "entities",
                []
            )
            or []
        )

        caption_entities = list(
            msg.get(
                "caption_entities",
                []
            )
            or []
        )

        forward_info = (
            extract_forward_source_metadata(
                msg
            )
        )

        logger.info(
            f"[{req_id}] 🔬 MESSAGE-DIAGNOSTIC | "
            f"has_text={bool(raw_text)} | "
            f"text_length={len(raw_text)} | "
            f"has_caption={bool(raw_caption)} | "
            f"caption_length={len(raw_caption)} | "
            f"media_group_id="
            f"{msg.get('media_group_id') or '-'}"
        )

        logger.info(
            f"[{req_id}] 🔬 ENTITY-DIAGNOSTIC | "
            f"entities={len(entities)} | "
            f"caption_entities="
            f"{len(caption_entities)}"
        )

        if caption_entities:

            types = [
                str(
                    entity.get(
                        "type",
                        ""
                    )
                )
                for entity
                in caption_entities
            ]

            logger.info(
                f"[{req_id}] 🔬 CAPTION-ENTITY-TYPES | "
                f"{types}"
            )

        logger.info(
            f"[{req_id}] 🔬 FORWARD-DIAGNOSTIC | "
            f"is_forwarded="
            f"{forward_info.get('is_forwarded')} | "
            f"origin_type="
            f"{forward_info.get('origin_type') or '-'} | "
            f"source_chat_id="
            f"{forward_info.get('source_chat_id') or '-'} | "
            f"source_title="
            f"{forward_info.get('source_title') or '-'} | "
            f"source_username="
            f"{forward_info.get('source_username') or '-'} | "
            f"source_message_id="
            f"{forward_info.get('source_message_id') or '-'}"
        )

        if raw_caption:

            logger.info(
                f"[{req_id}] 🔬 CAPTION-TAIL | "
                f"{raw_caption[-500:]!r}"
            )

        elif raw_text:

            logger.info(
                f"[{req_id}] 🔬 TEXT-TAIL | "
                f"{raw_text[-500:]!r}"
            )

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Diagnostic error | "
            f"{e}"
        )


# =========================================================
# GET MEDIA
# =========================================================

def get_media_from_message(
    msg: Dict[str, Any]
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "type": None,
        "file_id": None,
        "caption": ""
    }

    if "video" in msg:

        result["type"] = "video"

        result["file_id"] = (
            msg["video"].get(
                "file_id"
            )
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    if "photo" in msg:

        photos = (
            msg.get(
                "photo",
                []
            )
            or []
        )

        if photos:

            result["type"] = "photo"

            result["file_id"] = (
                photos[-1].get(
                    "file_id"
                )
            )

            result["caption"] = (
                msg.get(
                    "caption",
                    ""
                )
                or ""
            )

        return result

    if "document" in msg:

        result["type"] = "document"

        result["file_id"] = (
            msg["document"].get(
                "file_id"
            )
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    if "voice" in msg:

        result["type"] = "voice"

        result["file_id"] = (
            msg["voice"].get(
                "file_id"
            )
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    if "audio" in msg:

        result["type"] = "audio"

        result["file_id"] = (
            msg["audio"].get(
                "file_id"
            )
        )

        result["caption"] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    return result


# =========================================================
# SEND MESSAGE TO USER
# =========================================================

def send_message(
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[
        Dict[str, Any]
    ] = None
) -> bool:

    if not API_URL:

        logger.error(
            "❌ API_URL not configured"
        )

        return False

    try:

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text
        }

        if parse_mode:

            payload[
                "parse_mode"
            ] = parse_mode

        if reply_markup:

            payload[
                "reply_markup"
            ] = reply_markup

        response = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            return True

        logger.error(
            f"❌ User message failed | "
            f"status={response.status_code} | "
            f"response={response.text[:500]}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ send_message failed | "
            f"{e}"
        )

        return False


# =========================================================
# ANSWER CALLBACK QUERY
# =========================================================

def answer_callback_query(
    callback_query_id: str,
    text: str = ""
) -> bool:

    if not API_URL:
        return False

    if not callback_query_id:
        return False

    try:

        payload: Dict[str, Any] = {
            "callback_query_id":
                callback_query_id
        }

        if text:

            payload[
                "text"
            ] = text

        response = requests.post(
            f"{API_URL}/answerCallbackQuery",
            json=payload,
            timeout=30
        )

        return (
            response.status_code
            == 200
        )

    except Exception as e:

        logger.exception(
            f"❌ answer_callback_query failed | "
            f"{e}"
        )

        return False


# =========================================================
# SEND TEXT TO CHANNEL
# =========================================================

def send_to_channel(
    text: str,
    parse_mode: Optional[str] = None
) -> bool:

    if not API_URL or not CHANNEL_ID:

        logger.error(
            "❌ API_URL or CHANNEL_ID not configured"
        )

        return False

    if not text:
        return False

    try:

        payload: Dict[str, Any] = {
            "chat_id": CHANNEL_ID,
            "text": text
        }

        if parse_mode:

            payload[
                "parse_mode"
            ] = parse_mode

        response = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            return True

        logger.error(
            f"❌ send_to_channel failed | "
            f"status={response.status_code} | "
            f"response={response.text[:1000]}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ send_to_channel exception | "
            f"{e}"
        )

        return False


# =========================================================
# BRANDING
# =========================================================

def build_branding_for_user(
    user_id: int
) -> str:

    try:

        from core.branding_manager import (
            get_branding
        )

        branding = (
            get_branding(
                user_id
            )
            or {}
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

        return "\n".join(
            parts
        )

    except Exception as e:

        logger.exception(
            f"❌ Branding failed | "
            f"user={user_id} | "
            f"{e}"
        )

        return ""


# =========================================================
# FORMAT WITH OPTIONAL SOURCE
# =========================================================

def format_with_source(
    text: str,
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> str:

    from core.formatter import (
        format_news
    )

    source = (
        forward_source
        or {}
    )

    source_title = (
        source.get(
            "source_title",
            ""
        )
        or ""
    )

    source_username = (
        source.get(
            "source_username",
            ""
        )
        or ""
    )

    if (
        source.get(
            "is_forwarded"
        )
        and (
            source_title
            or source_username
        )
    ):

        logger.info(
            f"🧹 SOURCE-FORMAT | "
            f"title={source_title or '-'} | "
            f"username={source_username or '-'}"
        )

        return (
            format_news(
                text,
                source_title=source_title,
                source_username=source_username
            )
        )

    return format_news(
        text
    )


# =========================================================
# EDITORIAL DISPLAY HELPER
# =========================================================

def build_editorial_display(
    title: str = "",
    author: str = "",
    body: str = ""
) -> str:

    try:

        from core.editorial_structure import (
            rebuild_editorial_display_text
        )

        return (
            rebuild_editorial_display_text(
                title=title,
                author=author,
                body=body
            )
        )

    except Exception as e:

        logger.exception(
            f"❌ Editorial display build failed | "
            f"{e}"
        )

        parts: List[str] = []

        title = str(
            title
            or ""
        ).strip()

        author = str(
            author
            or ""
        ).strip()

        body = str(
            body
            or ""
        ).strip()

        if title:

            parts.append(
                f"📝 {title}"
            )

        if author:

            parts.append(
                f"✍️ {author}"
            )

        if body:

            if parts:

                return (
                    "\n".join(
                        parts
                    )
                    + "\n\n"
                    + body
                )

            return body

        return "\n".join(
            parts
        )


# =========================================================
# PUBLISH PREPARED TEXT
# =========================================================

def publish_prepared_text(
    chat_id: int,
    main_text: str,
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    other_entities: Optional[
        List[Dict[str, Any]]
    ] = None
) -> bool:

    try:

        from core.caption_manager import (
            analyze_content
        )

        from core.bale_forwarder import (
            send_to_bale_for_user
        )

        blockquote_blocks = list(
            blockquote_blocks
            or []
        )

        expandable_blocks = list(
            expandable_blocks
            or []
        )

        other_entities = list(
            other_entities
            or []
        )

        branding = (
            build_branding_for_user(
                chat_id
            )
        )

        publication_plan = (
            analyze_content(
                main_text=main_text,
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
            publication_plan.text[
                "telegram"
            ]
        )

        bale_plan = (
            publication_plan.text[
                "bale"
            ]
        )

        telegram_messages = list(
            telegram_plan.get(
                "messages",
                []
            )
            or []
        )

        telegram_blockquotes = list(
            telegram_plan.get(
                "blockquote_messages",
                []
            )
            or []
        )

        for message in telegram_messages:

            if not message:
                continue

            if not send_to_channel(
                message
            ):

                logger.error(
                    "❌ Telegram prepared text "
                    "main message failed"
                )

                return False

        for blockquote_message in (
            telegram_blockquotes
        ):

            if not blockquote_message:
                continue

            if not send_to_channel(
                blockquote_message,
                parse_mode="HTML"
            ):

                logger.error(
                    "❌ Telegram prepared text "
                    "blockquote failed"
                )

                return False

        bale_messages = list(
            bale_plan.get(
                "messages",
                []
            )
            or []
        )

        bale_blockquotes = list(
            bale_plan.get(
                "blockquote_messages",
                []
            )
            or []
        )

        for message in bale_messages:

            if not message:
                continue

            try:

                bale_success = (
                    send_to_bale_for_user(
                        chat_id,
                        message
                    )
                )

                if bale_success is False:

                    logger.warning(
                        "⚠️ Bale prepared text "
                        "main message failed"
                    )

            except Exception as e:

                logger.warning(
                    f"⚠️ Bale prepared text "
                    f"main exception | {e}"
                )

        for blockquote_message in (
            bale_blockquotes
        ):

            if not blockquote_message:
                continue

            try:

                bale_success = (
                    send_to_bale_for_user(
                        chat_id,
                        blockquote_message
                    )
                )

                if bale_success is False:

                    logger.warning(
                        "⚠️ Bale prepared text "
                        "blockquote failed"
                    )

            except Exception as e:

                logger.warning(
                    f"⚠️ Bale prepared text "
                    f"blockquote exception | {e}"
                )

        return True

    except Exception as e:

        logger.exception(
            f"❌ publish_prepared_text failed | "
            f"{e}"
        )

        return False


# =========================================================
# PROCESS SINGLE PHOTO / VIDEO
# =========================================================

def process_single_photo_video(
    chat_id: int,
    file_id: str,
    media_type: str,
    caption: str,
    caption_entities: List[
        Dict[str, Any]
    ],
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> bool:

    try:

        from core.content_entities import (
            parse_telegram_entities
        )

        from core.caption_manager import (
            analyze_content
        )

        from core.media_handler import (
            execute_telegram_plan,
            execute_bale_plan
        )

        parsed = (
            parse_telegram_entities(
                caption or "",
                caption_entities or []
            )
        )

        main_text = (
            parsed.get(
                "main_text",
                ""
            )
            or ""
        )

        blockquote_blocks = list(
            parsed.get(
                "blockquote_blocks",
                []
            )
            or []
        )

        expandable_blocks = list(
            parsed.get(
                "expandable_blocks",
                []
            )
            or []
        )

        other_entities = list(
            parsed.get(
                "other_entities",
                []
            )
            or []
        )

        logger.info(
            f"🔬 SINGLE-MEDIA-PRE-FORMAT | "
            f"raw_caption_length={len(caption or '')} | "
            f"main_text_length={len(main_text)} | "
            f"blockquote={len(blockquote_blocks)} | "
            f"expandable={len(expandable_blocks)} | "
            f"other_entities={len(other_entities)}"
        )

        formatted_main_text = ""

        if main_text:

            try:

                formatted_main_text = (
                    format_with_source(
                        main_text,
                        forward_source
                    )
                    or main_text
                )

            except Exception as e:

                logger.exception(
                    f"❌ Formatter failed | "
                    f"{e}"
                )

                formatted_main_text = (
                    main_text
                )

        branding = (
            build_branding_for_user(
                chat_id
            )
        )

        publication_plan = (
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

        files = [
            {
                "type": media_type,
                "file_id": file_id
            }
        ]

        telegram_success = (
            execute_telegram_plan(
                files,
                publication_plan.telegram
            )
        )

        if not telegram_success:

            logger.error(
                "❌ Telegram single media failed"
            )

            return False

        bale_success = (
            execute_bale_plan(
                chat_id,
                files,
                publication_plan.bale
            )
        )

        if not bale_success:

            logger.warning(
                "⚠️ Telegram succeeded but Bale failed"
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Single media processing failed | "
            f"{e}"
        )

        return False


# =========================================================
# LEGACY MEDIA
# =========================================================

def process_legacy_single_media(
    chat_id: int,
    file_id: str,
    media_type: str,
    caption: str,
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> bool:

    try:

        from core.media_sender import (
            send_media_to_channel
        )

        from core.bale_forwarder import (
            send_to_bale_for_user
        )

        formatted_caption = ""

        if caption:

            try:

                formatted_caption = (
                    format_with_source(
                        caption,
                        forward_source
                    )
                    or caption
                )

            except Exception:

                formatted_caption = (
                    caption
                )

        branding = (
            build_branding_for_user(
                chat_id
            )
        )

        if branding:

            if formatted_caption:

                formatted_caption = (
                    f"{formatted_caption}\n\n"
                    f"{branding}"
                )

            else:

                formatted_caption = (
                    branding
                )

        success = (
            send_media_to_channel(
                API_URL,
                CHANNEL_ID,
                file_id,
                media_type,
                formatted_caption
            )
        )

        if not success:
            return False

        try:

            send_to_bale_for_user(
                chat_id,
                formatted_caption,
                file_id,
                media_type
            )

        except Exception as e:

            logger.warning(
                f"⚠️ Legacy Bale send failed | "
                f"{e}"
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Legacy media processing failed | "
            f"{e}"
        )

        return False


# =========================================================
# PREPARE TEXT
# =========================================================

def prepare_text_content(
    text: str,
    entities: List[
        Dict[str, Any]
    ],
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> Dict[str, Any]:

    from core.content_entities import (
        parse_telegram_entities
    )

    try:

        parsed = (
            parse_telegram_entities(
                text or "",
                entities or []
            )
        )

    except Exception as e:

        logger.exception(
            f"❌ Text entity parser failed | "
            f"{e}"
        )

        parsed = {
            "main_text": text or "",
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "other_entities": []
        }

    main_text = (
        parsed.get(
            "main_text",
            ""
        )
        or ""
    )

    blockquote_blocks = list(
        parsed.get(
            "blockquote_blocks",
            []
        )
        or []
    )

    expandable_blocks = list(
        parsed.get(
            "expandable_blocks",
            []
        )
        or []
    )

    other_entities = list(
        parsed.get(
            "other_entities",
            []
        )
        or []
    )

    formatted_main_text = ""

    if main_text:

        try:

            formatted_main_text = (
                format_with_source(
                    main_text,
                    forward_source
                )
                or main_text
            )

        except Exception as e:

            logger.exception(
                f"❌ Text formatter failed | "
                f"{e}"
            )

            formatted_main_text = (
                main_text
            )

    return {
        "main_text":
            formatted_main_text,
        "blockquote_blocks":
            blockquote_blocks,
        "expandable_blocks":
            expandable_blocks,
        "other_entities":
            other_entities
    }


# =========================================================
# TEXT MESSAGE
# =========================================================

def process_text_message(
    chat_id: int,
    text: str,
    entities: List[
        Dict[str, Any]
    ],
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> bool:

    try:

        prepared = (
            prepare_text_content(
                text=text,
                entities=entities,
                forward_source=forward_source
            )
        )

        return publish_prepared_text(
            chat_id=chat_id,
            main_text=(
                prepared[
                    "main_text"
                ]
            ),
            blockquote_blocks=(
                prepared[
                    "blockquote_blocks"
                ]
            ),
            expandable_blocks=(
                prepared[
                    "expandable_blocks"
                ]
            ),
            other_entities=(
                prepared[
                    "other_entities"
                ]
            )
        )

    except Exception as e:

        logger.exception(
            f"❌ Text processing failed | "
            f"{e}"
        )

        return False


# =========================================================
# EDITORIAL REVIEW SOURCE
# =========================================================

def build_editorial_source_text(
    prepared: Dict[str, Any]
) -> str:

    parts: List[str] = []

    main_text = (
        prepared.get(
            "main_text",
            ""
        )
        or ""
    )

    if main_text:
        parts.append(
            main_text
        )

    combined_blocks: List[
        Dict[str, Any]
    ] = []

    for block in (
        prepared.get(
            "blockquote_blocks",
            []
        )
        or []
    ):

        value = dict(
            block
        )

        value[
            "_expandable"
        ] = False

        combined_blocks.append(
            value
        )

    for block in (
        prepared.get(
            "expandable_blocks",
            []
        )
        or []
    ):

        value = dict(
            block
        )

        value[
            "_expandable"
        ] = True

        combined_blocks.append(
            value
        )

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    for block in combined_blocks:

        block_text = (
            str(
                block.get(
                    "text",
                    ""
                )
                or ""
            )
            .strip()
        )

        if block_text:
            parts.append(
                block_text
            )

    return "\n\n".join(
        parts
    ).strip()


# =========================================================
# EDITORIAL BUTTONS
#
# FINAL POLICY
#
# منوی تحریریه همیشه پنج ردیف دارد.
#
# اگر خلاصه معتبر باشد:
#
# ✅ انتشار خلاصه
# 📄 انتشار متن اصلی
# 🔄 خلاصه‌سازی دوباره
# ✏️ اصلاح با دستور ادمین
# ❌ لغو
#
# اگر خلاصه معتبر نباشد، گزینه‌های مربوط به
# Summary حذف نمی‌شوند و فقط حالت اطلاع‌رسانی دارند.
# =========================================================

def build_editorial_keyboard(
    review_id: str,
    has_summary: bool = True,
    can_regenerate: bool = True
) -> Dict[str, Any]:

    rows: List[
        List[Dict[str, str]]
    ] = []

    # =====================================================
    # 1. SUMMARY
    # =====================================================

    if has_summary:

        rows.append([
            {
                "text":
                    "✅ انتشار خلاصه",
                "callback_data":
                    f"ed:summary:{review_id}"
            }
        ])

    else:

        rows.append([
            {
                "text":
                    "⚠️ خلاصه آماده نیست",
                "callback_data":
                    f"ed:summary_unavailable:{review_id}"
            }
        ])

    # =====================================================
    # 2. ORIGINAL
    # =====================================================

    rows.append([
        {
            "text":
                "📄 انتشار متن اصلی",
            "callback_data":
                f"ed:original:{review_id}"
        }
    ])

    # =====================================================
    # 3. REGENERATE
    # =====================================================

    if can_regenerate:

        rows.append([
            {
                "text":
                    "🔄 خلاصه‌سازی دوباره",
                "callback_data":
                    f"ed:regen:{review_id}"
            }
        ])

    else:

        rows.append([
            {
                "text":
                    "⛔️ بازنویسی به پایان رسید",
                "callback_data":
                    f"ed:regen_unavailable:{review_id}"
            }
        ])

    # =====================================================
    # 4. ADMIN INSTRUCTION
    # =====================================================

    if has_summary:

        rows.append([
            {
                "text":
                    "✏️ اصلاح با دستور ادمین",
                "callback_data":
                    f"ed:instruction:{review_id}"
            }
        ])

    else:

        rows.append([
            {
                "text":
                    "✏️ اصلاح پس از ساخت خلاصه",
                "callback_data":
                    f"ed:instruction_unavailable:{review_id}"
            }
        ])

    # =====================================================
    # 5. CANCEL
    # =====================================================

    rows.append([
        {
            "text":
                "❌ لغو",
            "callback_data":
                f"ed:cancel:{review_id}"
        }
    ])

    return {
        "inline_keyboard":
            rows
    }


# =========================================================
# CONTENT TYPE LABEL
# =========================================================

def editorial_type_label(
    content_type: str
) -> str:

    if content_type == "opinion_note":
        return "یادداشت"

    if content_type == "news_analysis":
        return "تحلیل خبری"

    if content_type == "sensitive_content":
        return "محتوای حساس"

    if content_type == "normal_news":
        return "خبر"

    return "نامشخص"


# =========================================================
# PREVIEW
# =========================================================

def build_editorial_preview(
    content_type: str,
    summary_text: str,
    original_length: int,
    regeneration_count: int = 0,
    summary_success: bool = True,
    title: str = "",
    author: str = ""
) -> str:

    label = (
        editorial_type_label(
            content_type
        )
    )

    summary_text = (
        str(
            summary_text
            or ""
        )
        .strip()
    )

    display_summary = (
        build_editorial_display(
            title=title,
            author=author,
            body=summary_text
        )
    )

    preview_limit = 3000

    if len(display_summary) > preview_limit:

        preview_text = (
            display_summary[
                :preview_limit
            ]
            .rstrip()
            + "\n\n..."
        )

    else:

        preview_text = (
            display_summary
        )

    if summary_success:

        status = (
            "نسخه پیشنهادی آماده است."
        )

    else:

        status = (
            "خلاصه پیشنهادی آماده نشد. "
            "متن اصلی محفوظ است."
        )

    return (
        "📝 پیش‌نمایش تحریریه\n\n"
        f"نوع محتوا: {label}\n"
        f"طول متن اصلی: {original_length}\n"
        f"بازنویسی مجدد: {regeneration_count}/3\n"
        f"وضعیت: {status}\n\n"
        f"{preview_text}\n\n"
        "تا قبل از انتخاب گزینه انتشار، "
        "این محتوا در کانال منتشر نمی‌شود."
    )


# =========================================================
# CREATE EDITORIAL REVIEW FOR TEXT
# =========================================================

def try_queue_editorial_text_review(
    chat_id: int,
    text: str,
    entities: List[
        Dict[str, Any]
    ],
    forward_source: Optional[
        Dict[str, Any]
    ] = None
) -> bool:

    if not editorial_review_enabled():

        return False

    try:

        from core.editorial_review import (
            CONTENT_TYPE_NEWS_ANALYSIS,
            CONTENT_TYPE_OPINION_NOTE,
            analyze_editorial_content
        )

        from core.editorial_pending import (
            create_pending_review
        )

        from core.editorial_structure import (
            extract_editorial_structure
        )

        prepared = (
            prepare_text_content(
                text=text,
                entities=entities,
                forward_source=forward_source
            )
        )

        editorial_source = (
            build_editorial_source_text(
                prepared
            )
        )

        if not editorial_source:
            return False

        structure = (
            extract_editorial_structure(
                editorial_source
            )
        )

        editorial_title = (
            structure.title
            or ""
        )

        editorial_author = (
            structure.author
            or ""
        )

        editorial_body = (
            structure.body
            or editorial_source
        )

        logger.info(
            f"🧩 Editorial structure ready | "
            f"user={chat_id} | "
            f"title={bool(editorial_title)} | "
            f"author={editorial_author or '-'} | "
            f"source={len(editorial_source)} | "
            f"body={len(editorial_body)}"
        )

        review_result = (
            analyze_editorial_content(
                original_text=(
                    editorial_body
                )
            )
        )

        if (
            review_result.content_type
            not in (
                CONTENT_TYPE_OPINION_NOTE,
                CONTENT_TYPE_NEWS_ANALYSIS,
            )
        ):

            return False

        if not review_result.needs_approval:

            return False

        pending = (
            create_pending_review(
                user_id=chat_id,
                content_type=(
                    review_result.content_type
                ),
                original_text=(
                    editorial_source
                ),
                current_summary=(
                    review_result.suggested_text
                ),
                regeneration_count=(
                    review_result.metadata.get(
                        "regeneration_count",
                        0
                    )
                ),
                metadata={
                    "kind": "text",
                    "main_text":
                        prepared[
                            "main_text"
                        ],
                    "blockquote_blocks":
                        prepared[
                            "blockquote_blocks"
                        ],
                    "expandable_blocks":
                        prepared[
                            "expandable_blocks"
                        ],
                    "other_entities":
                        prepared[
                            "other_entities"
                        ],
                    "forward_source":
                        dict(
                            forward_source
                            or {}
                        ),
                    "summary_success":
                        review_result.summary_success,
                    "review_reason":
                        review_result.reason,
                    "editorial_title":
                        editorial_title,
                    "editorial_author":
                        editorial_author,
                    "editorial_body":
                        editorial_body,
                    "editorial_author_source":
                        structure.author_source,
                    "editorial_author_confidence":
                        structure.author_confidence
                }
            )
        )

        keyboard = (
            build_editorial_keyboard(
                review_id=(
                    pending.review_id
                ),
                has_summary=(
                    review_result.summary_success
                ),
                can_regenerate=(
                    pending.regeneration_count
                    < 3
                )
            )
        )

        preview = (
            build_editorial_preview(
                content_type=(
                    pending.content_type
                ),
                summary_text=(
                    pending.current_summary
                ),
                original_length=len(
                    editorial_body
                ),
                regeneration_count=(
                    pending.regeneration_count
                ),
                summary_success=(
                    review_result.summary_success
                ),
                title=(
                    editorial_title
                ),
                author=(
                    editorial_author
                )
            )
        )

        sent = send_message(
            chat_id=chat_id,
            text=preview,
            reply_markup=keyboard
        )

        if not sent:

            logger.error(
                f"❌ Editorial preview send failed | "
                f"review_id={pending.review_id}"
            )

            return False

        logger.info(
            f"✅ Editorial review queued | "
            f"review_id={pending.review_id} | "
            f"user={chat_id}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Editorial review queue failed | "
            f"{e}"
        )

        return False


# =========================================================
# PROCESS ADMIN INSTRUCTION MESSAGE
# =========================================================

def process_admin_instruction_message(
    chat_id: int,
    instruction_text: str,
    req_id: str = ""
) -> bool:

    try:

        from core.editorial_pending import (
            get_waiting_admin_instruction_review,
            record_admin_instruction_applied,
            update_pending_summary,
        )

        from core.editorial_review import (
            MAX_REGENERATION_COUNT,
            apply_admin_instruction_to_editorial_summary,
        )

        instruction_text = (
            str(
                instruction_text
                or ""
            )
            .strip()
        )

        if not instruction_text:

            return False

        review = (
            get_waiting_admin_instruction_review(
                user_id=chat_id
            )
        )

        if review is None:

            return False

        metadata = (
            review.metadata
            or {}
        )

        editorial_body = (
            metadata.get(
                "editorial_body",
                ""
            )
            or ""
        )

        editorial_title = (
            metadata.get(
                "editorial_title",
                ""
            )
            or ""
        )

        editorial_author = (
            metadata.get(
                "editorial_author",
                ""
            )
            or ""
        )

        original_body = (
            editorial_body
            or review.original_text
        )

        logger.info(
            f"[{req_id}] ✏️ ADMIN-INSTRUCTION-CONSUMED | "
            f"review_id={review.review_id} | "
            f"user={chat_id} | "
            f"instruction_length="
            f"{len(instruction_text)} | "
            f"body_length={len(original_body)}"
        )

        result = (
            apply_admin_instruction_to_editorial_summary(
                original_text=(
                    original_body
                ),
                previous_summary=(
                    review.current_summary
                ),
                admin_instruction=(
                    instruction_text
                ),
                content_type=(
                    review.content_type
                )
            )
        )

        if not result.summary_success:

            logger.warning(
                f"[{req_id}] ⚠️ Admin instruction rejected | "
                f"review_id={review.review_id} | "
                f"reason={result.reason}"
            )

            send_message(
                chat_id,
                (
                    "⚠️ دستور ادمین نتوانست یک نسخه معتبر "
                    "از نظر سیستم ضدتحریف تولید کند.\n\n"
                    "نسخه قبلی خلاصه محفوظ مانده است.\n\n"
                    "می‌توانی دستور دیگری ارسال کنی."
                )
            )

            return True

        new_summary = (
            str(
                result.suggested_text
                or ""
            )
            .strip()
        )

        if not new_summary:

            logger.warning(
                f"[{req_id}] ⚠️ Admin instruction "
                f"returned empty summary | "
                f"review_id={review.review_id}"
            )

            send_message(
                chat_id,
                (
                    "⚠️ نسخه جدید معتبر تولید نشد.\n\n"
                    "نسخه قبلی خلاصه محفوظ مانده است."
                )
            )

            return True

        updated_metadata = dict(
            review.metadata
            or {}
        )

        updated_metadata.update({
            "summary_success": True,
            "admin_instruction_reason":
                result.reason,
            "admin_instruction_validation":
                result.metadata.get(
                    "validation"
                ),
            "admin_instruction_certainty_retry":
                result.metadata.get(
                    "certainty_retry_called",
                    False
                )
        })

        updated = (
            update_pending_summary(
                review_id=(
                    review.review_id
                ),
                user_id=chat_id,
                new_summary=(
                    new_summary
                ),
                regeneration_count=(
                    review.regeneration_count
                ),
                metadata=(
                    updated_metadata
                )
            )
        )

        if updated is None:

            logger.error(
                f"[{req_id}] ❌ Admin instruction "
                f"summary update failed | "
                f"review_id={review.review_id}"
            )

            send_message(
                chat_id,
                (
                    "❌ نسخه جدید ساخته شد اما ذخیره "
                    "وضعیت آن با مشکل روبرو شد.\n\n"
                    "نسخه قبلی محفوظ مانده است."
                )
            )

            return True

        recorded = (
            record_admin_instruction_applied(
                review_id=(
                    updated.review_id
                ),
                user_id=chat_id,
                instruction=(
                    instruction_text
                )
            )
        )

        if recorded is not None:

            updated = recorded

        from core.editorial_pending import (
            STATUS_PENDING
        )

        if updated.status != STATUS_PENDING:

            logger.error(
                f"[{req_id}] ❌ Admin edit unexpectedly "
                f"finalized review | "
                f"review_id={updated.review_id} | "
                f"status={updated.status}"
            )

        updated_metadata = (
            updated.metadata
            or {}
        )

        can_regenerate = (
            updated.regeneration_count
            < MAX_REGENERATION_COUNT
        )

        keyboard = (
            build_editorial_keyboard(
                review_id=(
                    updated.review_id
                ),
                has_summary=True,
                can_regenerate=(
                    can_regenerate
                )
            )
        )

        preview = (
            build_editorial_preview(
                content_type=(
                    updated.content_type
                ),
                summary_text=(
                    updated.current_summary
                ),
                original_length=len(
                    updated_metadata.get(
                        "editorial_body",
                        updated.original_text
                    )
                    or updated.original_text
                ),
                regeneration_count=(
                    updated.regeneration_count
                ),
                summary_success=True,
                title=(
                    updated_metadata.get(
                        "editorial_title",
                        editorial_title
                    )
                    or editorial_title
                ),
                author=(
                    updated_metadata.get(
                        "editorial_author",
                        editorial_author
                    )
                    or editorial_author
                )
            )
        )

        send_message(
            chat_id=chat_id,
            text=(
                "✅ دستور ادمین اعمال شد.\n\n"
                + preview
            ),
            reply_markup=keyboard
        )

        logger.info(
            f"[{req_id}] ✅ Admin instruction applied | "
            f"review_id={updated.review_id} | "
            f"user={chat_id} | "
            f"summary_length="
            f"{len(updated.current_summary or '')} | "
            f"status={updated.status}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Admin instruction "
            f"processing failed | {e}"
        )

        send_message(
            chat_id,
            (
                "❌ پردازش دستور ادمین با خطا روبرو شد.\n\n"
                "نسخه قبلی خلاصه محفوظ مانده است."
            )
        )

        return True


# =========================================================
# CALLBACK HANDLER
# =========================================================

def handle_editorial_callback(
    callback_query: Dict[str, Any],
    req_id: str
) -> bool:

    callback_data = (
        callback_query.get(
            "data",
            ""
        )
        or ""
    )

    if not callback_data.startswith(
        "ed:"
    ):

        return False

    callback_id = (
        callback_query.get(
            "id",
            ""
        )
        or ""
    )

    from_user = (
        callback_query.get(
            "from",
            {}
        )
        or {}
    )

    user_id = (
        from_user.get(
            "id"
        )
    )

    if user_id is None:

        answer_callback_query(
            callback_id,
            "کاربر قابل تشخیص نیست."
        )

        return True

    parts = callback_data.split(
        ":",
        2
    )

    if len(parts) != 3:

        answer_callback_query(
            callback_id,
            "دستور نامعتبر است."
        )

        return True

    action = parts[1]
    review_id = parts[2]

    try:

        from core.editorial_pending import (
            STATUS_PENDING,
            cancel_pending_review,
            get_pending_review,
            mark_original_published,
            mark_summary_published,
            update_pending_summary,
            set_admin_instruction_waiting,
        )

        from core.editorial_review import (
            MAX_REGENERATION_COUNT,
            regenerate_editorial_summary
        )

        review = get_pending_review(
            review_id=review_id,
            user_id=user_id
        )

        if review is None:

            answer_callback_query(
                callback_id,
                "این پیش‌نمایش پیدا نشد."
            )

            return True

        if (
            review.status
            != STATUS_PENDING
        ):

            answer_callback_query(
                callback_id,
                "این درخواست قبلاً نهایی شده است."
            )

            return True

        metadata = (
            review.metadata
            or {}
        )

        editorial_title = (
            metadata.get(
                "editorial_title",
                ""
            )
            or ""
        )

        editorial_author = (
            metadata.get(
                "editorial_author",
                ""
            )
            or ""
        )

        editorial_body = (
            metadata.get(
                "editorial_body",
                ""
            )
            or ""
        )

        # =================================================
        # INFORMATIONAL / UNAVAILABLE ACTIONS
        # =================================================

        if action == "summary_unavailable":

            answer_callback_query(
                callback_id,
                "خلاصه معتبر هنوز آماده نشده است."
            )

            send_message(
                user_id,
                (
                    "⚠️ نسخه خلاصه هنوز مورد تأیید "
                    "سیستم ضدتحریف قرار نگرفته است.\n\n"
                    "می‌توانید «خلاصه‌سازی دوباره» را انتخاب کنید "
                    "یا متن اصلی را منتشر کنید."
                )
            )

            return True

        if action == "instruction_unavailable":

            answer_callback_query(
                callback_id,
                "ابتدا باید یک خلاصه معتبر ساخته شود."
            )

            send_message(
                user_id,
                (
                    "✏️ اصلاح با دستور ادمین زمانی فعال می‌شود "
                    "که ابتدا یک نسخه خلاصه معتبر آماده باشد.\n\n"
                    "ابتدا «خلاصه‌سازی دوباره» را انتخاب کنید."
                )
            )

            return True

        if action == "regen_unavailable":

            answer_callback_query(
                callback_id,
                "حداکثر تعداد بازنویسی انجام شده است."
            )

            send_message(
                user_id,
                (
                    "⛔️ سقف مجاز خلاصه‌سازی دوباره "
                    "برای این محتوا به پایان رسیده است.\n\n"
                    "می‌توانید نسخه موجود یا متن اصلی را منتشر کنید."
                )
            )

            return True

        # =================================================
        # ADMIN INSTRUCTION MODE
        # =================================================

        if action == "instruction":

            if not (
                review.current_summary
                or ""
            ).strip():

                answer_callback_query(
                    callback_id,
                    "خلاصه‌ای برای اصلاح وجود ندارد."
                )

                return True

            if (
                metadata.get(
                    "summary_success"
                )
                is False
            ):

                answer_callback_query(
                    callback_id,
                    "خلاصه معتبر آماده نشده است."
                )

                return True

            waiting_review = (
                set_admin_instruction_waiting(
                    review_id=review_id,
                    user_id=user_id
                )
            )

            if waiting_review is None:

                answer_callback_query(
                    callback_id,
                    "فعال‌سازی حالت اصلاح ناموفق بود."
                )

                send_message(
                    user_id,
                    (
                        "❌ امکان فعال‌سازی اصلاح "
                        "با دستور ادمین وجود ندارد."
                    )
                )

                return True

            answer_callback_query(
                callback_id,
                "منتظر دستور شما هستم."
            )

            send_message(
                user_id,
                (
                    "✏️ حالت اصلاح با دستور ادمین فعال شد.\n\n"
                    "در پیام بعدی دقیقاً بنویس چه تغییری "
                    "می‌خواهی روی خلاصه اعمال شود.\n\n"
                    "مثال:\n"
                    "متن را کمی کوتاه‌تر کن و تأکید بیشتری "
                    "روی بخش مربوط به مذاکرات داشته باش.\n\n"
                    "تا زمان پردازش موفق دستور، "
                    "نسخه فعلی خلاصه محفوظ می‌ماند."
                )
            )

            logger.info(
                f"[{req_id}] ✏️ Editorial admin "
                f"instruction waiting enabled | "
                f"review_id={review_id} | "
                f"user={user_id}"
            )

            return True

        # =================================================
        # CANCEL
        # =================================================

        if action == "cancel":

            cancel_pending_review(
                review_id=review_id,
                user_id=user_id
            )

            answer_callback_query(
                callback_id,
                "لغو شد."
            )

            send_message(
                user_id,
                "❌ انتشار این محتوا لغو شد."
            )

            return True

        # =================================================
        # ORIGINAL
        # =================================================

        if action == "original":

            success = (
                publish_prepared_text(
                    chat_id=user_id,
                    main_text=(
                        metadata.get(
                            "main_text",
                            review.original_text
                        )
                        or review.original_text
                    ),
                    blockquote_blocks=(
                        metadata.get(
                            "blockquote_blocks",
                            []
                        )
                    ),
                    expandable_blocks=(
                        metadata.get(
                            "expandable_blocks",
                            []
                        )
                    ),
                    other_entities=(
                        metadata.get(
                            "other_entities",
                            []
                        )
                    )
                )
            )

            if success:

                mark_original_published(
                    review_id=review_id,
                    user_id=user_id
                )

                answer_callback_query(
                    callback_id,
                    "متن اصلی منتشر شد."
                )

                send_message(
                    user_id,
                    "✅ متن اصلی در کانال منتشر شد."
                )

            else:

                answer_callback_query(
                    callback_id,
                    "انتشار با خطا روبرو شد."
                )

                send_message(
                    user_id,
                    "❌ انتشار متن اصلی با مشکل روبرو شد."
                )

            return True

        # =================================================
        # SUMMARY
        # =================================================

        if action == "summary":

            if not (
                review.current_summary
                or ""
            ).strip():

                answer_callback_query(
                    callback_id,
                    "خلاصه‌ای برای انتشار وجود ندارد."
                )

                return True

            if (
                metadata.get(
                    "summary_success"
                )
                is False
            ):

                answer_callback_query(
                    callback_id,
                    "خلاصه معتبر آماده نشده است."
                )

                return True

            final_summary = (
                build_editorial_display(
                    title=editorial_title,
                    author=editorial_author,
                    body=(
                        review.current_summary
                    )
                )
            )

            success = (
                publish_prepared_text(
                    chat_id=user_id,
                    main_text=(
                        final_summary
                    ),
                    blockquote_blocks=[],
                    expandable_blocks=[],
                    other_entities=[]
                )
            )

            if success:

                mark_summary_published(
                    review_id=review_id,
                    user_id=user_id
                )

                answer_callback_query(
                    callback_id,
                    "خلاصه منتشر شد."
                )

                send_message(
                    user_id,
                    "✅ نسخه خلاصه در کانال منتشر شد."
                )

            else:

                answer_callback_query(
                    callback_id,
                    "انتشار با خطا روبرو شد."
                )

                send_message(
                    user_id,
                    "❌ انتشار خلاصه با مشکل روبرو شد."
                )

            return True

        # =================================================
        # REGENERATE
        # =================================================

        if action == "regen":

            if (
                review.regeneration_count
                >= MAX_REGENERATION_COUNT
            ):

                answer_callback_query(
                    callback_id,
                    "حداکثر تعداد بازنویسی انجام شده است."
                )

                return True

            answer_callback_query(
                callback_id,
                "در حال ساخت نسخه جدید..."
            )

            regeneration_source = (
                editorial_body
                or review.original_text
            )

            regeneration_result = (
                regenerate_editorial_summary(
                    original_text=(
                        regeneration_source
                    ),
                    previous_summary=(
                        review.current_summary
                    ),
                    content_type=(
                        review.content_type
                    ),
                    regeneration_count=(
                        review.regeneration_count
                    )
                )
            )

            next_count = (
                regeneration_result.metadata.get(
                    "regeneration_count",
                    review.regeneration_count
                )
            )

            updated_metadata = dict(
                review.metadata
                or {}
            )

            updated_metadata.update({
                "summary_success":
                    regeneration_result.summary_success,
                "regeneration_reason":
                    regeneration_result.reason
            })

            updated = (
                update_pending_summary(
                    review_id=review_id,
                    user_id=user_id,
                    new_summary=(
                        regeneration_result.suggested_text
                        or review.current_summary
                    ),
                    regeneration_count=(
                        next_count
                    ),
                    metadata=(
                        updated_metadata
                    )
                )
            )

            if updated is None:

                send_message(
                    user_id,
                    (
                        "❌ وضعیت بازنویسی "
                        "قابل به‌روزرسانی نیست."
                    )
                )

                return True

            if not regeneration_result.summary_success:

                keyboard = (
                    build_editorial_keyboard(
                        review_id=review_id,
                        has_summary=False,
                        can_regenerate=(
                            updated.regeneration_count
                            < MAX_REGENERATION_COUNT
                        )
                    )
                )

                send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ نسخه جدید مورد تأیید "
                        "سیستم ضدتحریف قرار نگرفت.\n\n"
                        "نسخه قبلی محفوظ مانده است."
                    ),
                    reply_markup=keyboard
                )

                return True

            keyboard = (
                build_editorial_keyboard(
                    review_id=review_id,
                    has_summary=True,
                    can_regenerate=(
                        updated.regeneration_count
                        < MAX_REGENERATION_COUNT
                    )
                )
            )

            updated_metadata = (
                updated.metadata
                or {}
            )

            preview = (
                build_editorial_preview(
                    content_type=(
                        updated.content_type
                    ),
                    summary_text=(
                        updated.current_summary
                    ),
                    original_length=len(
                        updated_metadata.get(
                            "editorial_body",
                            updated.original_text
                        )
                        or updated.original_text
                    ),
                    regeneration_count=(
                        updated.regeneration_count
                    ),
                    summary_success=True,
                    title=(
                        updated_metadata.get(
                            "editorial_title",
                            ""
                        )
                        or ""
                    ),
                    author=(
                        updated_metadata.get(
                            "editorial_author",
                            ""
                        )
                        or ""
                    )
                )
            )

            send_message(
                chat_id=user_id,
                text=preview,
                reply_markup=keyboard
            )

            return True

        answer_callback_query(
            callback_id,
            "دستور ناشناخته است."
        )

        return True

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Editorial callback failed | "
            f"{e}"
        )

        answer_callback_query(
            callback_id,
            "خطا در پردازش درخواست."
        )

        return True


# =========================================================
# WEBHOOK HANDLER
# =========================================================

def handle_webhook() -> Tuple[
    Dict[str, Any],
    int
]:

    req_id = (
        str(
            uuid.uuid4()
        )[:8]
    )

    logger.info(
        f"[{req_id}] 📥 Telegram Webhook received"
    )

    try:

        # =================================================
        # SECURITY
        # =================================================

        if not validate_webhook_token():

            return {
                "ok": False
            }, 403

        # =================================================
        # JSON
        # =================================================

        data = request.get_json(
            silent=True
        )

        if not data:

            return {
                "ok": True
            }, 200

        # =================================================
        # CALLBACK
        # =================================================

        callback_query = data.get(
            "callback_query"
        )

        if isinstance(
            callback_query,
            dict
        ):

            handled = (
                handle_editorial_callback(
                    callback_query,
                    req_id
                )
            )

            return {
                "ok": True,
                "callback_handled":
                    bool(
                        handled
                    )
            }, 200

        # =================================================
        # MESSAGE
        # =================================================

        msg = data.get(
            "message"
        )

        if not msg:

            return {
                "ok": True
            }, 200

        chat_id = (
            msg.get(
                "chat",
                {}
            )
            .get(
                "id"
            )
        )

        if chat_id is None:

            return {
                "ok": True
            }, 200

        # =================================================
        # DIAGNOSTICS
        # =================================================

        log_message_diagnostics(
            req_id,
            msg
        )

        forward_source = (
            extract_forward_source_metadata(
                msg
            )
        )

        entities = list(
            msg.get(
                "entities",
                []
            )
            or []
        )

        caption_entities = list(
            msg.get(
                "caption_entities",
                []
            )
            or []
        )

        # =================================================
        # COMMAND
        # =================================================

        command_text = (
            msg.get(
                "text",
                ""
            )
            or ""
        )

        if command_text.startswith("/"):

            try:

                from core.command_handler import (
                    handle_command
                )

                handle_command(
                    command_text,
                    chat_id
                )

            except Exception as e:

                logger.exception(
                    f"[{req_id}] ❌ Command error | "
                    f"{e}"
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # TENANT
        # =================================================

        try:

            from core.database import (
                get_tenant
            )

            tenant = get_tenant(
                chat_id
            )

        except Exception as e:

            logger.exception(
                f"[{req_id}] ❌ Tenant lookup failed | "
                f"{e}"
            )

            send_message(
                chat_id,
                "❌ خطای دیتابیسی. لطفاً بعداً تلاش کنید."
            )

            return {
                "ok": True
            }, 200

        if (
            not tenant
            or not tenant.get(
                "telegram_channel"
            )
        ):

            send_message(
                chat_id,
                (
                    "❌ ابتدا با /register ثبت‌نام "
                    "و کانال را تنظیم کنید."
                )
            )

            return {
                "ok": True
            }, 200

        # =================================================
        # ADMIN INSTRUCTION TEXT GATE
        # =================================================

        pure_text = (
            msg.get(
                "text",
                ""
            )
            or ""
        )

        if pure_text.strip():

            try:

                from core.editorial_pending import (
                    get_waiting_admin_instruction_review
                )

                waiting_review = (
                    get_waiting_admin_instruction_review(
                        user_id=chat_id
                    )
                )

            except Exception as e:

                logger.exception(
                    f"[{req_id}] ❌ Admin instruction "
                    f"waiting lookup failed | {e}"
                )

                waiting_review = None

            if waiting_review is not None:

                logger.info(
                    f"[{req_id}] ✏️ ADMIN-INSTRUCTION-GATE | "
                    f"review_id="
                    f"{waiting_review.review_id} | "
                    f"user={chat_id}"
                )

                process_admin_instruction_message(
                    chat_id=chat_id,
                    instruction_text=(
                        pure_text
                    ),
                    req_id=req_id
                )

                return {
                    "ok": True,
                    "admin_instruction": True,
                    "review_id":
                        waiting_review.review_id
                }, 200

        # =================================================
        # MEDIA INFO
        # =================================================

        media_info = (
            get_media_from_message(
                msg
            )
        )

        media_type = (
            media_info.get(
                "type"
            )
        )

        file_id = (
            media_info.get(
                "file_id"
            )
        )

        caption = (
            media_info.get(
                "caption",
                ""
            )
            or ""
        )

        # =================================================
        # MEDIA GROUP
        # =================================================

        if (
            media_type
            and file_id
            and msg.get(
                "media_group_id"
            )
        ):

            try:

                from core.media_handler import (
                    handle_media_group_message
                )

                message_for_media = dict(
                    msg
                )

                if forward_source.get(
                    "is_forwarded"
                ):

                    message_for_media[
                        "_forward_source"
                    ] = forward_source

                accepted = (
                    handle_media_group_message(
                        message=(
                            message_for_media
                        ),
                        file_id=file_id,
                        media_type=media_type,
                        caption=caption,
                        caption_entities=(
                            caption_entities
                        )
                    )
                )

                if accepted:

                    send_message(
                        chat_id,
                        (
                            "✅ آلبوم شما در حال "
                            "پردازش است..."
                        )
                    )

                else:

                    send_message(
                        chat_id,
                        "❌ خطا در پردازش آلبوم"
                    )

            except Exception as e:

                logger.exception(
                    f"[{req_id}] ❌ Media Group error | "
                    f"{e}"
                )

                send_message(
                    chat_id,
                    "❌ خطا در پردازش آلبوم"
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # SINGLE PHOTO / VIDEO
        # =================================================

        if (
            media_type
            in (
                "photo",
                "video"
            )
            and file_id
        ):

            kwargs = {
                "chat_id": chat_id,
                "file_id": file_id,
                "media_type": media_type,
                "caption": caption,
                "caption_entities":
                    caption_entities
            }

            if forward_source.get(
                "is_forwarded"
            ):

                kwargs[
                    "forward_source"
                ] = forward_source

            success = (
                process_single_photo_video(
                    **kwargs
                )
            )

            if success:

                send_message(
                    chat_id,
                    (
                        "✅ خبر تصویری/ویدیویی شما "
                        "در کانال منتشر شد."
                    )
                )

            else:

                send_message(
                    chat_id,
                    (
                        "❌ ارسال رسانه با مشکل "
                        "روبرو شد."
                    )
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # DOCUMENT / VOICE / AUDIO
        # =================================================

        if (
            media_type
            in (
                "document",
                "voice",
                "audio"
            )
            and file_id
        ):

            kwargs = {
                "chat_id": chat_id,
                "file_id": file_id,
                "media_type": media_type,
                "caption": caption
            }

            if forward_source.get(
                "is_forwarded"
            ):

                kwargs[
                    "forward_source"
                ] = forward_source

            success = (
                process_legacy_single_media(
                    **kwargs
                )
            )

            if success:

                send_message(
                    chat_id,
                    (
                        "✅ رسانه شما در کانال "
                        "منتشر شد."
                    )
                )

            else:

                send_message(
                    chat_id,
                    (
                        "❌ ارسال رسانه با مشکل "
                        "روبرو شد."
                    )
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # NORMAL TEXT
        # =================================================

        if pure_text.strip():

            queued_for_review = (
                try_queue_editorial_text_review(
                    chat_id=chat_id,
                    text=pure_text,
                    entities=entities,
                    forward_source=(
                        forward_source
                        if forward_source.get(
                            "is_forwarded"
                        )
                        else None
                    )
                )
            )

            if queued_for_review:

                logger.info(
                    f"[{req_id}] 📝 Text held for "
                    f"editorial approval | "
                    f"user={chat_id}"
                )

                return {
                    "ok": True,
                    "editorial_review": True
                }, 200

            kwargs = {
                "chat_id": chat_id,
                "text": pure_text,
                "entities": entities
            }

            if forward_source.get(
                "is_forwarded"
            ):

                kwargs[
                    "forward_source"
                ] = forward_source

            success = (
                process_text_message(
                    **kwargs
                )
            )

            if success:

                send_message(
                    chat_id,
                    (
                        "✅ خبر شما در کانال "
                        "منتشر شد."
                    )
                )

            else:

                send_message(
                    chat_id,
                    (
                        "❌ ارسال خبر به کانال "
                        "با مشکل روبرو شد."
                    )
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # UNSUPPORTED
        # =================================================

        send_message(
            chat_id,
            "❌ پیام قابل پردازش نیست."
        )

        return {
            "ok": True
        }, 200

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Webhook fatal error | "
            f"{e}"
        )

        return {
            "ok": False,
            "error": str(
                e
            )
        }, 500
