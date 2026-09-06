"""Materialization boundary for transport-neutral external media."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from core.external_content_model import (
    ExternalMedia,
)
from core.external_fetcher import (
    ExternalFetchError,
    FetchPolicy,
    SafeExternalFetcher,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalMediaMaterializationError(
    RuntimeError
):
    """Base error for external-media materialization."""


class ExternalMediaDownloadError(
    ExternalMediaMaterializationError
):
    """Raised when external media cannot be acquired safely."""


class UnsupportedExternalMedia(
    ExternalMediaMaterializationError
):
    """Raised when an external media type cannot be materialized."""


class ExternalMediaUploadError(
    ExternalMediaMaterializationError
):
    """Raised when a transport materializer cannot prepare the media."""


# =========================================================
# MATERIALIZED SOURCE
# =========================================================


@dataclass(frozen=True)
class AcquiredExternalMedia:
    """
    Safely downloaded external media.

    This remains independent from Telegram and Bale.
    """

    type: str

    source_url: str
    final_url: str

    content: bytes

    mime_type: str = ""

    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    position: int = 0
    presentation: str = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def size_bytes(
        self,
    ) -> int:
        return len(
            self.content
        )


# =========================================================
# TRANSPORT-READY MEDIA
# =========================================================


@dataclass(frozen=True)
class MaterializedExternalMedia:
    """
    External media prepared for the existing publication pipeline.

    `file_id` is optional by design. The transport materializer decides
    whether a reusable platform identifier exists.

    The original external URL is preserved only as provenance.
    """

    type: str

    file_id: str = ""

    position: int = 0
    presentation: str = ""

    source_url: str = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def as_prepared_file(
        self,
    ) -> Mapping[str, Any]:
        """
        Return the mapping shape accepted by PreparedContent.files.

        This method must only be used after the media has actually been
        prepared for the target publication transport.
        """

        if not self.file_id:
            raise ExternalMediaMaterializationError(
                "materialized media has no transport file_id"
            )

        return {
            "type": self.type,
            "file_id": self.file_id,
            "position": self.position,
            "presentation": self.presentation,
            "external_source_url": self.source_url,
            "external_metadata": dict(
                self.metadata
                or {}
            ),
        }


# =========================================================
# TRANSPORT MATERIALIZER CONTRACT
# =========================================================


class ExternalMediaTransportMaterializer(
    Protocol
):
    """
    Contract for preparing acquired bytes for a publication transport.

    Implementations may later prepare media through Telegram, Bale,
    or another transport-specific staging mechanism.

    This layer does not publish to a destination channel.
    """

    name: str

    def supports(
        self,
        media: AcquiredExternalMedia,
    ) -> bool:
        ...

    def materialize(
        self,
        media: AcquiredExternalMedia,
    ) -> MaterializedExternalMedia:
        ...


# =========================================================
# MIME POLICY
# =========================================================


_MEDIA_MIME_POLICY = {
    "photo": (
        "image/*",
    ),
    "image": (
        "image/*",
    ),
    "video": (
        "video/*",
    ),
    "document": (
        "application/pdf",
        "application/octet-stream",
        "text/plain",
    ),
    "audio": (
        "audio/*",
    ),
}


def _normalize_media_type(
    value: Any,
) -> str:
    media_type = str(
        value
        or ""
    ).strip().lower()

    aliases = {
        "image": "photo",
        "picture": "photo",
        "jpg": "photo",
        "jpeg": "photo",
        "png": "photo",
        "movie": "video",
        "reel": "video",
    }

    return aliases.get(
        media_type,
        media_type,
    )


def _allowed_mime_types(
    media_type: str,
) -> Tuple[str, ...]:
    normalized = _normalize_media_type(
        media_type
    )

    allowed = _MEDIA_MIME_POLICY.get(
        normalized
    )

    if not allowed:
        raise UnsupportedExternalMedia(
            f"unsupported external media type: {normalized}"
        )

    return tuple(
        allowed
    )


# =========================================================
# SAFE ACQUISITION
# =========================================================


class ExternalMediaAcquirer:
    """
    Safely acquires bytes referenced by ExternalMedia.

    Network security is delegated to the already-established
    SafeExternalFetcher:
      - SSRF protection
      - redirect revalidation
      - timeout
      - response-size limit
      - MIME validation
    """

    def __init__(
        self,
        *,
        fetcher: Optional[
            SafeExternalFetcher
        ] = None,
        max_bytes: int = (
            25 * 1024 * 1024
        ),
    ) -> None:
        if max_bytes <= 0:
            raise ValueError(
                "max_bytes must be > 0"
            )

        self.max_bytes = int(
            max_bytes
        )

        self.fetcher = (
            fetcher
            or SafeExternalFetcher(
                policy=FetchPolicy(
                    max_bytes=(
                        self.max_bytes
                    )
                )
            )
        )

    def acquire(
        self,
        media: ExternalMedia,
    ) -> AcquiredExternalMedia:
        if not isinstance(
            media,
            ExternalMedia,
        ):
            raise TypeError(
                "media must be ExternalMedia"
            )

        media_type = (
            _normalize_media_type(
                media.type
            )
        )

        allowed_mime_types = (
            _allowed_mime_types(
                media_type
            )
        )

        try:
            result = self.fetcher.fetch(
                media.source_url,
                allowed_content_types=(
                    allowed_mime_types
                ),
            )

        except ExternalFetchError as exc:
            raise ExternalMediaDownloadError(
                "external media acquisition failed"
            ) from exc

        if not result.content:
            raise ExternalMediaDownloadError(
                "external media response is empty"
            )

        if (
            result.size_bytes
            > self.max_bytes
        ):
            raise ExternalMediaDownloadError(
                "external media exceeds materialization size limit"
            )

        return AcquiredExternalMedia(
            type=media_type,
            source_url=(
                media.source_url
            ),
            final_url=(
                result.final_url
            ),
            content=(
                result.content
            ),
            mime_type=(
                result.content_type
            ),
            width=(
                media.width
            ),
            height=(
                media.height
            ),
            duration=(
                media.duration
            ),
            position=(
                media.position
            ),
            presentation=(
                media.presentation
            ),
            metadata={
                "external_metadata": dict(
                    media.metadata
                    or {}
                ),
                "download_size_bytes": (
                    result.size_bytes
                ),
                "redirect_chain": tuple(
                    result.redirect_chain
                    or ()
                ),
            },
        )


# =========================================================
# MATERIALIZATION SERVICE
# =========================================================


class ExternalMediaMaterializer:
    """
    Orchestrates safe acquisition and transport preparation.

    It does NOT publish to Telegram/Bale destinations.
    """

    def __init__(
        self,
        *,
        acquirer: Optional[
            ExternalMediaAcquirer
        ] = None,
        transports: Sequence[
            ExternalMediaTransportMaterializer
        ] = (),
    ) -> None:
        self.acquirer = (
            acquirer
            or ExternalMediaAcquirer()
        )

        self.transports = tuple(
            transports
            or ()
        )

    def _resolve_transport(
        self,
        media: AcquiredExternalMedia,
    ) -> ExternalMediaTransportMaterializer:
        for transport in self.transports:
            try:
                supported = (
                    transport.supports(
                        media
                    )
                )
            except Exception:
                supported = False

            if supported:
                return transport

        raise UnsupportedExternalMedia(
            "no configured transport materializer supports this media"
        )

    def materialize_one(
        self,
        media: ExternalMedia,
    ) -> MaterializedExternalMedia:
        acquired = self.acquirer.acquire(
            media
        )

        transport = self._resolve_transport(
            acquired
        )

        try:
            result = transport.materialize(
                acquired
            )

        except ExternalMediaMaterializationError:
            raise

        except Exception as exc:
            raise ExternalMediaUploadError(
                "external media transport materialization failed"
            ) from exc

        if not isinstance(
            result,
            MaterializedExternalMedia,
        ):
            raise ExternalMediaUploadError(
                "transport materializer returned an invalid result"
            )

        if not result.file_id:
            raise ExternalMediaUploadError(
                "transport materializer returned no file_id"
            )

        return result

    def materialize_many(
        self,
        media_items: Sequence[
            ExternalMedia
        ],
    ) -> Tuple[
        MaterializedExternalMedia,
        ...
    ]:
        """
        Materialize external media in deterministic source order.

        No partial result is returned if any item fails. This prevents
        accidental publication of incomplete external galleries.
        """

        ordered = sorted(
            tuple(
                media_items
                or ()
            ),
            key=lambda item: (
                item.position,
                item.source_url,
            ),
        )

        results = []

        for media in ordered:
            results.append(
                self.materialize_one(
                    media
                )
            )

        return tuple(
            results
        )

    def build_prepared_files(
        self,
        media_items: Sequence[
            ExternalMedia
        ],
    ) -> Tuple[
        Mapping[str, Any],
        ...
    ]:
        """
        Materialize and convert media into PreparedContent.files mappings.

        This is the only boundary in this module where external media may
        become compatible with the existing publication pipeline.
        """

        materialized = (
            self.materialize_many(
                media_items
            )
        )

        return tuple(
            item.as_prepared_file()
            for item in materialized
        )
