"""Bale inbound adapter (Bale Full Bot Parity — slice 1).



Normalizes inbound Bale bot updates and runs them through the

SAME shared command handlers the Telegram webhook uses. Platform

differences live here:



- secret-token validation of the inbound Bale webhook,

- update shape normalization (message/text/callback),

- binding the Bale outbound messaging context,

- binding the Bale identity origin so shared logic resolves the

  user through ``bale_user_id`` (never via Telegram numeric IDs).



Business logic (commands, onboarding, workspaces) is NOT

duplicated: ``core.command_handler.handle_command`` is invoked

exactly as the Telegram webhook does.

"""



import logging

import os

import secrets

from typing import Any, Dict, Optional, Tuple



from core import command_handler

from core.messaging import BaleMessagingContext





logger = logging.getLogger(__name__)





BALE_WEBHOOK_INITIALIZED: bool = False

BALE_SECRET_TOKEN: str = ""





def initialize(secret_token: str = "") -> None:

    """Configure the Bale webhook secret (optional endpoint)."""

    global BALE_WEBHOOK_INITIALIZED

    global BALE_SECRET_TOKEN



    BALE_SECRET_TOKEN = (secret_token or "").strip()

    BALE_WEBHOOK_INITIALIZED = True



    logger.info(

        "✅ Bale Adapter initialized | secret_configured=%s",

        bool(BALE_SECRET_TOKEN),

    )





def validate_bale_webhook_token(request) -> bool:
    """Validate Bale webhook when Bale supplies the optional secret header."""
    if not BALE_WEBHOOK_INITIALIZED:
        logger.error(
            "❌ Bale Adapter not initialized"
        )
        return False

    request_token = request.headers.get(
        "X-Bale-Bot-Secret-Token"
    )

    # Bale webhook delivery may omit the optional secret header.
    # If a secret header is supplied, validate it strictly.
    if request_token:
        if not BALE_SECRET_TOKEN:
            logger.error(
                "❌ Bale webhook supplied a secret but no local secret is configured"
            )
            return False

        if not secrets.compare_digest(
            request_token,
            BALE_SECRET_TOKEN,
        ):
            logger.error(
                "❌ Invalid Bale webhook secret token"
            )
            return False

    return True

def _extract_callback_query(

    data: Dict[str, Any],

) -> Optional[Dict[str, Any]]:

    """Normalize a Bale callback query into the shared Telegram shape.



    The shared workspace/setup logic reads ``id``, ``from.id``,

    ``data`` and ``message.chat.id``/``message.message_id``; Bale

    payloads use the same field names, so normalization is a pass-

    through with defensive typing (no business logic here).

    """

    callback = data.get("callback_query")



    if not isinstance(callback, dict):

        return None



    normalized = {

        "id": str(callback.get("id", "") or ""),

        "data": str(callback.get("data", "") or ""),

        "from": (

            callback.get("from")

            if isinstance(callback.get("from"), dict)

            else {}

        ),

    }



    if isinstance(callback.get("message"), dict):

        normalized["message"] = callback["message"]



    return normalized





def _handle_bale_callback(

    callback_query: Dict[str, Any],

) -> Tuple[Dict[str, Any], int]:

    """Route a Bale callback into the SHARED callback logic.



    ``ws:``/``wp:`` payloads go to the existing workspace callback

    handler; ``setup:`` payloads go to the existing setup callback

    handler. Business logic is not duplicated here.

    """

    from core.messaging import bind_context

    from core.messaging import reset_default_context



    callback_data = str(

        callback_query.get("data", "") or ""

    )



    previous_origin = command_handler.CURRENT_ORIGIN



    try:

        command_handler.CURRENT_ORIGIN = "bale"



        bind_context(BaleMessagingContext())



        if callback_data.startswith("setup:"):

            from core.webhook_handler import (

                handle_setup_callback,

            )



            handle_setup_callback(

                callback_query,

                "bale-callback",

            )



            return {"ok": True, "handled": True}, 200



        if callback_data.startswith(("ws:", "wp:")):

            from core.workspace_publisher import (

                handle_workspace_callback,

            )



            handle_workspace_callback(

                callback_query,

                "bale-callback",

                None,

            )



            return {"ok": True, "handled": True}, 200



        if callback_data.startswith("dup:"):

            from core.webhook_handler import (

                handle_duplicate_override_callback,

            )



            handle_duplicate_override_callback(

                callback_query,

                "bale-callback",

            )



            return {"ok": True, "handled": True}, 200



        if callback_data.startswith("ed:"):

            from core.webhook_handler import (

                handle_editorial_callback,

            )



            handled = handle_editorial_callback(

                callback_query,

                "bale-callback",

            )



            return {

                "ok": True,

                "handled": bool(handled),

            }, 200



        # Unknown payload families are acknowledged so the client

        # does not hang, but no shared logic is invoked.

        from core.messaging import current_context



        current_context().acknowledge_callback(

            callback_query.get("id", ""),

            "",

        )



        return {

            "ok": True,

            "handled": False,

            "reason": "unsupported_callback",

        }, 200

    except Exception as exc:

        logger.exception(

            "❌ Bale callback handling failed | %s",

            exc,

        )

        return {"ok": True, "handled": False}, 200

    finally:

        command_handler.CURRENT_ORIGIN = previous_origin



        reset_default_context()





def _extract_message(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    message = data.get("message")



    if isinstance(message, dict):

        return message



    # Bale may deliver edited updates; we handle them separately

    # for lifecycle sync

    edited = data.get("edited_message")

    if isinstance(edited, dict) and edited.get("text"):

        # Return the edited message for processing, but we'll need

        # to signal that this is an edit event

        edited["_is_edited"] = True

        return edited



    return None





def _extract_command_text(message: Dict[str, Any]) -> str:

    text = str(message.get("text") or "").strip()



    if not text:

        # Bale bot commands may arrive as entities over captions.

        caption = str(message.get("caption") or "").strip()



        if caption.startswith("/"):

            text = caption



    return text





def _is_bot_command(message: Dict[str, Any], text: str) -> bool:

    if not text.startswith("/"):

        return False



    entities = message.get("entities") or []



    for entity in entities:

        if (

            isinstance(entity, dict)

            and entity.get("type") == "bot_command"

            and int(entity.get("offset") or 0) == 0

        ):

            return True



    # Fallback for Bale clients that omit entities: leading slash

    # with a valid command shape.

    first = text.split(" ")[0]

    return first.startswith("/") and len(first) > 1





def handle_bale_update(

    data: Dict[str, Any],

) -> Tuple[Dict[str, Any], int]:

    """Process one Bale update through the shared application core.



    Returns a JSON-serializable response tuple. Commands are

    executed by the shared ``handle_command``; non-command text

    and unsupported update kinds are acknowledged without action

    in slice 1 (media, callbacks and editorial flows follow in

    later slices).

    """

    callback_query = _extract_callback_query(data)



    if callback_query is not None:

        return _handle_bale_callback(

            callback_query,

        )



    message = _extract_message(data)



    if message is None:

        return {"ok": True, "handled": False}, 200



    chat = message.get("chat") or {}

    chat_id = chat.get("id")



    if chat_id is None:

        return {"ok": True, "handled": False}, 200



    text = _extract_command_text(message)



    if not _is_bot_command(message, text):

        return _handle_bale_content(

            message,

            chat_id,

        )



    previous_origin = command_handler.CURRENT_ORIGIN
    private_user_context = None



    try:

        command_handler.CURRENT_ORIGIN = "bale"
        sender = message.get("from") or {}
        private_user_context = command_handler.CURRENT_BALE_PRIVATE_USER_ID.set(
            int(chat_id)
            if chat.get("type") == "private"
            and str(sender.get("id")) == str(chat_id)
            else None
        )



        from core.messaging import bind_context



        bind_context(BaleMessagingContext())



        handled = command_handler.handle_command(

            text,

            int(chat_id),

        )



        return {

            "ok": True,

            "handled": bool(handled),

        }, 200

    except Exception as exc:

        logger.exception(

            "❌ Bale command handling failed | chat=%s | %s",

            chat_id,

            exc,

        )

        return {"ok": True, "handled": False}, 200

    finally:

        command_handler.CURRENT_ORIGIN = previous_origin
        if private_user_context is not None:
            command_handler.CURRENT_BALE_PRIVATE_USER_ID.reset(private_user_context)



        from core.messaging import reset_default_context



        reset_default_context()





def _handle_bale_content(

    message: Dict[str, Any],

    chat_id: Any,

) -> Tuple[Dict[str, Any], int]:

    """Feed non-command Bale content into the SHARED pipeline.



    Text, photos, videos, documents, voice/audio and captions all

    enter ``process_incoming_message`` — the exact pipeline the

    Telegram webhook uses — after normalizing the Bale update into

    the Telegram-shaped message the pipeline already understands.

    Media-group aggregation, Editorial detection, Pending Guard,

    #یادداشت / #تحلیل, Smart Summary and publication all stay

    single-sourced in the shared core.

    """

    # Check if this is an edited message for lifecycle sync

    if message.get("_is_edited"):

        # Handle Bale edited_message -> Telegram edit sync

        text = message.get("text", "")

        if text.strip():

            try:

                from core.database import handle_bale_edit_sync

                sync_attempted = handle_bale_edit_sync(

                    chat_id,

                    message.get("message_id", 0),

                    text,

                )

                if sync_attempted:

                    logger.info(

                        f"🔄 Bale edit sync processed | "

                        f"bale={chat_id}:{message.get('message_id')} "

                        f"→ telegram"

                    )

                    # Perform actual Telegram message edit

                    from core.database import get_publication_sync_targets_for_bale_message

                    mapping = get_publication_sync_targets_for_bale_message(

                        chat_id,

                        message.get("message_id", 0)

                    )

                    if mapping and mapping.get("telegram"):

                        telegram_chat_id = mapping.get("telegram")["chat_id"]

                        telegram_message_id = mapping.get("telegram")["message_ids"][0]

                        from core.webhook_handler import edit_message

                        edit_message(

                            int(telegram_chat_id),

                            int(telegram_message_id),

                            text

                        )

                else:

                    logger.info(

                        f"⏭️ Bale edit sync skipped (no mapping or target deleted) | "

                        f"bale={chat_id}:{message.get('message_id')}"

                    )

                # Always consume the edit event, never fall through

                return {"ok": True, "handled": True, "reason": "bale_edit_sync"}, 200

            except Exception as e:

                logger.exception(

                    f"❌ Bale edit sync failed | "

                    f"bale={chat_id}:{message.get('message_id')} | {e}"

                )

                # Always consume the edit event, never fall through

                return {"ok": True, "handled": True, "reason": "bale_edit_sync_error"}, 200



    from core.messaging import bind_context

    from core.messaging import reset_default_context



    previous_origin = command_handler.CURRENT_ORIGIN



    try:

        command_handler.CURRENT_ORIGIN = "bale"



        bind_context(BaleMessagingContext())



        from core.webhook_handler import (

            process_incoming_message,

        )



        response, status = process_incoming_message(

            message,

            "bale-content",

        )



        handled = bool(

            response.get(

                "ok",

                False,

            )

        )



        reason = "content"



        for marker in (

            "editorial_review",

            "admin_instruction",

            "workspace_setup_input",

            "media",

            "translation_input",

            "external_publishable",

        ):

            if response.get(marker):

                reason = marker

                break



        return {

            "ok": True,

            "handled": handled,

            "reason": reason,

        }, 200

    except Exception as exc:

        logger.exception(

            "❌ Bale content handling failed | chat=%s | %s",

            chat_id,

            exc,

        )

        return {"ok": True, "handled": False}, 200

    finally:

        command_handler.CURRENT_ORIGIN = previous_origin



        reset_default_context()





def bale_secret_configured() -> bool:

    return bool(

        os.getenv("BALE_WEBHOOK_SECRET_TOKEN", "").strip()

    )
