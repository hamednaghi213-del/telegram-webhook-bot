from core.external_content_model import (
    ExternalMedia,
)
from core.external_review_telegram_panel import (
    reconcile_media_panel,
    send_media_panel,
)


# =========================================================
# FAKE TELEGRAM API
# =========================================================


class FakeTelegramApi:
    def __init__(self):
        self.calls = []
        self.next_message_id = 5000
        self.next_file_id = 0

    def __call__(self, method, payload):
        payload = dict(payload or {})

        self.calls.append(
            (method, payload)
        )

        if method == "sendPhoto" and (
            "photo_bytes" in payload
        ):
            # Staging upload.
            self.next_message_id += 1
            self.next_file_id += 1

            return {
                "ok": True,
                "result": {
                    "message_id": (
                        self.next_message_id
                    ),
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

        if method == "sendPhoto":
            self.next_message_id += 1

            return {
                "ok": True,
                "result": {
                    "message_id": (
                        self.next_message_id
                    ),
                },
            }

        if method == "sendMediaGroup":
            result = []

            for _ in payload.get("media", []):
                self.next_message_id += 1
                result.append(
                    {
                        "message_id": (
                            self.next_message_id
                        ),
                    }
                )

            return {
                "ok": True,
                "result": result,
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


def _media(url, position):
    return ExternalMedia(
        type="image",
        source_url=url,
        position=position,
    )


def _fetcher(url):
    return b"fake-image-bytes"


# =========================================================
# STAGING + DISPLAY
# =========================================================


def test_single_photo_is_staged_then_displayed():
    api = FakeTelegramApi()

    result = send_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="-1001",
        media=[
            _media("https://example.com/1.jpg", 0),
        ],
        fetcher=_fetcher,
    )

    staging_calls = [
        payload
        for payload in api.payloads("sendPhoto")
        if "photo_bytes" in payload
    ]

    display_calls = [
        payload
        for payload in api.payloads("sendPhoto")
        if "photo_bytes" not in payload
    ]

    assert len(staging_calls) == 1
    assert staging_calls[0]["chat_id"] == "-1001"

    assert len(display_calls) == 1
    assert display_calls[0]["chat_id"] == 123
    assert display_calls[0]["photo"] == "staged-1"

    assert len(result.message_ids) == 1
    assert result.file_ids_by_position == {
        0: "staged-1",
    }

    # Staging message was deleted after capture.
    deletes = api.payloads("deleteMessage")
    assert any(
        item["chat_id"] == "-1001"
        for item in deletes
    )


def test_multiple_photos_display_as_album():
    api = FakeTelegramApi()

    result = send_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="-1001",
        media=[
            _media("https://example.com/1.jpg", 0),
            _media("https://example.com/2.jpg", 1),
        ],
        fetcher=_fetcher,
    )

    groups = api.payloads("sendMediaGroup")

    assert len(groups) == 1
    assert groups[0]["chat_id"] == 123
    assert len(groups[0]["media"]) == 2

    assert len(result.message_ids) == 2
    assert result.file_ids_by_position == {
        0: "staged-1",
        1: "staged-2",
    }


def test_missing_staging_chat_shows_nothing():
    api = FakeTelegramApi()

    result = send_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="",
        media=[
            _media("https://example.com/1.jpg", 0),
        ],
        fetcher=_fetcher,
    )

    assert result.message_ids == ()
    assert api.methods() == []


# =========================================================
# STAGED FILE_ID REUSE
# =========================================================


def test_staged_file_ids_skip_fetch_and_staging():
    api = FakeTelegramApi()

    result = send_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="-1001",
        media=[
            _media("https://example.com/1.jpg", 0),
        ],
        staged_file_ids=("already-staged",),
        fetcher=_fetcher,
    )

    # No staging upload happened; the cached file_id was
    # displayed directly.
    assert all(
        "photo_bytes" not in payload
        for payload in api.payloads("sendPhoto")
    )

    display_calls = [
        payload
        for payload in api.payloads("sendPhoto")
        if "photo_bytes" not in payload
    ]

    assert len(display_calls) == 1
    assert display_calls[0]["photo"] == "already-staged"

    assert result.file_ids_by_position == {
        0: "already-staged",
    }


def test_reconcile_without_media_deletes_panel():
    api = FakeTelegramApi()

    result = reconcile_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="-1001",
        media=(),
        current_message_ids=(777, 778),
    )

    deletes = api.payloads("deleteMessage")

    assert len(deletes) == 2
    assert {
        item["message_id"] for item in deletes
    } == {777, 778}

    assert result.message_ids == ()
    assert "sendPhoto" not in api.methods()


def test_reconcile_replaces_existing_panel():
    api = FakeTelegramApi()

    result = reconcile_media_panel(
        telegram_api=api,
        chat_id=123,
        staging_chat_id="-1001",
        media=[
            _media("https://example.com/1.jpg", 0),
        ],
        current_message_ids=(777,),
        staged_file_ids=("already-staged",),
    )

    deletes = api.payloads("deleteMessage")
    assert any(
        item["message_id"] == 777
        for item in deletes
    )

    assert len(result.message_ids) == 1
