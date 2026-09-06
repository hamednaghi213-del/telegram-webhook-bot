import pytest

from core.external_media_materializer import (
    AcquiredExternalMedia,
    ExternalMediaUploadError,
    MaterializedExternalMedia,
)
from core.telegram_external_media_materializer import (
    TelegramExternalMediaMaterializer,
    _extract_file_id,
    _safe_filename,
    _telegram_method,
)


# =========================================================
# FAKE RESPONSE / SESSION
# =========================================================


class FakeResponse:

    def __init__(
        self,
        *,
        status_code=200,
        payload=None,
        json_error=None,
    ):
        self.status_code = status_code
        self._payload = (
            payload
            if payload is not None
            else {}
        )
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error

        return self._payload


class FakeSession:

    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )
        self.calls = []

    def post(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            {
                "url": url,
                **kwargs,
            }
        )

        if not self.responses:
            raise AssertionError(
                "unexpected HTTP call"
            )

        response = self.responses.pop(
            0
        )

        if isinstance(
            response,
            Exception,
        ):
            raise response

        return response


# =========================================================
# HELPERS
# =========================================================


def _media(
    *,
    media_type="photo",
    mime_type="image/jpeg",
    final_url=(
        "https://cdn.example.com/news/photo.jpg"
    ),
    source_url=(
        "https://example.com/photo.jpg"
    ),
    content=b"external-media-bytes",
    position=0,
    presentation="",
):
    return AcquiredExternalMedia(
        type=media_type,
        source_url=source_url,
        final_url=final_url,
        content=content,
        mime_type=mime_type,
        position=position,
        presentation=presentation,
        metadata={
            "source": "test",
        },
    )


def _materializer(
    session,
):
    return TelegramExternalMediaMaterializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001234567890",
        session=session,
    )


# =========================================================
# CONFIG
# =========================================================


def test_requires_api_url():
    with pytest.raises(
        ValueError,
    ):
        TelegramExternalMediaMaterializer(
            api_url="",
            staging_chat_id="-1001",
        )


def test_requires_staging_chat(
    monkeypatch,
):
    monkeypatch.delenv(
        "EXTERNAL_MEDIA_STAGING_CHAT_ID",
        raising=False,
    )

    with pytest.raises(
        ValueError,
    ):
        TelegramExternalMediaMaterializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
        )


def test_reads_staging_chat_from_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "EXTERNAL_MEDIA_STAGING_CHAT_ID",
        "-100999",
    )

    materializer = (
        TelegramExternalMediaMaterializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
        )
    )

    assert (
        materializer.staging_chat_id
        == "-100999"
    )


def test_requires_positive_timeout():
    with pytest.raises(
        ValueError,
    ):
        TelegramExternalMediaMaterializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
            staging_chat_id="-1001",
            timeout_seconds=0,
        )


# =========================================================
# SUPPORT
# =========================================================


@pytest.mark.parametrize(
    "media_type",
    (
        "photo",
        "video",
        "audio",
        "document",
    ),
)
def test_supports_expected_media_types(
    media_type,
):
    materializer = _materializer(
        FakeSession([])
    )

    assert (
        materializer.supports(
            _media(
                media_type=media_type,
            )
        )
        is True
    )


def test_does_not_support_unknown_type():
    materializer = _materializer(
        FakeSession([])
    )

    assert (
        materializer.supports(
            _media(
                media_type="voice",
            )
        )
        is False
    )


def test_does_not_support_empty_content():
    materializer = _materializer(
        FakeSession([])
    )

    assert (
        materializer.supports(
            _media(
                content=b"",
            )
        )
        is False
    )


def test_supports_rejects_wrong_object():
    materializer = _materializer(
        FakeSession([])
    )

    assert (
        materializer.supports(
            object()
        )
        is False
    )


# =========================================================
# METHOD MAPPING
# =========================================================


@pytest.mark.parametrize(
    (
        "media_type",
        "expected_method",
        "expected_field",
    ),
    (
        (
            "photo",
            "sendPhoto",
            "photo",
        ),
        (
            "video",
            "sendVideo",
            "video",
        ),
        (
            "audio",
            "sendAudio",
            "audio",
        ),
        (
            "document",
            "sendDocument",
            "document",
        ),
    ),
)
def test_telegram_method_mapping(
    media_type,
    expected_method,
    expected_field,
):
    method, field = (
        _telegram_method(
            media_type
        )
    )

    assert method == expected_method
    assert field == expected_field


def test_telegram_method_rejects_unknown_type():
    with pytest.raises(
        ExternalMediaUploadError,
    ):
        _telegram_method(
            "voice"
        )


# =========================================================
# FILENAME
# =========================================================


def test_safe_filename_uses_url_basename():
    filename = _safe_filename(
        _media(
            final_url=(
                "https://cdn.example.com/"
                "images/my-photo.jpg?x=1"
            )
        )
    )

    assert filename == "my-photo.jpg"


def test_safe_filename_sanitizes_url_basename():
    filename = _safe_filename(
        _media(
            final_url=(
                "https://cdn.example.com/"
                "images/my%20photo!!.jpg"
            )
        )
    )

    assert "/" not in filename
    assert "\\" not in filename
    assert len(filename) <= 120


def test_safe_filename_falls_back_from_mime():
    filename = _safe_filename(
        _media(
            final_url=(
                "https://cdn.example.com/"
            ),
            source_url=(
                "https://example.com/"
            ),
            mime_type="image/jpeg",
        )
    )

    assert filename.startswith(
        "external_image"
    )


# =========================================================
# FILE-ID EXTRACTION
# =========================================================


def test_extract_photo_file_id_uses_largest_variant():
    result = {
        "photo": [
            {
                "file_id": "small-id",
            },
            {
                "file_id": "large-id",
            },
        ]
    }

    assert (
        _extract_file_id(
            media_type="photo",
            result=result,
        )
        == "large-id"
    )


@pytest.mark.parametrize(
    "media_type",
    (
        "video",
        "audio",
        "document",
    ),
)
def test_extract_non_photo_file_id(
    media_type,
):
    result = {
        media_type: {
            "file_id": "telegram-file-id",
        }
    }

    assert (
        _extract_file_id(
            media_type=media_type,
            result=result,
        )
        == "telegram-file-id"
    )


def test_extract_file_id_returns_empty_when_missing():
    assert (
        _extract_file_id(
            media_type="photo",
            result={},
        )
        == ""
    )


# =========================================================
# SUCCESS
# =========================================================


def test_materialize_photo_returns_real_file_id():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 55,
                        "photo": [
                            {
                                "file_id": (
                                    "photo-small"
                                )
                            },
                            {
                                "file_id": (
                                    "photo-large"
                                )
                            },
                        ],
                    },
                }
            ),
            FakeResponse(
                payload={
                    "ok": True,
                    "result": True,
                }
            ),
        ]
    )

    materializer = _materializer(
        session
    )

    result = materializer.materialize(
        _media(
            position=2,
            presentation="slideshow",
        )
    )

    assert isinstance(
        result,
        MaterializedExternalMedia,
    )

    assert (
        result.file_id
        == "photo-large"
    )

    assert result.type == "photo"
    assert result.position == 2

    assert (
        result.presentation
        == "slideshow"
    )

    assert (
        result.source_url
        == "https://example.com/photo.jpg"
    )

    assert (
        result.metadata[
            "transport"
        ]
        == "telegram_staging"
    )

    assert (
        result.metadata[
            "telegram_staging_message_id"
        ]
        == 55
    )


def test_materialize_uploads_bytes_to_staging_chat():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 10,
                        "video": {
                            "file_id": (
                                "video-file-id"
                            )
                        },
                    },
                }
            ),
            FakeResponse(
                payload={
                    "ok": True,
                }
            ),
        ]
    )

    materializer = _materializer(
        session
    )

    materializer.materialize(
        _media(
            media_type="video",
            mime_type="video/mp4",
        )
    )

    upload = session.calls[0]

    assert (
        upload["url"]
        == (
            "https://api.telegram.org/"
            "botTEST_TOKEN/sendVideo"
        )
    )

    assert (
        upload["data"]["chat_id"]
        == "-1001234567890"
    )

    assert "video" in upload["files"]

    uploaded_file = (
        upload["files"]["video"]
    )

    assert (
        uploaded_file[1]
        == b"external-media-bytes"
    )

    assert (
        uploaded_file[2]
        == "video/mp4"
    )


def test_successful_materialization_deletes_staging_message():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 77,
                        "document": {
                            "file_id": (
                                "document-file-id"
                            )
                        },
                    },
                }
            ),
            FakeResponse(
                payload={
                    "ok": True,
                    "result": True,
                }
            ),
        ]
    )

    materializer = _materializer(
        session
    )

    result = materializer.materialize(
        _media(
            media_type="document",
            mime_type=(
                "application/pdf"
            ),
        )
    )

    assert (
        result.file_id
        == "document-file-id"
    )

    assert len(session.calls) == 2

    delete_call = session.calls[1]

    assert (
        delete_call["url"]
        == (
            "https://api.telegram.org/"
            "botTEST_TOKEN/deleteMessage"
        )
    )

    assert (
        delete_call["json"]
        == {
            "chat_id": (
                "-1001234567890"
            ),
            "message_id": 77,
        }
    )


# =========================================================
# FAIL-CLOSED
# =========================================================


def test_materialize_rejects_wrong_object():
    materializer = _materializer(
        FakeSession([])
    )

    with pytest.raises(
        TypeError,
    ):
        materializer.materialize(
            object()
        )


def test_materialize_rejects_unsupported_media():
    materializer = _materializer(
        FakeSession([])
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media(
                media_type="voice",
            )
        )


def test_network_failure_is_wrapped():
    session = FakeSession(
        [
            RuntimeError(
                "network unavailable"
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


def test_invalid_json_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                json_error=ValueError(
                    "invalid json"
                )
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


def test_non_200_response_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                status_code=400,
                payload={
                    "ok": False,
                    "description": (
                        "Bad Request"
                    ),
                },
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


def test_telegram_ok_false_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                status_code=200,
                payload={
                    "ok": False,
                    "description": (
                        "Telegram rejected file"
                    ),
                },
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


def test_missing_result_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                }
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


def test_missing_file_id_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 99,
                        "photo": [],
                    },
                }
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )


# =========================================================
# CLEANUP POLICY
# =========================================================


def test_cleanup_failure_does_not_destroy_valid_file_id():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 123,
                        "photo": [
                            {
                                "file_id": (
                                    "valid-file-id"
                                )
                            }
                        ],
                    },
                }
            ),
            RuntimeError(
                "cleanup failed"
            ),
        ]
    )

    materializer = _materializer(
        session
    )

    result = materializer.materialize(
        _media()
    )

    assert (
        result.file_id
        == "valid-file-id"
    )


def test_no_cleanup_attempt_when_upload_fails():
    session = FakeSession(
        [
            FakeResponse(
                status_code=400,
                payload={
                    "ok": False,
                },
            )
        ]
    )

    materializer = _materializer(
        session
    )

    with pytest.raises(
        ExternalMediaUploadError,
    ):
        materializer.materialize(
            _media()
        )

    assert len(session.calls) == 1


# =========================================================
# NO DESTINATION PUBLICATION
# =========================================================


def test_transport_only_uses_staging_and_cleanup_methods():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 321,
                        "photo": [
                            {
                                "file_id": (
                                    "file-id"
                                )
                            }
                        ],
                    },
                }
            ),
            FakeResponse(
                payload={
                    "ok": True,
                }
            ),
        ]
    )

    materializer = _materializer(
        session
    )

    materializer.materialize(
        _media()
    )

    urls = [
        call["url"]
        for call in session.calls
    ]

    assert any(
        url.endswith(
            "/sendPhoto"
        )
        for url in urls
    )

    assert any(
        url.endswith(
            "/deleteMessage"
        )
        for url in urls
    )

    assert not any(
        url.endswith(
            "/sendMediaGroup"
        )
        for url in urls
    )
