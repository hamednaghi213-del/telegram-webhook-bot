"""Transport-neutral models for external content ingestion."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple


def _deep_freeze(value: Any) -> Any:
    """Recursively detach and freeze external-source metadata."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _deep_freeze(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(
            _deep_freeze(item)
            for item in value
        )

    if isinstance(value, (set, frozenset)):
        return frozenset(
            _deep_freeze(item)
            for item in value
        )

    return value


def _freeze_mapping(
    value: Optional[Mapping[str, Any]]
) -> Mapping[str, Any]:
    return _deep_freeze(dict(value or {}))


@dataclass(frozen=True)
class ExternalMedia:
    """
    Transport-neutral media discovered in an external source.

    This object deliberately contains no Telegram file_id,
    Bale identifier, or destination-specific representation.
    """

    type: str
    source_url: str

    mime_type: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    alt_text: str = ""
    position: int = 0

    # Semantic presentation hint only.
    #
    # Examples:
    #   ""          -> ordinary media
    #   "gallery"   -> ordered gallery
    #   "slideshow" -> slideshow/carousel where supported
    #   "cover"     -> primary/hero media
    presentation: str = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata),
        )

    @property
    def has_source(self) -> bool:
        return bool(self.source_url.strip())


@dataclass(frozen=True)
class NormalizedExternalContent:
    """
    Canonical result produced by external-content adapters.

    Possible producers include:
      - web articles
      - social posts
      - newspaper front pages
      - future external sources

    Translation is intentionally not performed here. The original
    language and original extracted content remain intact so a future
    translation layer can operate without changing the ingestion model.
    """

    source_type: str
    source_url: str

    canonical_url: str = ""
    content_type: str = ""

    title: str = ""
    lead: str = ""
    body: str = ""

    author: str = ""
    published_at: str = ""

    # Language of the original source content.
    # Examples: "fa", "en", "ar", "fr".
    original_language: str = ""

    source_name: str = ""

    media: Tuple[ExternalMedia, ...] = field(
        default_factory=tuple
    )

    extraction_confidence: float = 0.0

    warnings: Tuple[str, ...] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "media",
            tuple(self.media or ()),
        )

        object.__setattr__(
            self,
            "warnings",
            tuple(
                str(item)
                for item in (self.warnings or ())
            ),
        )

        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata),
        )

        confidence = float(self.extraction_confidence)

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "extraction_confidence must be between 0.0 and 1.0"
            )

        object.__setattr__(
            self,
            "extraction_confidence",
            confidence,
        )

        for item in self.media:
            if not isinstance(item, ExternalMedia):
                raise TypeError(
                    "media items must be ExternalMedia instances"
                )

    @property
    def best_url(self) -> str:
        return (
            self.canonical_url.strip()
            or self.source_url.strip()
        )

    @property
    def has_text(self) -> bool:
        return bool(
            self.title.strip()
            or self.lead.strip()
            or self.body.strip()
        )

    @property
    def has_media(self) -> bool:
        return bool(self.media)

    @property
    def is_publishable_candidate(self) -> bool:
        """
        Indicates only whether useful extracted content exists.

        This is not editorial approval and must never be treated
        as permission to publish automatically.
        """
        return self.has_text or self.has_media
