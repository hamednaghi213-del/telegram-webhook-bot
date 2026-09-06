import pytest

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalMediaMode,
    ExternalReviewMode,
)
from core.external_review_callback import (
    EXTERNAL_REVIEW_CALLBACK_PREFIX,
    ExternalReviewCallbackError,
    _build_selection,
    _parse_indexes,
    handle_external_review_callback,
)
from core.external_review_controller import (
    ExternalReviewController,
)
from core.external_review_state import (
    ExternalReviewNotFound,
    ExternalReviewStateStore,
)


# =========================================================
# FIXTURES
# =========================================================


def _content():
    return NormalizedExternalContent(
        source_type="web_article",
        source_url=(
            "https://example.com/news"
        ),
        canonical_url=(
            "https://example.com/news"
        ),
        content_type="article",
        title="عنوان خبر",
        lead="لید خبر",
        body=(
            "پاراگراف اول\n\n"
            "پاراگراف دوم\n\n"
            "پاراگراف سوم"
        ),
        source_name="Example",
        extraction_confidence=0.95,
    )


def _controller():
    return ExternalReviewController(
        state_store=(
            ExternalReviewStateStore(
                ttl_seconds=1800
            )
        )
    )


def _create_pending(
    controller,
    *,
    review_id="review-1",
    chat_id=12345,
):
    return controller.create_pending(
        chat_id=chat_id,
        content=_content(),
        review_id=review_id,
    )


# =========================================================
# PREFIX / FOREIGN CALLBACKS
# =========================================================


def test_callback_prefix_is_namespaced():
    assert (
        EXTERNAL_REVIEW_CALLBACK_PREFIX
        == "extrev:"
    )


def test_foreign_callback_is_not_handled():
    controller = _controller()

    result = (
        handle_external_review_callback(
            callback_data="setup:start",
            chat_id=12345,
            controller=controller,
        )
    )

    assert result.handled is False
    assert result.completed is False
    assert result.decision is None
    assert result.cancelled is None


def test_empty_callback_is_not_handled():
    controller = _controller()

    result = (
        handle_external_review_callback(
            callback_data="",
            chat_id=12345,
            controller=controller,
        )
    )

    assert result.handled is False


# =========================================================
# INDEX PARSING
# =========================================================


def test_parse_single_index():
    assert (
        _parse_indexes("0")
        == (0,)
    )


def test_parse_multiple_indexes():
    assert (
        _parse_indexes("0,2,4")
        == (0, 2, 4)
    )


def test_parse_indexes_strips_spaces():
    assert (
        _parse_indexes(
            " 0, 2, 4 "
        )
        == (0, 2, 4)
    )


@pytest.mark.parametrize(
    "value",
    (
        "",
        " ",
        "a",
        "0,a",
        "-1",
        "0,,2",
        "1,1",
    ),
)
def test_invalid_indexes_are_rejected(
    value,
):
    with pytest.raises(
        ExternalReviewCallbackError
    ):
        _parse_indexes(
            value
        )


# =========================================================
# SELECTION MAPPING
# =========================================================


@pytest.mark.parametrize(
    (
        "action",
        "expected_mode",
    ),
    (
        (
            "standard",
            ExternalReviewMode.STANDARD,
        ),
        (
            "headline",
            ExternalReviewMode.HEADLINE_ONLY,
        ),
        (
            "lead",
            ExternalReviewMode.HEADLINE_LEAD,
        ),
        (
            "short",
            ExternalReviewMode.SHORT,
        ),
        (
            "editorial",
            ExternalReviewMode.EDITORIAL_REWRITE,
        ),
    ),
)
def test_review_action_maps_to_mode(
    action,
    expected_mode,
):
    selection = _build_selection(
        action=action
    )

    assert (
        selection.mode
        == expected_mode
    )


def test_paragraph_action_maps_indexes():
    selection = _build_selection(
        action="paragraphs",
        argument="0,2",
    )

    assert (
        selection.mode
        == ExternalReviewMode.PARAGRAPHS
    )

    assert (
        selection.paragraph_indexes
        == (0, 2)
    )


def test_no_media_action_maps_media_mode():
    selection = _build_selection(
        action="nomedia"
    )

    assert (
        selection.media_mode
        == ExternalMediaMode.NONE
    )


def test_media_action_maps_indexes():
    selection = _build_selection(
        action="media",
        argument="0,2",
    )

    assert (
        selection.media_mode
        == ExternalMediaMode.SELECTED
    )

    assert (
        selection.media_indexes
        == (0, 2)
    )


def test_unknown_action_is_rejected():
    with pytest.raises(
        ExternalReviewCallbackError
    ):
        _build_selection(
            action="unknown"
        )


# =========================================================
# STANDARD DECISION
# =========================================================


def test_standard_callback_produces_decision():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:standard:review-1"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert result.handled is True
    assert result.completed is True
    assert result.action == "standard"
    assert result.review_id == "review-1"

    assert result.decision is not None
    assert result.cancelled is None

    assert (
        result.decision.review.title
        == "عنوان خبر"
    )

    assert (
        result.decision.review.lead
        == "لید خبر"
    )

    assert (
        "پاراگراف اول"
        in result.decision.review.body
    )


def test_standard_callback_preserves_pending_until_execution_success():
    controller = _controller()

    _create_pending(
        controller
    )

    result = handle_external_review_callback(
        callback_data=(
            "extrev:standard:review-1"
        ),
        chat_id=12345,
        controller=controller,
    )

    assert result.handled is True
    assert result.decision is not None

    pending = controller.get_pending(
        review_id="review-1",
        chat_id=12345,
    )

    assert pending is not None
    assert pending.review_id == "review-1"
    assert pending.chat_id == 12345


def test_standard_callback_can_be_consumed_after_success():
    controller = _controller()

    _create_pending(
        controller
    )

    result = handle_external_review_callback(
        callback_data=(
            "extrev:standard:review-1"
        ),
        chat_id=12345,
        controller=controller,
    )

    assert result.decision is not None

    consumed = (
        controller.consume_after_success(
            review_id="review-1",
            chat_id=12345,
        )
    )

    assert consumed.review_id == "review-1"

    with pytest.raises(
        ExternalReviewNotFound
    ):
        controller.get_pending(
            review_id="review-1",
            chat_id=12345,
        )


# =========================================================
# SHORT / EDITORIAL SIGNALS
# =========================================================


def test_short_callback_preserves_smart_summary_signal():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:short:review-1"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert (
        result.decision
        is not None
    )

    assert (
        result.decision
        .requires_smart_summary
        is True
    )


def test_editorial_callback_preserves_editorial_signal():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:editorial:review-1"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert (
        result.decision
        is not None
    )

    assert (
        result.decision
        .requires_editorial_rewrite
        is True
    )


# =========================================================
# PARAGRAPH SELECTION
# =========================================================


def test_paragraph_callback_applies_selection():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:paragraphs:"
                "review-1:0,2"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert (
        result.decision
        is not None
    )

    assert (
        result.decision.review
        .selected_paragraph_indexes
        == (0, 2)
    )

    assert (
        "پاراگراف اول"
        in result.decision.review.body
    )

    assert (
        "پاراگراف سوم"
        in result.decision.review.body
    )

    assert (
        "پاراگراف دوم"
        not in result.decision.review.body
    )


# =========================================================
# CANCEL
# =========================================================


def test_cancel_callback_cancels_pending_review():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:cancel:review-1"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert result.handled is True
    assert result.completed is True
    assert result.action == "cancel"

    assert result.cancelled is not None
    assert result.decision is None

    with pytest.raises(
        ExternalReviewNotFound
    ):
        controller.get_pending(
            review_id="review-1",
            chat_id=12345,
        )


# =========================================================
# SECURITY / OWNERSHIP
# =========================================================


def test_callback_cannot_consume_another_chat_review():
    controller = _controller()

    _create_pending(
        controller,
        chat_id=111,
    )

    with pytest.raises(
        Exception
    ):
        handle_external_review_callback(
            callback_data=(
                "extrev:standard:review-1"
            ),
            chat_id=222,
            controller=controller,
        )

    pending = (
        controller.get_pending(
            review_id="review-1",
            chat_id=111,
        )
    )

    assert pending is not None
    assert pending.chat_id == 111


# =========================================================
# INVALID CALLBACKS
# =========================================================


@pytest.mark.parametrize(
    "callback_data",
    (
        "extrev:",
        "extrev:standard",
        "extrev::review-1",
        "extrev:unknown:review-1",
        "extrev:paragraphs:review-1",
        "extrev:media:review-1",
    ),
)
def test_malformed_external_callback_is_rejected(
    callback_data,
):
    controller = _controller()

    _create_pending(
        controller
    )

    with pytest.raises(
        ExternalReviewCallbackError
    ):
        handle_external_review_callback(
            callback_data=callback_data,
            chat_id=12345,
            controller=controller,
        )


# =========================================================
# NO PUBLICATION SIDE EFFECT
# =========================================================


def test_callback_handler_has_no_publication_side_effect():
    controller = _controller()

    _create_pending(
        controller
    )

    result = (
        handle_external_review_callback(
            callback_data=(
                "extrev:standard:review-1"
            ),
            chat_id=12345,
            controller=controller,
        )
    )

    assert result.handled is True
    assert result.decision is not None

    assert not hasattr(
        result,
        "delivery_result",
    )
