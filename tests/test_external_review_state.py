import pytest

from copy import deepcopy

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
        media_presentation_mode,
    ) = _review_state_from_content_dict(
        payload,
        media_count=1,
    )

    assert indexes == (1,)
    assert explicit is True
    assert message_id == 555
    assert media_ids == (901,)
    assert file_ids == ("",)
    assert media_presentation_mode == "normal"


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
        media_presentation_mode,
    ) = _review_state_from_content_dict(payload)

    assert indexes == (0,)
    assert explicit is True
    assert message_id is None
    assert media_ids == ()
    assert file_ids == ()
    assert media_presentation_mode == "normal"


# =========================================================
# REQUIREMENT C: media_presentation_mode
# =========================================================


def test_new_pending_review_defaults_to_normal_presentation_mode():
    """
    Default value must match current (pre-existing) behavior: a
    freshly created pending review is not in album mode.
    """

    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert pending.media_presentation_mode == "normal"


def test_update_media_presentation_mode_toggles_and_preserves_state():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_media_selection(
        review_id="review-1",
        chat_id=100,
        selected_media_indexes=(),
        explicit=True,
    )

    store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id=555,
    )

    updated = store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    assert updated.media_presentation_mode == "album"
    # All other pending state must be preserved by the toggle.
    assert updated.selected_media_indexes == ()
    assert updated.media_selection_explicit is True
    assert updated.preview_message_id == 555

    back_to_normal = store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="normal",
    )

    assert back_to_normal.media_presentation_mode == "normal"
    assert back_to_normal.selected_media_indexes == ()


def test_update_media_presentation_mode_rejects_invalid_value_fails_closed():
    """
    An unrecognized mode value must fail closed to the default
    ("normal") instead of silently storing an unsupported value.
    """

    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    updated = store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="not-a-real-mode",
    )

    assert updated.media_presentation_mode == "normal"


def test_media_selection_update_preserves_presentation_mode():
    """
    Toggling media selection must never silently reset the
    presentation mode toggle back to the default.
    """

    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    updated = store.update_media_selection(
        review_id="review-1",
        chat_id=100,
        selected_media_indexes=(),
        explicit=True,
    )

    assert updated.media_presentation_mode == "album"


def test_preview_message_refs_update_preserves_presentation_mode():
    store = ExternalReviewStateStore(
        ttl_seconds=60,
    )

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    updated = store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id=777,
    )

    assert updated.media_presentation_mode == "album"


def test_serialized_ui_state_round_trips_presentation_mode():
    from core.external_review_state import (
        _content_with_review_state_to_dict,
        _review_state_from_content_dict,
        EXTERNAL_REVIEW_UI_STATE_KEY,
    )

    payload = _content_with_review_state_to_dict(
        _content(),
        media_presentation_mode="album",
    )

    state = payload[EXTERNAL_REVIEW_UI_STATE_KEY]

    assert state["media_presentation_mode"] == "album"

    (
        _,
        _,
        _,
        _,
        _,
        media_presentation_mode,
    ) = _review_state_from_content_dict(payload)

    assert media_presentation_mode == "album"


def test_serialized_ui_state_normalizes_invalid_presentation_mode():
    from core.external_review_state import (
        _content_with_review_state_to_dict,
        _review_state_from_content_dict,
        EXTERNAL_REVIEW_UI_STATE_KEY,
    )

    payload = _content_with_review_state_to_dict(
        _content(),
        media_presentation_mode="not-a-real-mode",
    )

    state = payload[EXTERNAL_REVIEW_UI_STATE_KEY]

    assert state["media_presentation_mode"] == "normal"

    (
        _,
        _,
        _,
        _,
        _,
        media_presentation_mode,
    ) = _review_state_from_content_dict(payload)

    assert media_presentation_mode == "normal"


# =========================================================
# MINIMAL FAKE SUPABASE CLIENT
#
# Just enough of the postgrest-style query builder chain used by
# PersistentExternalReviewStateStore (.table().insert()/.select()/
# .update()/.delete()/.eq()/.limit().execute()) to exercise the
# durable-store code paths without a real Supabase connection.
# =========================================================


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = []
        self.limit_value = None

    def select(self, columns=None):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def lt(self, column, value):
        self.filters.append((column, "<", value))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def _rows(self):
        return self.client.rows

    def _matches(self, row):
        for item in self.filters:
            if len(item) == 2:
                column, value = item
                if row.get(column) != value:
                    return False
            else:
                column, _, value = item
                if not (row.get(column) < value):
                    return False
        return True

    def execute(self):
        if self.operation == "insert":
            payloads = (
                self.payload
                if isinstance(self.payload, list)
                else [self.payload]
            )

            inserted = []

            for payload in payloads:
                row = deepcopy(payload)
                self.client.rows.append(row)
                inserted.append(deepcopy(row))

            return _FakeResult(inserted)

        if self.operation == "select":
            matched = [
                deepcopy(row)
                for row in self._rows()
                if self._matches(row)
            ]

            if self.limit_value is not None:
                matched = matched[: self.limit_value]

            return _FakeResult(matched)

        if self.operation == "update":
            updated = []

            for row in self._rows():
                if self._matches(row):
                    row.update(deepcopy(self.payload))
                    updated.append(deepcopy(row))

            return _FakeResult(updated)

        if self.operation == "delete":
            remaining = []
            deleted = []

            for row in self._rows():
                if self._matches(row):
                    deleted.append(deepcopy(row))
                else:
                    remaining.append(row)

            self.client.rows = remaining

            return _FakeResult(deleted)

        raise AssertionError(
            f"unsupported fake operation: {self.operation}"
        )


class FakeExternalReviewSupabaseClient:
    def __init__(self):
        self.rows = []

    def table(self, table_name):
        return _FakeQuery(self, table_name)


def _persistent_store(ttl_seconds=60):
    from core.external_review_state import (
        PersistentExternalReviewStateStore,
    )

    client = FakeExternalReviewSupabaseClient()

    store = PersistentExternalReviewStateStore(
        ttl_seconds=ttl_seconds,
        client=client,
    )

    return store, client


# =========================================================
# REQUIREMENT C: PersistentExternalReviewStateStore
# (media_presentation_mode persisted through Supabase-shaped JSON)
# =========================================================


def test_persistent_store_new_pending_review_defaults_to_normal():
    store, _client = _persistent_store()

    pending = store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    assert pending.media_presentation_mode == "normal"


def test_persistent_store_round_trips_media_presentation_mode():
    """
    The mode must persist inside the existing JSON content column
    (no schema migration) for both create and later reads, matching
    the in-memory store contract.
    """

    store, client = _persistent_store()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    updated = store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    assert updated.media_presentation_mode == "album"

    # Re-read through the durable store (simulates a different
    # worker/process picking up the persisted row).
    reloaded = store.require(
        review_id="review-1",
        chat_id=100,
    )

    assert reloaded.media_presentation_mode == "album"

    # The mode is stored inside the existing JSON content column,
    # not a new top-level database column.
    assert "media_presentation_mode" not in client.rows[0]

    stored_content = client.rows[0]["content"]

    assert (
        stored_content["__external_review_ui_state__"][
            "media_presentation_mode"
        ]
        == "album"
    )


def test_persistent_store_media_selection_update_preserves_presentation_mode():
    store, _client = _persistent_store()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    updated = store.update_media_selection(
        review_id="review-1",
        chat_id=100,
        selected_media_indexes=(),
        explicit=True,
    )

    assert updated.media_presentation_mode == "album"


def test_persistent_store_preview_refs_update_preserves_presentation_mode():
    store, _client = _persistent_store()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    store.update_media_presentation_mode(
        review_id="review-1",
        chat_id=100,
        media_presentation_mode="album",
    )

    updated = store.update_preview_message_refs(
        review_id="review-1",
        chat_id=100,
        preview_message_id=555,
    )

    assert updated.media_presentation_mode == "album"
    assert updated.preview_message_id == 555


def test_persistent_store_legacy_row_without_mode_defaults_to_normal():
    """
    A row persisted before this feature existed (no
    media_presentation_mode key in the stored JSON UI state) must
    keep behaving exactly as before: "normal".
    """

    store, client = _persistent_store()

    store.create(
        review_id="review-1",
        chat_id=100,
        content=_content(),
    )

    # Simulate a legacy persisted row missing the new key entirely.
    stored_state = client.rows[0]["content"][
        "__external_review_ui_state__"
    ]
    del stored_state["media_presentation_mode"]

    reloaded = store.require(
        review_id="review-1",
        chat_id=100,
    )

    assert reloaded.media_presentation_mode == "normal"
