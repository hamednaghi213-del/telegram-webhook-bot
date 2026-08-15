import logging
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
# INITIALIZE
# =========================================================

def initialize(
    api_url: str,
    channel_id: str,
    secret_token: str
) -> None:
    """
    مقداردهی Webhook Handler.
    """

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
        f"channel={CHANNEL_ID}"
    )


# =========================================================
# VALIDATE SECRET TOKEN
# =========================================================

def validate_webhook_token() -> bool:
    """
    اعتبارسنجی Telegram Webhook Secret Token.
    """

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

    is_valid = secrets.compare_digest(
        request_token,
        SECRET_TOKEN
    )

    if not is_valid:

        logger.error(
            "❌ Invalid Telegram webhook secret token"
        )

        return False

    logger.debug(
        "✅ Telegram webhook token validated"
    )

    return True


# =========================================================
# GET MESSAGE TEXT
# =========================================================

def get_message_text(
    msg: Dict[str, Any]
) -> str:
    """
    استخراج text یا caption.
    """

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
# GET CORRECT ENTITIES
# =========================================================

def get_message_entities(
    msg: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Caption:
        caption_entities

    Text:
        entities
    """

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
    """
    استخراج اطلاعات کانال یا منبع Forward.

    این تابع فعلاً فقط برای Diagnostic استفاده می‌شود.

    هیچ متنی حذف یا تغییر داده نمی‌شود.
    """

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

        # =================================================
        # MODERN TELEGRAM FORWARD_ORIGIN
        # =================================================

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

            # ---------------------------------------------
            # CHANNEL OR CHAT ORIGIN
            # ---------------------------------------------

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

        # =================================================
        # BACKWARD COMPATIBILITY
        # =================================================

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
            f"❌ Forward metadata parse error | "
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
    """
    Diagnostic برای بررسی:

    1. دو تکه شدن Caption
    2. Forward source
    3. Channel username/title
    4. Entities
    5. Media Group

    این تابع هیچ تغییری در Message ایجاد نمی‌کند.
    """

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

        media_group_id = (
            msg.get(
                "media_group_id"
            )
        )

        forward_info = (
            extract_forward_source_metadata(
                msg
            )
        )

        # =================================================
        # BASIC LENGTH DIAGNOSTIC
        # =================================================

        logger.info(
            f"[{req_id}] 🔬 MESSAGE-DIAGNOSTIC | "
            f"has_text={bool(raw_text)} | "
            f"text_length={len(raw_text)} | "
            f"has_caption={bool(raw_caption)} | "
            f"caption_length={len(raw_caption)} | "
            f"media_group_id={media_group_id or '-'}"
        )

        # =================================================
        # ENTITY DIAGNOSTIC
        # =================================================

        logger.info(
            f"[{req_id}] 🔬 ENTITY-DIAGNOSTIC | "
            f"entities={len(entities)} | "
            f"caption_entities="
            f"{len(caption_entities)}"
        )

        if entities:

            entity_types = [
                str(
                    entity.get(
                        "type",
                        ""
                    )
                )
                for entity in entities
            ]

            logger.info(
                f"[{req_id}] 🔬 TEXT-ENTITY-TYPES | "
                f"{entity_types}"
            )

        if caption_entities:

            caption_entity_types = [
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
                f"{caption_entity_types}"
            )

        # =================================================
        # FORWARD DIAGNOSTIC
        # =================================================

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
            f"{forward_info.get('source_message_id') or '-'} | "
            f"sender_name="
            f"{forward_info.get('sender_name') or '-'}"
        )

        # =================================================
        # TAIL DIAGNOSTIC
        # =================================================
        #
        # برای دیدن همان بخش‌هایی مثل:
        #
        # 🔷 🆔
        # کانال ...
        # @username
        #
        # فقط 500 کاراکتر انتهایی Caption را Log می‌کنیم.
        # =================================================

        if raw_caption:

            caption_tail = (
                raw_caption[
                    -500:
                ]
            )

            logger.info(
                f"[{req_id}] 🔬 CAPTION-TAIL | "
                f"{caption_tail!r}"
            )

        elif raw_text:

            text_tail = (
                raw_text[
                    -500:
                ]
            )

            logger.info(
                f"[{req_id}] 🔬 TEXT-TAIL | "
                f"{text_tail!r}"
            )

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Diagnostic logging failed | "
            f"{e}"
        )


# =========================================================
# GET MEDIA FROM MESSAGE
# =========================================================

def get_media_from_message(
    msg: Dict[str, Any]
) -> Dict[str, Any]:
    """
    استخراج Media از Telegram Message.
    """

    result: Dict[str, Any] = {
        "type": None,
        "file_id": None,
        "caption": ""
    }

    # =====================================================
    # VIDEO
    # =====================================================

    if "video" in msg:

        result[
            "type"
        ] = "video"

        result[
            "file_id"
        ] = (
            msg[
                "video"
            ].get(
                "file_id"
            )
        )

        result[
            "caption"
        ] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    # =====================================================
    # PHOTO
    # =====================================================

    if "photo" in msg:

        photos = (
            msg.get(
                "photo",
                []
            )
            or []
        )

        if photos:

            result[
                "type"
            ] = "photo"

            result[
                "file_id"
            ] = (
                photos[
                    -1
                ].get(
                    "file_id"
                )
            )

            result[
                "caption"
            ] = (
                msg.get(
                    "caption",
                    ""
                )
                or ""
            )

        return result

    # =====================================================
    # DOCUMENT
    # =====================================================

    if "document" in msg:

        result[
            "type"
        ] = "document"

        result[
            "file_id"
        ] = (
            msg[
                "document"
            ].get(
                "file_id"
            )
        )

        result[
            "caption"
        ] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    # =====================================================
    # VOICE
    # =====================================================

    if "voice" in msg:

        result[
            "type"
        ] = "voice"

        result[
            "file_id"
        ] = (
            msg[
                "voice"
            ].get(
                "file_id"
            )
        )

        result[
            "caption"
        ] = (
            msg.get(
                "caption",
                ""
            )
            or ""
        )

        return result

    # =====================================================
    # AUDIO
    # =====================================================

    if "audio" in msg:

        result[
            "type"
        ] = "audio"

        result[
            "file_id"
        ] = (
            msg[
                "audio"
            ].get(
                "file_id"
            )
        )

        result[
            "caption"
        ] = (
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
    parse_mode: Optional[str] = None
) -> bool:
    """
    ارسال Status Message به کاربر.
    """

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

        response = requests.post(
            f"{API_URL}/sendMessage",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:

            return True

        logger.error(
            f"❌ User status message failed | "
            f"status={response.status_code} | "
            f"response={response.text[:500]}"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ send_message exception | "
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
    """
    ارسال Text Message مستقیم به کانال.
    """

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

            logger.info(
                f"✅ Telegram channel text sent | "
                f"length={len(text)}"
            )

            return True

        logger.error(
            f"❌ Telegram channel text failed | "
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
# BUILD USER BRANDING
# =========================================================

def build_branding_for_user(
    user_id: int
) -> str:
    """
    ساخت Branding مخصوص Tenant.
    """

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
            f"❌ Branding load failed | "
            f"user={user_id} | "
            f"{e}"
        )

        return ""


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
    ]
) -> bool:
    """
    Single Photo/Video را از معماری جدید عبور می‌دهد.
    """

    try:

        from core.content_entities import (
            parse_telegram_entities
        )

        from core.formatter import (
            format_news
        )

        from core.caption_manager import (
            analyze_content
        )

        from core.media_handler import (
            execute_telegram_plan,
            execute_bale_plan
        )

        # =================================================
        # ENTITY PARSING
        # =================================================

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

        # =================================================
        # FORMAT
        # =================================================

        formatted_main_text = ""

        if main_text:

            try:

                formatted_main_text = (
                    format_news(
                        main_text
                    )
                    or main_text
                )

            except Exception as e:

                logger.exception(
                    f"❌ Single media formatter failed | "
                    f"{e}"
                )

                formatted_main_text = (
                    main_text
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
            f"🔬 SINGLE-MEDIA-LENGTHS | "
            f"formatted={len(formatted_main_text)} | "
            f"branding={len(branding)} | "
            f"combined_estimate="
            f"{len(formatted_main_text) + len(branding)}"
        )

        # =================================================
        # PLAN
        # =================================================

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

        logger.info(
            f"🔬 SINGLE-MEDIA-PLAN | "
            f"telegram_caption_length="
            f"{len(publication_plan.telegram.get('media_caption', ''))} | "
            f"telegram_followups="
            f"{len(publication_plan.telegram.get('followup_messages', []))} | "
            f"telegram_blockquotes="
            f"{len(publication_plan.telegram.get('blockquote_messages', []))} | "
            f"telegram_fallback="
            f"{publication_plan.telegram.get('document_fallback', False)} | "
            f"bale_caption_length="
            f"{len(publication_plan.bale.get('media_caption', ''))} | "
            f"bale_followups="
            f"{len(publication_plan.bale.get('followup_messages', []))}"
        )

        files = [
            {
                "type": media_type,
                "file_id": file_id
            }
        ]

        # =================================================
        # TELEGRAM
        # =================================================

        telegram_success = (
            execute_telegram_plan(
                files,
                publication_plan.telegram
            )
        )

        if not telegram_success:

            logger.error(
                "❌ Single media Telegram plan failed"
            )

            return False

        # =================================================
        # BALE
        # =================================================

        bale_success = (
            execute_bale_plan(
                chat_id,
                files,
                publication_plan.bale
            )
        )

        if not bale_success:

            logger.warning(
                "⚠️ Single media Telegram succeeded "
                "but Bale failed"
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Single photo/video processing failed | "
            f"{e}"
        )

        return False


# =========================================================
# PROCESS LEGACY SINGLE MEDIA
# =========================================================

def process_legacy_single_media(
    chat_id: int,
    file_id: str,
    media_type: str,
    caption: str
) -> bool:
    """
    مسیر قبلی برای document / voice / audio.
    """

    try:

        from core.media_sender import (
            send_media_to_channel
        )

        from core.formatter import (
            format_news
        )

        from core.bale_forwarder import (
            send_to_bale_for_user
        )

        formatted_caption = ""

        if caption:

            try:

                formatted_caption = (
                    format_news(
                        caption
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
# PROCESS TEXT MESSAGE
# =========================================================

def process_text_message(
    chat_id: int,
    text: str,
    entities: List[
        Dict[str, Any]
    ]
) -> bool:
    """
    مسیر Text-only.
    """

    try:

        from core.formatter import (
            format_news
        )

        from core.content_entities import (
            build_full_html
        )

        from core.bale_forwarder import (
            send_to_bale_for_user
        )

        formatted = (
            format_news(
                text
            )
        )

        if not formatted:

            return False

        if entities:

            try:

                html_content = (
                    build_full_html(
                        text,
                        entities
                    )
                )

                success = (
                    send_to_channel(
                        html_content,
                        parse_mode="HTML"
                    )
                )

            except Exception as e:

                logger.warning(
                    f"⚠️ Text HTML fallback | "
                    f"{e}"
                )

                success = (
                    send_to_channel(
                        formatted
                    )
                )

        else:

            success = (
                send_to_channel(
                    formatted
                )
            )

        if not success:

            return False

        try:

            send_to_bale_for_user(
                chat_id,
                formatted
            )

        except Exception as e:

            logger.warning(
                f"⚠️ Bale text failed | "
                f"{e}"
            )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Text processing failed | "
            f"{e}"
        )

        return False


# =========================================================
# WEBHOOK HANDLER
# =========================================================

def handle_webhook() -> Tuple[
    Dict[str, Any],
    int
]:
    """
    پردازش اصلی Telegram Webhook.
    """

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

            logger.error(
                f"[{req_id}] 🔒 Webhook validation failed"
            )

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

            logger.warning(
                f"[{req_id}] ⚠️ Empty Webhook JSON"
            )

            return {
                "ok": True
            }, 200

        # =================================================
        # MESSAGE
        # =================================================

        msg = data.get(
            "message"
        )

        if not msg:

            logger.info(
                f"[{req_id}] ℹ️ Update has no message"
            )

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

            logger.error(
                f"[{req_id}] ❌ chat_id not found"
            )

            return {
                "ok": True
            }, 200

        # =================================================
        # DIAGNOSTIC
        # =================================================
        #
        # هیچ تغییری در Message ایجاد نمی‌کند.
        # =================================================

        log_message_diagnostics(
            req_id,
            msg
        )

        # =================================================
        # INPUT DATA
        # =================================================

        text = (
            get_message_text(
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

        logger.info(
            f"[{req_id}] 📩 Message received | "
            f"chat={chat_id} | "
            f"text={bool(msg.get('text'))} | "
            f"caption={bool(msg.get('caption'))} | "
            f"entities={len(entities)} | "
            f"caption_entities={len(caption_entities)}"
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
        # TENANT VALIDATION
        # =================================================

        try:

            from core.database import (
                get_tenant
            )

            tenant = (
                get_tenant(
                    chat_id
                )
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
                "❌ ابتدا با /register ثبت‌نام و کانال را تنظیم کنید."
            )

            return {
                "ok": True
            }, 200

        # =================================================
        # MEDIA
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

            logger.info(
                f"[{req_id}] 🖼️ Media Group | "
                f"group={msg.get('media_group_id')} | "
                f"type={media_type}"
            )

            try:

                from core.media_handler import (
                    handle_media_group_message
                )

                accepted = (
                    handle_media_group_message(
                        message=msg,
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
                        "✅ آلبوم شما در حال پردازش است..."
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

            logger.info(
                f"[{req_id}] 🎞️ Single Media | "
                f"type={media_type}"
            )

            success = (
                process_single_photo_video(
                    chat_id=chat_id,
                    file_id=file_id,
                    media_type=media_type,
                    caption=caption,
                    caption_entities=(
                        caption_entities
                    )
                )
            )

            if success:

                send_message(
                    chat_id,
                    "✅ خبر تصویری/ویدیویی شما "
                    "در کانال منتشر شد."
                )

            else:

                send_message(
                    chat_id,
                    "❌ ارسال رسانه با مشکل روبرو شد."
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

            logger.info(
                f"[{req_id}] 📎 Legacy Single Media | "
                f"type={media_type}"
            )

            success = (
                process_legacy_single_media(
                    chat_id=chat_id,
                    file_id=file_id,
                    media_type=media_type,
                    caption=caption
                )
            )

            if success:

                send_message(
                    chat_id,
                    "✅ رسانه شما در کانال منتشر شد."
                )

            else:

                send_message(
                    chat_id,
                    "❌ ارسال رسانه با مشکل روبرو شد."
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # TEXT
        # =================================================

        pure_text = (
            msg.get(
                "text",
                ""
            )
            or ""
        )

        if pure_text.strip():

            logger.info(
                f"[{req_id}] 📝 Text Message"
            )

            success = (
                process_text_message(
                    chat_id=chat_id,
                    text=pure_text,
                    entities=entities
                )
            )

            if success:

                send_message(
                    chat_id,
                    "✅ خبر شما در کانال منتشر شد."
                )

            else:

                send_message(
                    chat_id,
                    "❌ ارسال خبر به کانال "
                    "با مشکل روبرو شد."
                )

            return {
                "ok": True
            }, 200

        # =================================================
        # EMPTY / UNSUPPORTED
        # =================================================

        logger.warning(
            f"[{req_id}] ⚠️ Empty or unsupported message"
        )

        send_message(
            chat_id,
            "❌ پیام قابل پردازش نیست."
        )

        return {
            "ok": True
        }, 200

    except Exception as e:

        logger.exception(
            f"[{req_id}] ❌ Webhook Handler fatal error | "
            f"{e}"
        )

        return {
            "ok": False,
            "error": str(e)
        }, 500
