import socket

import pytest
import requests

from core.external_fetcher import (
    ExternalFetchHTTPError,
    ExternalResponseTooLarge,
    FetchPolicy,
    SafeExternalFetcher,
    UnsafeExternalURL,
    UnsupportedExternalContentType,
    canonicalize_external_url,
)


PUBLIC_IPV4 = "93.184.216.34"


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        headers=None,
        chunks=None,
        encoding="utf-8",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.encoding = encoding
        self.closed = False

    def iter_content(
        self,
        chunk_size=65536,
    ):
        del chunk_size

        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )
        self.calls = []
        self.trust_env = True

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        if not self.responses:
            raise AssertionError(
                "unexpected HTTP request"
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


def public_dns(
    host,
    port,
    *,
    type=0,
):
    del host
    del type

    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (
                PUBLIC_IPV4,
                port,
            ),
        )
    ]


def test_canonicalize_external_url():
    assert canonicalize_external_url(
        " HTTPS://Example.COM:443/story?id=7#section "
    ) == (
        "https://example.com/story?id=7"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "data:text/plain,test",
        "javascript:alert(1)",
    ],
)
def test_non_http_schemes_are_rejected(
    url,
):
    with pytest.raises(
        UnsafeExternalURL
    ):
        canonicalize_external_url(
            url
        )


def test_url_credentials_are_rejected():
    with pytest.raises(
        UnsafeExternalURL,
        match="credentials",
    ):
        canonicalize_external_url(
            "https://user:pass@example.com/story"
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://service.localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.5/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ],
)
def test_private_and_local_destinations_are_rejected(
    url,
):
    fetcher = SafeExternalFetcher()

    with pytest.raises(
        UnsafeExternalURL
    ):
        fetcher.validate_url(
            url
        )


def test_dns_private_address_is_rejected(
    monkeypatch,
):
    def private_dns(
        host,
        port,
        *,
        type=0,
    ):
        del host
        del type

        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (
                    "10.20.30.40",
                    port,
                ),
            )
        ]

    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        private_dns,
    )

    fetcher = SafeExternalFetcher()

    with pytest.raises(
        UnsafeExternalURL
    ):
        fetcher.validate_url(
            "https://example.com/story"
        )


def test_mixed_public_and_private_dns_is_rejected(
    monkeypatch,
):
    def mixed_dns(
        host,
        port,
        *,
        type=0,
    ):
        del host
        del type

        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (
                    PUBLIC_IPV4,
                    port,
                ),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (
                    "127.0.0.1",
                    port,
                ),
            ),
        ]

    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        mixed_dns,
    )

    fetcher = SafeExternalFetcher()

    with pytest.raises(
        UnsafeExternalURL
    ):
        fetcher.validate_url(
            "https://example.com/story"
        )


def test_nonstandard_port_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    fetcher = SafeExternalFetcher()

    with pytest.raises(
        UnsafeExternalURL,
        match="port",
    ):
        fetcher.validate_url(
            "https://example.com:8443/story"
        )


def test_safe_html_fetch(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={
            "Content-Type": (
                "text/html; charset=utf-8"
            ),
            "Content-Length": "31",
        },
        chunks=[
            b"<html>",
            b"<body>Hello</body>",
            b"</html>",
        ],
    )

    session = FakeSession(
        [
            response,
        ]
    )

    fetcher = SafeExternalFetcher(
        session=session
    )

    result = fetcher.fetch(
        "https://example.com/story"
    )

    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert "Hello" in result.text
    assert result.final_url == (
        "https://example.com/story"
    )
    assert result.redirect_chain == ()
    assert result.size_bytes == len(
        result.content
    )

    assert session.trust_env is False

    assert session.calls[0][1][
        "allow_redirects"
    ] is False

    assert session.calls[0][1][
        "stream"
    ] is True

    assert response.closed is True


def test_redirect_is_followed_and_revalidated(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    first = FakeResponse(
        status_code=302,
        headers={
            "Location": "/final",
        },
    )

    second = FakeResponse(
        status_code=200,
        headers={
            "Content-Type": "text/html",
        },
        chunks=[
            b"<html>done</html>",
        ],
    )

    session = FakeSession(
        [
            first,
            second,
        ]
    )

    fetcher = SafeExternalFetcher(
        session=session
    )

    result = fetcher.fetch(
        "https://example.com/start"
    )

    assert result.final_url == (
        "https://example.com/final"
    )

    assert result.redirect_chain == (
        "https://example.com/final",
    )

    assert len(
        session.calls
    ) == 2

    assert first.closed is True
    assert second.closed is True


def test_redirect_to_private_address_is_blocked(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    first = FakeResponse(
        status_code=302,
        headers={
            "Location": (
                "http://127.0.0.1/internal"
            ),
        },
    )

    session = FakeSession(
        [
            first,
        ]
    )

    fetcher = SafeExternalFetcher(
        session=session
    )

    with pytest.raises(
        UnsafeExternalURL
    ):
        fetcher.fetch(
            "https://example.com/start"
        )

    # The private redirect target must never be requested.
    assert len(
        session.calls
    ) == 1

    assert first.closed is True


def test_redirect_limit_is_enforced(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        status_code=302,
        headers={
            "Location": "/again",
        },
    )

    session = FakeSession(
        [
            response,
        ]
    )

    fetcher = SafeExternalFetcher(
        policy=FetchPolicy(
            max_redirects=0
        ),
        session=session,
    )

    with pytest.raises(
        ExternalFetchHTTPError,
        match="redirect limit",
    ):
        fetcher.fetch(
            "https://example.com/start"
        )


def test_disallowed_content_type_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={
            "Content-Type": (
                "application/octet-stream"
            ),
        },
        chunks=[
            b"binary",
        ],
    )

    fetcher = SafeExternalFetcher(
        session=FakeSession(
            [
                response,
            ]
        )
    )

    with pytest.raises(
        UnsupportedExternalContentType
    ):
        fetcher.fetch(
            "https://example.com/file"
        )


def test_content_type_wildcard_allows_images(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={
            "Content-Type": "image/jpeg",
        },
        chunks=[
            b"jpeg-data",
        ],
    )

    fetcher = SafeExternalFetcher(
        session=FakeSession(
            [
                response,
            ]
        )
    )

    result = fetcher.fetch(
        "https://example.com/photo.jpg",
        allowed_content_types={
            "image/*",
        },
    )

    assert result.content_type == (
        "image/jpeg"
    )


def test_content_length_limit_is_enforced(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={
            "Content-Type": "text/html",
            "Content-Length": "5000",
        },
    )

    fetcher = SafeExternalFetcher(
        session=FakeSession(
            [
                response,
            ]
        )
    )

    with pytest.raises(
        ExternalResponseTooLarge
    ):
        fetcher.fetch(
            "https://example.com/story",
            max_bytes=100,
        )


def test_streamed_size_limit_is_enforced(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={
            "Content-Type": "text/html",
        },
        chunks=[
            b"a" * 60,
            b"b" * 60,
        ],
    )

    fetcher = SafeExternalFetcher(
        session=FakeSession(
            [
                response,
            ]
        )
    )

    with pytest.raises(
        ExternalResponseTooLarge
    ):
        fetcher.fetch(
            "https://example.com/story",
            max_bytes=100,
        )


def test_missing_content_type_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.external_fetcher.socket.getaddrinfo",
        public_dns,
    )

    response = FakeResponse(
        headers={},
        chunks=[
            b"<html></html>",
        ],
    )

    fetcher = SafeExternalFetcher(
        session=FakeSession(
            [
                response,
            ]
        )
    )

    with pytest.raises(
        UnsupportedExternalContentType,
        match="no Content-Type",
    ):
        fetcher.fetch(
            "https://example.com/story"
        )
