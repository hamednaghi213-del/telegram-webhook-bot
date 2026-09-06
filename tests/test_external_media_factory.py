import pytest

from core.external_fetcher import (
    SafeExternalFetcher,
)
from core.external_media_factory import (
    DEFAULT_EXTERNAL_MEDIA_MAX_BYTES,
    build_external_media_materializer,
)
from core.external_media_materializer import (
    ExternalMediaAcquirer,
    ExternalMediaMaterializer,
)
from core.telegram_external_media_materializer import (
    TelegramExternalMediaMaterializer,
)


# =========================================================
# FAKES
# =========================================================


class FakeTelegramSession:
    pass


class FakeFetcher(
    SafeExternalFetcher
):
    """
    We only need a recognizable fetcher instance here.

    No network request is performed by these tests.
    """

    def __init__(self):
        pass


# =========================================================
# BASIC FACTORY
# =========================================================


def test_factory_returns_external_media_materializer():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001234567890",
    )

    assert isinstance(
        result,
        ExternalMediaMaterializer,
    )


def test_factory_builds_external_media_acquirer():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001234567890",
    )

    assert isinstance(
        result.acquirer,
        ExternalMediaAcquirer,
    )


def test_factory_configures_one_transport():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001234567890",
    )

    assert len(
        result.transports
    ) == 1

    assert isinstance(
        result.transports[0],
        TelegramExternalMediaMaterializer,
    )


# =========================================================
# TELEGRAM CONFIG
# =========================================================


def test_factory_passes_api_url_to_transport():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN/"
        ),
        staging_chat_id="-1001234567890",
    )

    transport = (
        result.transports[0]
    )

    assert (
        transport.api_url
        == (
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        )
    )


def test_factory_passes_staging_chat_to_transport():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1009876543210",
    )

    transport = (
        result.transports[0]
    )

    assert (
        transport.staging_chat_id
        == "-1009876543210"
    )


def test_factory_can_use_environment_staging_chat(
    monkeypatch,
):
    monkeypatch.setenv(
        "EXTERNAL_MEDIA_STAGING_CHAT_ID",
        "-1005555555555",
    )

    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
    )

    transport = (
        result.transports[0]
    )

    assert (
        transport.staging_chat_id
        == "-1005555555555"
    )


def test_factory_passes_timeout_to_transport():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001",
        timeout_seconds=123,
    )

    transport = (
        result.transports[0]
    )

    assert (
        transport.timeout_seconds
        == 123
    )


def test_factory_passes_custom_session():
    session = FakeTelegramSession()

    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001",
        telegram_session=session,
    )

    transport = (
        result.transports[0]
    )

    assert (
        transport.session
        is session
    )


# =========================================================
# FETCHER / ACQUIRER
# =========================================================


def test_factory_uses_custom_fetcher():
    fetcher = FakeFetcher()

    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001",
        fetcher=fetcher,
    )

    assert (
        result.acquirer.fetcher
        is fetcher
    )


def test_factory_passes_max_bytes_to_acquirer():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001",
        max_bytes=123456,
    )

    assert (
        result.acquirer.max_bytes
        == 123456
    )


def test_factory_uses_default_media_size_limit():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST_TOKEN"
        ),
        staging_chat_id="-1001",
    )

    assert (
        result.acquirer.max_bytes
        == DEFAULT_EXTERNAL_MEDIA_MAX_BYTES
    )

    assert (
        DEFAULT_EXTERNAL_MEDIA_MAX_BYTES
        == 25 * 1024 * 1024
    )


# =========================================================
# VALIDATION
# =========================================================


@pytest.mark.parametrize(
    "api_url",
    (
        "",
        " ",
        None,
    ),
)
def test_factory_rejects_empty_api_url(
    api_url,
):
    with pytest.raises(
        ValueError,
        match="api_url is required",
    ):
        build_external_media_materializer(
            api_url=api_url,
            staging_chat_id="-1001",
        )


@pytest.mark.parametrize(
    "max_bytes",
    (
        0,
        -1,
        -100,
    ),
)
def test_factory_rejects_invalid_max_bytes(
    max_bytes,
):
    with pytest.raises(
        ValueError,
        match="max_bytes must be > 0",
    ):
        build_external_media_materializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
            staging_chat_id="-1001",
            max_bytes=max_bytes,
        )


@pytest.mark.parametrize(
    "timeout_seconds",
    (
        0,
        -1,
        -50,
    ),
)
def test_factory_rejects_invalid_timeout(
    timeout_seconds,
):
    with pytest.raises(
        ValueError,
        match=(
            "timeout_seconds must be > 0"
        ),
    ):
        build_external_media_materializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
            staging_chat_id="-1001",
            timeout_seconds=(
                timeout_seconds
            ),
        )


def test_factory_fails_closed_without_staging_chat(
    monkeypatch,
):
    monkeypatch.delenv(
        "EXTERNAL_MEDIA_STAGING_CHAT_ID",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match=(
            "external media staging chat "
            "is not configured"
        ),
    ):
        build_external_media_materializer(
            api_url=(
                "https://api.telegram.org/"
                "botTEST"
            ),
        )


# =========================================================
# ARCHITECTURAL BOUNDARY
# =========================================================


def test_factory_does_not_publish_or_make_http_calls():
    session = FakeTelegramSession()
    fetcher = FakeFetcher()

    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST"
        ),
        staging_chat_id="-1001",
        fetcher=fetcher,
        telegram_session=session,
    )

    assert isinstance(
        result,
        ExternalMediaMaterializer,
    )

    assert (
        result.acquirer.fetcher
        is fetcher
    )

    assert (
        result.transports[0].session
        is session
    )


def test_factory_preserves_shared_materializer_boundary():
    result = build_external_media_materializer(
        api_url=(
            "https://api.telegram.org/"
            "botTEST"
        ),
        staging_chat_id="-1001",
    )

    assert callable(
        result.materialize_one
    )

    assert callable(
        result.materialize_many
    )

    assert callable(
        result.build_prepared_files
    )
