from dataclasses import FrozenInstanceError

import pytest

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)


def test_external_media_is_transport_neutral_and_immutable():
    media = ExternalMedia(
        type="photo",
        source_url="https://example.com/photo.jpg",
        width=1600,
        height=900,
        metadata={
            "credit": "Example",
            "tags": ["world", "news"],
        },
    )

    assert media.type == "photo"
    assert media.source_url == "https://example.com/photo.jpg"
    assert media.has_source is True

    assert "file_id" not in media.__dataclass_fields__
    assert tuple(media.metadata["tags"]) == (
        "world",
        "news",
    )

    with pytest.raises(FrozenInstanceError):
        media.source_url = "https://example.com/other.jpg"

    with pytest.raises(TypeError):
        media.metadata["credit"] = "Changed"


def test_external_media_nested_metadata_is_frozen():
    media = ExternalMedia(
        type="photo",
        source_url="https://example.com/photo.jpg",
        metadata={
            "image": {
                "sizes": [640, 1280],
            }
        },
    )

    assert media.metadata["image"]["sizes"] == (
        640,
        1280,
    )

    with pytest.raises(TypeError):
        media.metadata["image"]["new"] = "value"


def test_normalized_external_content_preserves_media_order():
    first = ExternalMedia(
        type="photo",
        source_url="https://example.com/1.jpg",
        position=0,
    )

    second = ExternalMedia(
        type="photo",
        source_url="https://example.com/2.jpg",
        position=1,
    )

    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/story",
        canonical_url="https://example.com/story-canonical",
        title="Example title",
        body="Example body",
        original_language="en",
        media=[first, second],
        extraction_confidence=0.95,
    )

    assert content.media == (
        first,
        second,
    )

    assert content.best_url == (
        "https://example.com/story-canonical"
    )

    assert content.has_text is True
    assert content.has_media is True
    assert content.is_publishable_candidate is True


def test_normalized_external_content_keeps_original_language():
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/article",
        title="Foreign-language article",
        original_language="fr",
    )

    assert content.original_language == "fr"

    # Translation is deliberately not part of the ingestion contract.
    assert "translated_text" not in content.__dataclass_fields__
    assert "target_language" not in content.__dataclass_fields__


def test_normalized_external_content_supports_future_source_types():
    instagram = NormalizedExternalContent(
        source_type="instagram",
        source_url="https://example.com/social-source",
        body="Extracted social content",
    )

    newspaper = NormalizedExternalContent(
        source_type="newspaper_front_page",
        source_url="https://example.com/front-page",
        title="Front page",
    )

    assert instagram.source_type == "instagram"
    assert newspaper.source_type == "newspaper_front_page"


def test_normalized_external_content_metadata_is_deeply_frozen():
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/article",
        metadata={
            "json_ld": {
                "keywords": [
                    "politics",
                    "world",
                ]
            }
        },
    )

    assert content.metadata["json_ld"]["keywords"] == (
        "politics",
        "world",
    )

    with pytest.raises(TypeError):
        content.metadata["json_ld"]["new"] = "value"


@pytest.mark.parametrize(
    "confidence",
    [-0.01, 1.01, -10, 2],
)
def test_extraction_confidence_rejects_invalid_values(
    confidence,
):
    with pytest.raises(
        ValueError,
        match="extraction_confidence",
    ):
        NormalizedExternalContent(
            source_type="web_article",
            source_url="https://example.com/article",
            extraction_confidence=confidence,
        )


@pytest.mark.parametrize(
    "confidence",
    [0, 0.25, 0.5, 1],
)
def test_extraction_confidence_accepts_valid_values(
    confidence,
):
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/article",
        extraction_confidence=confidence,
    )

    assert content.extraction_confidence == float(
        confidence
    )


def test_media_rejects_transport_specific_plain_mapping():
    with pytest.raises(
        TypeError,
        match="ExternalMedia",
    ):
        NormalizedExternalContent(
            source_type="web_article",
            source_url="https://example.com/article",
            media=[
                {
                    "type": "photo",
                    "file_id": "telegram-file-id",
                }
            ],
        )


def test_empty_content_is_not_publishable_candidate():
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/article",
    )

    assert content.has_text is False
    assert content.has_media is False
    assert content.is_publishable_candidate is False
