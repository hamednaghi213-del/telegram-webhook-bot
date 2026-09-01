import pytest

from core.duplicate_guard import (
    DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    DuplicateCandidate,
    check_duplicate,
    duplicate_fingerprint,
    duplicate_similarity,
    normalize_duplicate_text,
    safe_check_duplicate,
)


def test_normalization_unifies_persian_arabic_variants_and_whitespace():
    assert normalize_duplicate_text(
        "خبر  مهم\u200c  درباره كاهش قيمت"
    ) == normalize_duplicate_text(
        "خبر مهم درباره کاهش قیمت"
    )


def test_exact_fingerprint_ignores_superficial_punctuation():
    left = "ایران و روسیه توافق جدیدی امضا کردند."
    right = "ایران و روسیه، توافق جدیدی امضا کردند"

    assert duplicate_fingerprint(left) == duplicate_fingerprint(right)


def test_exact_duplicate_detected_inside_same_media_identity():
    candidate = DuplicateCandidate(
        publication_id="pub-1",
        media_identity_id=10,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد.",
        actor_user_id=2,
        published_at="2026-09-01T12:00:00Z",
    )

    decision = check_duplicate(
        media_identity_id=10,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد",
        candidates=[candidate],
    )

    assert decision.duplicate is True
    assert decision.match_type == "exact"
    assert decision.similarity == 1.0
    assert decision.match is not None
    assert decision.match.publication_id == "pub-1"
    assert decision.match.actor_user_id == 2


def test_same_text_in_different_media_identity_is_not_duplicate():
    candidate = DuplicateCandidate(
        publication_id="pub-1",
        media_identity_id=11,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد.",
    )

    decision = check_duplicate(
        media_identity_id=10,
        text="وزیر خارجه ایران امروز با همتای روس خود دیدار کرد.",
        candidates=[candidate],
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_near_duplicate_detected():
    original = (
        "رئیس جمهور فرانسه اعلام کرد پاریس در نشست آینده اتحادیه اروپا "
        "موضوع افزایش همکاری های دفاعی میان کشورهای عضو را پیگیری خواهد کرد."
    )

    incoming = (
        "رئیس جمهور فرانسه گفت پاریس در نشست آینده اتحادیه اروپا "
        "افزایش همکاری های دفاعی کشورهای عضو را دنبال خواهد کرد."
    )

    similarity = duplicate_similarity(original, incoming)

    candidate = DuplicateCandidate(
        publication_id="pub-near",
        media_identity_id=20,
        text=original,
    )

    decision = check_duplicate(
        media_identity_id=20,
        text=incoming,
        candidates=[candidate],
        near_duplicate_threshold=0.70,
    )

    assert similarity >= 0.70
    assert decision.duplicate is True
    assert decision.match_type == "near"
    assert decision.match is not None
    assert decision.match.publication_id == "pub-near"


def test_unrelated_news_is_not_duplicate():
    candidates = [
        DuplicateCandidate(
            publication_id="pub-1",
            media_identity_id=20,
            text=(
                "وزارت خارجه چین درباره روابط تجاری با اتحادیه اروپا "
                "بیانیه تازه ای منتشر کرد."
            ),
        )
    ]

    decision = check_duplicate(
        media_identity_id=20,
        text=(
            "تیم ملی فوتبال ایران اردوی آماده سازی خود را "
            "برای مسابقات آینده آغاز کرد."
        ),
        candidates=candidates,
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_short_text_is_not_used_for_near_duplicate_detection():
    candidates = [
        DuplicateCandidate(
            publication_id="pub-1",
            media_identity_id=30,
            text="قیمت نفت افزایش یافت",
        )
    ]

    decision = check_duplicate(
        media_identity_id=30,
        text="قیمت نفت بالا رفت",
        candidates=candidates,
        near_duplicate_threshold=0.10,
    )

    assert decision.duplicate is False


def test_exact_duplicate_still_works_for_short_text():
    candidates = [
        DuplicateCandidate(
            publication_id="pub-short",
            media_identity_id=30,
            text="قیمت نفت افزایش یافت",
        )
    ]

    decision = check_duplicate(
        media_identity_id=30,
        text="قیمت نفت افزایش یافت",
        candidates=candidates,
    )

    assert decision.duplicate is True
    assert decision.match_type == "exact"


def test_best_near_duplicate_is_selected():
    incoming = (
        "دولت عراق اعلام کرد مذاکرات تازه ای درباره صادرات انرژی "
        "و همکاری اقتصادی با کشورهای همسایه آغاز شده است."
    )

    weak = DuplicateCandidate(
        publication_id="weak",
        media_identity_id=40,
        text=(
            "دولت عراق درباره برنامه های اقتصادی آینده و توسعه تجارت "
            "با برخی کشورهای منطقه توضیحاتی ارائه کرد."
        ),
    )

    strong = DuplicateCandidate(
        publication_id="strong",
        media_identity_id=40,
        text=(
            "دولت عراق اعلام کرد مذاکرات جدید درباره صادرات انرژی "
            "و همکاری اقتصادی با کشورهای همسایه آغاز شده است."
        ),
    )

    decision = check_duplicate(
        media_identity_id=40,
        text=incoming,
        candidates=[weak, strong],
        near_duplicate_threshold=0.60,
    )

    assert decision.duplicate is True
    assert decision.match is not None
    assert decision.match.publication_id == "strong"


def test_empty_text_is_safe():
    decision = check_duplicate(
        media_identity_id=50,
        text="",
        candidates=[],
    )

    assert decision.duplicate is False
    assert decision.match is None


def test_default_threshold_is_conservative():
    assert DEFAULT_NEAR_DUPLICATE_THRESHOLD >= 0.85


def test_safe_check_duplicate_is_fail_open(monkeypatch):
    import core.duplicate_guard as duplicate_guard

    def broken_check(**_kwargs):
        raise RuntimeError("detector failed")

    monkeypatch.setattr(
        duplicate_guard,
        "check_duplicate",
        broken_check,
    )

    decision = safe_check_duplicate(
        media_identity_id=99,
        text="یک خبر آزمایشی",
        candidates=[],
    )

    assert decision.duplicate is False
    assert decision.match is None


@pytest.mark.parametrize(
    "left,right",
    [
        ("ایران، روسیه", "ایران روسیه"),
        ("خبر\u200cفوری", "خبر فوری"),
        ("كاهش قيمت", "کاهش قیمت"),
    ],
)
def test_normalized_equivalents_share_fingerprint(left, right):
    assert duplicate_fingerprint(left) == duplicate_fingerprint(right)
