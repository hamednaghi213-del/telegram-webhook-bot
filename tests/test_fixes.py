"""
tests/test_fixes.py

Comprehensive tests for:
  FIX 1 – Text + Blockquote inline combination in caption_manager
  FIX 2 – #یادداشت summary safe truncation in editorial_review
"""

import pytest

# ---------------------------------------------------------------------------
# FIX 1 helpers
# ---------------------------------------------------------------------------
from core.caption_manager import (
    create_telegram_text_plan,
    try_combine_text_and_blockquotes_inline,
    TELEGRAM_MESSAGE_LIMIT,
)


def _bq_block(text: str, expandable: bool = False):
    return {"text": text, "expandable": expandable}


# ---------------------------------------------------------------------------
# FIX 1 – combined under 4096 → ONE message, no blockquote_messages
# ---------------------------------------------------------------------------

class TestCombineUnder4096:

    def test_combined_under_limit_returns_one_message(self):
        main = "A" * 2000
        bq_text = "B" * 1500
        brand = "C" * 100
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        # Should be ONE message and NO separate blockquote messages
        assert len(plan["messages"]) == 1
        assert plan["blockquote_messages"] == []

    def test_combined_message_contains_main_text(self):
        main = "Hello World " * 100
        bq_text = "Quote text " * 50
        brand = "Branding"
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        combined = plan["messages"][0]
        assert "Hello World" in combined
        assert "Quote text" in combined

    def test_combined_message_contains_branding(self):
        main = "Main " * 200
        bq_text = "BQ " * 100
        brand = "MyBrand"
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        combined = plan["messages"][0]
        assert "MyBrand" in combined

    def test_branding_not_duplicated(self):
        main = "Main text"
        bq_text = "Blockquote"
        brand = "BRAND"
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        combined = plan["messages"][0]
        assert combined.count("BRAND") == 1

    def test_blockquote_html_preserved(self):
        main = "Hello"
        bq_text = "Quote"
        brand = "B"
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        combined = plan["messages"][0]
        # build_blockquote_html wraps in <blockquote>
        assert "<blockquote" in combined

    def test_expandable_blockquote_html_preserved(self):
        main = "Hello"
        bq_text = "Quote"
        brand = "B"
        # expandable blocks go in expandable_blocks param
        exp_blocks = [_bq_block(bq_text, expandable=True)]
        plan = create_telegram_text_plan(main, [], exp_blocks, brand)
        combined = plan["messages"][0]
        assert "blockquote" in combined

    def test_no_blockquotes_returns_normal_plan(self):
        main = "Just text"
        brand = "Brand"
        plan = create_telegram_text_plan(main, [], [], brand)
        assert len(plan["messages"]) >= 1
        # blockquote_messages may be empty
        assert plan["blockquote_messages"] == []


# ---------------------------------------------------------------------------
# FIX 1 – combined over 4096 → split with branding on each part
# ---------------------------------------------------------------------------

class TestCombineOver4096:

    def test_over_limit_produces_separate_blockquote_messages(self):
        main = "M" * 2500
        bq_text = "Q" * 2000
        brand = "B" * 100
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        # Combined 2500+2000+100+4 > 4096 → must split
        total = len(main) + len(bq_text) + len(brand) + 4
        assert total > TELEGRAM_MESSAGE_LIMIT
        # Should NOT combine inline
        assert plan["blockquote_messages"] != []

    def test_over_limit_main_messages_have_branding(self):
        main = "M" * 2500
        bq_text = "Q" * 2000
        brand = "MYBRAND"
        blocks = [_bq_block(bq_text)]
        plan = create_telegram_text_plan(main, blocks, [], brand)
        for msg in plan["messages"]:
            assert "MYBRAND" in msg


# ---------------------------------------------------------------------------
# FIX 1 – try_combine_text_and_blockquotes_inline helper directly
# ---------------------------------------------------------------------------

class TestTryCombineHelper:

    def test_fits_returns_string(self):
        result = try_combine_text_and_blockquotes_inline(
            "A" * 100,
            [_bq_block("B" * 100)],
            [],
            "Brand"
        )
        assert result is not None
        assert isinstance(result, str)

    def test_too_long_returns_none(self):
        result = try_combine_text_and_blockquotes_inline(
            "A" * 3000,
            [_bq_block("B" * 2000)],
            [],
            "Brand"
        )
        assert result is None

    def test_no_blockquotes_returns_none(self):
        result = try_combine_text_and_blockquotes_inline(
            "Some text",
            [],
            [],
            "Brand"
        )
        assert result is None


# ---------------------------------------------------------------------------
# FIX 2 helpers
# ---------------------------------------------------------------------------
from core.editorial_review import safe_truncate_summary_to_limit


# ---------------------------------------------------------------------------
# FIX 2 – safe_truncate_summary_to_limit
# ---------------------------------------------------------------------------

class TestSafeTruncate:

    def test_already_within_limit_unchanged(self):
        text = "Hello world"
        assert safe_truncate_summary_to_limit(text, 100) == text

    def test_result_within_limit(self):
        text = "A" * 2000
        result = safe_truncate_summary_to_limit(text, 950)
        assert len(result) <= 950

    def test_prefers_paragraph_boundary(self):
        text = ("Para one.\n\n" * 10) + "Para two extra"
        result = safe_truncate_summary_to_limit(text, 60)
        assert "\n\n" not in result.rstrip() or result.endswith(".")
        assert len(result) <= 60

    def test_sentence_boundary_fallback(self):
        # No paragraph break within limit window
        text = "Word word word. More words here. Even more."
        limit = 25
        result = safe_truncate_summary_to_limit(text, limit)
        assert len(result) <= limit
        # Should end at a sentence
        assert result.endswith(".")

    def test_word_boundary_fallback(self):
        # No sentence punctuation
        text = "one two three four five six seven eight nine ten"
        limit = 15
        result = safe_truncate_summary_to_limit(text, limit)
        assert len(result) <= limit
        # Should not cut mid-word
        assert result == result.rstrip()
        last_char = result[-1]
        assert last_char != " "

    def test_hard_cut_last_resort(self):
        # A single long word with no separators
        text = "A" * 200
        result = safe_truncate_summary_to_limit(text, 50)
        assert len(result) <= 50

    def test_persian_sentence_boundary(self):
        text = "جمله اول۔ جمله دوم۔ جمله سوم و ادامه."
        limit = 15
        result = safe_truncate_summary_to_limit(text, limit)
        assert len(result) <= limit


# ---------------------------------------------------------------------------
# FIX 2 – generate_editorial_candidate truncation path
# ---------------------------------------------------------------------------
from unittest.mock import patch, MagicMock
from core.editorial_review import (
    generate_editorial_candidate,
    CONTENT_TYPE_OPINION_NOTE,
    only_overflow_validation_error,
    validate_editorial_candidate,
    OVERFLOW_RETRY_ENABLED,
)


def _make_summarizer(responses):
    """Returns a summarizer that yields successive responses."""
    it = iter(responses)

    def summarizer(text, instruction, target):
        return next(it)

    return summarizer


class TestGenerateEditorialCandidateTruncation:
    """
    Scenario: first=1129, retry=1066, target=950
    Expected: truncate 1066 to ~950 and succeed.
    """

    TARGET = 950
    ORIGINAL = "X" * 3918

    INSTRUCTION = "Summarize in under 950 chars"

    def _run(self, first_output, retry_output):
        summarizer = _make_summarizer(
            [first_output, retry_output]
        )
        return generate_editorial_candidate(
            original_text=self.ORIGINAL,
            instruction=self.INSTRUCTION,
            target_length=self.TARGET,
            minimum_length=0,
            content_type=CONTENT_TYPE_OPINION_NOTE,
            summarizer=summarizer,
        )

    def test_truncation_succeeds_instead_of_reject(self):
        # First=1129, retry=1066 (both exceed 950)
        first_output = "W " * 564 + "end"    # ~1131 chars
        retry_output = "W " * 532 + "tail"   # ~1068 chars
        result = self._run(first_output, retry_output)
        # Should succeed via truncation
        assert result["success"] is True

    def test_truncation_result_within_target(self):
        first_output = "Word " * 226        # 1130 chars
        retry_output = "Word " * 213        # 1065 chars
        result = self._run(first_output, retry_output)
        if result["success"]:
            assert len(result["candidate"]) <= self.TARGET

    def test_truncated_result_not_full_original(self):
        first_output = "Word " * 226
        retry_output = "Word " * 213
        result = self._run(first_output, retry_output)
        # Must NOT fall back to 3918-char original
        if result["success"]:
            assert len(result["candidate"]) < len(self.ORIGINAL)

    def test_reason_is_accepted_after_truncation(self):
        first_output = "Word " * 226
        retry_output = "Word " * 213
        result = self._run(first_output, retry_output)
        if result["success"]:
            assert result["reason"] == "accepted_after_truncation"


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

class TestRegressions:

    def test_normal_message_no_blockquote(self):
        plan = create_telegram_text_plan(
            "Simple message", [], [], "Brand"
        )
        assert plan["messages"]
        assert plan["blockquote_messages"] == []

    def test_empty_main_text_with_blockquote_fits(self):
        bq_text = "BQ " * 10
        plan = create_telegram_text_plan("", [_bq_block(bq_text)], [], "B")
        # Should produce a message
        assert any(plan["messages"])

    def test_truncate_exact_limit(self):
        text = "Hello world"
        result = safe_truncate_summary_to_limit(text, len(text))
        assert result == text

    def test_plan_always_returns_both_keys(self):
        plan = create_telegram_text_plan("text", [], [], "")
        assert "messages" in plan
        assert "blockquote_messages" in plan
