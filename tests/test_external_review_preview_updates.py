from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_review_controller import (
    ExternalReviewController,
)
from core.external_review_state import (
    ExternalReviewStateStore,
)
from core.external_review_telegram import (
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
        media=(
            ExternalMedia(
                type="image",
                source_url=(
                    "https://example.com/1.jpg"
                ),
                position=0,
            ),
            ExternalMedia(
                type="image",
                source_url=(
                    "https://example.com/2.jpg"
                ),
                position=1,
            ),
        ),
    )


def _controller():
    return ExternalReviewController(
        state_store=(
            ExternalReviewStateStore(
                ttl_seconds=1800
            )
        )
    )


def _callback(
    data,
    *,
    user_id=12345,
    callback_id="cb-1",
    message_id=555,
):
    callback = {
        "id": callback_id,
        "data": data,
        "from": {
            "id": user_id,
        },
    }

    if message_id is not None:
        callback["message"] = {
            "message_id": message_id,
            "chat": {
                "id": user_id,
            },
        }

    return callback


class FakeTelegramApi:
    """In-memory Bot API double used by the panel helpers."""

    def __init__(self):
        self.calls = []
        self.next_message_id = 1000
        self.fail_edit = False

    def __call__(self, method, payload):
        payload = dict(payload or {})

        self.calls.append(
            (method, payload)
        )

        if method == "sendMessage":
            self.next_message_id += 1

            return {
                "ok": True,
                "result": {
                    "message_id": (
                        self.next_message_id
                    ),
                },
            }

        if method == "editMessageText":
            if self.fail_edit:
                return {"ok": False}

            return {
                "ok": True,
                "result": True,
            }

        if method == "deleteMessage":
            return {
                "ok": True,
                "result": True,
            }

        return {"ok": True, "result": True}

    def methods(self):
        return [
            method
            for method, _ in self.calls
        ]

    def payloads(self, method):
        return [
            payload
            for item_method, payload in self.calls
            if item_method == method
        ]


# =========================================================
# MEDIA TOGGLE EDITS THE EXISTING PREVIEW
# =========================================================


def test_media_toggle_edits_control_message_in_place():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    answers = []
    messages = []
    api = FakeTelegramApi()

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:0"
            ),
            answer_callback_query=(
                lambda callback_id, text:
                answers.append(
                    (callback_id, text)
                )
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (args, kwargs)
                )
            ),
            telegram_api=api,
            controller=controller,
            req_id="req-1",
        )
    )

    assert handled is True

    # Toast only, no new status message.
    assert answers == [
        (
            "cb-1",
            "تصاویر آلبوم انتشار: 1",
        )
    ]

    assert messages == []

    edits = api.payloads("editMessageText")

    assert len(edits) == 1
    assert edits[0]["message_id"] == 555
    assert edits[0]["chat_id"] == 12345
    assert "تصاویر آلبوم انتشار: 1" in edits[0]["text"]
    assert "inline_keyboard" in edits[0]["reply_markup"]

    # No extra free-standing message was sent.
    assert "sendMessage" not in api.methods()


def test_media_toggle_without_staging_keeps_control_edit():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = FakeTelegramApi()

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True

    # Staging chat is not configured in tests, so no
    # panel is displayed, but the control message still
    # reflects the new selection.
    edits = api.payloads("editMessageText")

    assert len(edits) == 1
    assert "تصاویر آلبوم انتشار: 2" in edits[0]["text"]
    assert "sendPhoto" not in api.methods()
    assert "sendMediaGroup" not in api.methods()


def test_nomedia_marks_preview_without_image():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = FakeTelegramApi()

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:nomedia:review-1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True

    edits = api.payloads("editMessageText")

    assert len(edits) == 1
    assert "بدون تصویر" in edits[0]["text"]

    # Pending review survived: state-only action.
    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.media_selection_explicit is True
    assert pending.selected_media_indexes == ()


def test_manual_waiting_callback_updates_preview_in_place():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = FakeTelegramApi()

    handled = handle_external_review_telegram_callback(
        callback_query=_callback(
            "extrev:manual:review-1:waiting"
        ),
        answer_callback_query=(
            lambda *args, **kwargs: None
        ),
        send_message=(
            lambda *args, **kwargs: None
        ),
        telegram_api=api,
        controller=controller,
    )

    assert handled is True
    edits = api.payloads("editMessageText")
    assert len(edits) == 1
    assert "منتظر دریافت عکس" in edits[0]["text"]


def test_edit_failure_falls_back_to_single_control_message():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = FakeTelegramApi()
    api.fail_edit = True

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:0"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True

    sends = api.payloads("sendMessage")

    assert len(sends) == 1
    assert "تصاویر آلبوم انتشار: 1" in sends[0]["text"]

    # The fallback control message identity is persisted.
    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending.preview_message_id == (
        api.next_message_id
    )


# =========================================================
# TERMINAL STATES
# =========================================================


def test_cancel_edits_preview_to_terminal_state():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    messages = []
    api = FakeTelegramApi()

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:cancel:review-1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (args, kwargs)
                )
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True
    assert messages == []

    edits = api.payloads("editMessageText")

    assert len(edits) == 1
    assert edits[0]["message_id"] == 555
    assert "لغو شد" in edits[0]["text"]
    assert edits[0]["reply_markup"] == {
        "inline_keyboard": []
    }


def test_publish_success_edits_preview_to_terminal_state():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    class _Publication:
        ok = True

    class _Execution:
        published = True
        publication = _Publication()

    api = FakeTelegramApi()
    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:standard:review-1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (args, kwargs)
                )
            ),
            telegram_api=api,
            controller=controller,
            api_url="https://api.example",
            execute_decision=(
                lambda *, decision, api_url:
                _Execution()
            ),
        )
    )

    assert handled is True
    assert messages == []

    edits = api.payloads("editMessageText")

    assert len(edits) == 1
    assert "منتشر شد" in edits[0]["text"]
    assert edits[0]["reply_markup"] == {
        "inline_keyboard": []
    }


def test_publish_failure_preserves_pending_and_preview():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = FakeTelegramApi()

    def _failing_execute(*, decision, api_url):
        raise RuntimeError("boom")

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:standard:review-1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
            api_url="https://api.example",
            execute_decision=_failing_execute,
        )
    )

    assert handled is True

    # No destructive preview edit on failure.
    assert api.payloads("editMessageText") == []

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending is not None


# =========================================================
# LEGACY FALLBACK (NO EDIT CAPABILITY)
# =========================================================


def test_media_toggle_without_telegram_api_keeps_legacy_message():
    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    messages = []

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:0",
                message_id=None,
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs:
                messages.append(
                    (args, kwargs)
                )
            ),
            controller=controller,
        )
    )

    assert handled is True
    assert len(messages) == 1
    assert "تصاویر انتخاب‌شده" in messages[0][0][1]


# =========================================================
# MEDIA PANEL WITH STAGING (END-TO-END SURFACE)
# =========================================================


class StagingTelegramApi(FakeTelegramApi):
    def __init__(self):
        super().__init__()
        self.next_file_id = 0

    def __call__(self, method, payload):
        payload = dict(payload or {})

        if method == "sendPhoto" and (
            "photo_bytes" in payload
        ):
            self.calls.append((method, payload))
            self.next_message_id += 1
            self.next_file_id += 1

            return {
                "ok": True,
                "result": {
                    "message_id": self.next_message_id,
                    "photo": [
                        {
                            "file_id": (
                                "staged-"
                                f"{self.next_file_id}"
                            ),
                        }
                    ],
                },
            }

        if method == "sendMediaGroup":
            self.calls.append((method, payload))
            result = []

            for _ in payload.get("media", []):
                self.next_message_id += 1
                result.append(
                    {"message_id": self.next_message_id}
                )

            return {"ok": True, "result": result}

        return super().__call__(method, payload)


def test_media_toggle_with_staging_displays_and_caches(
    monkeypatch,
):
    monkeypatch.setenv(
        "EXTERNAL_MEDIA_STAGING_CHAT_ID",
        "-1001",
    )

    controller = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=12345,
        content=_content(),
    )

    api = StagingTelegramApi()

    monkeypatch.setattr(
        "core.external_review_telegram_panel."
        "_download_image",
        lambda *, media, max_bytes, fetcher=None:
        b"fake-image-bytes",
    )

    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:0"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True

    # One photo was staged and displayed.
    staging_calls = [
        payload
        for payload in api.payloads("sendPhoto")
        if "photo_bytes" in payload
    ]

    assert len(staging_calls) == 1

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    # Staged file_id persisted for reuse.
    assert pending.preview_media_file_ids[0] == "staged-1"
    assert pending.preview_message_id is not None

    # Toggle image 2 in: only image 2 should be staged now;
    # image 1 must reuse its cached file_id.
    handled = (
        handle_external_review_telegram_callback(
            callback_query=_callback(
                "extrev:media:review-1:1"
            ),
            answer_callback_query=(
                lambda *args, **kwargs: None
            ),
            send_message=(
                lambda *args, **kwargs: None
            ),
            telegram_api=api,
            controller=controller,
        )
    )

    assert handled is True

    staging_calls = [
        payload
        for payload in api.payloads("sendPhoto")
        if "photo_bytes" in payload
    ]

    assert len(staging_calls) == 2

    groups = api.payloads("sendMediaGroup")
    assert len(groups) == 1
    assert [
        item["media"] for item in groups[0]["media"]
    ] == ["staged-1", "staged-2"]

    # No new control message was created across both toggles.
    assert api.payloads("sendMessage") == []
    assert len(api.payloads("editMessageText")) == 2
