import pytest

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_resolver import (
    ExternalContentExtractionFailed,
    ExternalContentResolver,
    ExternalSourceKind,
    UnsupportedExternalContent,
    classify_external_url,
    extract_single_external_url,
)


# =========================================================
# FIXTURES / FAKES
# =========================================================


def _normalized(
    *,
    source_type="web_article",
    source_url="https://example.com/news/1",
    canonical_url="https://example.com/news/1",
):
    return NormalizedExternalContent(
        source_type=source_type,
        source_url=source_url,
        canonical_url=canonical_url,
        content_type="article",
        title="Headline",
        lead="Lead",
        body="Body",
        original_language="en",
        extraction_confidence=0.9,
    )


class FakeWebExtractor:
    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = (
            result
            if result is not None
            else _normalized()
        )
        self.error = error
        self.calls = []

    def extract(
        self,
        url,
    ):
        self.calls.append(
            url
        )

        if self.error:
            raise self.error

        return self.result


class FakeSocialAdapter:
    def __init__(
        self,
        result=None,
        error=None,
    ):
        self.result = (
            result
            if result is not None
            else _normalized(
                source_type="instagram",
                source_url=(
                    "https://www.instagram.com/p/abc/"
                ),
                canonical_url=(
                    "https://www.instagram.com/p/abc/"
                ),
            )
        )
        self.error = error
        self.calls = []

    def extract(
        self,
        url,
    ):
        self.calls.append(
            url
        )

        if self.error:
            raise self.error

        return self.result


# =========================================================
# URL CLASSIFICATION
# =========================================================


@pytest.mark.parametrize(
    "url",
    (
        "https://instagram.com/p/abc/",
        "https://www.instagram.com/reel/abc/",
        "https://m.instagram.com/p/abc/",
    ),
)
def test_instagram_urls_are_classified_as_instagram(
    url,
):
    assert (
        classify_external_url(
            url
        )
        == ExternalSourceKind.INSTAGRAM
    )


@pytest.mark.parametrize(
    "url",
    (
        "https://example.com/news/1",
        "https://www.reuters.com/world/test",
        "https://news.example.org/article?id=7",
    ),
)
def test_normal_http_urls_are_classified_as_web_articles(
    url,
):
    assert (
        classify_external_url(
            url
        )
        == ExternalSourceKind.WEB_ARTICLE
    )


def test_invalid_scheme_is_rejected():
    with pytest.raises(
        Exception,
    ):
        classify_external_url(
            "ftp://example.com/file"
        )


# =========================================================
# STANDALONE INPUT DETECTION
# =========================================================


def test_standalone_url_is_detected():
    result = (
        extract_single_external_url(
            "https://example.com/news/1"
        )
    )

    assert result == (
        "https://example.com/news/1"
    )


def test_surrounding_whitespace_is_allowed():
    result = (
        extract_single_external_url(
            "  https://example.com/news/1  "
        )
    )

    assert result == (
        "https://example.com/news/1"
    )


@pytest.mark.parametrize(
    "text",
    (
        "",
        "خبر عادی",
        (
            "این یک خبر است "
            "https://example.com/news/1"
        ),
        (
            "https://example.com/news/1 "
            "متن دیگر"
        ),
        (
            "https://example.com/a "
            "https://example.com/b"
        ),
    ),
)
def test_normal_message_is_not_hijacked_as_external_input(
    text,
):
    assert (
        extract_single_external_url(
            text
        )
        == ""
    )


def test_non_http_url_is_not_external_input():
    assert (
        extract_single_external_url(
            "ftp://example.com/file"
        )
        == ""
    )


# =========================================================
# WEB ARTICLE RESOLUTION
# =========================================================


def test_web_article_uses_professional_web_extractor():
    web = FakeWebExtractor()

    resolver = ExternalContentResolver(
        web_extractor=web,
    )

    result = resolver.resolve(
        "https://example.com/news/1"
    )

    assert (
        result.source_kind
        == ExternalSourceKind.WEB_ARTICLE
    )

    assert (
        result.content
        is web.result
    )

    assert len(
        web.calls
    ) == 1

    assert result.requires_review is True


def test_web_article_does_not_call_social_adapter():
    web = FakeWebExtractor()
    social = FakeSocialAdapter()

    resolver = ExternalContentResolver(
        web_extractor=web,
        social_adapter=social,
    )

    resolver.resolve(
        "https://example.com/news/1"
    )

    assert len(
        web.calls
    ) == 1

    assert social.calls == []


def test_web_extraction_failure_is_wrapped():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(
            error=RuntimeError(
                "boom"
            )
        ),
    )

    with pytest.raises(
        ExternalContentExtractionFailed,
        match="web article extraction failed",
    ):
        resolver.resolve(
            "https://example.com/news/1"
        )


def test_invalid_web_extractor_result_is_rejected():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(
            result="invalid"
        ),
    )

    with pytest.raises(
        ExternalContentExtractionFailed,
    ):
        resolver.resolve(
            "https://example.com/news/1"
        )


# =========================================================
# INSTAGRAM RESOLUTION
# =========================================================


def test_instagram_requires_configured_social_provider_path():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
        social_adapter=None,
    )

    with pytest.raises(
        UnsupportedExternalContent,
        match="configured social content provider",
    ):
        resolver.resolve(
            "https://www.instagram.com/p/abc/"
        )


def test_instagram_uses_social_adapter_extract():
    web = FakeWebExtractor()
    social = FakeSocialAdapter()

    resolver = ExternalContentResolver(
        web_extractor=web,
        social_adapter=social,
    )

    result = resolver.resolve(
        "https://www.instagram.com/p/abc/"
    )

    assert (
        result.source_kind
        == ExternalSourceKind.INSTAGRAM
    )

    assert (
        result.content
        is social.result
    )

    assert len(
        social.calls
    ) == 1

    assert web.calls == []


def test_social_extraction_failure_is_wrapped():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
        social_adapter=FakeSocialAdapter(
            error=RuntimeError(
                "provider failed"
            )
        ),
    )

    with pytest.raises(
        ExternalContentExtractionFailed,
        match="social content extraction failed",
    ):
        resolver.resolve(
            "https://www.instagram.com/p/abc/"
        )


def test_invalid_social_adapter_result_is_rejected():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
        social_adapter=FakeSocialAdapter(
            result="invalid"
        ),
    )

    with pytest.raises(
        ExternalContentExtractionFailed,
    ):
        resolver.resolve(
            "https://www.instagram.com/p/abc/"
        )


# =========================================================
# REVIEW / PUBLICATION SAFETY
# =========================================================


def test_every_external_resolution_requires_review():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
    )

    result = resolver.resolve(
        "https://example.com/news/1"
    )

    assert result.requires_review is True


def test_resolver_does_not_publish():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
    )

    assert not hasattr(
        resolver,
        "publish",
    )

    assert not hasattr(
        resolver,
        "send",
    )


def test_resolver_does_not_translate():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
    )

    result = resolver.resolve(
        "https://example.com/news/1"
    )

    assert (
        result.content.original_language
        == "en"
    )

    assert not hasattr(
        result,
        "translated_text",
    )


# =========================================================
# PLATFORM NEUTRALITY
# =========================================================


def test_resolution_has_no_telegram_or_bale_identity():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
    )

    result = resolver.resolve(
        "https://example.com/news/1"
    )

    assert not hasattr(
        result,
        "telegram_id",
    )

    assert not hasattr(
        result,
        "bale_id",
    )


def test_canonical_url_is_preserved_in_result():
    resolver = ExternalContentResolver(
        web_extractor=FakeWebExtractor(),
    )

    result = resolver.resolve(
        "https://example.com/news/1#fragment"
    )

    assert result.canonical_url == (
        "https://example.com/news/1"
    )
