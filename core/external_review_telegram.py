"""Telegram adapter for external-content review callbacks."""

from __future__ import annotations

import logging
import os

from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
)

from core.external_review_callback import (
    ExternalReviewCallbackError,
    handle_external_review_callback,
)
from core.external_review_controller import (
    DEFAULT_EXTERNAL_REVIEW_CONTROLLER,
    ExternalReviewController,
)
from core.external_review_state import (
    PendingExternalReview,
    _plain_value,
    _media_to_dict,
)


logger = logging.getLogger(__name__)


# =========================================================
# PREVIEW SURFACE HELPERS
# =========================================================


def _control_message_id(
    callback_query: Dict[str, Any],
    pending: Optional[
        PendingExternalReview
    ],
) -> Optional[int]:
    """
    Resolve the message that owns the review keyboard.

    The callback message identifies the control message directly.
    The persisted preview ref covers cases where Telegram omits the
    message envelope (or the callback arrived on the media panel).
    """

    message = (
        callback_query.get(
            "message",
            {},
        )
        or {}
    )

    try:
        message_id = int(
            message.get(
                "message_id"
            )
        )

        if message_id > 0:
            return message_id

    except (
        TypeError,
        ValueError,
    ):
        pass

    if pending is not None:
        return pending.preview_message_id

    return None


def _render_pending_view(
    pending: PendingExternalReview,
):
    from core.external_content_review import (
        build_external_content_preview,
    )
    from core.external_review_preview import (
        build_external_review_paragraph_preview,
        build_external_review_paragraph_select_view,
        build_external_review_preview,
        build_external_review_short_preview,
    )
    from core.external_review_state import (
        REVIEW_STAGE_PARAGRAPH_PREVIEW,
        REVIEW_STAGE_PARAGRAPH_SELECT,
        REVIEW_STAGE_SHORT_PREVIEW,
    )

    preview = build_external_content_preview(
        pending.content
    )

    if (
        pending.review_stage
        == REVIEW_STAGE_SHORT_PREVIEW
    ):
        return build_external_review_short_preview(
            review_id=pending.review_id,
            content=pending.content,
            preview=preview,
            draft_text=(
                pending.draft_text
            ),
            awaiting_edit_text=(
                pending.awaiting_edit_text
            ),
            selected_media_indexes=(
                pending.selected_media_indexes
            ),
            media_selection_explicit=(
                pending.media_selection_explicit
            ),
            manual_image_source=(
                pending.manual_image_source
            ),
            manual_image_file_id=(
                pending.manual_image_file_id
            ),
        )

    if (
        pending.review_stage
        == REVIEW_STAGE_PARAGRAPH_SELECT
    ):
        return build_external_review_paragraph_select_view(
            review_id=pending.review_id,
            content=pending.content,
            preview=preview,
            paragraph_page=(
                pending.paragraph_page
            ),
            paragraph_selected_indexes=(
                pending.paragraph_selected_indexes
            ),
            selected_media_indexes=(
                pending.selected_media_indexes
            ),
            media_selection_explicit=(
                pending.media_selection_explicit
            ),
            manual_image_source=(
                pending.manual_image_source
            ),
            manual_image_file_id=(
                pending.manual_image_file_id
            ),
        )

    if (
        pending.review_stage
        == REVIEW_STAGE_PARAGRAPH_PREVIEW
    ):
        return build_external_review_paragraph_preview(
            review_id=pending.review_id,
            content=pending.content,
            preview=preview,
            draft_text=(
                pending.draft_text
            ),
            awaiting_edit_text=(
                pending.awaiting_edit_text
            ),
            selected_media_indexes=(
                pending.selected_media_indexes
            ),
            media_selection_explicit=(
                pending.media_selection_explicit
            ),
            manual_image_source=(
                pending.manual_image_source
            ),
            manual_image_file_id=(
                pending.manual_image_file_id
            ),
        )

    return build_external_review_preview(
        review_id=pending.review_id,
        content=pending.content,
        preview=preview,
        selected_media_indexes=(
            pending.selected_media_indexes
        ),
        media_selection_explicit=(
            pending.media_selection_explicit
        ),
        media_presentation_mode=(
            pending.media_presentation_mode
        ),
        manual_image_source=(
            pending.manual_image_source
        ),
        manual_image_file_id=(
            pending.manual_image_file_id
        ),
        manual_image_waiting=(
            pending.manual_image_waiting
        ),
    )


def _staging_chat_id() -> str:
    return str(
        os.getenv(
            "EXTERNAL_MEDIA_STAGING_CHAT_ID",
            "",
        )
        or ""
    ).strip()


def _refresh_preview(
    *,
    callback_query: Dict[str, Any],
    pending: PendingExternalReview,
    chat_id: int,
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ],
    controller: ExternalReviewController,
    req_id: str,
) -> None:
    """
    Edit the existing review surface after a state change.

    Fail-soft: when the control message cannot be edited (missing
    identity or API rejection) a single fresh control message is
    sent so the review never becomes unusable.
    """

    if telegram_api is None:
        return

    from core.external_review_telegram_panel import (
        edit_control_message,
        reconcile_media_panel,
        send_control_message,
    )

    view = _render_pending_view(
        pending
    )

    control_id = _control_message_id(
        callback_query,
        pending,
    )

    panel_result = reconcile_media_panel(
        telegram_api=telegram_api,
        chat_id=chat_id,
        staging_chat_id=_staging_chat_id(),
        media=view.media,
        current_message_ids=(
            pending.preview_media_message_ids
        ),
        staged_file_ids=(
            view.media_file_ids
            or pending.preview_media_file_ids
        ),
    )

    edited = edit_control_message(
        telegram_api=telegram_api,
        chat_id=chat_id,
        message_id=control_id,
        text=view.text,
        reply_markup=view.reply_markup,
    )

    if not edited:
        fallback_id = send_control_message(
            telegram_api=telegram_api,
            chat_id=chat_id,
            text=view.text,
            reply_markup=view.reply_markup,
        )

        if fallback_id:
            control_id = fallback_id

    merged_file_ids = list(
        pending.preview_media_file_ids
    )

    if not view.media_file_ids:
        if len(merged_file_ids) < len(
            pending.content.media
        ):
            merged_file_ids.extend(
                [""]
                * (
                    len(pending.content.media)
                    - len(merged_file_ids)
                )
            )

        for position, file_id in (
            panel_result
            .file_ids_by_position
            .items()
        ):
            if 0 <= position < len(
                merged_file_ids
            ):
                merged_file_ids[position] = (
                    str(file_id or "")
                )

    try:
        controller.state_store.update_preview_message_refs(
            review_id=pending.review_id,
            chat_id=chat_id,
            preview_message_id=control_id,
            preview_media_message_ids=(
                panel_result.message_ids
            ),
            preview_media_file_ids=tuple(
                merged_file_ids
            ),
        )

    except Exception as exc:
        logger.exception(
            (
                "[%s] External review preview refs "
                "could not be persisted after refresh | "
                "review_id=%s | %s"
            ),
            req_id,
            pending.review_id,
            exc,
        )


def refresh_external_review_preview(
    *,
    pending: PendingExternalReview,
    chat_id: int,
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ],
    controller: ExternalReviewController,
    req_id: str,
) -> None:
    _refresh_preview(
        callback_query={},
        pending=pending,
        chat_id=chat_id,
        telegram_api=telegram_api,
        controller=controller,
        req_id=req_id,
    )


def _finalize_preview(
    *,
    callback_query: Dict[str, Any],
    pending: Optional[
        PendingExternalReview
    ],
    chat_id: int,
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ],
    text: str,
) -> None:
    """
    Move the preview surface into its terminal state.

    The control message loses its keyboard and shows the outcome;
    the media panel stays visible for reference.
    """

    if telegram_api is None:
        return

    from core.external_review_telegram_panel import (
        edit_control_message,
    )

    edit_control_message(
        telegram_api=telegram_api,
        chat_id=chat_id,
        message_id=_control_message_id(
            callback_query,
            pending,
        ),
        text=text,
        reply_markup={
            "inline_keyboard": []
        },
    )


# =========================================================
# SHORT / PARAGRAPHS DRAFT LIFECYCLE
#
# approve / edit / regenerate (SHORT only) / cancel.
#
# These callbacks operate on a review that already has a rendered
# draft (or is being paginated toward one). They are handled
# separately from the pure, deterministic `external_review_callback`
# dispatch because generating/regenerating a SHORT draft calls the
# existing shared Smart Summary (a side effect), and because
# approving a draft must publish exactly the (possibly edited) draft
# text instead of recomputing it from the original content.
#
# Nothing publishes here except the explicit "*_approve" actions.
# =========================================================


_DRAFT_LIFECYCLE_ACTIONS = frozenset(
    {
        "para_start",
        "para_toggle",
        "para_page",
        "para_confirm",
        "para_edit",
        "para_approve",
        "short_edit",
        "short_regenerate",
        "short_approve",
    }
)


def _resolve_media_selection_args(
    pending: PendingExternalReview,
):
    from core.external_content_review import (
        ExternalMediaMode,
    )

    if not pending.media_selection_explicit:
        return (
            ExternalMediaMode.DEFAULT,
            (),
        )

    if not pending.selected_media_indexes:
        return (
            ExternalMediaMode.NONE,
            (),
        )

    return (
        ExternalMediaMode.SELECTED,
        tuple(
            pending.selected_media_indexes
        ),
    )


def _build_approved_draft_decision(
    *,
    controller: ExternalReviewController,
    pending: PendingExternalReview,
):
    """
    Build the final publication decision for an approved SHORT or
    PARAGRAPHS draft.

    Media resolution is regained through the existing deterministic
    STANDARD selection (same persistent media/manual-image state as
    every other final action); the text is then replaced with the
    approved draft exactly as shown (possibly edited by the user).
    """

    from dataclasses import replace as _dc_replace

    from core.external_content_review import (
        ExternalReviewMode,
        ExternalReviewSelection,
    )

    media_mode, media_indexes = (
        _resolve_media_selection_args(
            pending
        )
    )

    selection = ExternalReviewSelection(
        mode=ExternalReviewMode.STANDARD,
        media_mode=media_mode,
        media_indexes=media_indexes,
    )

    decision = controller.apply_selection(
        review_id=pending.review_id,
        chat_id=pending.chat_id,
        selection=selection,
    )

    final_review = _dc_replace(
        decision.review,
        title="",
        lead="",
        body=str(
            pending.draft_text
            or ""
        ).strip(),
        requires_smart_summary=False,
        requires_editorial_rewrite=False,
    )

    return _dc_replace(
        decision,
        review=final_review,
    )


def _publish_approved_draft(
    *,
    pending: PendingExternalReview,
    controller: ExternalReviewController,
    api_url: str,
    execute_decision: Optional[
        Callable[..., Any]
    ],
    callback_query: Dict[str, Any],
    callback_id: str,
    chat_id: int,
    answer_callback_query: Callable[
        [str, str],
        Any,
    ],
    send_message: Callable[..., Any],
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ],
    req_id: str,
) -> bool:
    if not str(
        pending.draft_text
        or ""
    ).strip():
        answer_callback_query(
            callback_id,
            "متنی برای انتشار وجود ندارد.",
        )

        return True

    try:
        final_decision = (
            _build_approved_draft_decision(
                controller=controller,
                pending=pending,
            )
        )

    except Exception as exc:
        logger.exception(
            (
                "[%s] External review draft "
                "approval failed to prepare "
                "publication | review_id=%s | %s"
            ),
            req_id,
            pending.review_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            "آماده‌سازی انتشار با خطا روبرو شد.",
        )

        return True

    if execute_decision is None:
        answer_callback_query(
            callback_id,
            "امکان انتشار در این پیکربندی وجود ندارد.",
        )

        return True

    try:
        execution = execute_decision(
            decision=final_decision,
            api_url=api_url,
        )

    except Exception as exc:
        logger.exception(
            (
                "[%s] External review draft "
                "publication failed | "
                "review_id=%s | %s"
            ),
            req_id,
            pending.review_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            "انتشار مطلب با خطا روبرو شد.",
        )

        return True

    if not getattr(
        execution,
        "published",
        False,
    ):
        answer_callback_query(
            callback_id,
            "انتشار مطلب با خطا روبرو شد.",
        )

        return True

    try:
        controller.consume_after_success(
            review_id=pending.review_id,
            chat_id=chat_id,
        )

    except Exception as exc:
        logger.exception(
            (
                "[%s] External review draft "
                "published but pending-state "
                "cleanup failed | review_id=%s | %s"
            ),
            req_id,
            pending.review_id,
            exc,
        )

    answer_callback_query(
        callback_id,
        "منتشر شد.",
    )

    if telegram_api is not None:
        _finalize_preview(
            callback_query=callback_query,
            pending=None,
            chat_id=chat_id,
            telegram_api=telegram_api,
            text="✅ مطلب با موفقیت منتشر شد.",
        )

    else:
        send_message(
            chat_id,
            "✅ مطلب با موفقیت منتشر شد.",
        )

    return True


def _handle_draft_lifecycle_action(
    *,
    action: str,
    review_id: str,
    argument: str,
    chat_id: int,
    callback_id: str,
    callback_query: Dict[str, Any],
    answer_callback_query: Callable[
        [str, str],
        Any,
    ],
    send_message: Callable[..., Any],
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ],
    controller: ExternalReviewController,
    api_url: str,
    execute_decision: Optional[
        Callable[..., Any]
    ],
    req_id: str,
) -> bool:
    from core.external_review_execution import (
        ExternalReviewExecutionError,
        generate_external_review_short_summary_text,
    )
    from core.external_review_state import (
        ExternalReviewExpired,
        ExternalReviewNotFound,
        REVIEW_STAGE_PARAGRAPH_PREVIEW,
        REVIEW_STAGE_PARAGRAPH_SELECT,
        REVIEW_STAGE_SHORT_PREVIEW,
    )

    try:
        pending = controller.get_pending(
            review_id=review_id,
            chat_id=chat_id,
        )

    except (
        ExternalReviewNotFound,
        ExternalReviewExpired,
    ):
        answer_callback_query(
            callback_id,
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )

        return True

    # =====================================================
    # PARAGRAPH SELECTION (state-only, non-terminal)
    # =====================================================

    if action == "para_start":
        updated = (
            controller.state_store
            .update_review_stage(
                review_id=review_id,
                chat_id=chat_id,
                review_stage=(
                    REVIEW_STAGE_PARAGRAPH_SELECT
                ),
                paragraph_selected_indexes=(),
                paragraph_page=0,
                awaiting_edit_text=False,
            )
        )

        answer_callback_query(
            callback_id,
            "انتخاب پاراگراف‌ها را شروع کنید.",
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    if action == "para_toggle":
        try:
            index = int(
                argument
            )

        except (
            TypeError,
            ValueError,
        ):
            answer_callback_query(
                callback_id,
                "شماره پاراگراف نامعتبر است.",
            )

            return True

        current = set(
            pending.paragraph_selected_indexes
        )

        if index in current:
            current.discard(
                index
            )

        else:
            current.add(
                index
            )

        try:
            updated = (
                controller.state_store
                .update_review_stage(
                    review_id=review_id,
                    chat_id=chat_id,
                    paragraph_selected_indexes=tuple(
                        sorted(
                            current
                        )
                    ),
                )
            )

        except Exception as exc:
            logger.warning(
                (
                    "[%s] External review paragraph "
                    "toggle rejected | review_id=%s | %s"
                ),
                req_id,
                review_id,
                exc,
            )

            answer_callback_query(
                callback_id,
                "شماره پاراگراف نامعتبر است.",
            )

            return True

        answer_callback_query(
            callback_id,
            "انتخاب ثبت شد.",
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    if action == "para_page":
        try:
            page = int(
                argument
            )

        except (
            TypeError,
            ValueError,
        ):
            page = 0

        updated = (
            controller.state_store
            .update_review_stage(
                review_id=review_id,
                chat_id=chat_id,
                paragraph_page=page,
            )
        )

        answer_callback_query(
            callback_id,
            "صفحه تغییر کرد.",
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    if action == "para_confirm":
        if not pending.paragraph_selected_indexes:
            answer_callback_query(
                callback_id,
                (
                    "حداقل یک پاراگراف "
                    "را انتخاب کنید."
                ),
            )

            return True

        from core.external_content_review import (
            ExternalReviewMode,
            ExternalReviewSelection,
        )

        media_mode, media_indexes = (
            _resolve_media_selection_args(
                pending
            )
        )

        selection = ExternalReviewSelection(
            mode=(
                ExternalReviewMode.PARAGRAPHS
            ),
            media_mode=media_mode,
            media_indexes=media_indexes,
            paragraph_indexes=tuple(
                sorted(
                    pending.paragraph_selected_indexes
                )
            ),
        )

        try:
            decision = (
                controller.apply_selection(
                    review_id=review_id,
                    chat_id=chat_id,
                    selection=selection,
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review paragraph "
                    "confirm failed | review_id=%s | %s"
                ),
                req_id,
                review_id,
                exc,
            )

            answer_callback_query(
                callback_id,
                "آماده‌سازی پیش‌نمایش با خطا روبرو شد.",
            )

            return True

        draft_parts = [
            part
            for part in (
                decision.review.title,
                decision.review.lead,
                decision.review.body,
            )
            if part
        ]

        draft_text = "\n\n".join(
            draft_parts
        ).strip()

        updated = (
            controller.state_store
            .update_review_stage(
                review_id=review_id,
                chat_id=chat_id,
                review_stage=(
                    REVIEW_STAGE_PARAGRAPH_PREVIEW
                ),
                draft_text=draft_text,
                awaiting_edit_text=False,
            )
        )

        answer_callback_query(
            callback_id,
            "پیش‌نمایش آماده شد.",
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    # =====================================================
    # EDIT REQUEST (SHORT and PARAGRAPHS share this: the next
    # same-chat text message replaces the draft)
    # =====================================================

    if action in (
        "short_edit",
        "para_edit",
    ):
        updated = (
            controller.state_store
            .update_review_stage(
                review_id=review_id,
                chat_id=chat_id,
                awaiting_edit_text=True,
            )
        )

        answer_callback_query(
            callback_id,
            "متن جایگزین خود را ارسال کنید.",
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    # =====================================================
    # SHORT REGENERATE (re-runs the existing shared Smart
    # Summary against the ORIGINAL source text, never the
    # previous draft, to avoid compounding drift)
    # =====================================================

    if action == "short_regenerate":
        from core.external_content_review import (
            ExternalReviewMode,
            ExternalReviewSelection,
        )

        media_mode, media_indexes = (
            _resolve_media_selection_args(
                pending
            )
        )

        selection = ExternalReviewSelection(
            mode=ExternalReviewMode.SHORT,
            media_mode=media_mode,
            media_indexes=media_indexes,
        )

        answer_callback_query(
            callback_id,
            "در حال بازتولید نسخه کوتاه ...",
        )

        try:
            decision = (
                controller.apply_selection(
                    review_id=review_id,
                    chat_id=chat_id,
                    selection=selection,
                )
            )

            summary_text = (
                generate_external_review_short_summary_text(
                    decision
                )
            )

        except ExternalReviewExecutionError as exc:
            logger.warning(
                (
                    "[%s] External review SHORT "
                    "regenerate failed | "
                    "review_id=%s | %s"
                ),
                req_id,
                review_id,
                exc,
            )

            send_message(
                chat_id,
                (
                    "⚠️ بازتولید نسخه کوتاه ممکن نشد.\n\n"
                    "پیش‌نمایش قبلی شما محفوظ است."
                ),
            )

            return True

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review SHORT "
                    "regenerate failed unexpectedly | "
                    "review_id=%s | %s"
                ),
                req_id,
                review_id,
                exc,
            )

            send_message(
                chat_id,
                "⚠️ بازتولید نسخه کوتاه با خطا روبرو شد.",
            )

            return True

        updated = (
            controller.state_store
            .update_review_stage(
                review_id=review_id,
                chat_id=chat_id,
                review_stage=(
                    REVIEW_STAGE_SHORT_PREVIEW
                ),
                draft_text=summary_text,
                awaiting_edit_text=False,
            )
        )

        _refresh_preview(
            callback_query=callback_query,
            pending=updated,
            chat_id=chat_id,
            telegram_api=telegram_api,
            controller=controller,
            req_id=req_id,
        )

        return True

    # =====================================================
    # APPROVE (publishes exactly the shown/edited draft)
    # =====================================================

    if action in (
        "short_approve",
        "para_approve",
    ):
        return _publish_approved_draft(
            pending=pending,
            controller=controller,
            api_url=api_url,
            execute_decision=execute_decision,
            callback_query=callback_query,
            callback_id=callback_id,
            chat_id=chat_id,
            answer_callback_query=answer_callback_query,
            send_message=send_message,
            telegram_api=telegram_api,
            req_id=req_id,
        )

    answer_callback_query(
        callback_id,
        "دستور بررسی نامعتبر است.",
    )

    return True


# =========================================================
# PUBLIC HANDLER
# =========================================================


def handle_external_review_telegram_callback(
    *,
    callback_query: Dict[str, Any],
    answer_callback_query: Callable[
        [str, str],
        Any,
    ],
    send_message: Callable[..., Any],
    controller: Optional[
        ExternalReviewController
    ] = None,
    telegram_api: Optional[
        Callable[..., Mapping[str, Any]]
    ] = None,
    api_url: str = "",
    execute_decision: Optional[
        Callable[..., Any]
    ] = None,
    queue_editorial_review: Optional[
        Callable[..., Any]
    ] = None,
    req_id: str = "",
) -> bool:
    """
    Handle Telegram UI delivery for an external-review callback.

    Returns:
        False:
            callback does not belong to external review.

        True:
            callback belongs to external review and was handled.

    Lifecycle rule:

        create pending
            ↓
        optionally update media selection
            ↓
        choose final content mode
            ↓
        execute decision
            ↓
        publication succeeds
            ↓
        consume pending state

    Media selection is NON-TERMINAL.

    These actions only update review state:

        media
        nomedia

    They MUST NOT:
      - publish
      - summarize
      - run Editorial
      - consume pending state

    Final actions such as standard / short / headline / lead /
    editorial inherit the persistent media selection.

    A failed execution must NOT consume the pending review.
    """

    if not isinstance(
        callback_query,
        dict,
    ):
        return False

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
        or ""
    ).strip()

    if not callback_data.startswith(
        "extrev:"
    ):
        return False

    callback_id = str(
        callback_query.get(
            "id",
            "",
        )
        or ""
    )

    from_user = (
        callback_query.get(
            "from",
            {},
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
            "کاربر قابل تشخیص نیست.",
        )

        return True

    resolved_controller = (
        controller
        if controller is not None
        else DEFAULT_EXTERNAL_REVIEW_CONTROLLER
    )

    # =====================================================
    # SHORT / PARAGRAPHS DRAFT LIFECYCLE
    #
    # These actions never flow through the pure, deterministic
    # `handle_external_review_callback` dispatch: they mutate an
    # already-active draft (or paginate toward one) and, for SHORT,
    # call the existing shared Smart Summary as a side effect.
    # =====================================================

    callback_parts = [
        part.strip()
        for part in callback_data.split(":")
    ]

    if (
        len(callback_parts) >= 3
        and callback_parts[1].lower()
        in _DRAFT_LIFECYCLE_ACTIONS
    ):
        draft_action = (
            callback_parts[1].lower()
        )

        draft_review_id = (
            callback_parts[2]
        )

        draft_argument = (
            callback_parts[3]
            if len(callback_parts) >= 4
            else ""
        )

        if not draft_review_id:
            answer_callback_query(
                callback_id,
                "درخواست نامعتبر است.",
            )

            return True

        return _handle_draft_lifecycle_action(
            action=draft_action,
            review_id=draft_review_id,
            argument=draft_argument,
            chat_id=int(
                user_id
            ),
            callback_id=callback_id,
            callback_query=callback_query,
            answer_callback_query=(
                answer_callback_query
            ),
            send_message=send_message,
            telegram_api=telegram_api,
            controller=resolved_controller,
            api_url=api_url,
            execute_decision=execute_decision,
            req_id=req_id,
        )

    try:
        result = (
            handle_external_review_callback(
                callback_data=callback_data,
                chat_id=int(
                    user_id
                ),
                controller=resolved_controller,
            )
        )

    except ExternalReviewCallbackError as exc:
        logger.warning(
            "[%s] Invalid external review callback | %s",
            req_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            "دستور بررسی نامعتبر است.",
        )

        return True

    except Exception as exc:
        logger.exception(
            "[%s] External review callback failed | %s",
            req_id,
            exc,
        )

        answer_callback_query(
            callback_id,
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )

        return True

    if not result.handled:
        return False

    # =====================================================
    # CANCEL
    # =====================================================

    if result.cancelled is not None:
        answer_callback_query(
            callback_id,
            "لغو شد.",
        )

        cancelled_pending = (
            result.cancelled
        )

        finalized = False

        if telegram_api is not None:
            finalized = True

            _finalize_preview(
                callback_query=callback_query,
                pending=cancelled_pending,
                chat_id=int(
                    user_id
                ),
                telegram_api=telegram_api,
                text=(
                    "❌ بررسی این مطلب لغو شد."
                ),
            )

        if not finalized:
            send_message(
                int(
                    user_id
                ),
                "❌ بررسی این مطلب لغو شد.",
            )

        return True

    # =====================================================
    # NON-TERMINAL MEDIA STATE UPDATE
    # =====================================================

    if result.state_updated:
        pending = (
            result.pending
        )

        answer_callback_query(
            callback_id,
            result.message
            or "انتخاب تصویر ثبت شد.",
        )

        if pending is None:
            return True

        # =============================================
        # EDIT THE EXISTING PREVIEW IN PLACE
        # =============================================
        #
        # Media selection is non-terminal. The review
        # surface (media panel + one control message) is
        # updated in place; no new status messages are
        # created and pending state stays intact.
        # =============================================

        if telegram_api is not None:
            _refresh_preview(
                callback_query=callback_query,
                pending=pending,
                chat_id=int(
                    user_id
                ),
                telegram_api=telegram_api,
                controller=resolved_controller,
                req_id=req_id,
            )

            return True

        # Legacy fallback when no editing capability is
        # available (tests/older callers).

        if (
            pending.media_selection_explicit
            and not pending.selected_media_indexes
        ):
            send_message(
                int(
                    user_id
                ),
                (
                    "🚫 حالت بدون تصویر انتخاب شد.\n\n"
                    "حالا یکی از حالت‌های انتشار "
                    "مثل استاندارد، کوتاه یا تحریریه "
                    "را انتخاب کنید."
                ),
            )

            return True

        if pending.selected_media_indexes:
            selected_numbers = ", ".join(
                str(index + 1)
                for index
                in pending.selected_media_indexes
            )

            send_message(
                int(
                    user_id
                ),
                (
                    "🖼 تصاویر انتخاب‌شده: "
                    f"{selected_numbers}\n\n"
                    "می‌توانید تصاویر دیگری را هم "
                    "اضافه یا حذف کنید، سپس حالت "
                    "انتشار را انتخاب کنید."
                ),
            )

            return True

        answer_callback_query(
            callback_id,
            "انتخاب رسانه ثبت شد.",
        )

        return True

    # =====================================================
    # FINAL DECISION REQUIRED
    # =====================================================

    if result.decision is None:
        answer_callback_query(
            callback_id,
            "درخواست ثبت نشد.",
        )

        return True

    decision = (
        result.decision
    )

    review = (
        decision.review
    )

    # =====================================================
    # SHARED EDITORIAL FLOW
    #
    # Editorial rewrite is intentionally handled BEFORE
    # normal publication execution.
    #
    # It must:
    #   - preserve the selected media
    #   - materialize selected external media
    #   - create a Shared Editorial pending review
    #   - NOT publish immediately
    #   - transfer ownership only after queue success
    # =====================================================

    if (
        decision.requires_editorial_rewrite
    ):
        answer_callback_query(
            callback_id,
            "انتخاب ثبت شد.",
        )

        if queue_editorial_review is None:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ مسیر تحریریه در حال حاضر "
                    "در دسترس نیست."
                ),
            )

            return True

        review_parts = []

        if review.title:
            review_parts.append(
                str(
                    review.title
                ).strip()
            )

        if review.lead:
            review_parts.append(
                str(
                    review.lead
                ).strip()
            )

        if review.body:
            review_parts.append(
                str(
                    review.body
                ).strip()
            )

        editorial_text = "\n\n".join(
            part
            for part in review_parts
            if part
        ).strip()

        if not editorial_text:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ متنی برای بازنویسی "
                    "تحریریه وجود ندارد."
                ),
            )

            return True

        # =================================================
        # PRESERVE SELECTED EXTERNAL MEDIA
        # =================================================
        #
        # review.media contains exactly the media inherited
        # from the persistent External Review selection.
        #
        # External media is still transport-neutral here.
        # Before handing it to the existing Editorial Pending
        # flow, it must be converted to PreparedContent-style
        # media mappings containing reusable Telegram file_id.
        #
        # This staging/materialization step does NOT publish
        # anything to a destination.
        # =================================================

        editorial_media_files = []

        if decision.prepared_files:
            editorial_media_files = list(
                decision.prepared_files
            )

        elif review.media:

            try:
                from core.external_media_factory import (
                    build_external_media_materializer,
                )

                media_materializer = (
                    build_external_media_materializer(
                        api_url=api_url,
                    )
                )

                editorial_media_files = list(
                    media_materializer.build_prepared_files(
                        review.media
                    )
                )

            except Exception as exc:
                logger.exception(
                    (
                        "[%s] External editorial media "
                        "materialization failed | "
                        "review_id=%s | %s"
                    ),
                    req_id,
                    decision.review_id,
                    exc,
                )

                answer_callback_query(
                    callback_id,
                    (
                        "آماده‌سازی تصاویر برای "
                        "بازنویسی تحریریه ناموفق بود."
                    ),
                )

                send_message(
                    int(
                        user_id
                    ),
                    (
                        "⚠️ تصاویر انتخاب‌شده آماده نشدند.\n\n"
                        "متن و انتخاب تصاویر شما محفوظ است "
                        "و می‌توانید دوباره تلاش کنید."
                    ),
                )

                return True

        # =================================================
        # QUEUE INTO EXISTING SHARED EDITORIAL FLOW
        # =================================================

        source = decision.content
        source_metadata = {
            key: getattr(source, key) for key in
            ("source_url", "canonical_url", "source_name", "title", "author", "published_at")
            if getattr(source, key, None)
        }
        source_metadata["metadata"] = _plain_value(source.metadata or {})
        source_metadata["media"] = [
            _media_to_dict(item)
            for item in review.media
        ]
        forward_source = _plain_value((source.metadata or {}).get("forward_source") or {})
        source_title = (source.metadata or {}).get("source_title") or source.source_name
        if source_title:
            forward_source.setdefault("source_title", source_title)
        if (source.metadata or {}).get("source_username"):
            forward_source.setdefault("source_username", source.metadata["source_username"])

        try:
            queued = (
                queue_editorial_review(
                    chat_id=int(
                        user_id
                    ),
                    source_metadata=source_metadata,
                    forward_source=forward_source,
                    text=editorial_text,
                    entities=[],
                    forced_content_type=(
                        "news_analysis"
                    ),
                    media_files=(
                        editorial_media_files
                    ),
                    source_key=(
                        f"external:"
                        f"{decision.review_id}"
                    ),
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External editorial "
                    "queue failed | %s"
                ),
                req_id,
                exc,
            )

            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ ایجاد بررسی تحریریه "
                    "با خطا روبرو شد."
                ),
            )

            return True

        if not queued:
            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ بررسی تحریریه "
                    "ایجاد نشد."
                ),
            )

            return True

        # =================================================
        # OWNERSHIP TRANSFER
        # =================================================
        #
        # Shared Editorial Pending now owns:
        #   - text
        #   - selected media
        #   - confirmation lifecycle
        #
        # The original External Review pending state must
        # therefore be consumed only AFTER the Editorial
        # review has been created successfully.
        # =================================================

        try:
            resolved_controller.consume_after_success(
                review_id=decision.review_id,
                chat_id=decision.chat_id,
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review transferred to "
                    "Editorial but source pending cleanup "
                    "failed | review_id=%s | %s"
                ),
                req_id,
                decision.review_id,
                exc,
            )

        return True

    # =====================================================
    # SHORT DRAFT GENERATION
    #
    # SHORT is intentionally intercepted BEFORE normal execution,
    # exactly like Editorial above: it must generate a caption-safe
    # draft (existing shared Smart Summary) and show it for explicit
    # approve / edit / regenerate / cancel instead of publishing
    # immediately. Nothing is published from this branch.
    # =====================================================

    if (
        decision.requires_smart_summary
    ):
        answer_callback_query(
            callback_id,
            "انتخاب ثبت شد.",
        )

        from core.external_review_execution import (
            ExternalReviewExecutionError,
            generate_external_review_short_summary_text,
        )
        from core.external_review_state import (
            REVIEW_STAGE_SHORT_PREVIEW,
        )

        try:
            summary_text = (
                generate_external_review_short_summary_text(
                    decision
                )
            )

        except ExternalReviewExecutionError as exc:
            logger.warning(
                (
                    "[%s] External review SHORT draft "
                    "generation failed | review_id=%s | %s"
                ),
                req_id,
                decision.review_id,
                exc,
            )

            send_message(
                int(
                    user_id
                ),
                (
                    "⚠️ آماده‌سازی نسخه کوتاه ممکن نشد.\n\n"
                    "متن و انتخاب تصویر شما محفوظ است "
                    "و می‌توانید دوباره تلاش کنید."
                ),
            )

            return True

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review SHORT draft "
                    "generation failed unexpectedly | "
                    "review_id=%s | %s"
                ),
                req_id,
                decision.review_id,
                exc,
            )

            send_message(
                int(
                    user_id
                ),
                "⚠️ آماده‌سازی نسخه کوتاه با خطا روبرو شد.",
            )

            return True

        try:
            updated = (
                resolved_controller
                .state_store
                .update_review_stage(
                    review_id=decision.review_id,
                    chat_id=decision.chat_id,
                    review_stage=(
                        REVIEW_STAGE_SHORT_PREVIEW
                    ),
                    draft_text=summary_text,
                    awaiting_edit_text=False,
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review SHORT draft "
                    "could not be persisted | "
                    "review_id=%s | %s"
                ),
                req_id,
                decision.review_id,
                exc,
            )

            send_message(
                int(
                    user_id
                ),
                "⚠️ ثبت پیش‌نمایش نسخه کوتاه با خطا روبرو شد.",
            )

            return True

        if telegram_api is not None:
            _refresh_preview(
                callback_query=callback_query,
                pending=updated,
                chat_id=int(
                    user_id
                ),
                telegram_api=telegram_api,
                controller=resolved_controller,
                req_id=req_id,
            )

        else:
            send_message(
                int(
                    user_id
                ),
                (
                    "✂️ پیش‌نمایش نسخه کوتاه:\n\n"
                    f"{summary_text}"
                ),
            )

        return True

    # =====================================================
    # OPTIONAL EXECUTION BOUNDARY
    #
    # All normal final modes are executed through the
    # established External Review -> Shared Engine bridge.
    #
    # Editorial rewrite was intentionally intercepted above
    # because it must create another confirmation preview
    # instead of publishing immediately.
    # =====================================================

    if execute_decision is not None:

        try:
            execution = (
                execute_decision(
                    decision=decision,
                    api_url=api_url,
                )
            )

        except Exception as exc:
            logger.exception(
                (
                    "[%s] External review "
                    "execution failed | %s"
                ),
                req_id,
                exc,
            )

            # IMPORTANT:
            # Pending state remains intact.
            # This preserves both:
            #   - selected content mode
            #   - persistent media selection
            #
            # The user can retry after transformation or
            # publication failure.
            answer_callback_query(
                callback_id,
                "انتشار مطلب با خطا روبرو شد.",
            )

            return True

        if getattr(
            execution,
            "published",
            False,
        ):
            # =================================================
            # CONSUME ONLY AFTER SUCCESSFUL PUBLICATION
            # =================================================

            try:
                resolved_controller.consume_after_success(
                    review_id=decision.review_id,
                    chat_id=decision.chat_id,
                )

            except Exception as exc:
                # Publication has already succeeded.
                # Cleanup failure must not be reported as
                # publication failure.
                logger.exception(
                    (
                        "[%s] External review published but "
                        "pending-state cleanup failed | "
                        "review_id=%s chat_id=%s | %s"
                    ),
                    req_id,
                    decision.review_id,
                    decision.chat_id,
                    exc,
                )

                answer_callback_query(
                    callback_id,
                    (
                        "منتشر شد، اما پاک‌سازی "
                        "وضعیت بررسی کامل نشد."
                    ),
                )

                if telegram_api is not None:
                    _finalize_preview(
                        callback_query=callback_query,
                        pending=None,
                        chat_id=int(
                            user_id
                        ),
                        telegram_api=telegram_api,
                        text=(
                            "✅ مطلب با موفقیت منتشر شد.\n\n"
                            "⚠️ وضعیت بررسی به‌طور کامل "
                            "پاک نشد؛ از ارسال دوباره "
                            "همین انتخاب خودداری کنید."
                        ),
                    )

                else:
                    send_message(
                        int(
                            user_id
                        ),
                        (
                            "✅ مطلب با موفقیت منتشر شد.\n\n"
                            "⚠️ وضعیت بررسی به‌طور کامل "
                            "پاک نشد؛ از ارسال دوباره "
                            "همین انتخاب خودداری کنید."
                        ),
                    )

                return True

            answer_callback_query(
                callback_id,
                "منتشر شد.",
            )

            if telegram_api is not None:
                _finalize_preview(
                    callback_query=callback_query,
                    pending=None,
                    chat_id=int(
                        user_id
                    ),
                    telegram_api=telegram_api,
                    text=(
                        "✅ مطلب با موفقیت منتشر شد."
                    ),
                )

            else:
                send_message(
                    int(
                        user_id
                    ),
                    "✅ مطلب با موفقیت منتشر شد.",
                )

            return True

    # =====================================================
    # REVIEW PREVIEW
    # =====================================================

    answer_callback_query(
        callback_id,
        "انتخاب ثبت شد.",
    )

    preview_parts = []

    if review.title:
        preview_parts.append(
            review.title
        )

    if review.lead:
        preview_parts.append(
            review.lead
        )

    if review.body:
        preview_parts.append(
            review.body
        )

    preview_text = "\n\n".join(
        preview_parts
    ).strip()

    if not preview_text:
        preview_text = (
            "انتخاب شما ثبت شد."
        )

    send_message(
        int(
            user_id
        ),
        (
            "✅ انتخاب شما ثبت شد.\n\n"
            f"{preview_text}"
        ),
    )

    return True
