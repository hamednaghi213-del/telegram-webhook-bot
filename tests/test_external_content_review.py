import pytest

from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalMediaMode,
    ExternalReviewError,
    ExternalReviewMode,
    ExternalReviewSelection,
    apply_external_review_selection,
    build_external_content_preview,
    split_external_paragraphs,
)


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/story",
        canonical_url=(
            "https://example.com/story-canonical"
        ),
        title="Sample headline",
        lead="Sample lead",
        body=(
            "First paragraph with useful information.\n\n"
            "Second paragraph with more context.\n\n"
            "Third paragraph with final details."
        ),
        source_name="Example News",
        original_language="en",
        extraction_confidence=0.91,
        warnings=(
            "example_warning",
        ),
        media=(
            ExternalMedia(
                type="photo",
                source_url=(
                    "https://example.com/1.jpg"
                ),
                presentation="cover",
            ),
            ExternalMedia(
                type="photo",
                source_url=(
                    "https://example.com/2.jpg"
                ),
                presentation="gallery",
            ),
        ),
    )


def test_build_preview_keeps_review_information():
    preview = build_external_content_preview(
        _content()
    )

    assert preview.title == (
        "Sample headline"
    )

    assert preview.lead == (
        "Sample lead"
    )

    assert preview.paragraph_count == 3

    assert preview.media_count == 2

    assert preview.source_name == (
        "Example News"
    )

    assert preview.original_language == (
        "en"
    )

    assert preview.extraction_confidence == (
        0.91
    )

    assert preview.canonical_url == (
        "https://example.com/story-canonical"
    )


def test_standard_mode_preserves_content():
    content = _content()

    result = apply_external_review_selection(
        content
    )

    assert result.title == (
        content.title
    )

    assert result.lead == (
        content.lead
    )

    assert result.body == (
        content.body
    )

    assert result.media == (
        content.media
    )

    assert result.requires_smart_summary is (
        False
    )

    assert (
        result.requires_editorial_rewrite
        is False
    )


def test_headline_only_removes_lead_and_body():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.HEADLINE_ONLY
            )
        ),
    )

    assert result.title == (
        "Sample headline"
    )

    assert result.lead == ""

    assert result.body == ""


def test_headline_lead_removes_body_only():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.HEADLINE_LEAD
            )
        ),
    )

    assert result.title == (
        "Sample headline"
    )

    assert result.lead == (
        "Sample lead"
    )

    assert result.body == ""


def test_selected_paragraphs_preserve_requested_order():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.PARAGRAPHS
            ),
            paragraph_indexes=(
                2,
                0,
            ),
        ),
    )

    assert result.body == (
        "Third paragraph with final details."
        "\n\n"
        "First paragraph with useful information."
    )

    assert (
        result.selected_paragraph_indexes
        == (
            2,
            0,
        )
    )


def test_paragraph_mode_requires_selection():
    with pytest.raises(
        ExternalReviewError,
        match="at least one paragraph",
    ):
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.PARAGRAPHS
            )
        )


def test_out_of_range_paragraph_is_rejected():
    with pytest.raises(
        ExternalReviewError,
        match="out of range",
    ):
        apply_external_review_selection(
            _content(),
            ExternalReviewSelection(
                mode=(
                    ExternalReviewMode.PARAGRAPHS
                ),
                paragraph_indexes=(
                    99,
                ),
            ),
        )


def test_no_media_mode_removes_all_media():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.NONE
            )
        ),
    )

    assert result.media == ()

    assert result.has_media is False


def test_selected_media_mode_uses_only_requested_media():
    content = _content()

    result = apply_external_review_selection(
        content,
        ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.SELECTED
            ),
            media_indexes=(
                1,
            ),
        ),
    )

    assert result.media == (
        content.media[1],
    )

    assert result.selected_media_indexes == (
        1,
    )


def test_selected_media_mode_requires_indexes():
    with pytest.raises(
        ExternalReviewError,
        match="at least one media index",
    ):
        ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.SELECTED
            )
        )


def test_out_of_range_media_is_rejected():
    with pytest.raises(
        ExternalReviewError,
        match="out of range",
    ):
        apply_external_review_selection(
            _content(),
            ExternalReviewSelection(
                media_mode=(
                    ExternalMediaMode.SELECTED
                ),
                media_indexes=(
                    7,
                ),
            ),
        )


def test_duplicate_indexes_are_rejected():
    with pytest.raises(
        ExternalReviewError,
        match="unique",
    ):
        ExternalReviewSelection(
            paragraph_indexes=(
                1,
                1,
            ),
        )

    with pytest.raises(
        ExternalReviewError,
        match="unique",
    ):
        ExternalReviewSelection(
            media_indexes=(
                0,
                0,
            ),
        )


def test_negative_indexes_are_rejected():
    with pytest.raises(
        ExternalReviewError,
        match=">= 0",
    ):
        ExternalReviewSelection(
            paragraph_indexes=(
                -1,
            ),
        )

    with pytest.raises(
        ExternalReviewError,
        match=">= 0",
    ):
        ExternalReviewSelection(
            media_indexes=(
                -1,
            ),
        )


def test_short_mode_signals_existing_smart_summary():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.SHORT
            )
        ),
    )

    assert result.requires_smart_summary is (
        True
    )

    assert (
        result.requires_editorial_rewrite
        is False
    )

    # Review layer must not summarize by itself.
    assert result.body == (
        _content().body
    )


def test_editorial_mode_signals_existing_editorial_pipeline():
    result = apply_external_review_selection(
        _content(),
        ExternalReviewSelection(
            mode=(
                ExternalReviewMode.EDITORIAL_REWRITE
            )
        ),
    )

    assert (
        result.requires_editorial_rewrite
        is True
    )

    assert result.requires_smart_summary is (
        False
    )

    # Review layer must not rewrite by itself.
    assert result.body == (
        _content().body
    )


def test_split_paragraphs_normalizes_whitespace():
    result = split_external_paragraphs(
        " First   paragraph. \n\n"
        " Second    paragraph. "
    )

    assert result == (
        "First paragraph.",
        "Second paragraph.",
    )


def test_review_does_not_translate_content():
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/fr",
        title="Titre français",
        body="Texte original français.",
        original_language="fr",
    )

    result = apply_external_review_selection(
        content
    )

    assert result.title == (
        "Titre français"
    )

    assert result.body == (
        "Texte original français."
    )


def test_review_never_adds_source_identity_to_output_text():
    result = apply_external_review_selection(
        _content()
    )

    assert result.title != (
        "Example News"
    )

    assert not result.body.endswith(
        "Example News"
    )


@pytest.mark.parametrize(
    "mode",
    [
        ExternalReviewMode.STANDARD,
        ExternalReviewMode.HEADLINE_ONLY,
        ExternalReviewMode.HEADLINE_LEAD,
        ExternalReviewMode.SHORT,
        ExternalReviewMode.EDITORIAL_REWRITE,
    ],
)
def test_review_modes_are_stable_string_contracts(
    mode,
):
    selection = ExternalReviewSelection(
        mode=mode
    )

    assert isinstance(
        selection.mode.value,
        str,
    )
