import pytest

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.social_content_adapter import (
    SocialContentAdapter,
    SocialContentIncomplete,
    SocialContentUnavailable,
    SocialMediaAsset,
    SocialSourceContent,
    UnsupportedSocialSource,
    classify_instagram_content_kind,
    is_instagram_url,
    normalize_social_source,
)


class FakeInstagramProvider:
    name = "fake_instagram"

    def supports(
        self,
        url,
    ):
        return is_instagram_url(
            url
        )

    def fetch(
        self,
        url,
    ):
        return SocialSourceContent(
            source_type="instagram",
            source_url=url,
            content_kind="carousel",
            caption=(
                "Officials announced a new regional meeting.\n\n"
                "The meeting is expected to take place next week."
            ),
            published_at=(
                "2026-09-06T10:00:00Z"
            ),
            original_language="en",
            media=(
                SocialMediaAsset(
                    type="image",
                    source_url=(
                        "https://cdn.example.com/1.jpg"
                    ),
                    width=1200,
                    height=800,
                    position=0,
                ),
                SocialMediaAsset(
                    type="image",
                    source_url=(
                        "https://cdn.example.com/2.jpg"
                    ),
                    width=1200,
                    height=800,
                    position=1,
                ),
            ),
            explicit_facts=(
                "The meeting concerns regional diplomacy.",
            ),
            account_name="Example News",
            account_username="example_news",
            account_id="123456789",
            provider_name="fake_instagram",
            confidence=0.90,
        )


class UnsupportedProvider:
    name = "unsupported"

    def supports(
        self,
        url,
    ):
        return False

    def fetch(
        self,
        url,
    ):
        raise AssertionError(
            "fetch must not be called"
        )


class BrokenProvider:
    name = "broken"

    def supports(
        self,
        url,
    ):
        return True

    def fetch(
        self,
        url,
    ):
        raise RuntimeError(
            "provider failed"
        )


class InvalidResultProvider:
    name = "invalid"

    def supports(
        self,
        url,
    ):
        return True

    def fetch(
        self,
        url,
    ):
        return {
            "caption": "invalid"
        }


# =========================================================
# URL DETECTION
# =========================================================


@pytest.mark.parametrize(
    "url",
    [
        "https://instagram.com/p/ABC123/",
        "https://www.instagram.com/p/ABC123/",
        "https://m.instagram.com/reel/XYZ987/",
    ],
)
def test_instagram_urls_are_detected(
    url,
):
    assert is_instagram_url(
        url
    ) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/post/1",
        "https://notinstagram.com/p/ABC/",
        "ftp://instagram.com/p/ABC/",
        "not-a-url",
    ],
)
def test_non_instagram_urls_are_rejected(
    url,
):
    assert is_instagram_url(
        url
    ) is False


@pytest.mark.parametrize(
    (
        "url",
        "expected",
    ),
    [
        (
            "https://instagram.com/p/ABC/",
            "post",
        ),
        (
            "https://instagram.com/reel/ABC/",
            "reel",
        ),
        (
            "https://instagram.com/reels/ABC/",
            "reel",
        ),
        (
            "https://instagram.com/tv/ABC/",
            "video",
        ),
        (
            "https://instagram.com/example/",
            "unknown",
        ),
    ],
)
def test_instagram_content_kind_classification(
    url,
    expected,
):
    assert (
        classify_instagram_content_kind(
            url
        )
        == expected
    )


# =========================================================
# SOCIAL MEDIA ASSET
# =========================================================


def test_social_media_asset_normalizes_url_and_type():
    asset = SocialMediaAsset(
        type="IMAGE",
        source_url=(
            "https://example.com/a.jpg#fragment"
        ),
        width=1000,
        height=700,
    )

    assert asset.type == "image"

    assert asset.source_url == (
        "https://example.com/a.jpg"
    )


def test_social_media_asset_requires_type():
    with pytest.raises(
        SocialContentIncomplete,
        match="type is required",
    ):
        SocialMediaAsset(
            type="",
            source_url=(
                "https://example.com/a.jpg"
            ),
        )


def test_social_media_asset_requires_valid_url():
    with pytest.raises(
        SocialContentIncomplete,
        match="URL is invalid",
    ):
        SocialMediaAsset(
            type="photo",
            source_url="not-a-url",
        )


@pytest.mark.parametrize(
    (
        "field_name",
        "value",
    ),
    [
        (
            "width",
            0,
        ),
        (
            "height",
            -1,
        ),
    ],
)
def test_social_media_asset_rejects_invalid_dimensions(
    field_name,
    value,
):
    kwargs = {
        "type": "photo",
        "source_url": (
            "https://example.com/a.jpg"
        ),
        field_name: value,
    }

    with pytest.raises(
        SocialContentIncomplete,
    ):
        SocialMediaAsset(
            **kwargs
        )


def test_social_media_asset_rejects_negative_duration():
    with pytest.raises(
        SocialContentIncomplete,
        match="duration",
    ):
        SocialMediaAsset(
            type="video",
            source_url=(
                "https://example.com/a.mp4"
            ),
            duration=-0.1,
        )


def test_social_media_asset_rejects_negative_position():
    with pytest.raises(
        SocialContentIncomplete,
        match="position",
    ):
        SocialMediaAsset(
            type="photo",
            source_url=(
                "https://example.com/a.jpg"
            ),
            position=-1,
        )


# =========================================================
# SOURCE CONTENT
# =========================================================


def test_social_source_normalizes_basic_fields():
    source = SocialSourceContent(
        source_type="Instagram_Post",
        source_url=(
            "https://instagram.com/p/ABC/#x"
        ),
        caption=(
            " First sentence. \n\n"
            " Second sentence. "
        ),
        original_language="EN-us",
        explicit_facts=(
            "Fact one",
            "Fact one",
            "Fact two",
        ),
        warnings=(
            "warning_one",
            "warning_one",
        ),
        confidence=0.8,
    )

    assert source.source_type == (
        "instagram"
    )

    assert source.source_url == (
        "https://instagram.com/p/ABC/"
    )

    assert source.original_language == (
        "en"
    )

    assert source.explicit_facts == (
        "Fact one",
        "Fact two",
    )

    assert source.warnings == (
        "warning_one",
    )


def test_social_source_rejects_invalid_confidence():
    with pytest.raises(
        SocialContentIncomplete,
        match="confidence",
    ):
        SocialSourceContent(
            source_type="instagram",
            source_url=(
                "https://instagram.com/p/ABC/"
            ),
            confidence=1.5,
        )


def test_social_source_requires_valid_url():
    with pytest.raises(
        SocialContentIncomplete,
        match="URL is invalid",
    ):
        SocialSourceContent(
            source_type="instagram",
            source_url="invalid",
        )


def test_social_source_requires_valid_media_objects():
    with pytest.raises(
        TypeError,
        match="SocialMediaAsset",
    ):
        SocialSourceContent(
            source_type="instagram",
            source_url=(
                "https://instagram.com/p/ABC/"
            ),
            media=(
                {
                    "type": "photo",
                },
            ),
        )


# =========================================================
# NORMALIZATION
# =========================================================


def test_normalize_social_source_returns_shared_model():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    assert isinstance(
        result,
        NormalizedExternalContent,
    )

    assert result.source_type == (
        "instagram"
    )

    assert result.content_type == (
        "carousel"
    )

    assert result.original_language == (
        "en"
    )

    assert result.has_text is True

    assert result.has_media is True


def test_normalization_preserves_source_facts():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    assert (
        "Officials announced a new regional meeting."
        in result.body
    )

    assert (
        "The meeting concerns regional diplomacy."
        in result.body
    )


def test_normalization_does_not_add_account_identity_to_visible_text():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    combined = " ".join(
        [
            result.title,
            result.lead,
            result.body,
            result.source_name,
        ]
    )

    assert "example_news" not in (
        combined
    )

    assert "123456789" not in (
        combined
    )

    assert "Example News" not in (
        combined
    )


def test_account_identity_remains_internal_metadata():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    assert (
        result.metadata[
            "account_username"
        ]
        == "example_news"
    )

    assert (
        result.metadata[
            "account_id"
        ]
        == "123456789"
    )


def test_normalization_does_not_translate_content():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/FRENCH/"
        ),
        caption=(
            "Le président a annoncé une réunion."
        ),
        original_language="fr",
        provider_name="provider",
        confidence=0.9,
    )

    result = normalize_social_source(
        source
    )

    assert result.original_language == (
        "fr"
    )

    assert result.body == (
        "Le président a annoncé une réunion."
    )


def test_normalization_orders_media_by_position():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/ORDER/"
        ),
        caption="A caption",
        media=(
            SocialMediaAsset(
                type="photo",
                source_url=(
                    "https://example.com/second.jpg"
                ),
                position=2,
            ),
            SocialMediaAsset(
                type="photo",
                source_url=(
                    "https://example.com/first.jpg"
                ),
                position=0,
            ),
        ),
        confidence=0.8,
    )

    result = normalize_social_source(
        source
    )

    assert result.media[
        0
    ].source_url == (
        "https://example.com/first.jpg"
    )

    assert result.media[
        1
    ].source_url == (
        "https://example.com/second.jpg"
    )


def test_media_is_transport_neutral():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    for media in result.media:
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


def test_empty_social_content_is_rejected():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/EMPTY/"
        ),
        confidence=0.5,
    )

    with pytest.raises(
        SocialContentIncomplete,
        match="no usable text or media",
    ):
        normalize_social_source(
            source
        )


def test_short_source_generates_quality_warning():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/SHORT/"
        ),
        caption="Short caption",
        provider_name="provider",
        confidence=0.3,
    )

    result = normalize_social_source(
        source
    )

    assert (
        "limited_source_context"
        in result.warnings
    )


def test_missing_media_generates_warning():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/TEXT/"
        ),
        caption=(
            "This is enough textual information "
            "to create a source candidate without media."
        ),
        provider_name="provider",
        confidence=0.8,
    )

    result = normalize_social_source(
        source
    )

    assert (
        "no_social_media"
        in result.warnings
    )


def test_missing_provider_generates_instagram_warning():
    source = SocialSourceContent(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/NOPROVIDER/"
        ),
        caption=(
            "A useful caption with enough context "
            "for a normalized source item."
        ),
        confidence=0.7,
    )

    result = normalize_social_source(
        source
    )

    assert (
        "instagram_provider_unspecified"
        in result.warnings
    )


# =========================================================
# ADAPTER
# =========================================================


def test_adapter_resolves_supported_provider():
    provider = FakeInstagramProvider()

    adapter = SocialContentAdapter(
        providers=(
            UnsupportedProvider(),
            provider,
        )
    )

    resolved = adapter.resolve_provider(
        "https://instagram.com/p/ABC/"
    )

    assert resolved is provider


def test_adapter_rejects_unsupported_source():
    adapter = SocialContentAdapter(
        providers=(
            UnsupportedProvider(),
        )
    )

    with pytest.raises(
        UnsupportedSocialSource,
    ):
        adapter.resolve_provider(
            "https://instagram.com/p/ABC/"
        )


def test_adapter_extract_returns_normalized_content():
    adapter = SocialContentAdapter(
        providers=(
            FakeInstagramProvider(),
        )
    )

    result = adapter.extract(
        "https://instagram.com/p/ABC/"
    )

    assert isinstance(
        result,
        NormalizedExternalContent,
    )

    assert result.source_type == (
        "instagram"
    )

    assert len(
        result.media
    ) == 2


def test_adapter_wraps_provider_failure():
    adapter = SocialContentAdapter(
        providers=(
            BrokenProvider(),
        )
    )

    with pytest.raises(
        SocialContentUnavailable,
        match="provider failed",
    ):
        adapter.extract(
            "https://instagram.com/p/ABC/"
        )


def test_adapter_rejects_invalid_provider_result():
    adapter = SocialContentAdapter(
        providers=(
            InvalidResultProvider(),
        )
    )

    with pytest.raises(
        SocialContentUnavailable,
        match="invalid result",
    ):
        adapter.extract(
            "https://instagram.com/p/ABC/"
        )


def test_provider_support_exception_does_not_break_resolution():
    class ExplodingSupportProvider:
        name = "exploding"

        def supports(
            self,
            url,
        ):
            raise RuntimeError(
                "boom"
            )

        def fetch(
            self,
            url,
        ):
            raise AssertionError

    adapter = SocialContentAdapter(
        providers=(
            ExplodingSupportProvider(),
            FakeInstagramProvider(),
        )
    )

    resolved = adapter.resolve_provider(
        "https://instagram.com/p/ABC/"
    )

    assert isinstance(
        resolved,
        FakeInstagramProvider,
    )


# =========================================================
# ARCHITECTURAL CONTRACTS
# =========================================================


def test_social_adapter_does_not_publish():
    adapter = SocialContentAdapter()

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


def test_social_model_has_no_translation_output():
    source = FakeInstagramProvider().fetch(
        "https://instagram.com/p/ABC/"
    )

    result = normalize_social_source(
        source
    )

    assert not hasattr(
        result,
        "translated_body",
    )

    assert not hasattr(
        result,
        "translated_title",
    )
