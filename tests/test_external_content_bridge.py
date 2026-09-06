import pytest

from core.content_model import PreparedContent
from core.external_content_bridge import (
    ExternalContentBridgeError,
    ExternalPreparedBridgeResult,
    build_external_prepared_content,
    build_external_source_key,
)
from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalReviewResult,
)
from core.external_media_materializer import (
    ExternalMediaMaterializer,
    MaterializedExternalMedia,
)


# =========================================================
# HELPERS
# =========================================================


def _content(
    *,
    source_type="web_article",
    source_url="https://example.com/article?id=1",
    canonical_url="https://example.com/article",
    title="Main Headline",
    lead="Main Lead",
    body="Paragraph one.\n\nParagraph two.",
    language="en",
    media=(),
    warnings=(),
    confidence=0.91,
):
    return NormalizedExternalContent(
        source_type=source_type,
        source_url=source_url,
        canonical_url=canonical_url,
        content_type="article",
        title=title,
        lead=lead,
        body=body,
        original_language=language,
        source_name="Example News",
        media=tuple(media),
        extraction_confidence=confidence,
        warnings=tuple(warnings),
    )


def _review(
    *,
    title="Main Headline",
    lead="Main Lead",
    body="Paragraph one.\n\nParagraph two.",
    media=(),
    requires_smart_summary=False,
    requires_editorial_rewrite=False,
):
    return ExternalReviewResult(
        title=title,
        lead=lead,
        body=body,
        media=tuple(media),
        requires_smart_summary=(
            requires_smart_summary
        ),
        requires_editorial_rewrite=(
            requires_editorial_rewrite
        ),
    )


def _media(
    *,
    url="https://example.com/photo.jpg",
    position=0,
    presentation="",
):
    return ExternalMedia(
        type="photo",
        source_url=url,
        position=position,
        presentation=presentation,
    )


# =========================================================
# FAKE MATERIALIZER
# =========================================================


class FakeMaterializer:
    def __init__(
        self,
        *,
        file_ids=None,
    ):
        self.file_ids = tuple(
            file_ids
            or (
                "file-1",
            )
        )
        self.received = None

    def build_prepared_files(
        self,
        media_items,
    ):
        self.received = tuple(
            media_items
        )

        result = []

        for index, media in enumerate(
            self.received
        ):
            file_id = (
                self.file_ids[index]
                if index < len(
                    self.file_ids
                )
                else f"file-{index + 1}"
            )

            result.append(
                {
                    "type": media.type,
                    "file_id": file_id,
                    "position": media.position,
                    "presentation": (
                        media.presentation
                    ),
                    "external_source_url": (
                        media.source_url
                    ),
                }
            )

        return tuple(
            result
        )


# =========================================================
# SOURCE KEY
# =========================================================


def test_external_source_key_is_stable():
    content = _content()

    first = build_external_source_key(
        content
    )

    second = build_external_source_key(
        content
    )

    assert first == second


def test_external_source_key_is_platform_neutral():
    content = _content(
        source_type="web_article"
    )

    key = build_external_source_key(
        content
    )

    assert key.startswith(
        "external:web_article:"
    )

    assert "telegram" not in key
    assert "bale" not in key


def test_external_source_key_uses_best_url():
    first = _content(
        source_url=(
            "https://example.com/article?utm_source=x"
        ),
        canonical_url=(
            "https://example.com/article"
        ),
    )

    second = _content(
        source_url=(
            "https://example.com/article?utm_source=y"
        ),
        canonical_url=(
            "https://example.com/article"
        ),
    )

    assert (
        build_external_source_key(
            first
        )
        == build_external_source_key(
            second
        )
    )


def test_different_canonical_urls_get_different_source_keys():
    first = _content(
        canonical_url=(
            "https://example.com/a"
        )
    )

    second = _content(
        canonical_url=(
            "https://example.com/b"
        )
    )

    assert (
        build_external_source_key(
            first
        )
        != build_external_source_key(
            second
        )
    )


def test_source_key_requires_normalized_external_content():
    with pytest.raises(
        TypeError,
        match="NormalizedExternalContent",
    ):
        build_external_source_key(
            {
                "canonical_url":
                "https://example.com/article"
            }
        )


# =========================================================
# TEXT BRIDGE
# =========================================================


def test_text_only_external_content_becomes_prepared_content():
    content = _content()

    review = _review()

    result = build_external_prepared_content(
        content,
        review,
    )

    assert isinstance(
        result,
        ExternalPreparedBridgeResult,
    )

    assert isinstance(
        result.prepared_content,
        PreparedContent,
    )

    assert (
        result.prepared_content.main_text
        == (
            "Main Headline\n\n"
            "Main Lead\n\n"
            "Paragraph one.\n"
            "Paragraph two."
        )
    )


def test_neutral_text_matches_external_reviewed_text():
    result = build_external_prepared_content(
        _content(),
        _review(),
    )

    assert (
        result.prepared_content.neutral_text
        == result.prepared_content.main_text
    )


def test_exact_duplicate_text_blocks_are_not_repeated():
    content = _content(
        title="Same",
        lead="Same",
        body="Same",
    )

    review = _review(
        title="Same",
        lead="Same",
        body="Same",
    )

    result = build_external_prepared_content(
        content,
        review,
    )

    assert (
        result.prepared_content.main_text
        == "Same"
    )


def test_empty_lines_are_cleaned_without_rewriting_content():
    review = _review(
        title="  Headline  ",
        lead="  Lead   text ",
        body=(
            " Paragraph   one \n\n"
            " Paragraph   two "
        ),
    )

    result = build_external_prepared_content(
        _content(),
        review,
    )

    text = (
        result.prepared_content.main_text
    )

    assert "Headline" in text
    assert "Lead text" in text
    assert "Paragraph one" in text
    assert "Paragraph two" in text


def test_bridge_rejects_empty_text_and_empty_media():
    content = _content(
        title="",
        lead="",
        body="",
    )

    review = _review(
        title="",
        lead="",
        body="",
        media=(),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="no text or media",
    ):
        build_external_prepared_content(
            content,
            review,
        )


# =========================================================
# MEDIA BRIDGE
# =========================================================


def test_external_media_requires_materialization():
    media = (
        _media(),
    )

    content = _content(
        media=media
    )

    review = _review(
        media=media
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="must be materialized",
    ):
        build_external_prepared_content(
            content,
            review,
        )


def test_materializer_output_enters_prepared_files():
    media = (
        _media(),
    )

    materializer = FakeMaterializer(
        file_ids=(
            "transport-file",
        )
    )

    result = build_external_prepared_content(
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        materializer=materializer,
    )

    files = (
        result.prepared_content.files
    )

    assert len(
        files
    ) == 1

    assert files[
        0
    ][
        "file_id"
    ] == "transport-file"

    assert files[
        0
    ][
        "type"
    ] == "photo"


def test_raw_external_url_cannot_be_used_as_file_id():
    media = (
        _media(),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="URL cannot be used",
    ):
        build_external_prepared_content(
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": (
                        "https://example.com/photo.jpg"
                    ),
                },
            ),
        )


def test_prepared_media_requires_type():
    media = (
        _media(),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="has no type",
    ):
        build_external_prepared_content(
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            prepared_files=(
                {
                    "type": "",
                    "file_id": "file-1",
                },
            ),
        )


def test_prepared_media_requires_file_id():
    media = (
        _media(),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="has no file_id",
    ):
        build_external_prepared_content(
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": "",
                },
            ),
        )


def test_materialized_media_count_must_match_review():
    media = (
        _media(
            url="https://example.com/1.jpg",
            position=1,
        ),
        _media(
            url="https://example.com/2.jpg",
            position=2,
        ),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="count does not match",
    ):
        build_external_prepared_content(
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": "file-1",
                },
            ),
        )


def test_cannot_supply_materializer_and_prepared_files_together():
    media = (
        _media(),
    )

    with pytest.raises(
        ExternalContentBridgeError,
        match="either prepared_files or materializer",
    ):
        build_external_prepared_content(
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            materializer=FakeMaterializer(),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": "file-1",
                },
            ),
        )


def test_prepared_files_are_rejected_when_review_has_no_media():
    with pytest.raises(
        ExternalContentBridgeError,
        match="no selected media",
    ):
        build_external_prepared_content(
            _content(),
            _review(
                media=()
            ),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": "file-1",
                },
            ),
        )


# =========================================================
# PRESENTATION
# =========================================================


def test_slideshow_presentation_is_preserved():
    media = (
        _media(
            url="https://example.com/1.jpg",
            position=1,
            presentation="slideshow",
        ),
        _media(
            url="https://example.com/2.jpg",
            position=2,
            presentation="slideshow",
        ),
    )

    result = build_external_prepared_content(
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        prepared_files=(
            {
                "type": "photo",
                "file_id": "file-1",
            },
            {
                "type": "photo",
                "file_id": "file-2",
            },
        ),
    )

    assert (
        result.prepared_content.media_presentation
        == "slideshow"
    )


def test_collage_presentation_is_preserved():
    media = (
        _media(
            presentation="collage",
        ),
    )

    result = build_external_prepared_content(
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        prepared_files=(
            {
                "type": "photo",
                "file_id": "file-1",
            },
        ),
    )

    assert (
        result.prepared_content.media_presentation
        == "collage"
    )


def test_mixed_media_presentation_falls_back_to_normal_media():
    media = (
        _media(
            url="https://example.com/1.jpg",
            position=1,
            presentation="slideshow",
        ),
        _media(
            url="https://example.com/2.jpg",
            position=2,
            presentation="",
        ),
    )

    result = build_external_prepared_content(
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        prepared_files=(
            {
                "type": "photo",
                "file_id": "file-1",
            },
            {
                "type": "photo",
                "file_id": "file-2",
            },
        ),
    )

    assert (
        result.prepared_content.media_presentation
        == "slideshow"
    )


# =========================================================
# SHARED ENGINE SIGNALS
# =========================================================


def test_short_mode_signal_is_preserved_for_shared_smart_summary():
    result = build_external_prepared_content(
        _content(),
        _review(
            requires_smart_summary=True,
        ),
    )

    assert (
        result.requires_smart_summary
        is True
    )

    assert (
        result.requires_editorial_rewrite
        is False
    )


def test_editorial_signal_is_preserved_for_shared_editorial_pipeline():
    result = build_external_prepared_content(
        _content(),
        _review(
            requires_editorial_rewrite=True,
        ),
    )

    assert (
        result.requires_editorial_rewrite
        is True
    )


# =========================================================
# PROVENANCE
# =========================================================


def test_bridge_preserves_external_provenance():
    content = _content(
        source_type="instagram",
        source_url=(
            "https://instagram.com/p/example/"
        ),
        canonical_url=(
            "https://instagram.com/p/example/"
        ),
        language="en",
        confidence=0.77,
        warnings=(
            "limited_source_context",
        ),
    )

    result = build_external_prepared_content(
        content,
        _review(),
    )

    assert result.source_type == (
        "instagram"
    )

    assert result.source_url == (
        "https://instagram.com/p/example/"
    )

    assert result.canonical_url == (
        "https://instagram.com/p/example/"
    )

    assert result.original_language == (
        "en"
    )

    assert result.extraction_confidence == (
        0.77
    )

    assert result.warnings == (
        "limited_source_context",
    )


def test_external_source_name_is_not_added_to_visible_text():
    content = _content()

    result = build_external_prepared_content(
        content,
        _review(),
    )

    assert (
        "Example News"
        not in result.prepared_content.main_text
    )


# =========================================================
# CUSTOM SOURCE KEY
# =========================================================


def test_explicit_source_key_can_be_supplied():
    result = build_external_prepared_content(
        _content(),
        _review(),
        source_key=(
            "external:custom:123"
        ),
    )

    assert (
        result.prepared_content.source_key
        == "external:custom:123"
    )


def test_automatic_source_key_is_written_to_prepared_content():
    content = _content()

    result = build_external_prepared_content(
        content,
        _review(),
    )

    assert (
        result.prepared_content.source_key
        == build_external_source_key(
            content
        )
    )


# =========================================================
# IMMUTABILITY / ARCHITECTURE
# =========================================================


def test_prepared_files_remain_immutable_after_bridge():
    media = (
        _media(),
    )

    result = build_external_prepared_content(
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        prepared_files=(
            {
                "type": "photo",
                "file_id": "file-1",
                "meta": {
                    "tags": [
                        "a",
                    ]
                },
            },
        ),
    )

    with pytest.raises(
        TypeError
    ):
        result.prepared_content.files[
            0
        ][
            "file_id"
        ] = "changed"


def test_bridge_has_no_publication_side_effect():
    result = build_external_prepared_content(
        _content(),
        _review(),
    )

    assert isinstance(
        result.prepared_content,
        PreparedContent,
    )

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
                result
            )
        )
    )


def test_bridge_does_not_translate_content():
    result = build_external_prepared_content(
        _content(
            language="en"
        ),
        _review(
            title="Original English Headline",
            lead="Original lead",
            body="Original body",
        ),
    )

    assert (
        "Original English Headline"
        in result.prepared_content.main_text
    )

    assert not hasattr(
        result,
        "translated_text",
    )
