from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_review_controller import (
    ExternalReviewController,
)
from core.external_review_state import (
    ExternalReviewStateStore,
)
from core.external_review_telegram import (
    _render_pending_view,
    handle_external_review_telegram_callback,
)


# =========================================================
# HELPERS
# =========================================================


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/news",
        canonical_url="https://example.com/news",
        content_type="article",
        title="عنوان خبر",
        lead="لید خبر",
        body=(
            "پاراگراف اول\n\n"
            "پاراگراف دوم"
        ),
        source_name="Example",
        extraction_confidence=0.95,
    )


def _controller():
    return ExternalReviewController(
        state_store=(
            ExternalReviewStateStore(
                ttl_seconds=1800
            )
        )
    )


def _create_pending(
    controller,
    *,
    review_id="review-1",
    chat_id=12345,
):
    controller.create_pending(
        review_id=review_id,
        chat_id=chat_id,
        content=_content(),
    )


def _callback(
    data,
    *,
    user_id=12345,
    callback_id="cb-1",
):
    return {
        "id": callback_id,
        "data": data,
        "from": {
            "id": user_id,
        },
    }


# =========================================================
# FOREIGN CALLBACK
# =========================================================


def test_foreign_callback_is_not_claimed():
    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "setup:start"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=_controller(),
            req_id="req-1",
        )
    )

    assert handled is False
    assert answers == []
    assert messages == []


# =========================================================
# USER VALIDATION
# =========================================================


def test_missing_user_is_handled():
    answers = []

    callback = {
        "id": "cb-1",
        "data": (
            "extrev:standard:review-1"
        ),
        "from": {},
    }

    handled = (
        handle_external_review_telegram_callback(
            callback_query=callback,
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=_controller(),
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "کاربر قابل تشخیص نیست.",
        )
    ]


# =========================================================
# STANDARD
# =========================================================


def test_standard_callback_is_consumed():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
            req_id="req-1",
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert messages[0][0][0] == 12345

    assert (
        "عنوان خبر"
        in messages[0][0][1]
    )

    assert (
        "لید خبر"
        in messages[0][0][1]
    )

    assert (
        "پاراگراف اول"
        in messages[0][0][1]
    )


# =========================================================
# SHORT
# =========================================================


def test_short_callback_generates_draft_without_publishing(
    monkeypatch,
):
    """
    Requirement: SHORT must generate a caption-safe faithful draft
    and never publish until an explicit approve.
    """

    monkeypatch.setattr(
        "core.external_review_execution.gemini_provider_configured",
        lambda: True,
    )

    from types import SimpleNamespace

    monkeypatch.setattr(
        "core.external_review_execution.summarize_text_safely",
        lambda **kwargs: SimpleNamespace(
            success=True,
            validation_passed=True,
            summary_text="خلاصه کوتاه امن برای کپشن.",
        ),
    )

    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:short:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "خلاصه کوتاه امن برای کپشن."
        in messages[0][0][1]
    )

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert (
        pending.review_stage
        == "short_preview"
    )

    assert (
        pending.draft_text
        == (
            "عنوان خبر\n\n"
            "به گزارش Example، خلاصه کوتاه امن برای کپشن."
        )
    )


def test_short_callback_fails_closed_without_publishing_when_gemini_unavailable():
    """
    Fail-closed: if Gemini is not configured, no draft is generated
    and nothing is published; the pending review stays intact so the
    user can retry.
    """

    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:short:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True
    assert len(messages) == 1
    assert "ممکن نشد" in messages[0][0][1]

    # Pending state remains intact for retry (stage unchanged).
    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.review_stage == "select"


# =========================================================
# EDITORIAL
# =========================================================


def test_editorial_callback_reports_shared_editorial_path():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:editorial:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "انتخاب ثبت شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "مسیر تحریریه در حال حاضر"
        in messages[0][0][1]
    )

    assert (
        "در دسترس نیست"
        in messages[0][0][1]
    )


def test_editorial_callback_queues_pending_review_with_manual_media():
    controller = _controller()
    _create_pending(controller)
    controller.state_store.update_manual_image_state(
        review_id="review-1",
        chat_id=12345,
        manual_image_source="replace",
        manual_image_file_id="manual-photo-1",
        manual_image_waiting=False,
    )

    queued = []
    executed = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:editorial:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
        api_url="https://api.telegram.test",
        execute_decision=(
            lambda **kwargs: executed.append(kwargs)
        ),
        queue_editorial_review=(
            lambda **kwargs: queued.append(kwargs) or True
        ),
    )

    assert handled is True
    assert executed == []
    assert len(queued) == 1
    assert queued[0]["forced_content_type"] == (
        "news_analysis"
    )
    assert queued[0]["source_key"] == (
        "external:review-1"
    )
    assert queued[0]["media_files"] == [
        {
            "type": "photo",
            "file_id": "manual-photo-1",
        },
    ]


# =========================================================
# CANCEL
# =========================================================


def test_cancel_callback_is_acknowledged():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:cancel:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "لغو شد.",
        )
    ]

    assert len(messages) == 1

    assert (
        "لغو شد"
        in messages[0][0][1]
    )


# =========================================================
# INVALID CALLBACK
# =========================================================


def test_invalid_external_callback_is_handled_safely():
    controller = _controller()

    _create_pending(
        controller
    )

    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:unknown:review-1"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            "دستور بررسی نامعتبر است.",
        )
    ]


# =========================================================
# EXPIRED / MISSING REVIEW
# =========================================================


def test_missing_review_is_handled_safely():
    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:not-found"
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=_controller(),
            req_id="req-1",
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )
    ]


# =========================================================
# OWNERSHIP
# =========================================================


def test_user_cannot_consume_another_users_review():
    controller = _controller()

    _create_pending(
        controller,
        chat_id=111,
    )

    answers = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1",
                    user_id=222,
                )
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (
                        callback_id,
                        text,
                    )
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                None
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert answers == [
        (
            "cb-1",
            (
                "این پیش‌نمایش منقضی شده "
                "یا دیگر در دسترس نیست."
            ),
        )
    ]

    pending = (
        controller.get_pending(
            review_id="review-1",
            chat_id=111,
        )
    )

    assert pending is not None


# =========================================================
# NO PUBLICATION
# =========================================================


def test_telegram_adapter_does_not_publish():
    controller = _controller()

    _create_pending(
        controller
    )

    calls = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=(
                _callback(
                    "extrev:standard:review-1"
                )
            ),
            answer_callback_query=(
                lambda *args, **kwargs:
                None
            ),
            send_message=(
                lambda *args, **kwargs:
                calls.append(
                    (
                        args,
                        kwargs,
                    )
                )
            ),
            controller=controller,
        )
    )

    assert handled is True

    assert len(calls) == 1


# =========================================================
# SHORT: EDIT / REGENERATE / APPROVE
# =========================================================


def test_short_edit_sets_awaiting_flag_without_publishing():
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه اول",
    )

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_edit:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True
    assert answers[0][1] == "متن جایگزین خود را ارسال کنید."

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.awaiting_edit_text is True
    # Draft body is untouched until the edited text actually arrives.
    assert pending.draft_text == "خلاصه اول"


def test_short_regenerate_replaces_draft_with_new_summary(monkeypatch):
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه قدیمی",
    )

    monkeypatch.setattr(
        "core.external_review_execution.gemini_provider_configured",
        lambda: True,
    )

    from types import SimpleNamespace

    monkeypatch.setattr(
        "core.external_review_execution.summarize_text_safely",
        lambda **kwargs: SimpleNamespace(
            success=True,
            validation_passed=True,
            summary_text="خلاصه جدید بازتولید شده",
        ),
    )

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_regenerate:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert (
        pending.draft_text
        == (
            "عنوان خبر\n\n"
            "به گزارش Example، خلاصه جدید بازتولید شده"
        )
    )
    assert pending.review_stage == "short_preview"


def test_short_regenerate_failure_keeps_previous_draft(monkeypatch):
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه قدیمی",
    )

    messages = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_regenerate:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: messages.append(
                (args, kwargs)
            )
        ),
        controller=controller,
    )

    assert handled is True
    assert "ممکن نشد" in messages[-1][0][1]

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    # Gemini unconfigured -> fail closed, previous draft preserved.
    assert pending.draft_text == "خلاصه قدیمی"


def test_short_approve_publishes_draft_and_consumes_pending():
    from types import SimpleNamespace

    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه نهایی برای انتشار",
    )

    executed = []

    def fake_execute(*, decision, api_url):
        executed.append(decision)
        return SimpleNamespace(published=True)

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_approve:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
        api_url="https://api.telegram.test",
        execute_decision=fake_execute,
    )

    assert handled is True
    assert len(executed) == 1
    assert executed[0].review.body == "خلاصه نهایی برای انتشار"
    assert executed[0].review.title == ""
    assert executed[0].review.lead == ""
    assert answers[-1] == ("cb-1", "منتشر شد.")

    # Pending state is consumed after a successful publish.
    import pytest as _pytest
    from core.external_review_state import ExternalReviewNotFound

    with _pytest.raises(ExternalReviewNotFound):
        controller.get_pending(
            review_id="review-1",
            chat_id=12345,
        )


def test_short_approve_failure_keeps_pending_for_retry():
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه نهایی",
    )

    def failing_execute(*, decision, api_url):
        raise RuntimeError("boom")

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_approve:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
        api_url="https://api.telegram.test",
        execute_decision=failing_execute,
    )

    assert handled is True
    assert "خطا" in answers[-1][1]

    # Pending review remains intact for retry.
    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )
    assert pending.draft_text == "خلاصه نهایی"


def test_short_approve_blocks_publication_when_draft_is_empty():
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="",
    )

    executed = []

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:short_approve:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
        api_url="https://api.telegram.test",
        execute_decision=(
            lambda **kwargs: executed.append(kwargs)
        ),
    )

    assert handled is True
    assert executed == []
    assert "متنی برای انتشار وجود ندارد" in answers[-1][1]


def test_short_preview_cancel_removes_pending_review():
    controller = _controller()
    _create_pending(controller)

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="short_preview",
        draft_text="خلاصه",
    )

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:cancel:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True

    import pytest as _pytest
    from core.external_review_state import ExternalReviewNotFound

    with _pytest.raises(ExternalReviewNotFound):
        controller.get_pending(
            review_id="review-1",
            chat_id=12345,
        )


# =========================================================
# PARAGRAPHS: PAGINATED, PERSISTENT, TRUE MULTI-SELECT
# =========================================================


def _paragraph_controller():
    controller = _controller()
    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=NormalizedExternalContent(
            source_type="web_article",
            source_url="https://example.com/news",
            canonical_url="https://example.com/news",
            content_type="article",
            title="عنوان خبر",
            lead="لید خبر",
            body="\n\n".join(
                f"پاراگراف شماره {index}"
                for index in range(9)
            ),
            source_name="Example",
            extraction_confidence=0.95,
        ),
    )
    return controller


def test_paragraph_start_transitions_to_select_stage():
    controller = _paragraph_controller()

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_start:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.review_stage == "paragraph_select"
    assert pending.paragraph_selected_indexes == ()
    assert pending.paragraph_page == 0


def test_paragraph_toggle_persists_selection_across_pages():
    controller = _paragraph_controller()

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_select",
    )

    # Select paragraph 1 on page 0.
    handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_toggle:review-1:1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    # Move to page 1.
    handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_page:review-1:1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )
    assert pending.paragraph_page == 1
    # Selection from the previous page persists.
    assert pending.paragraph_selected_indexes == (1,)

    # Select paragraph 7 (page 1) too, then toggle 1 off again.
    handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_toggle:review-1:7"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )
    handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_toggle:review-1:1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )
    assert pending.paragraph_selected_indexes == (7,)


def test_paragraph_selector_bounds_preview_without_changing_content():
    controller = _controller()
    long_paragraph = "واژه " * 300
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/long",
        canonical_url="https://example.com/long",
        content_type="article",
        title="عنوان خبر",
        lead="",
        body="\n\n".join(long_paragraph for _ in range(7)),
        source_name="Example",
        extraction_confidence=0.95,
    )
    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=content,
    )
    pending = controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_select",
        paragraph_selected_indexes=(0, 6),
    )

    view = _render_pending_view(pending)

    assert len(view.text) <= 3500
    assert len(view.text) < len(long_paragraph) * 6
    assert pending.content.body == content.body
    assert pending.paragraph_selected_indexes == (0, 6)


def test_paragraph_confirm_blocks_when_nothing_selected():
    controller = _paragraph_controller()

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_select",
    )

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_confirm:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True
    assert "حداقل یک پاراگراف" in answers[-1][1]

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )
    # Blocked: stage stays at selection, nothing to publish yet.
    assert pending.review_stage == "paragraph_select"


def test_paragraph_confirm_builds_draft_with_headline_and_source_order():
    controller = _paragraph_controller()

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_select",
        paragraph_selected_indexes=(5, 1),
    )

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_confirm:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.review_stage == "paragraph_preview"

    # Headline present, only the two selected paragraphs, in
    # ascending (source) order regardless of selection click order.
    assert "عنوان خبر" in pending.draft_text
    para1_pos = pending.draft_text.index("پاراگراف شماره 1")
    para5_pos = pending.draft_text.index("پاراگراف شماره 5")
    assert para1_pos < para5_pos
    assert "پاراگراف شماره 0" not in pending.draft_text
    assert "پاراگراف شماره 2" not in pending.draft_text


def test_paragraph_approve_publishes_only_selected_paragraphs():
    from types import SimpleNamespace

    controller = _paragraph_controller()

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_preview",
        draft_text="عنوان خبر\n\nپاراگراف شماره 3",
    )

    executed = []

    def fake_execute(*, decision, api_url):
        executed.append(decision)
        return SimpleNamespace(published=True)

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_approve:review-1"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
        api_url="https://api.telegram.test",
        execute_decision=fake_execute,
    )

    assert handled is True
    assert len(executed) == 1
    assert executed[0].review.body == (
        "عنوان خبر\n\nپاراگراف شماره 3"
    )

    import pytest as _pytest
    from core.external_review_state import ExternalReviewNotFound

    with _pytest.raises(ExternalReviewNotFound):
        controller.get_pending(
            review_id="review-1",
            chat_id=12345,
        )


def test_paragraph_edit_sets_awaiting_flag():
    controller = _paragraph_controller()

    controller.state_store.update_review_stage(
        review_id="review-1",
        chat_id=12345,
        review_stage="paragraph_preview",
        draft_text="عنوان خبر\n\nپاراگراف شماره 3",
    )

    answers = []

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:para_edit:review-1"
        ),
        answer_callback_query=(
            lambda callback_id, text: answers.append(
                (callback_id, text)
            )
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        controller=controller,
    )

    assert handled is True
    assert answers[0][1] == "متن جایگزین خود را ارسال کنید."

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )
    assert pending.awaiting_edit_text is True
