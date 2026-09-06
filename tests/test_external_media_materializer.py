import pytest

from core.external_content_model import ExternalMedia
from core.external_fetcher import (
    ExternalFetchError,
)
from core.external_media_materializer import (
    AcquiredExternalMedia,
    ExternalMediaAcquirer,
    ExternalMediaDownloadError,
    ExternalMediaMaterializationError,
    ExternalMediaMaterializer,
    ExternalMediaUploadError,
    MaterializedExternalMedia,
    UnsupportedExternalMedia,
)


# =========================================================
# FAKE FETCH RESULT
# =========================================================


class FakeFetchResult:
    def __init__(
        self,
        *,
        content=b"media-bytes",
        final_url="https://cdn.example.com/final.jpg",
        content_type="image/jpeg",
        redirect_chain=(),
    ):
        self.content = content
        self.final_url = final_url
        self.content_type = content_type
        self.redirect_chain = tuple(
            redirect_chain
        )
        self.size_bytes = len(
            content
        )


# =========================================================
# FAKE FETCHERS
# =========================================================


class FakeFetcher:
    def __init__(
        self,
        result=None,
    ):
        self.result = (
            result
            or FakeFetchResult()
        )
        self.calls = []

    def fetch(
        self,
        url,
        *,
        allowed_content_types=None,
    ):
        self.calls.append(
            {
                "url": url,
                "allowed_content_types": tuple(
                    allowed_content_types
                    or ()
                ),
            }
        )

        return self.result


class FailingFetcher:
    def fetch(
        self,
        url,
        *,
        allowed_content_types=None,
    ):
        raise ExternalFetchError(
            "network failure"
        )


# =========================================================
# FAKE TRANSPORTS
# =========================================================


class FakeTransport:
    name = "fake"

    def __init__(
        self,
        *,
        supported=True,
        file_id="transport-file-123",
    ):
        self.supported = supported
        self.file_id = file_id
        self.received = []

    def supports(
        self,
        media,
    ):
        return self.supported

    def materialize(
        self,
        media,
    ):
        self.received.append(
            media
        )

        return MaterializedExternalMedia(
            type=media.type,
            file_id=self.file_id,
            position=media.position,
            presentation=media.presentation,
            source_url=media.source_url,
            metadata={
                "transport": self.name,
            },
        )


class BrokenTransport:
    name = "broken"

    def supports(
        self,
        media,
    ):
        return True

    def materialize(
        self,
        media,
    ):
        raise RuntimeError(
            "upload failed"
        )


class InvalidTransport:
    name = "invalid"

    def supports(
        self,
        media,
    ):
        return True

    def materialize(
        self,
        media,
    ):
        return {
            "file_id": "bad-result"
        }


class EmptyFileIdTransport:
    name = "empty"

    def supports(
        self,
        media,
    ):
        return True

    def materialize(
        self,
        media,
    ):
        return MaterializedExternalMedia(
            type=media.type,
            file_id="",
            source_url=media.source_url,
        )


# =========================================================
# HELPERS
# =========================================================


def _photo(
    *,
    url="https://example.com/photo.jpg",
    position=0,
    presentation="cover",
):
    return ExternalMedia(
        type="photo",
        source_url=url,
        width=1200,
        height=800,
        position=position,
        presentation=presentation,
        metadata={
            "source": "test",
        },
    )


# =========================================================
# ACQUIRED MEDIA
# =========================================================


def test_acquired_media_reports_byte_size():
    media = AcquiredExternalMedia(
        type="photo",
        source_url=(
            "https://example.com/a.jpg"
        ),
        final_url=(
            "https://cdn.example.com/a.jpg"
        ),
        content=b"12345",
        mime_type="image/jpeg",
    )

    assert media.size_bytes == 5


# =========================================================
# MATERIALIZED MEDIA
# =========================================================


def test_materialized_media_builds_prepared_file():
    media = MaterializedExternalMedia(
        type="photo",
        file_id="file-123",
        position=2,
        presentation="cover",
        source_url=(
            "https://example.com/a.jpg"
        ),
        metadata={
            "provider": "test",
        },
    )

    result = media.as_prepared_file()

    assert result["type"] == "photo"
    assert result["file_id"] == "file-123"
    assert result["position"] == 2
    assert result["presentation"] == "cover"

    assert result[
        "external_source_url"
    ] == (
        "https://example.com/a.jpg"
    )

    assert result[
        "external_metadata"
    ][
        "provider"
    ] == "test"


def test_materialized_media_requires_file_id_before_prepared_conversion():
    media = MaterializedExternalMedia(
        type="photo",
        file_id="",
        source_url=(
            "https://example.com/a.jpg"
        ),
    )

    with pytest.raises(
        ExternalMediaMaterializationError,
        match="no transport file_id",
    ):
        media.as_prepared_file()


# =========================================================
# SAFE ACQUISITION
# =========================================================


def test_acquirer_downloads_photo_with_image_mime_policy():
    fetcher = FakeFetcher()

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    result = acquirer.acquire(
        _photo()
    )

    assert isinstance(
        result,
        AcquiredExternalMedia,
    )

    assert result.type == "photo"

    assert fetcher.calls[
        0
    ][
        "allowed_content_types"
    ] == (
        "image/*",
    )


def test_acquirer_preserves_external_media_metadata():
    fetcher = FakeFetcher()

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    result = acquirer.acquire(
        _photo(
            position=3,
            presentation="gallery",
        )
    )

    assert result.position == 3

    assert result.presentation == (
        "gallery"
    )

    assert result.width == 1200
    assert result.height == 800

    assert result.metadata[
        "external_metadata"
    ][
        "source"
    ] == "test"


def test_acquirer_preserves_final_url_and_redirect_chain():
    fetcher = FakeFetcher(
        FakeFetchResult(
            final_url=(
                "https://cdn.example.com/final.jpg"
            ),
            redirect_chain=(
                "https://example.com/photo.jpg",
            ),
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    result = acquirer.acquire(
        _photo()
    )

    assert result.final_url == (
        "https://cdn.example.com/final.jpg"
    )

    assert result.metadata[
        "redirect_chain"
    ] == (
        "https://example.com/photo.jpg",
    )


def test_acquirer_normalizes_image_alias_to_photo():
    media = ExternalMedia(
        type="image",
        source_url=(
            "https://example.com/a.jpg"
        ),
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=FakeFetcher(),
    )

    result = acquirer.acquire(
        media
    )

    assert result.type == "photo"


def test_acquirer_uses_video_mime_policy():
    media = ExternalMedia(
        type="video",
        source_url=(
            "https://example.com/a.mp4"
        ),
    )

    fetcher = FakeFetcher(
        FakeFetchResult(
            final_url=(
                "https://example.com/a.mp4"
            ),
            content_type="video/mp4",
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    result = acquirer.acquire(
        media
    )

    assert result.type == "video"

    assert fetcher.calls[
        0
    ][
        "allowed_content_types"
    ] == (
        "video/*",
    )


def test_acquirer_uses_audio_mime_policy():
    media = ExternalMedia(
        type="audio",
        source_url=(
            "https://example.com/a.mp3"
        ),
    )

    fetcher = FakeFetcher(
        FakeFetchResult(
            final_url=(
                "https://example.com/a.mp3"
            ),
            content_type="audio/mpeg",
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    acquirer.acquire(
        media
    )

    assert fetcher.calls[
        0
    ][
        "allowed_content_types"
    ] == (
        "audio/*",
    )


def test_acquirer_uses_document_mime_policy():
    media = ExternalMedia(
        type="document",
        source_url=(
            "https://example.com/a.pdf"
        ),
    )

    fetcher = FakeFetcher(
        FakeFetchResult(
            final_url=(
                "https://example.com/a.pdf"
            ),
            content_type=(
                "application/pdf"
            ),
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    acquirer.acquire(
        media
    )

    allowed = fetcher.calls[
        0
    ][
        "allowed_content_types"
    ]

    assert "application/pdf" in allowed

    assert (
        "application/octet-stream"
        in allowed
    )


def test_acquirer_rejects_unsupported_media_type():
    media = ExternalMedia(
        type="sticker",
        source_url=(
            "https://example.com/a.webp"
        ),
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=FakeFetcher(),
    )

    with pytest.raises(
        UnsupportedExternalMedia,
        match="unsupported external media type",
    ):
        acquirer.acquire(
            media
        )


def test_acquirer_wraps_safe_fetch_failure():
    acquirer = ExternalMediaAcquirer(
        fetcher=FailingFetcher(),
    )

    with pytest.raises(
        ExternalMediaDownloadError,
        match="acquisition failed",
    ):
        acquirer.acquire(
            _photo()
        )


def test_acquirer_rejects_empty_response():
    fetcher = FakeFetcher(
        FakeFetchResult(
            content=b"",
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
    )

    with pytest.raises(
        ExternalMediaDownloadError,
        match="response is empty",
    ):
        acquirer.acquire(
            _photo()
        )


def test_acquirer_enforces_materialization_size_limit():
    fetcher = FakeFetcher(
        FakeFetchResult(
            content=b"123456",
        )
    )

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
        max_bytes=5,
    )

    with pytest.raises(
        ExternalMediaDownloadError,
        match="size limit",
    ):
        acquirer.acquire(
            _photo()
        )


def test_acquirer_requires_external_media_model():
    acquirer = ExternalMediaAcquirer(
        fetcher=FakeFetcher(),
    )

    with pytest.raises(
        TypeError,
        match="ExternalMedia",
    ):
        acquirer.acquire(
            {
                "type": "photo",
            }
        )


# =========================================================
# TRANSPORT RESOLUTION
# =========================================================


def test_materializer_resolves_supported_transport():
    unsupported = FakeTransport(
        supported=False
    )

    supported = FakeTransport(
        supported=True
    )

    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            unsupported,
            supported,
        ),
    )

    result = service.materialize_one(
        _photo()
    )

    assert result.file_id == (
        "transport-file-123"
    )

    assert len(
        supported.received
    ) == 1


def test_transport_support_exception_does_not_break_resolution():
    class ExplodingTransport:
        name = "exploding"

        def supports(
            self,
            media,
        ):
            raise RuntimeError(
                "boom"
            )

        def materialize(
            self,
            media,
        ):
            raise AssertionError

    valid = FakeTransport()

    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            ExplodingTransport(),
            valid,
        ),
    )

    result = service.materialize_one(
        _photo()
    )

    assert result.file_id == (
        "transport-file-123"
    )


def test_materializer_rejects_missing_transport():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(),
    )

    with pytest.raises(
        UnsupportedExternalMedia,
        match="no configured transport",
    ):
        service.materialize_one(
            _photo()
        )


# =========================================================
# TRANSPORT MATERIALIZATION
# =========================================================


def test_materializer_wraps_transport_failure():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            BrokenTransport(),
        ),
    )

    with pytest.raises(
        ExternalMediaUploadError,
        match="transport materialization failed",
    ):
        service.materialize_one(
            _photo()
        )


def test_materializer_rejects_invalid_transport_result():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            InvalidTransport(),
        ),
    )

    with pytest.raises(
        ExternalMediaUploadError,
        match="invalid result",
    ):
        service.materialize_one(
            _photo()
        )


def test_materializer_rejects_empty_transport_file_id():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            EmptyFileIdTransport(),
        ),
    )

    with pytest.raises(
        ExternalMediaUploadError,
        match="no file_id",
    ):
        service.materialize_one(
            _photo()
        )


# =========================================================
# MULTI-MEDIA
# =========================================================


def test_materialize_many_preserves_deterministic_position_order():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            FakeTransport(),
        ),
    )

    results = service.materialize_many(
        (
            _photo(
                url=(
                    "https://example.com/3.jpg"
                ),
                position=3,
            ),
            _photo(
                url=(
                    "https://example.com/1.jpg"
                ),
                position=1,
            ),
            _photo(
                url=(
                    "https://example.com/2.jpg"
                ),
                position=2,
            ),
        )
    )

    assert tuple(
        item.position
        for item in results
    ) == (
        1,
        2,
        3,
    )


def test_build_prepared_files_requires_completed_materialization():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            FakeTransport(
                file_id="ready-file"
            ),
        ),
    )

    files = service.build_prepared_files(
        (
            _photo(),
        )
    )

    assert len(
        files
    ) == 1

    assert files[
        0
    ][
        "file_id"
    ] == "ready-file"

    assert files[
        0
    ][
        "type"
    ] == "photo"


def test_external_url_is_not_used_as_file_id():
    source_url = (
        "https://example.com/photo.jpg"
    )

    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        ),
        transports=(
            FakeTransport(
                file_id="platform-file-id"
            ),
        ),
    )

    files = service.build_prepared_files(
        (
            _photo(
                url=source_url
            ),
        )
    )

    assert files[
        0
    ][
        "file_id"
    ] == "platform-file-id"

    assert files[
        0
    ][
        "file_id"
    ] != source_url

    assert files[
        0
    ][
        "external_source_url"
    ] == source_url


# =========================================================
# ARCHITECTURAL LOCKS
# =========================================================


def test_materializer_has_no_destination_publication_methods():
    service = ExternalMediaMaterializer(
        acquirer=ExternalMediaAcquirer(
            fetcher=FakeFetcher(),
        )
    )

    forbidden = {
        "publish",
        "send",
        "send_message",
        "send_photo",
        "send_video",
        "send_media_group",
    }

    assert forbidden.isdisjoint(
        set(
            dir(
                service
            )
        )
    )


def test_acquired_media_contains_no_platform_file_id():
    acquired = AcquiredExternalMedia(
        type="photo",
        source_url=(
            "https://example.com/a.jpg"
        ),
        final_url=(
            "https://example.com/a.jpg"
        ),
        content=b"data",
    )

    assert not hasattr(
        acquired,
        "telegram_file_id",
    )

    assert not hasattr(
        acquired,
        "bale_file_id",
    )
