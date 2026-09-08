"""Platform-neutral resolver for external content URLs."""

from __future__ import annotations

from dataclasses import (
    dataclass,
    replace,
)
from enum import Enum
from typing import (
    Any,
    Optional,
)
from urllib.parse import (
    urlsplit,
)

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_fetcher import (
    canonicalize_external_url,
)
from core.social_content_adapter import (
    SocialContentAdapter,
    is_instagram_url,
)
from core.web_article_extractor import (
    WebArticleExtractor,
)


# =========================================================
# ERRORS
# =========================================================


class ExternalContentResolutionError(
    RuntimeError
):
    """Base external content resolution error."""


class UnsupportedExternalContent(
    ExternalContentResolutionError
):
    """Raised when no configured resolver can handle the URL."""


class ExternalContentExtractionFailed(
    ExternalContentResolutionError
):
    """Raised when the selected resolver cannot normalize the source."""


# =========================================================
# SOURCE KIND
# =========================================================


class ExternalSourceKind(
    str,
    Enum,
):
    WEB_ARTICLE = "web_article"
    INSTAGRAM = "instagram"


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True)
class ExternalResolutionResult:
    requested_url: str
    canonical_url: str
    source_kind: ExternalSourceKind
    content: NormalizedExternalContent

    @property
    def requires_review(
        self,
    ) -> bool:
        # External ingestion never publishes blindly.
        return True

    @property
    def is_publishable_candidate(
        self,
    ) -> bool:
        return bool(
            self.content
            .is_publishable_candidate
        )


# =========================================================
# URL CLASSIFICATION
# =========================================================


def _hostname(
    url: str,
) -> str:
    try:
        return (
            urlsplit(
                url
            )
            .hostname
            or ""
        ).strip().lower()

    except Exception:
        return ""


def classify_external_url(
    url: str,
) -> ExternalSourceKind:
    """
    Classify source without tying the decision to Telegram/Bale input.

    Instagram remains a dedicated source because arbitrary social content
    extraction needs provider-specific handling. Other safe HTTP(S) URLs
    enter the professional Web Article extractor.
    """

    canonical = (
        canonicalize_external_url(
            url
        )
    )

    if is_instagram_url(
        canonical
    ):
        return (
            ExternalSourceKind
            .INSTAGRAM
        )

    host = _hostname(
        canonical
    )

    if not host:
        raise UnsupportedExternalContent(
            "external URL has no hostname"
        )

    return (
        ExternalSourceKind
        .WEB_ARTICLE
    )


# =========================================================
# RESOLVER
# =========================================================


class ExternalContentResolver:
    """
    Single platform-neutral entry point for external URL ingestion.

    Telegram Input Adapter
    Bale Input Adapter
    Future Input Adapter
            ↓
    ExternalContentResolver
            ↓
    NormalizedExternalContent
    """

    def __init__(
        self,
        *,
        web_extractor: Optional[
            WebArticleExtractor
        ] = None,
        social_adapter: Optional[
            SocialContentAdapter
        ] = None,
    ) -> None:
        self.web_extractor = (
            web_extractor
            or WebArticleExtractor()
        )

        self.social_adapter = (
            social_adapter
        )

    def resolve(
        self,
        url: str,
    ) -> ExternalResolutionResult:
        canonical = (
            canonicalize_external_url(
                url
            )
        )

        source_kind = (
            classify_external_url(
                canonical
            )
        )

        if (
            source_kind
            == ExternalSourceKind
            .INSTAGRAM
        ):
            content = (
                self._resolve_instagram(
                    canonical
                )
            )

        elif (
            source_kind
            == ExternalSourceKind
            .WEB_ARTICLE
        ):
            content = (
                self._resolve_web_article(
                    canonical
                )
            )

        else:
            raise UnsupportedExternalContent(
                f"unsupported external source: {source_kind}"
            )

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise ExternalContentExtractionFailed(
                "external resolver returned invalid normalized content"
            )

        return ExternalResolutionResult(
            requested_url=str(
                url
                or ""
            ).strip(),
            canonical_url=canonical,
            source_kind=source_kind,
            content=content,
        )

    def _resolve_web_article(
        self,
        url: str,
    ) -> NormalizedExternalContent:
        try:
            content = (
                self.web_extractor
                .extract(
                    url
                )
            )

        except Exception as exc:
            raise ExternalContentExtractionFailed(
                f"web article extraction failed: {exc}"
            ) from exc

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise ExternalContentExtractionFailed(
                "web article extractor returned invalid content"
            )

        if not content.media:
            return content

        trusted_primary = next(
            (
                item
                for item in (
                    content.media
                    or ()
                )
                if bool(
                    getattr(
                        item,
                        "metadata",
                        {},
                    ).get(
                        "trustworthy_primary",
                        False,
                    )
                )
            ),
            None,
        )

        if trusted_primary is None:
            return replace(
                content,
                media=(),
            )

        return replace(
            content,
            media=(
                replace(
                    trusted_primary,
                    position=0,
                    presentation="cover",
                ),
            ),
        )

    def _resolve_instagram(
        self,
        url: str,
    ) -> NormalizedExternalContent:
        """
        Instagram extraction is intentionally provider-backed.

        We do not pretend the official Instagram API can retrieve arbitrary
        public posts. A configured SocialContentAdapter/provider must supply
        source facts before news reconstruction.
        """

        if self.social_adapter is None:
            raise UnsupportedExternalContent(
                "Instagram source requires a configured social content provider"
            )

        try:
            content = (
                self.social_adapter
                .extract(
                    url
                )
            )

        except Exception as exc:
            raise ExternalContentExtractionFailed(
                f"social content extraction failed: {exc}"
            ) from exc

        if not isinstance(
            content,
            NormalizedExternalContent,
        ):
            raise ExternalContentExtractionFailed(
                "social content adapter returned invalid content"
            )

        return content


# =========================================================
# INPUT HELPER
# =========================================================


def extract_single_external_url(
    text: Any,
) -> str:
    """
    Return one standalone HTTP(S) URL from an input message.

    This deliberately does not treat a URL buried inside ordinary news text
    as an ingestion command. Existing Telegram/Bale text publication must
    therefore remain unchanged.
    """

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return ""

    if any(
        char.isspace()
        for char in value
    ):
        return ""

    try:
        canonical = (
            canonicalize_external_url(
                value
            )
        )

    except Exception:
        return ""

    return canonical
