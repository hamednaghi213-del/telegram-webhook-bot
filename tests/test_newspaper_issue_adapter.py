import pytest

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.newspaper_issue_adapter import (
    NewspaperCandidatePreview,
    NewspaperIssue,
    NewspaperIssueAdapter,
    NewspaperIssueAsset,
    NewspaperIssueIncomplete,
    NewspaperIssueUnavailable,
    NewspaperPage,
    NewspaperStoryCandidate,
    NewspaperTarget,
    UnsupportedNewspaperSource,
    build_newspaper_candidate_previews,
    normalize_selected_newspaper_candidate,
)


# =========================================================
# FAKE PROVIDERS
# =========================================================


class FakeNewspaperProvider:
    name = "fake_newspaper"

    def supports(
        self,
        target,
    ):
        return (
            target.key
            == "world_daily"
        )

    def fetch_issue(
        self,
        target,
        issue_date,
    ):
        return NewspaperIssue(
            newspaper_key=target.key,
            newspaper_name=target.name,
            issue_date=issue_date,
            source_url=(
                "https://example.com/issues/"
                f"{issue_date}.pdf"
            ),
            country="GB",
            language="en",
            assets=(
                NewspaperIssueAsset(
                    type="pdf",
                    source_url=(
                        "https://example.com/issues/"
                        f"{issue_date}.pdf"
                    ),
                    mime_type="application/pdf",
                    page_count=3,
                ),
            ),
            pages=(
                NewspaperPage(
                    page_number=1,
                    image_url=(
                        "https://example.com/pages/1.jpg"
                    ),
                    text="Front page story",
                    section="Front Page",
                    confidence=0.95,
                ),
                NewspaperPage(
                    page_number=2,
                    image_url=(
                        "https://example.com/pages/2.jpg"
                    ),
                    text="World affairs page",
                    section="World",
                    confidence=0.90,
                ),
                NewspaperPage(
                    page_number=3,
                    image_url=(
                        "https://example.com/pages/3.jpg"
                    ),
                    text="Economy page",
                    section="Economy",
                    confidence=0.88,
                ),
            ),
            candidates=(
                NewspaperStoryCandidate(
                    candidate_id="story-front",
                    headline="Front Page Headline",
                    subheadline="Front page lead",
                    summary=(
                        "Summary of the front-page story."
                    ),
                    section="Front Page",
                    page_number=1,
                    position_on_page=0,
                    importance=0.80,
                    confidence=0.90,
                    article_url=(
                        "https://example.com/articles/front"
                    ),
                    image_url=(
                        "https://example.com/media/front.jpg"
                    ),
                    explicit_facts=(
                        "Fact from the front-page story.",
                    ),
                ),
                NewspaperStoryCandidate(
                    candidate_id="story-world",
                    headline=(
                        "Important Story From Page Two"
                    ),
                    subheadline=(
                        "A major international development"
                    ),
                    summary=(
                        "Summary of the international story."
                    ),
                    body_excerpt=(
                        "Additional source text from page two."
                    ),
                    section="World",
                    page_number=2,
                    position_on_page=1,
                    importance=0.98,
                    confidence=0.94,
                    article_url=(
                        "https://example.com/articles/world"
                    ),
                    image_url=(
                        "https://example.com/media/world.jpg"
                    ),
                    explicit_facts=(
                        "The story appeared on page two.",
                    ),
                ),
                NewspaperStoryCandidate(
                    candidate_id="story-economy",
                    headline="Economy Story",
                    summary=(
                        "Summary of the economy story."
                    ),
                    section="Economy",
                    page_number=3,
                    position_on_page=0,
                    importance=0.70,
                    confidence=0.85,
                ),
            ),
            provider_name=self.name,
            confidence=0.92,
        )


class UnsupportedProvider:
    name = "unsupported"

    def supports(
        self,
        target,
    ):
        return False

    def fetch_issue(
        self,
        target,
        issue_date,
    ):
        raise AssertionError(
            "fetch_issue must not be called"
        )


class BrokenProvider:
    name = "broken"

    def supports(
        self,
        target,
    ):
        return True

    def fetch_issue(
        self,
        target,
        issue_date,
    ):
        raise RuntimeError(
            "provider failed"
        )


class InvalidResultProvider:
    name = "invalid"

    def supports(
        self,
        target,
    ):
        return True

    def fetch_issue(
        self,
        target,
        issue_date,
    ):
        return {
            "issue": "invalid"
        }


# =========================================================
# TARGET CONFIG
# =========================================================


def _target(
    **overrides,
):
    values = {
        "key": "world_daily",
        "name": "World Daily",
        "country": "GB",
        "language": "EN-gb",
        "source_url": (
            "https://example.com/newspaper/"
        ),
        "provider_key": "",
        "active": True,
        "priority": 10,
        "topic_preferences": (
            "World",
            "Economy",
            "World",
        ),
    }

    values.update(
        overrides
    )

    return NewspaperTarget(
        **values
    )


def test_newspaper_target_normalizes_fields():
    target = _target()

    assert target.key == "world_daily"
    assert target.name == "World Daily"
    assert target.language == "en"

    assert target.topic_preferences == (
        "World",
        "Economy",
    )


def test_newspaper_target_requires_key():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="key is required",
    ):
        _target(
            key=""
        )


def test_newspaper_target_requires_name():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="name is required",
    ):
        _target(
            name=""
        )


def test_newspaper_target_rejects_invalid_source_url():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="source URL is invalid",
    ):
        _target(
            source_url="not-a-url"
        )


# =========================================================
# ISSUE ASSET
# =========================================================


def test_issue_asset_accepts_full_pdf():
    asset = NewspaperIssueAsset(
        type="PDF",
        source_url=(
            "https://example.com/issue.pdf#page=1"
        ),
        mime_type="application/pdf",
        page_count=24,
    )

    assert asset.type == "pdf"

    assert asset.source_url == (
        "https://example.com/issue.pdf"
    )

    assert asset.page_count == 24


def test_issue_asset_rejects_invalid_page_count():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="page count",
    ):
        NewspaperIssueAsset(
            type="pdf",
            source_url=(
                "https://example.com/issue.pdf"
            ),
            page_count=0,
        )


# =========================================================
# PAGE MODEL
# =========================================================


def test_page_can_represent_internal_newspaper_page():
    page = NewspaperPage(
        page_number=7,
        image_url=(
            "https://example.com/page7.jpg"
        ),
        text=(
            "Headline\n\n"
            "Article text"
        ),
        section="International",
        confidence=0.9,
    )

    assert page.page_number == 7
    assert page.section == "International"

    assert "Article text" in (
        page.text
    )


def test_page_number_must_be_positive():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="page number",
    ):
        NewspaperPage(
            page_number=0,
        )


def test_page_confidence_must_be_valid():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="confidence",
    ):
        NewspaperPage(
            page_number=1,
            confidence=1.2,
        )


# =========================================================
# STORY CANDIDATE
# =========================================================


def test_story_can_exist_outside_front_page():
    story = NewspaperStoryCandidate(
        candidate_id="page-12-story",
        headline="Important Internal Story",
        page_number=12,
        importance=0.95,
        confidence=0.90,
    )

    assert story.page_number == 12

    assert story.headline == (
        "Important Internal Story"
    )


def test_story_requires_headline():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="headline is required",
    ):
        NewspaperStoryCandidate(
            candidate_id="story",
            headline="",
        )


def test_story_requires_candidate_id():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="candidate id is required",
    ):
        NewspaperStoryCandidate(
            candidate_id="",
            headline="Headline",
        )


def test_story_rejects_invalid_importance():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="importance",
    ):
        NewspaperStoryCandidate(
            candidate_id="story",
            headline="Headline",
            importance=1.1,
        )


def test_story_rejects_invalid_confidence():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="confidence",
    ):
        NewspaperStoryCandidate(
            candidate_id="story",
            headline="Headline",
            confidence=-0.1,
        )


# =========================================================
# COMPLETE ISSUE
# =========================================================


def test_issue_represents_multiple_pages():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    assert len(
        issue.pages
    ) == 3

    assert {
        page.page_number
        for page in issue.pages
    } == {
        1,
        2,
        3,
    }


def test_issue_contains_candidates_from_internal_pages():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    internal = [
        candidate
        for candidate in issue.candidates
        if candidate.page_number > 1
    ]

    assert len(
        internal
    ) == 2


def test_issue_rejects_duplicate_page_numbers():
    with pytest.raises(
        NewspaperIssueIncomplete,
        match="page numbers must be unique",
    ):
        NewspaperIssue(
            newspaper_key="paper",
            newspaper_name="Paper",
            issue_date="2026-09-06",
            source_url=(
                "https://example.com/issue.pdf"
            ),
            pages=(
                NewspaperPage(
                    page_number=1,
                ),
                NewspaperPage(
                    page_number=1,
                ),
            ),
        )


def test_issue_rejects_duplicate_candidate_ids():
    story_a = NewspaperStoryCandidate(
        candidate_id="duplicate",
        headline="First",
    )

    story_b = NewspaperStoryCandidate(
        candidate_id="duplicate",
        headline="Second",
    )

    with pytest.raises(
        NewspaperIssueIncomplete,
        match="candidate ids must be unique",
    ):
        NewspaperIssue(
            newspaper_key="paper",
            newspaper_name="Paper",
            issue_date="2026-09-06",
            source_url=(
                "https://example.com/issue.pdf"
            ),
            candidates=(
                story_a,
                story_b,
            ),
        )


# =========================================================
# CANDIDATE REVIEW
# =========================================================


def test_preview_includes_candidates_from_all_pages():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    previews = (
        build_newspaper_candidate_previews(
            issue
        )
    )

    pages = {
        preview.page_number
        for preview in previews
    }

    assert pages == {
        1,
        2,
        3,
    }


def test_candidate_preview_requires_review():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    previews = (
        build_newspaper_candidate_previews(
            issue
        )
    )

    assert all(
        isinstance(
            preview,
            NewspaperCandidatePreview,
        )
        for preview in previews
    )

    assert all(
        preview.requires_review
        for preview in previews
    )


def test_more_important_internal_story_can_rank_above_front_page():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    previews = (
        build_newspaper_candidate_previews(
            issue
        )
    )

    assert (
        previews[
            0
        ].candidate_id
        == "story-world"
    )

    assert (
        previews[
            0
        ].page_number
        == 2
    )


# =========================================================
# SELECTED CANDIDATE NORMALIZATION
# =========================================================


def test_selected_internal_story_becomes_normalized_content():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert isinstance(
        result,
        NormalizedExternalContent,
    )

    assert result.source_type == (
        "newspaper_issue"
    )

    assert result.title == (
        "Important Story From Page Two"
    )

    assert result.metadata[
        "page_number"
    ] == 2


def test_selected_story_preserves_original_language():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert result.original_language == (
        "en"
    )


def test_selected_story_preserves_newspaper_provenance():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert result.source_name == (
        "World Daily"
    )

    assert result.metadata[
        "newspaper_key"
    ] == "world_daily"


def test_selected_story_uses_article_url_when_available():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert result.source_url == (
        "https://example.com/articles/world"
    )


def test_selected_story_contains_only_source_supplied_text():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert (
        "Summary of the international story."
        in result.body
    )

    assert (
        "Additional source text from page two."
        in result.body
    )

    assert (
        "The story appeared on page two."
        in result.body
    )


def test_selected_story_media_is_transport_neutral():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert len(
        result.media
    ) == 1

    media = result.media[
        0
    ]

    assert media.type == "photo"

    assert not hasattr(
        media,
        "file_id",
    )

    assert not hasattr(
        media,
        "telegram_file_id",
    )

    assert not hasattr(
        media,
        "bale_file_id",
    )


def test_candidate_without_article_url_gets_warning():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-economy",
        )
    )

    assert (
        "full_article_url_unavailable"
        in result.warnings
    )


def test_unknown_candidate_is_rejected():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    with pytest.raises(
        NewspaperIssueIncomplete,
        match="candidate not found",
    ):
        normalize_selected_newspaper_candidate(
            issue,
            "missing",
        )


# =========================================================
# ADAPTER
# =========================================================


def test_adapter_resolves_provider():
    provider = FakeNewspaperProvider()

    adapter = NewspaperIssueAdapter(
        providers=(
            UnsupportedProvider(),
            provider,
        )
    )

    resolved = adapter.resolve_provider(
        _target()
    )

    assert resolved is provider


def test_adapter_fetches_complete_issue():
    adapter = NewspaperIssueAdapter(
        providers=(
            FakeNewspaperProvider(),
        )
    )

    issue = adapter.fetch_issue(
        _target(),
        "2026-09-06",
    )

    assert isinstance(
        issue,
        NewspaperIssue,
    )

    assert len(
        issue.pages
    ) == 3

    assert len(
        issue.candidates
    ) == 3


def test_adapter_rejects_inactive_target():
    adapter = NewspaperIssueAdapter(
        providers=(
            FakeNewspaperProvider(),
        )
    )

    with pytest.raises(
        NewspaperIssueUnavailable,
        match="inactive",
    ):
        adapter.fetch_issue(
            _target(
                active=False
            ),
            "2026-09-06",
        )


def test_adapter_rejects_unsupported_newspaper():
    adapter = NewspaperIssueAdapter(
        providers=(
            UnsupportedProvider(),
        )
    )

    with pytest.raises(
        UnsupportedNewspaperSource,
    ):
        adapter.resolve_provider(
            _target()
        )


def test_adapter_wraps_provider_failure():
    adapter = NewspaperIssueAdapter(
        providers=(
            BrokenProvider(),
        )
    )

    with pytest.raises(
        NewspaperIssueUnavailable,
        match="provider failed",
    ):
        adapter.fetch_issue(
            _target(),
            "2026-09-06",
        )


def test_adapter_rejects_invalid_provider_result():
    adapter = NewspaperIssueAdapter(
        providers=(
            InvalidResultProvider(),
        )
    )

    with pytest.raises(
        NewspaperIssueUnavailable,
        match="invalid result",
    ):
        adapter.fetch_issue(
            _target(),
            "2026-09-06",
        )


def test_adapter_rejects_candidate_for_unknown_page():
    class BadPageProvider:
        name = "bad"

        def supports(
            self,
            target,
        ):
            return True

        def fetch_issue(
            self,
            target,
            issue_date,
        ):
            return NewspaperIssue(
                newspaper_key=target.key,
                newspaper_name=target.name,
                issue_date=issue_date,
                source_url=(
                    "https://example.com/issue.pdf"
                ),
                pages=(
                    NewspaperPage(
                        page_number=1,
                        confidence=0.9,
                    ),
                ),
                candidates=(
                    NewspaperStoryCandidate(
                        candidate_id="bad",
                        headline="Bad Candidate",
                        page_number=9,
                        importance=0.8,
                        confidence=0.8,
                    ),
                ),
                confidence=0.9,
            )

    adapter = NewspaperIssueAdapter(
        providers=(
            BadPageProvider(),
        )
    )

    with pytest.raises(
        NewspaperIssueIncomplete,
        match="unknown newspaper page",
    ):
        adapter.fetch_issue(
            _target(),
            "2026-09-06",
        )


# =========================================================
# ARCHITECTURAL CONTRACTS
# =========================================================


def test_newspaper_adapter_has_no_publication_method():
    adapter = NewspaperIssueAdapter()

    forbidden = {
        "publish",
        "send",
        "send_message",
        "send_photo",
        "send_media_group",
    }

    assert forbidden.isdisjoint(
        set(
            dir(
                adapter
            )
        )
    )


def test_newspaper_normalization_has_no_translation_output():
    issue = FakeNewspaperProvider().fetch_issue(
        _target(),
        "2026-09-06",
    )

    result = (
        normalize_selected_newspaper_candidate(
            issue,
            "story-world",
        )
    )

    assert not hasattr(
        result,
        "translated_body",
    )

    assert not hasattr(
        result,
        "translated_title",
    )
