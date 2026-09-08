import pytest

from core.external_content_model import (
    NormalizedExternalContent,
)
from core.external_review_state import (
    ExternalReviewConflict,
    ExternalReviewExpired,
    ExternalReviewNotFound,
    ExternalReviewStateStore,
)


# =========================================================
# FIXTURES
# =========================================================


def _content(
    url="https://example.com/news/1",
):
    return NormalizedExternalContent(
        source_type="web_article",
        source_url=url,
        canonical_url=url,
        content_type="article",
        title="Headline",
        lead="Lead",
        body="Body",
        original_language="en",
        extraction_confidence=0.9,
    )


# =========================================================
# CREATE / READ
# =========================================================


def test_create_pending_review():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    content = _content()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=content,
    )

    assert pending.review_id == "review-1"
    assert pending.chat_id == 100
    assert pending.content is content
    assert pending.expires_at > pending.created_at

    assert len(store) == 1


def test_get_review_for_chat():
    store = ExternalReviewStateStore()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert (
        store.get_for_chat(100)
        is pending
    )


def test_get_review_by_id():
    store = ExternalReviewStateStore()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert (
        store.get_by_id("review-1")
        is pending
    )


def test_unknown_review_returns_none():
    store = ExternalReviewStateStore()

    assert (
        store.get_by_id("missing")
        is None
    )

    assert (
        store.get_for_chat(999)
        is None
    )


# =========================================================
# VALIDATION
# =========================================================


def test_empty_review_id_is_rejected():
    store = ExternalReviewStateStore()

    with pytest.raises(
        ValueError,
        match="review_id",
    ):
        store.create(
            review_id="",
            chat_id=100,
            content=_content(),
        )


def test_invalid_content_is_rejected():
    store = ExternalReviewStateStore()

    with pytest.raises(
        TypeError,
        match="NormalizedExternalContent",
    ):
        store.create(
            review_id="review-1",
            chat_id=100,
            content="invalid",
        )


def test_invalid_ttl_is_rejected():
    with pytest.raises(
        ValueError,
        match="ttl_seconds",
    ):
        ExternalReviewStateStore(
            ttl_seconds=0,
        )


# =========================================================
# CONFLICT PROTECTION
# =========================================================


def test_chat_cannot_have_two_active_reviews_by_default():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewConflict,
        match="already has an active",
    ):
        store.create(
            review_id="review-2",
            chat_id=100,
            content=_content(
                "https://example.com/news/2"
            ),
        )

    assert (
        store.get_for_chat(100)
        .review_id
        == "review-1"
    )


def test_review_id_cannot_belong_to_another_chat():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewConflict,
        match="another chat",
    ):
        store.create(
            review_id="review-1",
            chat_id=200,
            content=_content(),
        )


def test_replace_existing_review_when_explicitly_requested():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    replacement = store.create(
        review_id="review-2",
        chat_id=100,
        content=_content(
            "https://example.com/news/2"
        ),
        replace_existing=True,
    )

    assert (
        store.get_for_chat(100)
        is replacement
    )

    assert (
        store.get_by_id("review-1")
        is None
    )

    assert (
        store.get_by_id("review-2")
        is replacement
    )

    assert len(store) == 1


# =========================================================
# REQUIRE / OWNERSHIP
# =========================================================


def test_require_returns_owned_review():
    store = ExternalReviewStateStore()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert (
        store.require(
            review_id="review-1",
            chat_id=100,
        )
        is pending
    )


def test_require_rejects_wrong_chat():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        store.require(
            review_id="review-1",
            chat_id=200,
        )


def test_require_missing_review():
    store = ExternalReviewStateStore()

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        store.require(
            review_id="missing",
            chat_id=100,
        )


# =========================================================
# POP / CANCEL
# =========================================================


def test_pop_returns_and_removes_review():
    store = ExternalReviewStateStore()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    result = store.pop(
        review_id="review-1",
        chat_id=100,
    )

    assert result is pending
    assert store.get_by_id("review-1") is None
    assert store.get_for_chat(100) is None
    assert len(store) == 0


def test_pop_wrong_chat_does_not_remove_review():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    with pytest.raises(
        ExternalReviewNotFound,
    ):
        store.pop(
            review_id="review-1",
            chat_id=200,
        )

    assert (
        store.get_by_id("review-1")
        is not None
    )


def test_cancel_for_chat():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert (
        store.cancel_for_chat(100)
        is True
    )

    assert (
        store.cancel_for_chat(100)
        is False
    )

    assert len(store) == 0


# =========================================================
# EXPIRATION
# =========================================================


def test_require_expired_review_raises_expired(
    monkeypatch,
):
    store = ExternalReviewStateStore(
        ttl_seconds=10,
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 100.0,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 111.0,
    )

    with pytest.raises(
        ExternalReviewExpired,
    ):
        store.require(
            review_id="review-1",
            chat_id=100,
        )

    assert len(store) == 0


def test_get_expired_review_returns_none(
    monkeypatch,
):
    store = ExternalReviewStateStore(
        ttl_seconds=10,
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 100.0,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 111.0,
    )

    assert (
        store.get_by_id("review-1")
        is None
    )

    assert (
        store.get_for_chat(100)
        is None
    )

    assert len(store) == 0


def test_cleanup_expired_removes_only_expired(
    monkeypatch,
):
    store = ExternalReviewStateStore(
        ttl_seconds=10,
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 100.0,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 105.0,
    )

    store.create(
        review_id="review-2",
        chat_id=200,
        content=_content(
            "https://example.com/news/2"
        ),
    )

    monkeypatch.setattr(
        "core.external_review_state.time",
        lambda: 111.0,
    )

    assert (
        store.cleanup_expired()
        == 1
    )

    assert (
        store.get_by_id("review-1")
        is None
    )

    assert (
        store.get_by_id("review-2")
        is not None
    )


# =========================================================
# RESET / IDS
# =========================================================


def test_active_review_ids_are_deterministic():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-b",
        chat_id=200,
        content=_content(),
    )

    store.create(
        review_id="review-a",
        chat_id=100,
        content=_content(),
    )

    assert (
        store.active_review_ids()
        == (
            "review-a",
            "review-b",
        )
    )


def test_reset_clears_all_state():
    store = ExternalReviewStateStore()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.create(
        review_id="review-2",
        chat_id=200,
        content=_content(),
    )

    store.reset()

    assert len(store) == 0
    assert store.active_review_ids() == ()


# =========================================================
# PREVIEW MESSAGE IDENTITY
# =========================================================


def test_preview_message_refs_default_empty():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert pending.preview_message_id is None
    assert pending.preview_media_message_ids == ()


def test_update_preview_message_refs_roundtrip():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    updated = store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id=555,
        preview_media_message_ids=(901, 902),
    )

    assert updated.preview_message_id == 555
    assert updated.preview_media_message_ids == (901, 902)

    reloaded = store.require(
        review_id="review-1",
        chat_id=100,
    )

    assert reloaded.preview_message_id == 555
    assert reloaded.preview_media_message_ids == (901, 902)


def test_media_selection_update_preserves_message_refs():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id=555,
    )

    updated = store.update_media_selection(
        review_id="review-1",
        chat_id=100,
        selected_media_indexes=(),
        explicit=True,
    )

    assert updated.preview_message_id == 555


def test_preview_message_refs_normalize_invalid_values():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    updated = store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id="not-a-number",
        preview_media_message_ids=(0, -3, 42, 42),
    )

    assert updated.preview_message_id is None
    assert updated.preview_media_message_ids == (42,)


def test_serialized_ui_state_includes_message_refs():
    from core.external_review_state import (
        _content_with_review_state_to_dict,
        _review_state_from_content_dict,
        EXTERNAL_REVIEW_UI_STATE_KEY,
    )

    payload = _content_with_review_state_to_dict(
        _content(),
        selected_media_indexes=(1,),
        media_selection_explicit=True,
        preview_message_id=555,
        preview_media_message_ids=(901,),
    )

    state = payload[EXTERNAL_REVIEW_UI_STATE_KEY]

    assert state["preview_message_id"] == 555
    assert state["preview_media_message_ids"] == [901]

    (
        indexes,
        explicit,
        message_id,
        media_ids,
        file_ids,
    ) = _review_state_from_content_dict(
        payload,
        media_count=1,
    )

    assert indexes == (1,)
    assert explicit is True
    assert message_id == 555
    assert media_ids == (901,)
    assert file_ids == ("",)


def test_legacy_ui_state_without_message_refs_is_compatible():
    from core.external_review_state import (
        _review_state_from_content_dict,
        EXTERNAL_REVIEW_UI_STATE_KEY,
    )

    payload = {
        EXTERNAL_REVIEW_UI_STATE_KEY: {
            "selected_media_indexes": [0],
            "media_selection_explicit": True,
        }
    }

    (
        indexes,
        explicit,
        message_id,
        media_ids,
        file_ids,
    ) = _review_state_from_content_dict(payload)

    assert indexes == (0,)
    assert explicit is True
    assert message_id is None
    assert media_ids == ()
    assert file_ids == ()
