"""Secure acquisition layer for external HTTP/HTTPS content."""

from __future__ import annotations

import ipaddress
import re
import socket

from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Mapping, Optional, Tuple
from urllib.parse import (
    urljoin,
    urlsplit,
    urlunsplit,
)

import requests


_REDIRECT_STATUS_CODES = frozenset(
    {
        301,
        302,
        303,
        307,
        308,
    }
)

_DEFAULT_HTML_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
    }
)

_DEFAULT_USER_AGENT = (
    "Donya24-ExternalContent/1.0 "
    "(secure external-content fetcher)"
)


class ExternalFetchError(RuntimeError):
    """Base error for external-content acquisition."""


class UnsafeExternalURL(ExternalFetchError):
    """Raised when a URL is unsafe or violates fetch policy."""


class ExternalFetchNetworkError(ExternalFetchError):
    """Raised when the remote request cannot be completed safely."""


class ExternalFetchHTTPError(ExternalFetchError):
    """Raised for unexpected HTTP response status codes."""


class UnsupportedExternalContentType(ExternalFetchError):
    """Raised when the response MIME type is not allowed."""


class ExternalResponseTooLarge(ExternalFetchError):
    """Raised when the response exceeds the configured byte limit."""


@dataclass(frozen=True)
class FetchPolicy:
    """
    Security policy for external network acquisition.

    The defaults are deliberately conservative and appropriate for
    ordinary public web content.
    """

    max_redirects: int = 5

    connect_timeout: float = 5.0
    read_timeout: float = 15.0

    max_bytes: int = 4 * 1024 * 1024

    allowed_ports: FrozenSet[int] = field(
        default_factory=lambda: frozenset(
            {
                80,
                443,
            }
        )
    )

    user_agent: str = _DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if self.max_redirects < 0:
            raise ValueError(
                "max_redirects must be >= 0"
            )

        if self.connect_timeout <= 0:
            raise ValueError(
                "connect_timeout must be > 0"
            )

        if self.read_timeout <= 0:
            raise ValueError(
                "read_timeout must be > 0"
            )

        if self.max_bytes <= 0:
            raise ValueError(
                "max_bytes must be > 0"
            )

        if not self.allowed_ports:
            raise ValueError(
                "allowed_ports cannot be empty"
            )


@dataclass(frozen=True)
class FetchResult:
    """Immutable result of a successful external fetch."""

    requested_url: str
    final_url: str

    status_code: int
    content_type: str

    content: bytes

    encoding: str = ""

    redirect_chain: Tuple[str, ...] = field(
        default_factory=tuple
    )

    response_headers: Mapping[str, str] = field(
        default_factory=dict
    )

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def text(self) -> str:
        """
        Decode fetched textual content conservatively.

        Some HTTP servers omit charset information or cause Requests
        to fall back to a Western single-byte encoding even when the
        actual document is UTF-8.

        Prefer BOM and document-declared charset information first.
        When the HTTP encoding is absent or looks like a common
        Latin-1 fallback, prefer UTF-8 when the bytes are valid UTF-8.

        This logic is source-neutral and performs no translation.
        """

        content = self.content or b""

        if not content:
            return ""

        # -------------------------------------------------
        # BOM
        # -------------------------------------------------

        if content.startswith(
            b"\xef\xbb\xbf"
        ):
            return content.decode(
                "utf-8-sig",
                errors="replace",
            )

        if (
            content.startswith(
                b"\xff\xfe"
            )
            or content.startswith(
                b"\xfe\xff"
            )
        ):
            try:
                return content.decode(
                    "utf-16",
                    errors="strict",
                )
            except UnicodeError:
                pass

        # -------------------------------------------------
        # HTML / XML declared charset
        # -------------------------------------------------

        head = content[:8192]

        head_ascii = head.decode(
            "ascii",
            errors="ignore",
        )

        charset_match = re.search(
            (
                r"""(?i)charset\s*=\s*"""
                r"""["']?\s*([a-z0-9._-]+)"""
            ),
            head_ascii,
        )

        declared_encoding = (
            charset_match.group(1).strip()
            if charset_match
            else ""
        )

        if declared_encoding:
            try:
                return content.decode(
                    declared_encoding,
                    errors="strict",
                )
            except (
                LookupError,
                UnicodeError,
            ):
                pass

        # -------------------------------------------------
        # HTTP / Requests encoding
        # -------------------------------------------------

        response_encoding = (
            self.encoding
            .strip()
            .lower()
        )

        weak_encodings = {
            "",
            "iso-8859-1",
            "latin-1",
            "latin1",
            "windows-1252",
            "cp1252",
        }

        # Requests commonly uses ISO-8859-1 for HTTP text when
        # no reliable charset is supplied. Before accepting that
        # fallback, check whether the payload is valid UTF-8.
        if response_encoding in weak_encodings:
            try:
                return content.decode(
                    "utf-8",
                    errors="strict",
                )
            except UnicodeError:
                pass

        if response_encoding:
            try:
                return content.decode(
                    response_encoding,
                    errors="strict",
                )
            except (
                LookupError,
                UnicodeError,
            ):
                pass

        # -------------------------------------------------
        # Deterministic fallbacks
        # -------------------------------------------------

        try:
            return content.decode(
                "utf-8",
                errors="strict",
            )
        except UnicodeError:
            pass

        return content.decode(
            (
                response_encoding
                if response_encoding
                else "utf-8"
            ),
            errors="replace",
        )


def canonicalize_external_url(url: str) -> str:
    """
    Normalize a public HTTP/HTTPS URL without fetching it.

    This intentionally removes URL fragments because fragments are
    never sent to an HTTP server.
    """

    if not isinstance(url, str):
        raise UnsafeExternalURL(
            "external URL must be a string"
        )

    candidate = url.strip()

    if not candidate:
        raise UnsafeExternalURL(
            "external URL is empty"
        )

    if any(
        character in candidate
        for character in (
            "\r",
            "\n",
            "\x00",
        )
    ):
        raise UnsafeExternalURL(
            "external URL contains unsafe characters"
        )

    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeExternalURL(
            "external URL is invalid"
        ) from exc

    scheme = parsed.scheme.lower()

    if scheme not in {
        "http",
        "https",
    }:
        raise UnsafeExternalURL(
            "only http and https URLs are allowed"
        )

    if parsed.username is not None:
        raise UnsafeExternalURL(
            "URLs containing credentials are not allowed"
        )

    if parsed.password is not None:
        raise UnsafeExternalURL(
            "URLs containing credentials are not allowed"
        )

    hostname = parsed.hostname

    if not hostname:
        raise UnsafeExternalURL(
            "external URL has no hostname"
        )

    hostname = (
        hostname
        .rstrip(".")
        .lower()
    )

    if not hostname:
        raise UnsafeExternalURL(
            "external URL has no valid hostname"
        )

    try:
        hostname_ascii = (
            hostname
            .encode("idna")
            .decode("ascii")
        )
    except UnicodeError as exc:
        raise UnsafeExternalURL(
            "external hostname is invalid"
        ) from exc

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeExternalURL(
            "external URL has an invalid port"
        ) from exc

    default_port = (
        80
        if scheme == "http"
        else 443
    )

    if ":" in hostname_ascii:
        rendered_host = (
            f"[{hostname_ascii}]"
        )
    else:
        rendered_host = hostname_ascii

    if (
        port is not None
        and port != default_port
    ):
        netloc = (
            f"{rendered_host}:{port}"
        )
    else:
        netloc = rendered_host

    path = parsed.path or "/"

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            parsed.query,
            "",
        )
    )


def _effective_port(url: str) -> int:
    parsed = urlsplit(url)

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise UnsafeExternalURL(
            "external URL has an invalid port"
        ) from exc

    if explicit_port is not None:
        return explicit_port

    return (
        443
        if parsed.scheme.lower() == "https"
        else 80
    )


def _is_forbidden_hostname(
    hostname: str,
) -> bool:
    normalized = (
        hostname
        .rstrip(".")
        .lower()
    )

    if normalized == "localhost":
        return True

    if normalized.endswith(
        ".localhost"
    ):
        return True

    return False


def _validate_ip_address(
    address: str,
) -> None:
    try:
        ip = ipaddress.ip_address(
            address
        )
    except ValueError as exc:
        raise UnsafeExternalURL(
            "resolved address is invalid"
        ) from exc

    if not ip.is_global:
        raise UnsafeExternalURL(
            (
                "external URL resolves to "
                f"non-public address: {ip}"
            )
        )

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise UnsafeExternalURL(
            (
                "external URL resolves to "
                f"forbidden address: {ip}"
            )
        )


def _resolve_and_validate_host(
    hostname: str,
    port: int,
) -> Tuple[str, ...]:

    if _is_forbidden_hostname(
        hostname
    ):
        raise UnsafeExternalURL(
            "localhost destinations are not allowed"
        )

    try:
        literal_ip = ipaddress.ip_address(
            hostname
        )
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        _validate_ip_address(
            str(literal_ip)
        )

        return (
            str(literal_ip),
        )

    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ExternalFetchNetworkError(
            (
                "external hostname could "
                "not be resolved"
            )
        ) from exc

    addresses = []

    for record in records:
        sockaddr = record[4]

        if not sockaddr:
            continue

        address = str(
            sockaddr[0]
        )

        if address not in addresses:
            addresses.append(
                address
            )

    if not addresses:
        raise ExternalFetchNetworkError(
            (
                "external hostname returned "
                "no usable addresses"
            )
        )

    for address in addresses:
        _validate_ip_address(
            address
        )

    return tuple(
        addresses
    )


def _normalize_content_type(
    raw_content_type: str,
) -> str:
    return (
        str(
            raw_content_type
            or ""
        )
        .split(
            ";",
            1,
        )[0]
        .strip()
        .lower()
    )


def _content_type_is_allowed(
    content_type: str,
    allowed_content_types: Iterable[str],
) -> bool:

    normalized = (
        content_type.lower()
    )

    for allowed in allowed_content_types:
        pattern = (
            str(allowed)
            .strip()
            .lower()
        )

        if not pattern:
            continue

        if pattern == normalized:
            return True

        if (
            pattern.endswith("/*")
            and normalized.startswith(
                pattern[:-1]
            )
        ):
            return True

    return False


class SafeExternalFetcher:
    """
    Fetch public HTTP/HTTPS resources through a single guarded path.

    Security properties:
      - HTTP/HTTPS only
      - credentials in URLs rejected
      - localhost/private/link-local/reserved IPs rejected
      - DNS A/AAAA results validated
      - redirects followed manually and revalidated
      - environment proxies disabled
      - explicit connect/read timeouts
      - MIME allowlist
      - Content-Length and streamed-size limits
      - no cookies/authentication inherited from application state
    """

    def __init__(
        self,
        policy: Optional[
            FetchPolicy
        ] = None,
        session: Optional[
            requests.Session
        ] = None,
    ) -> None:

        self.policy = (
            policy
            or FetchPolicy()
        )

        self.session = (
            session
            or requests.Session()
        )

        # Do not inherit HTTP(S)_PROXY, cookies, netrc credentials,
        # or other environment-driven network behavior.
        self.session.trust_env = False

    def validate_url(
        self,
        url: str,
    ) -> str:

        canonical = (
            canonicalize_external_url(
                url
            )
        )

        parsed = urlsplit(
            canonical
        )

        hostname = (
            parsed.hostname
            or ""
        )

        port = _effective_port(
            canonical
        )

        if (
            port
            not in self.policy.allowed_ports
        ):
            raise UnsafeExternalURL(
                (
                    "external port is "
                    f"not allowed: {port}"
                )
            )

        _resolve_and_validate_host(
            hostname,
            port,
        )

        return canonical

    def fetch(
        self,
        url: str,
        *,
        allowed_content_types: Optional[
            Iterable[str]
        ] = None,
        max_bytes: Optional[
            int
        ] = None,
    ) -> FetchResult:
        """
        Fetch one external resource safely.

        allowed_content_types supports exact MIME types and simple
        wildcards such as "image/*" or "video/*".
        """

        accepted_types = frozenset(
            allowed_content_types
            or _DEFAULT_HTML_CONTENT_TYPES
        )

        if not accepted_types:
            raise ValueError(
                (
                    "allowed_content_types "
                    "cannot be empty"
                )
            )

        byte_limit = (
            self.policy.max_bytes
            if max_bytes is None
            else int(max_bytes)
        )

        if byte_limit <= 0:
            raise ValueError(
                "max_bytes must be > 0"
            )

        requested_url = (
            canonicalize_external_url(
                url
            )
        )

        current_url = requested_url

        redirect_chain = []

        for redirect_count in range(
            self.policy.max_redirects + 1
        ):
            current_url = (
                self.validate_url(
                    current_url
                )
            )

            try:
                response = self.session.get(
                    current_url,
                    headers={
                        "User-Agent": (
                            self.policy.user_agent
                        ),
                        "Accept": "*/*",
                    },
                    timeout=(
                        self.policy.connect_timeout,
                        self.policy.read_timeout,
                    ),
                    allow_redirects=False,
                    stream=True,
                )

            except requests.RequestException as exc:
                raise ExternalFetchNetworkError(
                    "external request failed"
                ) from exc

            try:
                status_code = int(
                    response.status_code
                )

                if (
                    status_code
                    in _REDIRECT_STATUS_CODES
                ):
                    location = (
                        response.headers.get(
                            "Location"
                        )
                    )

                    if not location:
                        raise ExternalFetchHTTPError(
                            (
                                "redirect response "
                                "has no Location header"
                            )
                        )

                    if (
                        redirect_count
                        >= self.policy.max_redirects
                    ):
                        raise ExternalFetchHTTPError(
                            (
                                "external redirect "
                                "limit exceeded"
                            )
                        )

                    next_url = urljoin(
                        current_url,
                        location,
                    )

                    next_url = (
                        canonicalize_external_url(
                            next_url
                        )
                    )

                    redirect_chain.append(
                        next_url
                    )

                    current_url = next_url
                    continue

                if not (
                    200
                    <= status_code
                    < 300
                ):
                    raise ExternalFetchHTTPError(
                        (
                            "unexpected external "
                            "HTTP status: "
                            f"{status_code}"
                        )
                    )

                content_type = (
                    _normalize_content_type(
                        response.headers.get(
                            "Content-Type",
                            "",
                        )
                    )
                )

                if not content_type:
                    raise UnsupportedExternalContentType(
                        (
                            "external response has "
                            "no Content-Type"
                        )
                    )

                if not _content_type_is_allowed(
                    content_type,
                    accepted_types,
                ):
                    raise UnsupportedExternalContentType(
                        (
                            "external content type "
                            "is not allowed: "
                            f"{content_type}"
                        )
                    )

                raw_content_length = (
                    response.headers.get(
                        "Content-Length"
                    )
                )

                if raw_content_length:
                    try:
                        content_length = int(
                            raw_content_length
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        content_length = None

                    if (
                        content_length is not None
                        and content_length
                        > byte_limit
                    ):
                        raise ExternalResponseTooLarge(
                            (
                                "external response "
                                "exceeds byte limit"
                            )
                        )

                chunks = []
                total_size = 0

                for chunk in response.iter_content(
                    chunk_size=64 * 1024
                ):
                    if not chunk:
                        continue

                    total_size += len(
                        chunk
                    )

                    if total_size > byte_limit:
                        raise ExternalResponseTooLarge(
                            (
                                "external response "
                                "exceeds byte limit"
                            )
                        )

                    chunks.append(
                        chunk
                    )

                body = b"".join(
                    chunks
                )

                encoding = str(
                    getattr(
                        response,
                        "encoding",
                        "",
                    )
                    or ""
                )

                headers = {
                    str(key): str(value)
                    for key, value
                    in response.headers.items()
                }

                return FetchResult(
                    requested_url=(
                        requested_url
                    ),
                    final_url=(
                        current_url
                    ),
                    status_code=(
                        status_code
                    ),
                    content_type=(
                        content_type
                    ),
                    content=body,
                    encoding=encoding,
                    redirect_chain=tuple(
                        redirect_chain
                    ),
                    response_headers=headers,
                )

            finally:
                response.close()

        raise ExternalFetchHTTPError(
            (
                "external fetch ended "
                "unexpectedly"
            )
        )
