import sys
import types

import core.duplicate_guard as duplicate_guard


def _install_fake_database(monkeypatch, history_reader):
    fake_database = types.ModuleType("core.database")
    fake_database.get_recent_duplicate_news = history_reader

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake_database,
    )


def test_history_exact_duplicate_is_detected(monkeypatch):
    rows = [
        {
            "id": 101,
            "media_identity_id": 7,
            "actor_user_id": 2,
            "content_text": (
                "وزیر خارجه ایران امروز با همتای روس خود دیدار کرد."
            ),
            "published_at": "2026-09-02T00:00:00Z",
        }
    ]

    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: rows,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=7,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد",
    )

    assert decision.duplicate is True
    assert decision.match_type == "exact"
    assert decision.match is not None
    assert decision.match.publication_id == "101"
    assert decision.match.actor_user_id == 2


def test_history_near_duplicate_is_detected(monkeypatch):
    rows = [
        {
            "id": 102,
            "media_identity_id": 9,
            "actor_user_id": 3,
            "content_text": (
                "رئیس جمهور فرانسه اعلام کرد پاریس در نشست آینده "
                "اتحادیه اروپا موضوع افزایش همکاری های دفاعی میان "
                "کشورهای عضو را پیگیری خواهد کرد."
            ),
            "published_at": "2026-09-02T00:00:00Z",
        }
    ]

    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: rows,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=9,
        text=(
            "رئیس جمهور فرانسه گفت پاریس در نشست آینده "
            "اتحادیه اروپا افزایش همکاری های دفاعی کشورهای "
            "عضو را دنبال خواهد کرد."
        ),
        near_duplicate_threshold=0.70,
    )

    assert decision.duplicate is True
    assert decision.match_type == "near"
    assert decision.match is not None
    assert decision.match.publication_id == "102"


def test_history_unrelated_news_is_not_duplicate(monkeypatch):
    rows = [
        {
            "id": 103,
            "media_identity_id": 5,
            "actor_user_id": 4,
            "content_text": (
                "وزارت خارجه چین درباره روابط تجاری با "
                "اتحادیه اروپا بیانیه تازه ای منتشر کرد."
            ),
            "published_at": "2026-09-02T00:00:00Z",
        }
    ]

    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: rows,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=5,
        text=(
            "تیم ملی فوتبال ایران اردوی آماده سازی خود را "
            "برای مسابقات آینده آغاز کرد."
        ),
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_history_reader_receives_requested_media_and_limit(
    monkeypatch,
):
    observed = {}

    def fake_history(media_identity_id, limit=50):
        observed["media_identity_id"] = media_identity_id
        observed["limit"] = limit
        return []

    _install_fake_database(
        monkeypatch,
        fake_history,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=12,
        text="یک خبر آزمایشی برای بررسی تاریخچه انتشار",
        history_limit=30,
    )

    assert decision.duplicate is False
    assert observed == {
        "media_identity_id": 12,
        "limit": 30,
    }


def test_history_database_failure_is_fail_open(monkeypatch):
    def broken_history(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    _install_fake_database(
        monkeypatch,
        broken_history,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=20,
        text="این خبر باید حتی در صورت خطای دیتابیس قابل انتشار باشد",
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_malformed_history_row_is_fail_open(monkeypatch):
    rows = [
        {
            "id": 104,
            "media_identity_id": "invalid",
            "actor_user_id": "invalid",
            "content_text": "خبر آزمایشی",
        }
    ]

    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: rows,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=7,
        text="خبر آزمایشی",
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_empty_history_is_safe(monkeypatch):
    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: [],
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=7,
        text="یک خبر جدید که سابقه ای ندارد",
    )

    assert decision.duplicate is False
    assert decision.match is None

def test_current_source_key_is_excluded_from_history(monkeypatch):
    rows = [
        {
            "id": 105,
            "media_identity_id": 7,
            "actor_user_id": 2,
            "source_key": "source:telegram:123",
            "content_text": (
                "وزیر خارجه ایران امروز با همتای روس خود دیدار کرد."
            ),
            "published_at": "2026-09-02T00:00:00Z",
        }
    ]

    _install_fake_database(
        monkeypatch,
        lambda media_identity_id, limit=50: rows,
    )

    decision = duplicate_guard.check_duplicate_against_history(
        media_identity_id=7,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد.",
        source_key="source:telegram:123",
    )

    assert decision.duplicate is False
    assert decision.match is None
