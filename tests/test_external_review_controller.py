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
)
from core.external_review_controller import (
    ExternalReviewController,
)
from core.external_review_state import (
    ExternalReviewNotFound,
    ExternalReviewStateStore,
)


# =========================================================
# HELPERS
# =========================================================


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/news/1",
        canonical_url="https://example.com/news/1",
        content_type="article",
        title="Main headline",
        lead="Main lead",
        body=(
            "Paragraph one.\n\n"
            "Paragraph two.\n\n"
            "Paragraph three."
        ),
        media=(
            ExternalMedia(
                type="photo",
                source_url=(
                    "https://example.com/1.jpg"
                ),
            ),
            ExternalMedia(
                type="photo",
                source_url=(
                    "https://example.com/2.jpg"
                ),
            ),
        ),
        original_language="en",
        extraction_confidence=0.95,
    )


def _controller():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    return (
        ExternalReviewController(
            state_store=store,
        ),
        store,
    )


# =========================================================
# CREATE / READ
# =========================================================


def test_create_pending_review():
    controller, store = _controller()

    content = _content()

    pending = controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=content,
    )

    assert pending.review_id == "review-1"
    assert pending.chat_id == 100
    assert pending.content is content

    assert (
        store.get_by_id("review-1")
        is pending
    )


def test_get_pending_review():
    controller, _store = _controller()

    created = controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    result = controller.get_pending(
        review_id="review-1",
        chat_id=100,
    )

    assert result is created


# =========================================================
# PREVIEW
# =========================================================


def test_get_preview_uses_existing_review_engine():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    preview = controller.get_preview(
        review_id="review-1",
        chat_id=100,
    )

    assert preview.title == "Main headline"
    assert preview.lead == "Main lead"

    assert preview.paragraphs == (
        "Paragraph one.",
        "Paragraph two.",
        "Paragraph three.",
    )

    assert preview.media_count == 2
    assert preview.original_language == "en"


# =========================================================
# STANDARD DECISION
# =========================================================


def test_standard_selection_preserves_pending_until_success():
    controller, store = _controller()

    content = _content()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=content,
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
    )

    assert decision.review_id == "review-1"
    assert decision.chat_id == 100
    assert decision.content is content

    assert (
        decision.review.title
        == "Main headline"
    )

    assert (
        decision.review.body
        == content.body
    )

    assert len(
        decision.review.media
    ) == 2

    pending = store.get_by_id(
        "review-1"
    )

    assert pending is not None
    assert pending.chat_id == 100

    assert (
        store.get_for_chat(100)
        is not None
    )


def test_consume_after_success_removes_pending_review():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    controller.apply_selection(
        review_id="review-1",
        chat_id=100,
    )

    consumed = (
        controller.consume_after_success(
            review_id="review-1",
            chat_id=100,
        )
    )

    assert consumed.review_id == "review-1"

    assert (
        store.get_by_id("review-1")
        is None
    )

    assert (
        store.get_for_chat(100)
        is None
    )


# =========================================================
# TEXT MODES
# =========================================================


def test_headline_only_selection():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_ONLY
            ),
        ),
    )

    assert (
        decision.review.title
        == "Main headline"
    )

    assert decision.review.lead == ""
    assert decision.review.body == ""


def test_headline_lead_selection():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .HEADLINE_LEAD
            ),
        ),
    )

    assert (
        decision.review.title
        == "Main headline"
    )

    assert (
        decision.review.lead
        == "Main lead"
    )

    assert decision.review.body == ""


def test_selected_paragraphs():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .PARAGRAPHS
            ),
            paragraph_indexes=(
                0,
                2,
            ),
        ),
    )

    assert (
        decision.review.body
        == (
            "Paragraph one.\n\n"
            "Paragraph three."
        )
    )

    assert (
        decision.review
        .selected_paragraph_indexes
        == (
            0,
            2,
        )
    )


# =========================================================
# SHARED TRANSFORMATION SIGNALS
# =========================================================


def test_short_mode_preserves_shared_summary_signal():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            mode=(
                ExternalReviewMode.SHORT
            ),
        ),
    )

    assert (
        decision.requires_smart_summary
        is True
    )

    assert (
        decision.requires_editorial_rewrite
        is False
    )

    assert len(
        decision.review.media
    ) == 2


def test_editorial_mode_preserves_shared_editorial_signal():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            mode=(
                ExternalReviewMode
                .EDITORIAL_REWRITE
            ),
        ),
    )

    assert (
        decision.requires_editorial_rewrite
        is True
    )

    assert (
        decision.requires_smart_summary
        is False
    )


# =========================================================
# MEDIA SELECTION
# =========================================================


def test_no_media_selection():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.NONE
            ),
        ),
    )

    assert decision.review.media == ()


def test_selected_media():
    controller, _store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    decision = controller.apply_selection(
        review_id="review-1",
        chat_id=100,
        selection=ExternalReviewSelection(
            media_mode=(
                ExternalMediaMode.SELECTED
            ),
            media_indexes=(1,),
        ),
    )

    assert len(
        decision.review.media
    ) == 1

    assert (
        decision.review.media[0]
        .source_url
        == "https://example.com/2.jpg"
    )

    assert (
        decision.review
        .selected_media_indexes
        == (1,)
    )


# =========================================================
# FAIL-CLOSED STATE
# =========================================================


def test_invalid_paragraph_selection_does_not_consume_pending():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewError,
    ):
        controller.apply_selection(
            review_id="review-1",
            chat_id=100,
            selection=ExternalReviewSelection(
                mode=(
                    ExternalReviewMode
                    .PARAGRAPHS
                ),
                paragraph_indexes=(99,),
            ),
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


def test_invalid_media_selection_does_not_consume_pending():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewError,
    ):
        controller.apply_selection(
            review_id="review-1",
            chat_id=100,
            selection=ExternalReviewSelection(
                media_mode=(
                    ExternalMediaMode
                    .SELECTED
                ),
                media_indexes=(99,),
            ),
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


def test_wrong_chat_cannot_consume_review():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        controller.apply_selection(
            review_id="review-1",
            chat_id=200,
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


def test_wrong_chat_cannot_consume_after_success():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        controller.consume_after_success(
            review_id="review-1",
            chat_id=200,
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


# =========================================================
# CANCEL
# =========================================================


def test_cancel_consumes_owned_pending_review():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    cancelled = controller.cancel(
        review_id="review-1",
        chat_id=100,
    )

    assert cancelled.review_id == "review-1"

    assert (
        store.get_by_id("review-1")
        is None
    )


def test_wrong_chat_cannot_cancel_review():
    controller, store = _controller()

    controller.create_pending(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        controller.cancel(
            review_id="review-1",
            chat_id=200,
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


# =========================================================
# NO SIDE EFFECTS
# =========================================================


def test_controller_has_no_publication_methods():
    controller, _store = _controller()

    assert not hasattr(
        controller,
        "publish",
    )

    assert not hasattr(
        controller,
        "send",
    )

    assert not hasattr(
        controller,
        "translate",
    )
