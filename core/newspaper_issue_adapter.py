"""Transport-neutral newspaper issue ingestion models and adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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
    NormalizedExternalContent,
)
from core.external_fetcher import (
    canonicalize_external_url,
)


# =========================================================
# ERRORS
# =========================================================


class NewspaperIssueError(RuntimeError):
    """Base error for newspaper issue ingestion."""


class NewspaperIssueUnavailable(
    NewspaperIssueError
):
    """Raised when a configured newspaper issue cannot be retrieved."""


class NewspaperIssueIncomplete(
    NewspaperIssueError
):
    """Raised when a newspaper issue has no usable content."""


class UnsupportedNewspaperSource(
    NewspaperIssueError
):
    """Raised when no provider supports a newspaper source."""


# =========================================================
# HELPERS
# =========================================================


def _clean_text(
    value: Any,
) -> str:
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

    parts = []

    for chunk in (
        raw.replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
        .split(
            "\n"
        )
    ):
        cleaned = _clean_text(
            chunk
        )

        if cleaned:
            parts.append(
                cleaned
            )

    return "\n\n".join(
        parts
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
            "-",
        )
        .split(
            "-",
            1,
        )[0]
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


def _normalize_issue_date(
    value: Any,
) -> str:
    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    return _clean_text(
        value
    )


def _normalize_score(
    value: Any,
    *,
    field_name: str,
) -> float:
    try:
        score = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise NewspaperIssueIncomplete(
            f"{field_name} must be numeric"
        ) from exc

    if not (
        0.0
        <= score
        <= 1.0
    ):
        raise NewspaperIssueIncomplete(
            f"{field_name} must be between 0.0 and 1.0"
        )

    return score


# =========================================================
# CONFIG
# =========================================================


@dataclass(frozen=True)
class NewspaperTarget:
    """
    Configured newspaper source.

    This object describes one publication, not one specific page.
    """

    key: str
    name: str

    country: str = ""
    language: str = ""

    source_url: str = ""
    provider_key: str = ""

    active: bool = True
    priority: int = 0

    topic_preferences: Tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        key = _clean_text(
            self.key
        )

        name = _clean_text(
            self.name
        )

        if not key:
            raise NewspaperIssueIncomplete(
                "newspaper key is required"
            )

        if not name:
            raise NewspaperIssueIncomplete(
                "newspaper name is required"
            )

        source_url = ""

        if self.source_url:
            source_url = _safe_url(
                self.source_url
            )

            if not source_url:
                raise NewspaperIssueIncomplete(
                    "newspaper source URL is invalid"
                )

        object.__setattr__(
            self,
            "key",
            key,
        )

        object.__setattr__(
            self,
            "name",
            name,
        )

        object.__setattr__(
            self,
            "country",
            _clean_text(
                self.country
            ),
        )

        object.__setattr__(
            self,
            "language",
            _normalize_language(
                self.language
            ),
        )

        object.__setattr__(
            self,
            "source_url",
            source_url,
        )

        object.__setattr__(
            self,
            "provider_key",
            _clean_text(
                self.provider_key
            ).lower(),
        )

        object.__setattr__(
            self,
            "priority",
            int(
                self.priority
            ),
        )

        object.__setattr__(
            self,
            "topic_preferences",
            _deduplicate_strings(
                self.topic_preferences
            ),
        )


# =========================================================
# ISSUE ASSET
# =========================================================


@dataclass(frozen=True)
class NewspaperIssueAsset:
    """
    Original newspaper issue resource.

    Examples:
      - full PDF
      - ZIP of page images
      - issue landing page
      - provider-owned issue resource
    """

    type: str
    source_url: str

    mime_type: str = ""

    page_count: Optional[int] = None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        asset_type = (
            _clean_text(
                self.type
            ).lower()
        )

        source_url = _safe_url(
            self.source_url
        )

        if not asset_type:
            raise NewspaperIssueIncomplete(
                "issue asset type is required"
            )

        if not source_url:
            raise NewspaperIssueIncomplete(
                "issue asset URL is invalid"
            )

        if (
            self.page_count is not None
            and int(
                self.page_count
            ) <= 0
        ):
            raise NewspaperIssueIncomplete(
                "issue page count must be > 0"
            )

        object.__setattr__(
            self,
            "type",
            asset_type,
        )

        object.__setattr__(
            self,
            "source_url",
            source_url,
        )

        if self.page_count is not None:
            object.__setattr__(
                self,
                "page_count",
                int(
                    self.page_count
                ),
            )


# =========================================================
# PAGE MODEL
# =========================================================


@dataclass(frozen=True)
class NewspaperPage:
    """
    One page of a newspaper issue after provider/layout analysis.
    """

    page_number: int

    image_url: str = ""
    text: str = ""

    section: str = ""

    confidence: float = 0.0

    warnings: Tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        page_number = int(
            self.page_number
        )

        if page_number <= 0:
            raise NewspaperIssueIncomplete(
                "page number must be > 0"
            )

        image_url = ""

        if self.image_url:
            image_url = _safe_url(
                self.image_url
            )

        confidence = _normalize_score(
            self.confidence,
            field_name="page confidence",
        )

        object.__setattr__(
            self,
            "page_number",
            page_number,
        )

        object.__setattr__(
            self,
            "image_url",
            image_url,
        )

        object.__setattr__(
            self,
            "text",
            _clean_multiline_text(
                self.text
            ),
        )

        object.__setattr__(
            self,
            "section",
            _clean_text(
                self.section
            ),
        )

        object.__setattr__(
            self,
            "confidence",
            confidence,
        )

        object.__setattr__(
            self,
            "warnings",
            _deduplicate_strings(
                self.warnings
            ),
        )


# =========================================================
# STORY CANDIDATE
# =========================================================


@dataclass(frozen=True)
class NewspaperStoryCandidate:
    """
    One story detected anywhere in the newspaper issue.

    A candidate may originate from page 1 or any internal page.
    """

    candidate_id: str
    headline: str

    subheadline: str = ""
    summary: str = ""
    body_excerpt: str = ""

    section: str = ""

    page_number: int = 1
    position_on_page: int = 0

    importance: float = 0.0
    confidence: float = 0.0

    article_url: str = ""
    image_url: str = ""

    explicit_facts: Tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    warnings: Tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        candidate_id = _clean_text(
            self.candidate_id
        )

        headline = _clean_text(
            self.headline
        )

        if not candidate_id:
            raise NewspaperIssueIncomplete(
                "newspaper candidate id is required"
            )

        if not headline:
            raise NewspaperIssueIncomplete(
                "newspaper candidate headline is required"
            )

        page_number = int(
            self.page_number
        )

        if page_number <= 0:
            raise NewspaperIssueIncomplete(
                "candidate page number must be > 0"
            )

        position = int(
            self.position_on_page
        )

        if position < 0:
            raise NewspaperIssueIncomplete(
                "candidate position must be >= 0"
            )

        importance = _normalize_score(
            self.importance,
            field_name="importance",
        )

        confidence = _normalize_score(
            self.confidence,
            field_name="confidence",
        )

        article_url = ""

        if self.article_url:
            article_url = _safe_url(
                self.article_url
            )

        image_url = ""

        if self.image_url:
            image_url = _safe_url(
                self.image_url
            )

        object.__setattr__(
            self,
            "candidate_id",
            candidate_id,
        )

        object.__setattr__(
            self,
            "headline",
            headline,
        )

        object.__setattr__(
            self,
            "subheadline",
            _clean_text(
                self.subheadline
            ),
        )

        object.__setattr__(
            self,
            "summary",
            _clean_multiline_text(
                self.summary
            ),
        )

        object.__setattr__(
            self,
            "body_excerpt",
            _clean_multiline_text(
                self.body_excerpt
            ),
        )

        object.__setattr__(
            self,
            "section",
            _clean_text(
                self.section
            ),
        )

        object.__setattr__(
            self,
            "page_number",
            page_number,
        )

        object.__setattr__(
            self,
            "position_on_page",
            position,
        )

        object.__setattr__(
            self,
            "importance",
            importance,
        )

        object.__setattr__(
            self,
            "confidence",
            confidence,
        )

        object.__setattr__(
            self,
            "article_url",
            article_url,
        )

        object.__setattr__(
            self,
            "image_url",
            image_url,
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


# =========================================================
# FULL ISSUE RESULT
# =========================================================


@dataclass(frozen=True)
class NewspaperIssue:
    """
    Provider-neutral result for one complete newspaper issue.
    """

    newspaper_key: str
    newspaper_name: str

    issue_date: str
    source_url: str

    country: str = ""
    language: str = ""

    assets: Tuple[
        NewspaperIssueAsset,
        ...
    ] = field(
        default_factory=tuple
    )

    pages: Tuple[
        NewspaperPage,
        ...
    ] = field(
        default_factory=tuple
    )

    candidates: Tuple[
        NewspaperStoryCandidate,
        ...
    ] = field(
        default_factory=tuple
    )

    provider_name: str = ""

    confidence: float = 0.0

    warnings: Tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        newspaper_key = _clean_text(
            self.newspaper_key
        )

        newspaper_name = _clean_text(
            self.newspaper_name
        )

        issue_date = _normalize_issue_date(
            self.issue_date
        )

        source_url = _safe_url(
            self.source_url
        )

        if not newspaper_key:
            raise NewspaperIssueIncomplete(
                "newspaper key is required"
            )

        if not newspaper_name:
            raise NewspaperIssueIncomplete(
                "newspaper name is required"
            )

        if not issue_date:
            raise NewspaperIssueIncomplete(
                "newspaper issue date is required"
            )

        if not source_url:
            raise NewspaperIssueIncomplete(
                "newspaper issue source URL is invalid"
            )

        assets = tuple(
            self.assets
            or ()
        )

        pages = tuple(
            self.pages
            or ()
        )

        candidates = tuple(
            self.candidates
            or ()
        )

        for asset in assets:
            if not isinstance(
                asset,
                NewspaperIssueAsset,
            ):
                raise TypeError(
                    "assets must be NewspaperIssueAsset instances"
                )

        for page in pages:
            if not isinstance(
                page,
                NewspaperPage,
            ):
                raise TypeError(
                    "pages must be NewspaperPage instances"
                )

        for candidate in candidates:
            if not isinstance(
                candidate,
                NewspaperStoryCandidate,
            ):
                raise TypeError(
                    "candidates must be NewspaperStoryCandidate instances"
                )

        page_numbers = [
            item.page_number
            for item in pages
        ]

        if len(
            page_numbers
        ) != len(
            set(
                page_numbers
            )
        ):
            raise NewspaperIssueIncomplete(
                "newspaper page numbers must be unique"
            )

        candidate_ids = [
            item.candidate_id
            for item in candidates
        ]

        if len(
            candidate_ids
        ) != len(
            set(
                candidate_ids
            )
        ):
            raise NewspaperIssueIncomplete(
                "newspaper candidate ids must be unique"
            )

        confidence = _normalize_score(
            self.confidence,
            field_name="issue confidence",
        )

        object.__setattr__(
            self,
            "newspaper_key",
            newspaper_key,
        )

        object.__setattr__(
            self,
            "newspaper_name",
            newspaper_name,
        )

        object.__setattr__(
            self,
            "issue_date",
            issue_date,
        )

        object.__setattr__(
            self,
            "source_url",
            source_url,
        )

        object.__setattr__(
            self,
            "country",
            _clean_text(
                self.country
            ),
        )

        object.__setattr__(
            self,
            "language",
            _normalize_language(
                self.language
            ),
        )

        object.__setattr__(
            self,
            "assets",
            assets,
        )

        object.__setattr__(
            self,
            "pages",
            pages,
        )

        object.__setattr__(
            self,
            "candidates",
            candidates,
        )

        object.__setattr__(
            self,
            "provider_name",
            _clean_text(
                self.provider_name
            ),
        )

        object.__setattr__(
            self,
            "confidence",
            confidence,
        )

        object.__setattr__(
            self,
            "warnings",
            _deduplicate_strings(
                self.warnings
            ),
        )


# =========================================================
# PROVIDER CONTRACT
# =========================================================


class NewspaperProvider(Protocol):
    """
    Provider contract for complete newspaper issues.

    Implementations may obtain:
      - PDF issues
      - page images
      - newspaper web editions
      - provider-specific digital editions
    """

    name: str

    def supports(
        self,
        target: NewspaperTarget,
    ) -> bool:
        ...

    def fetch_issue(
        self,
        target: NewspaperTarget,
        issue_date: str,
    ) -> NewspaperIssue:
        ...


# =========================================================
# REVIEW PREVIEW
# =========================================================


@dataclass(frozen=True)
class NewspaperCandidatePreview:
    """
    Candidate visible to the review layer.

    User approval remains mandatory before publication.
    """

    candidate_id: str

    headline: str
    subheadline: str
    summary: str

    section: str

    page_number: int
    position_on_page: int

    importance: float
    confidence: float

    article_url: str
    image_url: str

    warnings: Tuple[str, ...]

    requires_review: bool = True


def build_newspaper_candidate_previews(
    issue: NewspaperIssue,
) -> Tuple[
    NewspaperCandidatePreview,
    ...
]:
    if not isinstance(
        issue,
        NewspaperIssue,
    ):
        raise TypeError(
            "issue must be NewspaperIssue"
        )

    ordered = sorted(
        issue.candidates,
        key=lambda item: (
            -item.importance,
            -item.confidence,
            item.page_number,
            item.position_on_page,
            item.candidate_id,
        ),
    )

    return tuple(
        NewspaperCandidatePreview(
            candidate_id=(
                candidate.candidate_id
            ),
            headline=(
                candidate.headline
            ),
            subheadline=(
                candidate.subheadline
            ),
            summary=(
                candidate.summary
            ),
            section=(
                candidate.section
            ),
            page_number=(
                candidate.page_number
            ),
            position_on_page=(
                candidate.position_on_page
            ),
            importance=(
                candidate.importance
            ),
            confidence=(
                candidate.confidence
            ),
            article_url=(
                candidate.article_url
            ),
            image_url=(
                candidate.image_url
            ),
            warnings=(
                candidate.warnings
            ),
            requires_review=True,
        )
        for candidate in ordered
    )


# =========================================================
# CANDIDATE SELECTION
# =========================================================


def _find_candidate(
    issue: NewspaperIssue,
    candidate_id: str,
) -> NewspaperStoryCandidate:
    normalized_id = _clean_text(
        candidate_id
    )

    for candidate in issue.candidates:
        if (
            candidate.candidate_id
            == normalized_id
        ):
            return candidate

    raise NewspaperIssueIncomplete(
        f"newspaper candidate not found: {normalized_id}"
    )


def _candidate_body(
    candidate: NewspaperStoryCandidate,
) -> str:
    parts = []

    if candidate.summary:
        parts.append(
            candidate.summary
        )

    if candidate.body_excerpt:
        if (
            candidate.body_excerpt
            not in parts
        ):
            parts.append(
                candidate.body_excerpt
            )

    for fact in candidate.explicit_facts:
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
    )


def _candidate_media(
    candidate: NewspaperStoryCandidate,
) -> Tuple[
    ExternalMedia,
    ...
]:
    if not candidate.image_url:
        return ()

    return (
        ExternalMedia(
            type="photo",
            source_url=(
                candidate.image_url
            ),
            position=0,
            presentation="cover",
            metadata={
                "candidate_id": (
                    candidate.candidate_id
                ),
                "source": (
                    "newspaper_issue"
                ),
                "page_number": (
                    candidate.page_number
                ),
            },
        ),
    )


def normalize_selected_newspaper_candidate(
    issue: NewspaperIssue,
    candidate_id: str,
) -> NormalizedExternalContent:
    """
    Convert only a user-selected newspaper candidate.

    This function never assumes that the detected excerpt is the full article.
    """

    if not isinstance(
        issue,
        NewspaperIssue,
    ):
        raise TypeError(
            "issue must be NewspaperIssue"
        )

    candidate = _find_candidate(
        issue,
        candidate_id,
    )

    body = _candidate_body(
        candidate
    )

    media = _candidate_media(
        candidate
    )

    warnings = list(
        candidate.warnings
    )

    if not body:
        warnings.append(
            "headline_only_candidate"
        )

    if not candidate.article_url:
        warnings.append(
            "full_article_url_unavailable"
        )

    if candidate.confidence < 0.50:
        warnings.append(
            "low_candidate_confidence"
        )

    warnings = _deduplicate_strings(
        warnings
    )

    source_url = (
        candidate.article_url
        or issue.source_url
    )

    confidence = round(
        min(
            candidate.confidence,
            issue.confidence,
        ),
        3,
    )

    return NormalizedExternalContent(
        source_type=(
            "newspaper_issue"
        ),
        source_url=source_url,
        canonical_url=source_url,
        content_type=(
            "newspaper_story_candidate"
        ),
        title=(
            candidate.headline
        ),
        lead=(
            candidate.subheadline
        ),
        body=body,
        published_at=(
            issue.issue_date
        ),
        original_language=(
            issue.language
        ),
        source_name=(
            issue.newspaper_name
        ),
        media=media,
        extraction_confidence=(
            confidence
        ),
        warnings=warnings,
        metadata={
            "adapter": (
                "newspaper_issue_adapter"
            ),
            "candidate_id": (
                candidate.candidate_id
            ),
            "newspaper_key": (
                issue.newspaper_key
            ),
            "newspaper_name": (
                issue.newspaper_name
            ),
            "country": (
                issue.country
            ),
            "issue_date": (
                issue.issue_date
            ),
            "provider_name": (
                issue.provider_name
            ),
            "importance": (
                candidate.importance
            ),
            "section": (
                candidate.section
            ),
            "page_number": (
                candidate.page_number
            ),
            "position_on_page": (
                candidate.position_on_page
            ),
            "issue_source_url": (
                issue.source_url
            ),
            "explicit_facts": (
                candidate.explicit_facts
            ),
            "candidate_metadata": dict(
                candidate.metadata
                or {}
            ),
        },
    )


# =========================================================
# ADAPTER
# =========================================================


class NewspaperIssueAdapter:
    """
    Provider-neutral complete-newspaper adapter.

    It fetches one full issue and exposes story candidates from every page.
    It does not publish automatically.
    """

    def __init__(
        self,
        providers: Sequence[
            NewspaperProvider
        ] = (),
    ) -> None:
        self.providers = tuple(
            providers
            or ()
        )

    def resolve_provider(
        self,
        target: NewspaperTarget,
    ) -> NewspaperProvider:
        if not isinstance(
            target,
            NewspaperTarget,
        ):
            raise TypeError(
                "target must be NewspaperTarget"
            )

        for provider in self.providers:
            provider_name = (
                _clean_text(
                    getattr(
                        provider,
                        "name",
                        "",
                    )
                ).lower()
            )

            if (
                target.provider_key
                and provider_name
                != target.provider_key
            ):
                continue

            try:
                supported = (
                    provider.supports(
                        target
                    )
                )
            except Exception:
                supported = False

            if supported:
                return provider

        raise UnsupportedNewspaperSource(
            f"no configured provider supports newspaper: {target.key}"
        )

    def fetch_issue(
        self,
        target: NewspaperTarget,
        issue_date: Any,
    ) -> NewspaperIssue:
        if not isinstance(
            target,
            NewspaperTarget,
        ):
            raise TypeError(
                "target must be NewspaperTarget"
            )

        if not target.active:
            raise NewspaperIssueUnavailable(
                f"newspaper target is inactive: {target.key}"
            )

        normalized_date = (
            _normalize_issue_date(
                issue_date
            )
        )

        if not normalized_date:
            raise NewspaperIssueIncomplete(
                "issue date is required"
            )

        provider = self.resolve_provider(
            target
        )

        try:
            issue = provider.fetch_issue(
                target,
                normalized_date,
            )
        except NewspaperIssueError:
            raise
        except Exception as exc:
            raise NewspaperIssueUnavailable(
                "newspaper provider failed"
            ) from exc

        if not isinstance(
            issue,
            NewspaperIssue,
        ):
            raise NewspaperIssueUnavailable(
                "newspaper provider returned an invalid result"
            )

        if (
            issue.newspaper_key
            != target.key
        ):
            raise NewspaperIssueIncomplete(
                "provider returned a mismatched newspaper"
            )

        if (
            issue.issue_date
            != normalized_date
        ):
            raise NewspaperIssueIncomplete(
                "provider returned a mismatched issue date"
            )

        if not issue.pages:
            raise NewspaperIssueIncomplete(
                "newspaper issue contains no analyzed pages"
            )

        if not issue.candidates:
            raise NewspaperIssueIncomplete(
                "newspaper issue contains no detected story candidates"
            )

        known_pages = {
            page.page_number
            for page in issue.pages
        }

        for candidate in issue.candidates:
            if (
                candidate.page_number
                not in known_pages
            ):
                raise NewspaperIssueIncomplete(
                    "candidate references an unknown newspaper page"
                )

        return issue
