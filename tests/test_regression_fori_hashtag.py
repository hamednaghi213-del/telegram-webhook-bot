"""
Regression tests for #فوری preservation through clean_text / format_news.

Prior regression: HASH_PATTERN = r'#[^\s]+' blindly removed all hashtags
including the editorial breaking-news marker #فوری.

Fix: PRESERVED_EDITORIAL_HASHTAGS frozenset in core/cleaner.py;
replace_hash() returns the tag unchanged when it is in the set.
"""
import pytest

from core.cleaner import (
    clean_foreign_mentions_and_hashtags,
    clean_text,
    initialize,
)
from core.formatter import format_news


# =========================================================
# clean_foreign_mentions_and_hashtags
# =========================================================

def test_fori_hashtag_preserved_by_foreign_mention_cleaner():
    result = clean_foreign_mentions_and_hashtags("🔴 #فوری / متن خبر")
    assert "#فوری" in result


def test_fori_hashtag_preserved_when_followed_by_body():
    text = "#فوری\nخبر جدید منتشر شد."
    result = clean_foreign_mentions_and_hashtags(text)
    assert "#فوری" in result


def test_foreign_source_hashtag_still_removed():
    text = "خبر مهم\n#CNN"
    result = clean_foreign_mentions_and_hashtags(text)
    assert "#CNN" not in result


def test_foreign_latin_hashtag_still_removed():
    text = "خبر\n#BBCNews و متن"
    result = clean_foreign_mentions_and_hashtags(text)
    assert "#BBCNews" not in result


def test_tenant_branding_hashtag_still_preserved_alongside_fori(monkeypatch):
    monkeypatch.setattr("core.cleaner.HASHTAG", "#تست")
    monkeypatch.setattr("core.cleaner.CHANNEL_TAG", "@testbot")
    text = "#تست خبر #فوری جدید"
    result = clean_foreign_mentions_and_hashtags(text)
    assert "#تست" in result
    assert "#فوری" in result


def test_unrelated_persian_hashtag_without_exemption_is_removed():
    # #دنیا_۲۴_نیوز is a source branding tag, not in PRESERVED_EDITORIAL_HASHTAGS.
    # When HASHTAG global is not set to it, it should be removed.
    text = "خبر\n#دنیا_۲۴_نیوز"
    result = clean_foreign_mentions_and_hashtags(text)
    assert "#دنیا_۲۴_نیوز" not in result


# =========================================================
# clean_text (full pipeline)
# =========================================================

def test_fori_hashtag_preserved_through_clean_text():
    result = clean_text("🔴 #فوری / متن خبر تستی")
    assert "#فوری" in result


def test_fori_hashtag_preserved_through_clean_text_with_body():
    result = clean_text("🔴 #فوری\nخبر مهم امروز منتشر شد.")
    assert "#فوری" in result


# =========================================================
# format_news (end-to-end)
# =========================================================

def test_fori_hashtag_preserved_through_format_news():
    result = format_news("🔴 #فوری / متن خبر تستی. یک جمله کامل است.")
    assert "#فوری" in result


def test_fori_not_stripped_as_source_hashtag():
    # Confirm the leading slash/content is preserved (existing behavior),
    # and #فوری is now also preserved.
    text = "🔴 #فوری / متن خبر تستی. جمله کامل."
    result = format_news(text)
    assert "متن خبر" in result
    assert "#فوری" in result
