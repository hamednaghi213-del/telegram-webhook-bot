import time

from core.editorial_pending import (
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_PUBLISHED_ORIGINAL,
    STATUS_PUBLISHED_SUMMARY,
    cancel_pending_review,
    cleanup_expired_reviews,
    clear_pending_reviews,
    create_pending_review,
    delete_pending_review,
    get_pending_review,
    mark_original_published,
    mark_summary_published,
    pending_review_count,
    update_pending_summary,
)


# =========================================================
# TEST SETUP
# =========================================================


def setup_function():
    clear_pending_reviews()


def teardown_function():
    clear_pending_reviews()


# =========================================================
# CREATE REVIEW
# =========================================================


def test_create_pending_review():

    review = create_pending_review(
        user_id=123,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه فعلی",
        regeneration_count=0,
        metadata={
            "source": "test"
        }
    )

    assert review.review_id
    assert review.user_id == 123
    assert review.content_type == "opinion_note"
    assert review.original_text == "متن اصلی"
    assert review.current_summary == "خلاصه فعلی"
    assert review.regeneration_count == 0
    assert review.status == STATUS_PENDING
    assert review.metadata["source"] == "test"


# =========================================================
# COUNT
# =========================================================


def test_pending_review_count():

    assert pending_review_count() == 0

    create_pending_review(
        user_id=1,
        content_type="opinion_note",
        original_text="a",
        current_summary="b"
    )

    assert pending_review_count() == 1

    create_pending_review(
        user_id=2,
        content_type="news_analysis",
        original_text="c",
        current_summary="d"
    )

    assert pending_review_count() == 2


# =========================================================
# GET REVIEW
# =========================================================


def test_get_pending_review():

    created = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه"
    )

    loaded = get_pending_review(
        created.review_id,
        user_id=100
    )

    assert loaded is not None
    assert loaded.review_id == created.review_id
    assert loaded.user_id == 100
    assert loaded.status == STATUS_PENDING


# =========================================================
# USER ISOLATION
# =========================================================


def test_wrong_user_cannot_access_review():

    created = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن",
        current_summary="خلاصه"
    )

    result = get_pending_review(
        created.review_id,
        user_id=999
    )

    assert result is None


# =========================================================
# UNKNOWN REVIEW
# =========================================================


def test_unknown_review_returns_none():

    result = get_pending_review(
        "does-not-exist",
        user_id=100
    )

    assert result is None


# =========================================================
# UPDATE SUMMARY
# =========================================================


def test_update_pending_summary():

    created = create_pending_review(
        user_id=55,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه اول"
    )

    updated = update_pending_summary(
        review_id=created.review_id,
        user_id=55,
        new_summary="خلاصه دوم",
        regeneration_count=1,
        metadata={
            "regenerated": True
        }
    )

    assert updated is not None
    assert updated.current_summary == "خلاصه دوم"
    assert updated.regeneration_count == 1
    assert updated.metadata["regenerated"] is True
    assert updated.status == STATUS_PENDING


# =========================================================
# UPDATE WRONG USER
# =========================================================


def test_wrong_user_cannot_update_summary():

    created = create_pending_review(
        user_id=55,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه اول"
    )

    updated = update_pending_summary(
        review_id=created.review_id,
        user_id=999,
        new_summary="خلاصه غیرمجاز",
        regeneration_count=1
    )

    assert updated is None

    loaded = get_pending_review(
        created.review_id,
        user_id=55
    )

    assert loaded.current_summary == "خلاصه اول"
    assert loaded.regeneration_count == 0


# =========================================================
# MARK SUMMARY PUBLISHED
# =========================================================


def test_mark_summary_published():

    created = create_pending_review(
        user_id=1,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    result = mark_summary_published(
        created.review_id,
        user_id=1
    )

    assert result is not None
    assert (
        result.status
        == STATUS_PUBLISHED_SUMMARY
    )


# =========================================================
# MARK ORIGINAL PUBLISHED
# =========================================================


def test_mark_original_published():

    created = create_pending_review(
        user_id=2,
        content_type="news_analysis",
        original_text="اصل",
        current_summary="خلاصه"
    )

    result = mark_original_published(
        created.review_id,
        user_id=2
    )

    assert result is not None
    assert (
        result.status
        == STATUS_PUBLISHED_ORIGINAL
    )


# =========================================================
# CANCEL
# =========================================================


def test_cancel_pending_review():

    created = create_pending_review(
        user_id=3,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    result = cancel_pending_review(
        created.review_id,
        user_id=3
    )

    assert result is not None
    assert result.status == STATUS_CANCELLED


# =========================================================
# FINALIZED REVIEW CANNOT UPDATE SUMMARY
# =========================================================


def test_finalized_review_cannot_update_summary():

    created = create_pending_review(
        user_id=10,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه اول"
    )

    mark_summary_published(
        created.review_id,
        user_id=10
    )

    updated = update_pending_summary(
        review_id=created.review_id,
        user_id=10,
        new_summary="خلاصه دوم",
        regeneration_count=1
    )

    assert updated is None

    loaded = get_pending_review(
        created.review_id,
        user_id=10
    )

    assert (
        loaded.status
        == STATUS_PUBLISHED_SUMMARY
    )

    assert (
        loaded.current_summary
        == "خلاصه اول"
    )


# =========================================================
# FINALIZED REVIEW STATUS STAYS FINAL
# =========================================================


def test_finalized_review_cannot_be_republished_as_original():

    created = create_pending_review(
        user_id=10,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    first = mark_summary_published(
        created.review_id,
        user_id=10
    )

    second = mark_original_published(
        created.review_id,
        user_id=10
    )

    assert (
        first.status
        == STATUS_PUBLISHED_SUMMARY
    )

    assert (
        second.status
        == STATUS_PUBLISHED_SUMMARY
    )


# =========================================================
# DELETE REVIEW
# =========================================================


def test_delete_pending_review():

    created = create_pending_review(
        user_id=20,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    deleted = delete_pending_review(
        created.review_id,
        user_id=20
    )

    assert deleted is True

    loaded = get_pending_review(
        created.review_id,
        user_id=20
    )

    assert loaded is None

    assert pending_review_count() == 0


# =========================================================
# WRONG USER CANNOT DELETE
# =========================================================


def test_wrong_user_cannot_delete_review():

    created = create_pending_review(
        user_id=20,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    deleted = delete_pending_review(
        created.review_id,
        user_id=999
    )

    assert deleted is False

    assert (
        get_pending_review(
            created.review_id,
            user_id=20
        )
        is not None
    )


# =========================================================
# EMPTY REVIEW ID
# =========================================================


def test_empty_review_id_returns_none():

    assert (
        get_pending_review(
            "",
            user_id=1
        )
        is None
    )


def test_empty_review_id_delete_is_false():

    assert (
        delete_pending_review(
            "",
            user_id=1
        )
        is False
    )


# =========================================================
# EXPIRATION
# =========================================================


def test_pending_review_can_expire():

    created = create_pending_review(
        user_id=30,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    # TTL منفی یا صفر در ماژول یعنی
    # expiration غیرفعال است، پس از TTL کوچک
    # و دستکاری زمان استفاده می‌کنیم.

    created.updated_at = (
        time.time()
        - 100
    )

    loaded = get_pending_review(
        created.review_id,
        user_id=30,
        ttl_seconds=1
    )

    assert loaded is not None

    assert (
        loaded.status
        == STATUS_EXPIRED
    )


# =========================================================
# EXPIRED REVIEW CANNOT UPDATE
# =========================================================


def test_expired_review_cannot_update():

    created = create_pending_review(
        user_id=31,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه اول"
    )

    created.updated_at = (
        time.time()
        - 100
    )

    loaded = get_pending_review(
        created.review_id,
        user_id=31,
        ttl_seconds=1
    )

    assert (
        loaded.status
        == STATUS_EXPIRED
    )

    updated = update_pending_summary(
        review_id=created.review_id,
        user_id=31,
        new_summary="خلاصه دوم",
        regeneration_count=1
    )

    assert updated is None


# =========================================================
# CLEANUP EXPIRED
# =========================================================


def test_cleanup_expired_reviews():

    old_review = create_pending_review(
        user_id=40,
        content_type="opinion_note",
        original_text="اصل قدیمی",
        current_summary="خلاصه قدیمی"
    )

    fresh_review = create_pending_review(
        user_id=41,
        content_type="opinion_note",
        original_text="اصل جدید",
        current_summary="خلاصه جدید"
    )

    old_review.updated_at = (
        time.time()
        - 100
    )

    fresh_review.updated_at = (
        time.time()
    )

    removed = cleanup_expired_reviews(
        ttl_seconds=1
    )

    assert removed == 1

    assert (
        get_pending_review(
            old_review.review_id,
            user_id=40
        )
        is None
    )

    assert (
        get_pending_review(
            fresh_review.review_id,
            user_id=41
        )
        is not None
    )


# =========================================================
# CLEANUP DOES NOT REMOVE FINALIZED REVIEW
# =========================================================


def test_cleanup_does_not_remove_finalized_review():

    created = create_pending_review(
        user_id=50,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    mark_summary_published(
        created.review_id,
        user_id=50
    )

    created.updated_at = (
        time.time()
        - 100
    )

    removed = cleanup_expired_reviews(
        ttl_seconds=1
    )

    assert removed == 0

    loaded = get_pending_review(
        created.review_id,
        user_id=50
    )

    assert loaded is not None

    assert (
        loaded.status
        == STATUS_PUBLISHED_SUMMARY
    )


# =========================================================
# METADATA PRESERVATION
# =========================================================


def test_metadata_is_preserved_on_update():

    created = create_pending_review(
        user_id=60,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه",
        metadata={
            "source_chat_id": -100123,
            "source_message_id": 77
        }
    )

    updated = update_pending_summary(
        review_id=created.review_id,
        user_id=60,
        new_summary="خلاصه جدید",
        regeneration_count=1,
        metadata={
            "review_version": 2
        }
    )

    assert (
        updated.metadata[
            "source_chat_id"
        ]
        == -100123
    )

    assert (
        updated.metadata[
            "source_message_id"
        ]
        == 77
    )

    assert (
        updated.metadata[
            "review_version"
        ]
        == 2
    )


# =========================================================
# REVIEW IDS ARE UNIQUE
# =========================================================


def test_review_ids_are_unique():

    first = create_pending_review(
        user_id=70,
        content_type="opinion_note",
        original_text="اصل ۱",
        current_summary="خلاصه ۱"
    )

    second = create_pending_review(
        user_id=70,
        content_type="opinion_note",
        original_text="اصل ۲",
        current_summary="خلاصه ۲"
    )

    assert (
        first.review_id
        != second.review_id
    )


# =========================================================
# CLEAR STORE
# =========================================================


def test_clear_pending_reviews():

    create_pending_review(
        user_id=80,
        content_type="opinion_note",
        original_text="اصل",
        current_summary="خلاصه"
    )

    create_pending_review(
        user_id=81,
        content_type="news_analysis",
        original_text="اصل",
        current_summary="خلاصه"
    )

    assert pending_review_count() == 2

    clear_pending_reviews()

    assert pending_review_count() == 0
