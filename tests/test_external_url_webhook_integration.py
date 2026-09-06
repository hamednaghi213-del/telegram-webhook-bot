import sys
import types

from unittest.mock import (
    MagicMock,
    patch,
)

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_resolver import (
    ExternalResolutionResult,
    ExternalSourceKind,
)
from core.external_review_state import (
    DEFAULT_EXTERNAL_REVIEW_STATE_STORE,
)


# =========================================================
# FAKE DATABASE
# =========================================================


fake_database = types.ModuleType(
    "core.database"
)

fake_database.get_tenant = MagicMock(
    return_value={
        "telegram_channel": "@channel"
    }
)

fake_database.get_user_by_telegram_id = MagicMock(
    return_value={
        "id": 1
    }
)

fake_database.get_active_workspace_preference = (
    MagicMock(
        return_value={
            "context_type": "legacy",
            "active_workspace_id": None,
            "legacy_selected": True,
        }
    )
)

fake_database.list_selected_workspace_ids = (
    MagicMock(
        return_value=[]
    )
)


# =========================================================
# FAKE COMMAND HANDLER
# =========================================================


fake_command_handler = types.ModuleType(
    "core.command_handler"
)

fake_command_handler.handle_command = (
    MagicMock()
)


# =========================================================
# REGISTER FAKE MODULES
# =========================================================


sys.modules[
    "core.database"
] = fake_database

sys.modules[
    "core.command_handler"
] = fake_command_handler


# =========================================================
# IMPORT WEBHOOK HANDLER
# =========================================================


from core import webhook_handler


# =========================================================
# FAKE REQUEST
# =========================================================


class FakeRequest:

    def __init__(
        self,
        payload=None,
    ):
        self.payload = payload
        self.headers = {}

    def get_json(
        self,
        silent=True,
    ):
        return self.payload


# =========================================================
# HELPERS
# =========================================================


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url=(
            "https://example.com/news"
        ),
        canonical_url=(
            "https://example.com/news"
        ),
        content_type="article",
        title="عنوان خبر خارجی",
        lead="لید خبر خارجی",
        body=(
            "پاراگراف اول خبر.\n\n"
            "پاراگراف دوم خبر."
        ),
        original_language="fa",
        source_name="Example News",
        extraction_confidence=0.94,
    )


def _resolution():
    return ExternalResolutionResult(
        requested_url=(
            "https://example.com/news"
        ),
        canonical_url=(
            "https://example.com/news"
        ),
        source_kind=(
            ExternalSourceKind.WEB_ARTICLE
        ),
        content=_content(),
    )


def _message(
    text,
    *,
    message_id=100,
    chat_id=1001,
):
    return {
        "update_id": 9001,
        "message": {
            "message_id": message_id,
            "chat": {
                "id": chat_id,
            },
            "text": text,
            "entities": [],
        },
    }


def setup_function():

    sys.modules[
        "core.database"
    ] = fake_database

    sys.modules[
        "core.command_handler"
    ] = fake_command_handler

    fake_database.get_tenant.reset_mock()

    fake_database.get_tenant.return_value = {
        "telegram_channel": "@channel"
    }

    fake_database.get_user_by_telegram_id.reset_mock()

    fake_database.get_user_by_telegram_id.return_value = {
        "id": 1
    }

    fake_database.get_active_workspace_preference.reset_mock()

    fake_database.get_active_workspace_preference.return_value = {
        "context_type": "legacy",
        "active_workspace_id": None,
        "legacy_selected": True,
    }

    fake_database.list_selected_workspace_ids.reset_mock()

    fake_database.list_selected_workspace_ids.return_value = []

    fake_command_handler.handle_command.reset_mock()

    DEFAULT_EXTERNAL_REVIEW_STATE_STORE.reset()


# =========================================================
# STANDALONE URL
# =========================================================


def test_standalone_url_creates_external_review(
    monkeypatch,
):

    sent = []

    fake_request = FakeRequest(
        _message(
            "https://example.com/news"
        )
    )

    monkeypatch.setattr(
        "core.external_content_resolver."
        "ExternalContentResolver.resolve",
        lambda self, url: _resolution(),
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request,
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True,
    ), patch.object(
        webhook_handler,
        "send_message",
        side_effect=(
            lambda *args, **kwargs:
            sent.append(
                (
                    args,
                    kwargs,
                )
            )
        ),
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result["ok"] is True
    assert result["external_content"] is True
    assert result["external_resolved"] is True
    assert result["external_publishable"] is True
    assert result["external_review"] is True

    review_id = result["review_id"]

    assert review_id

    pending = (
        DEFAULT_EXTERNAL_REVIEW_STATE_STORE
        .require(
            review_id=review_id,
            chat_id=1001,
        )
    )

    assert (
        pending.content.title
        == "عنوان خبر خارجی"
    )

    assert len(sent) == 1

    args, kwargs = sent[0]

    assert args[0] == 1001

    assert (
        "پیش‌نمایش مطلب"
        in args[1]
    )

    assert (
        "عنوان خبر خارجی"
        in args[1]
    )

    assert (
        "Example News"
        in args[1]
    )

    assert "reply_markup" in kwargs

    keyboard = (
        kwargs["reply_markup"]
        ["inline_keyboard"]
    )

    callbacks = [
        button["callback_data"]
        for row in keyboard
        for button in row
    ]

    assert (
        f"extrev:standard:{review_id}"
        in callbacks
    )

    assert (
        f"extrev:short:{review_id}"
        in callbacks
    )

    assert (
        f"extrev:editorial:{review_id}"
        in callbacks
    )

    assert (
        f"extrev:cancel:{review_id}"
        in callbacks
    )


# =========================================================
# EMBEDDED URL MUST NOT HIJACK NORMAL NEWS
# =========================================================


def test_embedded_url_does_not_trigger_external_ingestion(
    monkeypatch,
):

    fake_request = FakeRequest(
        _message(
            (
                "این یک خبر عادی است و منبع آن "
                "https://example.com/news است."
            ),
            message_id=101,
        )
    )

    resolver_calls = []

    monkeypatch.setattr(
        "core.external_content_resolver."
        "ExternalContentResolver.resolve",
        (
            lambda self, url:
            resolver_calls.append(url)
        ),
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request,
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True,
    ), patch.object(
        webhook_handler,
        "send_message",
        return_value=True,
    ), patch.object(
        webhook_handler,
        "try_queue_editorial_text_review",
        return_value=False,
    ), patch.object(
        webhook_handler,
        "publish_prepared_text",
        return_value=True,
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result["ok"] is True

    assert resolver_calls == []


# =========================================================
# EXTRACTION FAILURE
# =========================================================


def test_external_resolution_failure_is_fail_closed(
    monkeypatch,
):

    sent = []

    fake_request = FakeRequest(
        _message(
            "https://example.com/broken",
            message_id=102,
        )
    )

    def _raise(
        self,
        url,
    ):
        raise RuntimeError(
            "extraction failed"
        )

    monkeypatch.setattr(
        "core.external_content_resolver."
        "ExternalContentResolver.resolve",
        _raise,
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request,
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True,
    ), patch.object(
        webhook_handler,
        "send_message",
        side_effect=(
            lambda *args, **kwargs:
            sent.append(
                (
                    args,
                    kwargs,
                )
            )
        ),
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result == {
        "ok": True,
        "external_content": True,
        "external_resolved": False,
    }

    assert len(sent) == 1

    assert (
        "استخراج این لینک ممکن نشد"
        in sent[0][0][1]
    )


# =========================================================
# EMPTY EXTRACTION
# =========================================================


def test_non_publishable_external_content_is_not_reviewed(
    monkeypatch,
):

    sent = []

    empty_content = (
        NormalizedExternalContent(
            source_type="web_article",
            source_url=(
                "https://example.com/empty"
            ),
            canonical_url=(
                "https://example.com/empty"
            ),
            extraction_confidence=0.10,
        )
    )

    resolution = ExternalResolutionResult(
        requested_url=(
            "https://example.com/empty"
        ),
        canonical_url=(
            "https://example.com/empty"
        ),
        source_kind=(
            ExternalSourceKind.WEB_ARTICLE
        ),
        content=empty_content,
    )

    fake_request = FakeRequest(
        _message(
            "https://example.com/empty",
            message_id=103,
        )
    )

    monkeypatch.setattr(
        "core.external_content_resolver."
        "ExternalContentResolver.resolve",
        lambda self, url: resolution,
    )

    with patch.object(
        webhook_handler,
        "request",
        fake_request,
    ), patch.object(
        webhook_handler,
        "validate_webhook_token",
        return_value=True,
    ), patch.object(
        webhook_handler,
        "send_message",
        side_effect=(
            lambda *args, **kwargs:
            sent.append(
                (
                    args,
                    kwargs,
                )
            )
        ),
    ):

        result, status = (
            webhook_handler.handle_webhook()
        )

    assert status == 200

    assert result["external_content"] is True
    assert result["external_resolved"] is True
    assert result["external_publishable"] is False

    assert len(sent) == 1

    assert (
        "محتوای کافی"
        in sent[0][0][1]
    )
