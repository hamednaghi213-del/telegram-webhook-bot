import pytest

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_fetcher import FetchResult
from core.web_article_extractor import (
    WebArticleExtractionError,
    WebArticleExtractor,
)


ARTICLE_HTML = """
<!doctype html>
<html lang="en">
<head>
    <title>Fallback page title</title>

    <link
        rel="canonical"
        href="/world/example-story"
    >

    <meta
        property="og:title"
        content="Open Graph title"
    >

    <meta
        property="og:description"
        content="A concise description of the article."
    >

    <meta
        property="og:site_name"
        content="Example News"
    >

    <meta
        property="og:image"
        content="/images/hero.jpg"
    >

    <meta
        property="og:image:width"
        content="1600"
    >

    <meta
        property="og:image:height"
        content="900"
    >

    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Professional article headline",
        "description": "JSON-LD article description.",
        "datePublished": "2026-09-06T08:00:00Z",
        "author": {
            "@type": "Person",
            "name": "Jane Reporter"
        },
        "publisher": {
            "@type": "Organization",
            "name": "Example News"
        },
        "inLanguage": "en-US",
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": "https://example.com/world/example-story"
        },
        "image": [
            {
                "@type": "ImageObject",
                "url": "https://example.com/images/hero.jpg",
                "width": 1600,
                "height": 900
            }
        ]
    }
    </script>
</head>

<body>
    <header>
        Navigation
    </header>

    <main>
        <article>
            <h1>Professional article headline</h1>

            <p>
                The first substantial paragraph explains the main event
                and provides enough information for article extraction.
            </p>

            <p>
                The second paragraph adds background, context, and more
                detail so the extracted body is clearly an article rather
                than a navigation or category page.
            </p>

            <p>
                A third paragraph describes likely consequences and
                additional facts relevant to the original report.
            </p>

            <img
                src="/images/hero.jpg"
                width="1600"
                height="900"
                alt="Professional article headline"
            >

            <img
                src="/images/gallery-2.jpg"
                width="1200"
                height="800"
                alt="Second news image"
            >

            <img
                src="/assets/site-logo.png"
                width="120"
                height="40"
                alt="Site logo"
            >
        </article>
    </main>

    <footer>
        Privacy About Contact
    </footer>
</body>
</html>
"""


MEDIA_FILTER_HTML = """
<html><head>
<meta property="og:title" content="Major election result">
<meta property="og:image" content="/ads/banner-election.jpg">
</head><body><article>
<h1>Major election result</h1>
<p>This article contains enough substantive reporting to be extracted
as a normal news article with several editorial photographs.</p>
<img src="/images/gallery-low.jpg" width="800" height="500">
<img src="/images/gallery-high.jpg" width="1600" height="900"
     alt="Major election result">
<img src="/assets/recommended-story.jpg" width="1200" height="800">
</article></body></html>
"""


PERSIAN_HTML = """
<!doctype html>
<html lang="fa-IR">
<head>
    <meta
        property="og:title"
        content="تحولات تازه منطقه"
    >

    <meta
        property="og:site_name"
        content="رسانه نمونه"
    >
</head>

<body>
    <article>
        <h1>تحولات تازه منطقه</h1>

        <p>
            تحولات تازه منطقه در شرایطی ادامه دارد که بازیگران اصلی
            تلاش می‌کنند موقعیت سیاسی و امنیتی خود را در معادلات جدید
            حفظ کنند و همزمان هزینه تصمیم‌های آینده را کاهش دهند.
        </p>

        <p>
            بررسی روندهای اخیر نشان می‌دهد که رقابت میان بازیگران
            منطقه‌ای و بین‌المللی همچنان یکی از عوامل اصلی شکل‌دهنده
            به مسیر تحولات سیاسی و دیپلماتیک خواهد بود.
        </p>

        <p>
            نتیجه این روند می‌تواند بر روابط میان دولت‌ها و همچنین
            بر تصمیم‌های اقتصادی و امنیتی ماه‌های آینده اثر بگذارد.
        </p>
    </article>
</body>
</html>
"""


class FakeFetcher:
    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def fetch(
        self,
        url,
        *,
        allowed_content_types=None,
        max_bytes=None,
    ):
        self.calls.append(
            {
                "url": url,
                "allowed_content_types": (
                    allowed_content_types
                ),
                "max_bytes": max_bytes,
            }
        )

        return self.result


def test_extracts_professional_article_metadata():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url=(
            "https://example.com/story?ref=home"
        ),
        final_url=(
            "https://example.com/story?ref=home"
        ),
    )

    assert isinstance(
        result,
        NormalizedExternalContent,
    )

    assert result.source_type == (
        "web_article"
    )

    assert result.content_type == (
        "article"
    )

    assert result.title == (
        "Professional article headline"
    )

    assert result.author == (
        "Jane Reporter"
    )

    assert result.published_at == (
        "2026-09-06T08:00:00Z"
    )

    assert result.source_name == (
        "Example News"
    )

    assert result.canonical_url == (
        "https://example.com/world/example-story"
    )

    assert result.original_language == (
        "en"
    )

    assert (
        "first substantial paragraph"
        in result.body
    )

    assert result.extraction_confidence >= (
        0.7
    )

    assert result.metadata[
        "has_json_ld_article"
    ] is True


def test_json_ld_has_priority_over_open_graph_title():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    assert result.title == (
        "Professional article headline"
    )

    assert result.title != (
        "Open Graph title"
    )


def test_extracts_and_ranks_article_images():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    assert result.has_media is True

    assert isinstance(
        result.media[0],
        ExternalMedia,
    )

    assert result.media[0].source_url == (
        "https://example.com/images/hero.jpg"
    )

    assert result.media[0].presentation == (
        "cover"
    )

    urls = [
        item.source_url
        for item in result.media
    ]

    assert (
        "https://example.com/images/gallery-2.jpg"
        in urls
    )

    assert (
        "https://example.com/assets/site-logo.png"
        not in urls
    )


def test_filters_assets_and_ranks_editorial_media_deterministically():
    result = WebArticleExtractor().extract_from_html(
        MEDIA_FILTER_HTML,
        source_url="https://example.com/story",
    )

    assert [
        item.source_url for item in result.media
    ] == [
        "https://example.com/images/gallery-high.jpg",
        "https://example.com/images/gallery-low.jpg",
    ]


def test_duplicate_image_sources_are_deduplicated():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    hero_count = sum(
        1
        for item in result.media
        if item.source_url
        == "https://example.com/images/hero.jpg"
    )

    assert hero_count == 1


def test_external_media_remains_transport_neutral():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    media = result.media[0]

    assert (
        "file_id"
        not in media.__dataclass_fields__
    )

    assert (
        "telegram_file_id"
        not in media.__dataclass_fields__
    )


def test_relative_canonical_url_is_resolved():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url=(
            "https://example.com/category/story"
        ),
    )

    assert result.canonical_url == (
        "https://example.com/world/example-story"
    )


def test_persian_language_is_preserved_or_detected():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        PERSIAN_HTML,
        source_url=(
            "https://example.com/fa/story"
        ),
    )

    assert result.original_language == (
        "fa"
    )

    assert "تحولات" in result.body


def test_translation_is_not_performed():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    assert (
        "translated_text"
        not in result.__dataclass_fields__
    )

    assert (
        "target_language"
        not in result.__dataclass_fields__
    )


def test_short_page_receives_warning():
    html = """
    <html lang="en">
    <head>
        <title>Short item</title>
    </head>
    <body>
        <p>Very short content.</p>
    </body>
    </html>
    """

    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        html,
        source_url="https://example.com/short",
    )

    assert (
        "short_or_incomplete_body"
        in result.warnings
    )


def test_possible_paywall_is_flagged():
    html = """
    <html lang="en">
    <head>
        <title>Premium report</title>
    </head>
    <body>
        <article>
            <p>
                This is the beginning of a premium report with some
                visible information for readers.
            </p>

            <p>
                Subscribe to continue reading the complete article.
            </p>
        </article>
    </body>
    </html>
    """

    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        html,
        source_url=(
            "https://example.com/premium"
        ),
    )

    assert (
        "possible_paywall"
        in result.warnings
    )


def test_js_heavy_page_is_flagged():
    scripts = "".join(
        "<script>window.x = 1;</script>"
        for _ in range(25)
    )

    html = f"""
    <html lang="en">
    <head>
        <title>Client rendered story</title>
    </head>
    <body>
        {scripts}
        <div id="app"></div>
    </body>
    </html>
    """

    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        html,
        source_url="https://example.com/app-story",
    )

    assert (
        "possible_js_rendered_page"
        in result.warnings
    )


def test_empty_html_is_rejected():
    extractor = WebArticleExtractor()

    with pytest.raises(
        WebArticleExtractionError,
        match="empty",
    ):
        extractor.extract_from_html(
            "",
            source_url="https://example.com/story",
        )


def test_network_extract_uses_safe_fetcher():
    fetch_result = FetchResult(
        requested_url=(
            "https://example.com/story"
        ),
        final_url=(
            "https://example.com/story"
        ),
        status_code=200,
        content_type="text/html",
        content=ARTICLE_HTML.encode(
            "utf-8"
        ),
        encoding="utf-8",
    )

    fetcher = FakeFetcher(
        fetch_result
    )

    extractor = WebArticleExtractor(
        fetcher=fetcher
    )

    result = extractor.extract(
        "https://example.com/story"
    )

    assert result.title == (
        "Professional article headline"
    )

    assert len(
        fetcher.calls
    ) == 1

    assert fetcher.calls[0][
        "allowed_content_types"
    ] == {
        "text/html",
        "application/xhtml+xml",
    }


def test_source_name_is_internal_metadata_not_forced_into_body():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    assert result.source_name == (
        "Example News"
    )

    assert not result.body.endswith(
        result.source_name
    )


def test_confidence_is_always_normalized():
    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        ARTICLE_HTML,
        source_url="https://example.com/story",
    )

    assert (
        0.0
        <= result.extraction_confidence
        <= 1.0
    )


def test_article_without_image_remains_valid_candidate():
    html = """
    <html lang="en">
    <head>
        <title>Text only report</title>
    </head>

    <body>
        <article>
            <h1>Text only report</h1>

            <p>
                This is a detailed article paragraph containing enough
                information to represent a genuine text report without
                an accompanying image on the source page.
            </p>

            <p>
                A second substantial paragraph provides additional
                context and background for the report and confirms that
                useful content is still available.
            </p>

            <p>
                The final paragraph explains the consequences and
                completes the article body for extraction purposes.
            </p>
        </article>
    </body>
    </html>
    """

    extractor = WebArticleExtractor()

    result = extractor.extract_from_html(
        html,
        source_url=(
            "https://example.com/text-report"
        ),
    )

    assert result.has_text is True

    assert result.is_publishable_candidate is (
        True
    )

    assert (
        "no_article_image"
        in result.warnings
    )
