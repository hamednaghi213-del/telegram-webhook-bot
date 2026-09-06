"""Transport-neutral adapter for social and Instagram source content."""

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
from urllib.parse import urlsplit

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_fetcher import (
    canonicalize_external_url,
)


# =========================================================
# ERRORS
# =========================================================


class SocialContentError(RuntimeError):
    """Base error for social-content ingestion."""


class SocialContentUnavailable(SocialContentError):
    """Raised when the requested social content cannot be retrieved."""


class SocialContentIncomplete(SocialContentError):
    """Raised when retrieved social content has no usable facts or media."""


class UnsupportedSocialSource(SocialContentError):
    """Raised when no provider supports the supplied social source."""


# =========================================================
# HELPERS
# =========================================================


def _clean_text(value: Any) -> str:
    return " ".join(
        str(
            value
            or ""
        ).split()
    ).strip()


def _clean_multiline_text(
    value: Any,
) -> str:
    raw = str(
        value
        or ""
    )

    paragraphs = []

    for chunk in raw.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split(
        "\n"
    ):
        cleaned = _clean_text(
            chunk
        )

        if cleaned:
            paragraphs.append(
                cleaned
            )

    return "\n\n".join(
        paragraphs
    )


def _normalize_language(
    value: Any,
) -> str:
    language = _clean_text(
        value
    ).lower()

    if not language:
        return ""

    return (
        language
        .replace(
            "_",
            "-"
        )
        .split(
            "-",
            1,
        )[0]
    )


def _normalize_source_type(
    value: Any,
) -> str:
    normalized = _clean_text(
        value
    ).lower()

    aliases = {
        "ig": "instagram",
        "instagram.com": "instagram",
        "www.instagram.com": "instagram",
        "reel": "instagram",
        "instagram_reel": "instagram",
        "instagram_post": "instagram",
        "instagram_carousel": "instagram",
    }

    return aliases.get(
        normalized,
        normalized,
    )


def _safe_url(
    value: Any,
) -> str:
    raw = _clean_text(
        value
    )

    if not raw:
        return ""

    try:
        return canonicalize_external_url(
            raw
        )
    except Exception:
        return ""


def _extract_hostname(
    url: str,
) -> str:
    try:
        return (
            urlsplit(
                url
            ).hostname
            or ""
        ).lower()
    except Exception:
        return ""


def _deduplicate_strings(
    values: Sequence[Any],
) -> Tuple[str, ...]:
    result = []
    seen = set()

    for value in values:
        cleaned = _clean_text(
            value
        )

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            cleaned
        )

    return tuple(
        result
    )


# =========================================================
# RAW SOURCE MODELS
# =========================================================


@dataclass(frozen=True)
class SocialMediaAsset:
    """
    Provider-neutral representation of media returned by a social source.

    No Telegram file_id or Bale-specific identifier is allowed here.
    """

    type: str
    source_url: str

    mime_type: str = ""

    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    alt_text: str = ""

    position: int = 0

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        media_type = (
            _clean_text(
                self.type
            ).lower()
        )

        source_url = _safe_url(
            self.source_url
        )

        if not media_type:
            raise SocialContentIncomplete(
                "social media asset type is required"
            )

        if not source_url:
            raise SocialContentIncomplete(
                "social media asset URL is invalid"
            )

        if (
            self.width is not None
            and int(
                self.width
            ) <= 0
        ):
            raise SocialContentIncomplete(
                "social media width must be > 0"
            )

        if (
            self.height is not None
            and int(
                self.height
            ) <= 0
        ):
            raise SocialContentIncomplete(
                "social media height must be > 0"
            )

        if (
            self.duration is not None
            and float(
                self.duration
            ) < 0
        ):
            raise SocialContentIncomplete(
                "social media duration must be >= 0"
            )

        if int(
            self.position
        ) < 0:
            raise SocialContentIncomplete(
                "social media position must be >= 0"
            )

        object.__setattr__(
            self,
            "type",
            media_type,
        )

        object.__setattr__(
            self,
            "source_url",
            source_url,
        )

        object.__setattr__(
            self,
            "position",
            int(
                self.position
            ),
        )


@dataclass(frozen=True)
class SocialSourceContent:
    """
    Raw but normalized facts returned by one social-source provider.

    Account identity is provenance only. It must never be automatically
    injected into the visible news body.
    """

    source_type: str
    source_url: str

    content_kind: str = "post"

    caption: str = ""
    title: str = ""

    published_at: str = ""
    original_language: str = ""

    media: Tuple[
        SocialMediaAsset,
        ...
    ] = field(
        default_factory=tuple
    )

    # Explicit facts reported by the source/provider.
    #
    # These are facts such as:
    #   - named people
    #   - stated location
    #   - stated event
    #   - explicit date/time
    #
    # They must not contain model-generated assumptions.
    explicit_facts: Tuple[str, ...] = field(
        default_factory=tuple
    )

    # Internal provenance only.
    account_name: str = ""
    account_username: str = ""
    account_id: str = ""

    provider_name: str = ""

    confidence: float = 0.0

    warnings: Tuple[str, ...] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        source_type = _normalize_source_type(
            self.source_type
        )

        source_url = _safe_url(
            self.source_url
        )

        if not source_type:
            raise SocialContentIncomplete(
                "social source type is required"
            )

        if not source_url:
            raise SocialContentIncomplete(
                "social source URL is invalid"
            )

        confidence = float(
            self.confidence
        )

        if not (
            0.0
            <= confidence
            <= 1.0
        ):
            raise SocialContentIncomplete(
                "social confidence must be between 0.0 and 1.0"
            )

        media = tuple(
            self.media
            or ()
        )

        for item in media:
            if not isinstance(
                item,
                SocialMediaAsset,
            ):
                raise TypeError(
                    "social media items must be SocialMediaAsset instances"
                )

        object.__setattr__(
            self,
            "source_type",
            source_type,
        )

        object.__setattr__(
            self,
            "source_url",
            source_url,
        )

        object.__setattr__(
            self,
            "caption",
            _clean_multiline_text(
                self.caption
            ),
        )

        object.__setattr__(
            self,
            "title",
            _clean_text(
                self.title
            ),
        )

        object.__setattr__(
            self,
            "content_kind",
            (
                _clean_text(
                    self.content_kind
                ).lower()
                or "post"
            ),
        )

        object.__setattr__(
            self,
            "published_at",
            _clean_text(
                self.published_at
            ),
        )

        object.__setattr__(
            self,
            "original_language",
            _normalize_language(
                self.original_language
            ),
        )

        object.__setattr__(
            self,
            "explicit_facts",
            _deduplicate_strings(
                self.explicit_facts
            ),
        )

        object.__setattr__(
            self,
            "warnings",
            _deduplicate_strings(
                self.warnings
            ),
        )

        object.__setattr__(
            self,
            "media",
            media,
        )

        object.__setattr__(
            self,
            "confidence",
            confidence,
        )


# =========================================================
# PROVIDER CONTRACT
# =========================================================


class SocialContentProvider(Protocol):
    """
    Contract implemented by Instagram or future social-source providers.

    The adapter does not assume how a provider obtains content.
    A provider may use an official API, authorized connector, external
    extraction service, or another compliant acquisition mechanism.
    """

    name: str

    def supports(
        self,
        url: str,
    ) -> bool:
        ...

    def fetch(
        self,
        url: str,
    ) -> SocialSourceContent:
        ...


# =========================================================
# INSTAGRAM URL DETECTION
# =========================================================


def is_instagram_url(
    url: str,
) -> bool:
    safe = _safe_url(
        url
    )

    if not safe:
        return False

    hostname = _extract_hostname(
        safe
    )

    return hostname in {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
    }


def classify_instagram_content_kind(
    url: str,
) -> str:
    """
    Infer only the structural Instagram URL type.

    This does not infer the subject or facts of the post.
    """

    safe = _safe_url(
        url
    )

    if not safe:
        return ""

    path = (
        urlsplit(
            safe
        ).path
        .strip("/")
        .lower()
    )

    if path.startswith(
        "reel/"
    ):
        return "reel"

    if path.startswith(
        "reels/"
    ):
        return "reel"

    if path.startswith(
        "p/"
    ):
        return "post"

    if path.startswith(
        "tv/"
    ):
        return "video"

    return "unknown"


# =========================================================
# MEDIA NORMALIZATION
# =========================================================


def _normalize_media_type(
    value: str,
) -> str:
    media_type = (
        _clean_text(
            value
        ).lower()
    )

    aliases = {
        "image": "photo",
        "jpeg": "photo",
        "jpg": "photo",
        "png": "photo",
        "picture": "photo",
        "movie": "video",
        "reel": "video",
    }

    return aliases.get(
        media_type,
        media_type,
    )


def _convert_media(
    assets: Tuple[
        SocialMediaAsset,
        ...
    ],
    content_kind: str,
) -> Tuple[
    ExternalMedia,
    ...
]:
    if not assets:
        return ()

    ordered = sorted(
        assets,
        key=lambda item: (
            item.position,
            item.source_url,
        ),
    )

    result = []

    multiple = len(
        ordered
    ) > 1

    for index, item in enumerate(
        ordered
    ):
        media_type = _normalize_media_type(
            item.type
        )

        if not media_type:
            continue

        if index == 0:
            presentation = "cover"

        elif multiple:
            presentation = "gallery"

        else:
            presentation = ""

        result.append(
            ExternalMedia(
                type=media_type,
                source_url=item.source_url,
                mime_type=item.mime_type,
                width=item.width,
                height=item.height,
                duration=item.duration,
                alt_text=item.alt_text,
                position=index,
                presentation=presentation,
                metadata={
                    "social_content_kind": (
                        content_kind
                    ),
                    "original_position": (
                        item.position
                    ),
                    **dict(
                        item.metadata
                        or {}
                    ),
                },
            )
        )

    return tuple(
        result
    )


# =========================================================
# FACT / CONTENT EXTRACTION
# =========================================================


def _build_fact_body(
    source: SocialSourceContent,
) -> str:
    """
    Build a factual source body without inventing information.

    Caption is primary evidence. Explicit provider facts supplement it.
    No unsupported names, dates, locations, motives, or consequences
    are generated here.
    """

    parts = []

    caption = _clean_multiline_text(
        source.caption
    )

    if caption:
        parts.append(
            caption
        )

    for fact in source.explicit_facts:
        cleaned = _clean_text(
            fact
        )

        if not cleaned:
            continue

        if any(
            cleaned.casefold()
            == existing.casefold()
            for existing in parts
        ):
            continue

        parts.append(
            cleaned
        )

    return "\n\n".join(
        parts
    ).strip()


def _derive_title(
    source: SocialSourceContent,
    body: str,
) -> str:
    """
    Use only explicit source text for a deterministic provisional title.

    Final editorial rewriting is intentionally left to the shared
    Editorial layer.
    """

    explicit_title = _clean_text(
        source.title
    )

    if explicit_title:
        return explicit_title

    if not body:
        return ""

    first_line = (
        body
        .split(
            "\n",
            1,
        )[0]
        .strip()
    )

    if len(
        first_line
    ) <= 140:
        return first_line

    shortened = (
        first_line[:137]
        .rsplit(
            " ",
            1,
        )[0]
        .strip()
    )

    if not shortened:
        shortened = first_line[
            :137
        ].strip()

    return (
        f"{shortened}…"
        if shortened
        else ""
    )


def _derive_lead(
    body: str,
    title: str,
) -> str:
    if not body:
        return ""

    paragraphs = [
        _clean_text(
            item
        )
        for item in body.split(
            "\n\n"
        )
        if _clean_text(
            item
        )
    ]

    for paragraph in paragraphs:
        if (
            title
            and paragraph
            == title
        ):
            continue

        return paragraph

    return ""


# =========================================================
# QUALITY / CONFIDENCE
# =========================================================


def _calculate_confidence(
    source: SocialSourceContent,
    body: str,
    media: Tuple[
        ExternalMedia,
        ...
    ],
) -> float:
    """
    Conservative confidence score.

    Confidence describes extraction completeness, not truthfulness.
    """

    score = 0.0

    if source.confidence > 0:
        score += (
            source.confidence
            * 0.50
        )

    if body:
        score += 0.20

    if len(
        body
    ) >= 120:
        score += 0.08

    if source.explicit_facts:
        score += 0.07

    if media:
        score += 0.08

    if source.published_at:
        score += 0.03

    if source.original_language:
        score += 0.02

    if source.provider_name:
        score += 0.02

    return round(
        min(
            max(
                score,
                0.0,
            ),
            1.0,
        ),
        3,
    )


def _build_warnings(
    source: SocialSourceContent,
    body: str,
    media: Tuple[
        ExternalMedia,
        ...
    ],
    confidence: float,
) -> Tuple[str, ...]:
    warnings = list(
        source.warnings
    )

    if not body:
        warnings.append(
            "no_social_text"
        )

    if not media:
        warnings.append(
            "no_social_media"
        )

    if (
        not source.explicit_facts
        and len(
            body
        ) < 80
    ):
        warnings.append(
            "limited_source_context"
        )

    if confidence < 0.50:
        warnings.append(
            "low_extraction_confidence"
        )

    if (
        source.source_type
        == "instagram"
        and not source.provider_name
    ):
        warnings.append(
            "instagram_provider_unspecified"
        )

    return _deduplicate_strings(
        warnings
    )


# =========================================================
# SOCIAL → NORMALIZED EXTERNAL CONTENT
# =========================================================


def normalize_social_source(
    source: SocialSourceContent,
) -> NormalizedExternalContent:
    """
    Convert provider output into the shared external-content model.

    Important:
      - account username/id stays internal in metadata
      - no account identity is automatically added to visible news text
      - no translation occurs
      - no AI rewriting occurs
      - no unsupported facts are invented
    """

    if not isinstance(
        source,
        SocialSourceContent,
    ):
        raise TypeError(
            "source must be SocialSourceContent"
        )

    body = _build_fact_body(
        source
    )

    media = _convert_media(
        source.media,
        source.content_kind,
    )

    if (
        not body
        and not media
    ):
        raise SocialContentIncomplete(
            "social source contains no usable text or media"
        )

    title = _derive_title(
        source,
        body,
    )

    lead = _derive_lead(
        body,
        title,
    )

    confidence = _calculate_confidence(
        source,
        body,
        media,
    )

    warnings = _build_warnings(
        source,
        body,
        media,
        confidence,
    )

    return NormalizedExternalContent(
        source_type=source.source_type,
        source_url=source.source_url,
        canonical_url=source.source_url,
        content_type=source.content_kind,
        title=title,
        lead=lead,
        body=body,
        published_at=source.published_at,
        original_language=(
            source.original_language
        ),
        # Intentionally blank for visible publication semantics.
        # Account/source identity remains provenance metadata below.
        source_name="",
        media=media,
        extraction_confidence=confidence,
        warnings=warnings,
        metadata={
            "adapter": (
                "social_content_adapter"
            ),
            "provider_name": (
                source.provider_name
            ),
            "account_name": (
                source.account_name
            ),
            "account_username": (
                source.account_username
            ),
            "account_id": (
                source.account_id
            ),
            "explicit_facts": (
                source.explicit_facts
            ),
            "source_metadata": dict(
                source.metadata
                or {}
            ),
        },
    )


# =========================================================
# ADAPTER
# =========================================================


class SocialContentAdapter:
    """
    Provider-neutral social-content adapter.

    Providers are injected so Instagram acquisition can evolve independently
    from the Shared Publication Engine.

    This is important because arbitrary public Instagram URL extraction
    cannot be guaranteed by one official API path alone.
    """

    def __init__(
        self,
        providers: Sequence[
            SocialContentProvider
        ] = (),
    ) -> None:
        self.providers = tuple(
            providers
            or ()
        )

    def resolve_provider(
        self,
        url: str,
    ) -> SocialContentProvider:
        canonical_url = _safe_url(
            url
        )

        if not canonical_url:
            raise UnsupportedSocialSource(
                "social source URL is invalid"
            )

        for provider in self.providers:
            try:
                supported = (
                    provider.supports(
                        canonical_url
                    )
                )
            except Exception:
                supported = False

            if supported:
                return provider

        raise UnsupportedSocialSource(
            "no configured provider supports this social source"
        )

    def extract(
        self,
        url: str,
    ) -> NormalizedExternalContent:
        canonical_url = _safe_url(
            url
        )

        if not canonical_url:
            raise UnsupportedSocialSource(
                "social source URL is invalid"
            )

        provider = self.resolve_provider(
            canonical_url
        )

        try:
            source = provider.fetch(
                canonical_url
            )
        except SocialContentError:
            raise
        except Exception as exc:
            raise SocialContentUnavailable(
                "social content provider failed"
            ) from exc

        if not isinstance(
            source,
            SocialSourceContent,
        ):
            raise SocialContentUnavailable(
                "social provider returned an invalid result"
            )

        return normalize_social_source(
            source
        )
