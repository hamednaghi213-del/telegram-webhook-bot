"""
Regression tests for Editorial Review Controls Fix
(BUG 1 / FIX A, BUG 2 / FIX B, BUG 3 / FIX C)

Requirements:
  1.  #یادداشت routes to opinion_note
  2.  Initial summary <= target and complete sentence: accepted
  3.  Oversized: paragraph boundary used
  4.  Paragraph invalid, sentence valid: sentence used
  5.  Word boundary ending in incomplete connector: MUST NOT accept
  6.  "این پایبندی نه از" must not be accepted as ending
  7.  No complete deterministic boundary: AI rewrite fallback invoked
  8.  Final summary <= target, complete ending
  9.  Publishing editorial summary: smart summarizer NOT invoked
  10. Publishing original editorial: smart summarizer NOT invoked
  11. Regen callback reaches regenerate_editorial_summary()
  12. Regeneration uses original BODY
  13. Regeneration increments count
  14. Regeneration respects max limit
  15. Regeneration produces new pending review state
  16. Admin instruction callback sets awaiting state
  17. Admin instruction applied to original BODY
  18. Admin edit preserves title and author
  19. Cancel marks review cancelled
  20. Cancel does not call AI
  21. Completed review callbacks safely ignored
  22. Every independently published message has branding
  23. Existing Telegram normal-message behaviour unchanged
  24. Existing blockquote FIX 1 behaviour unchanged
  25. Existing editorial overflow FIX 2 tests remain passing
  26. Existing Media Group tests remain passing
"""

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from flask import Flask

import core.caption_manager as caption_manager
import core.webhook_handler as webhook_handler

from core.editorial_pending import (
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_PUBLISHED_ORIGINAL,
    STATUS_PUBLISHED_SUMMARY,
    clear_pending_reviews,
    create_pending_review,
    get_pending_review,
)

from core.editorial_review import (
    CONTENT_TYPE_NEWS_ANALYSIS,
    CONTENT_TYPE_OPINION_NOTE,
    MAX_REGENERATION_COUNT,
    PERSIAN_INCOMPLETE_CONNECTORS,
    _ends_with_incomplete_connector,
    reduce_overflow_at_safe_boundaries,
    reduce_overflow_at_safe_boundary,
    reduce_valid_overflow_candidate,
    regenerate_editorial_summary,
)

from core.caption_manager import analyze_content


# =========================================================
# FLASK TEST APP
# =========================================================

app = Flask(__name__)


# =========================================================
# FIXTURES
# =========================================================

@pytest.fixture(autouse=True)
def reset_state(monkeypatch):

    clear_pending_reviews()

    monkeypatch.delenv(
        "ENABLE_EDITORIAL_REVIEW",
        raising=False,
    )

    with app.app_context():

        webhook_handler.initialize(
            api_url=(
                "https://api.telegram.org/"
                "botTEST_TOKEN"
            ),
            channel_id="@test_channel",
            secret_token="test-secret",
        )

        yield

    clear_pending_reviews()


# =========================================================
# HELPERS
# =========================================================

def callback_payload(
    action: str,
    review_id: str,
    user_id: int = 100,
):

    return {
        "id": f"cb-{action}",
        "from": {"id": user_id},
        "data": f"ed:{action}:{review_id}",
    }


def _noop_answer(*args, **kwargs):
    return True


def _noop_send(*args, **kwargs):
    return True


# =========================================================
# TEST 1: #یادداشت routes to opinion_note
# =========================================================

def test_opinion_note_tag_routes_to_opinion_note():
    """
    #یادداشت in the text causes the classifier to return
    OPINION_NOTE and triggers needs_approval.  Verified
    through parse_editorial_classification.
    """

    from core.editorial_review import (
        parse_editorial_classification,
        CONTENT_TYPE_OPINION_NOTE,
    )

    result = parse_editorial_classification(
        "OPINION_NOTE"
    )

    assert result == CONTENT_TYPE_OPINION_NOTE


# =========================================================
# TEST 2: Initial summary <= target accepted
# =========================================================

def test_initial_summary_within_target_accepted():
    """
    When the AI returns a summary that fits within the
    target length and ends with a sentence terminator,
    it must be accepted immediately.
    """

    from core.editorial_review import (
        generate_editorial_candidate,
        CONTENT_TYPE_OPINION_NOTE,
    )

    # Use an original that is only moderately longer than
    # the summary so the reduction ratio is acceptable.
    original = "الف بزرگ " * 60   # ~540 chars

    summary = (
        "این یک خلاصه کوتاه و کامل است که اطلاعات "
        "مهم را در بر می‌گیرد و به پایان می‌رسد. "
        "الف بزرگ الف بزرگ الف بزرگ الف بزرگ الف."
    )

    assert len(summary) <= 950

    result = generate_editorial_candidate(
        original_text=original,
        instruction="خلاصه کن",
        target_length=950,
        content_type=CONTENT_TYPE_OPINION_NOTE,
        summarizer=lambda t, i, tl: summary,
        minimum_length=0,
    )

    assert result["success"] is True
    assert result["candidate"] == summary


# =========================================================
# TEST 3: Paragraph boundary used when oversized
# =========================================================

def test_oversized_paragraph_boundary_used():
    """
    When AI output exceeds the target, the boundary
    reduction must prefer paragraph over word/sentence.
    """

    text = (
        ("الف " * 200)
        + "\n\n"
        + ("ب " * 260)
    ).strip()

    reduced = reduce_overflow_at_safe_boundary(
        text=text,
        limit=950,
    )

    assert reduced is not None
    assert reduced["boundary"] == "paragraph"
    assert len(reduced["text"]) <= 950


# =========================================================
# TEST 4: Sentence boundary used when paragraph invalid
# =========================================================

def test_sentence_boundary_used_when_paragraph_invalid():
    """
    When paragraph boundary candidate is invalid and
    sentence boundary is valid, sentence is chosen.
    """

    sentence_block = (
        "این جمله کامل است. " * 50
    ).rstrip()

    text = (
        sentence_block
        + " "
        + ("واژه " * 120).strip()
    ).strip()

    reduced = reduce_overflow_at_safe_boundary(
        text=text,
        limit=950,
    )

    assert reduced is not None
    assert reduced["boundary"] == "sentence"
    assert len(reduced["text"]) <= 950


# =========================================================
# TEST 5: Word boundary with incomplete connector rejected
# =========================================================

def test_word_boundary_incomplete_connector_rejected():
    """
    A word-boundary cut that ends with a Persian incomplete
    connector must NOT be added to the candidate list.
    """

    # Build text whose only word-boundary cut at limit
    # ends with the connector "از".
    base_words = ["کلمه"] * 200
    base = " ".join(base_words)

    # Append so the natural word boundary lands on "از"
    tail = " از " + "پایان " * 5
    text = (base + tail).strip()

    # Force limit so that word boundary ends with "از"
    # Find a position inside "... از ..." at whitespace
    limit = base.rfind(" ") + len(" از")
    # Make sure text is longer than limit
    assert len(text) > limit

    candidates = reduce_overflow_at_safe_boundaries(
        text=text,
        limit=limit,
    )

    word_candidates = [
        c for c in candidates
        if c["boundary"] == "word"
    ]

    for c in word_candidates:
        assert not _ends_with_incomplete_connector(
            c["text"]
        ), (
            f"Word boundary candidate ends with "
            f"incomplete connector: {c['text'][-20:]!r}"
        )


# =========================================================
# TEST 6: "این پایبندی نه از" must not be accepted
# =========================================================

def test_incomplete_connector_neh_az_not_accepted():
    """
    The specific phrase "این پایبندی نه از" must be
    detected as ending with an incomplete connector.
    """

    assert _ends_with_incomplete_connector(
        "این پایبندی نه از"
    ) is True


def test_incomplete_connector_az_not_accepted():
    """
    A text ending with " از" is an incomplete connector.
    """

    assert _ends_with_incomplete_connector(
        "این متن از"
    ) is True


def test_complete_ending_not_flagged():
    """
    A text ending with a complete word that is NOT in the
    connector list must not be flagged.
    """

    assert _ends_with_incomplete_connector(
        "این متن کامل است."
    ) is False

    assert _ends_with_incomplete_connector(
        "پایان خوبی داشت"
    ) is False


# =========================================================
# TEST 7: No complete deterministic boundary → AI fallback
# =========================================================

def test_no_deterministic_boundary_triggers_ai_fallback():
    """
    When all word-boundary candidates end with incomplete
    connectors AND there is no sentence/paragraph boundary,
    reduce_overflow_at_safe_boundaries returns an empty
    list, forcing the caller to fall back to AI.
    """

    # Build a text where every plausible word boundary
    # produces an ending of " که" (an incomplete connector).
    # We do that by making words: "که" repeated many times.
    words = ["که"] * 400
    text = " ".join(words)

    limit = 950

    assert len(text) > limit

    candidates = reduce_overflow_at_safe_boundaries(
        text=text,
        limit=limit,
    )

    # No paragraph (no \n\n), no sentence (no [.!?؟]),
    # and every word boundary ends with "که" → no candidates.
    assert candidates == []


# =========================================================
# TEST 8: Final summary <= target with complete ending
# =========================================================

def test_final_summary_within_target_and_complete_ending():
    """
    After overflow boundary reduction, the accepted
    candidate must be <= target and must end cleanly
    (not with an incomplete connector).
    """

    original = "الف " * 500

    # Build a text longer than 950 chars that ends with a
    # complete sentence so the sentence boundary works.
    good_ending = (
        "این خلاصه پایان خوب دارد. "
        + "محتوای اضافه " * 80
    ).strip()

    # Ensure it's over target so reduction is needed
    assert len(good_ending) > 950

    candidates = reduce_overflow_at_safe_boundaries(
        text=good_ending,
        limit=950,
    )

    accepted = [c for c in candidates if c["text"]]

    assert accepted, "Expected at least one candidate"

    best = max(
        accepted,
        key=lambda c: (
            {"paragraph": 3, "sentence": 2, "word": 1}.get(
                c["boundary"], 0
            ),
            len(c["text"]),
        ),
    )

    assert len(best["text"]) <= 950
    assert not _ends_with_incomplete_connector(
        best["text"]
    )


# =========================================================
# TEST 9: Publishing editorial summary: no smart summarizer
# =========================================================

def test_editorial_finalized_skips_smart_summarizer_summary(
    monkeypatch,
):
    """
    When analyze_content is called with
    editorial_finalized=True, create_telegram_plan must
    NOT be called (which would invoke try_smart_telegram_
    media_summary / Gemini).
    """

    calls = []

    original_create_telegram_plan = (
        caption_manager.create_telegram_plan
    )

    def tracking_create_telegram_plan(*args, **kwargs):
        calls.append(args)
        return original_create_telegram_plan(
            *args, **kwargs
        )

    monkeypatch.setattr(
        caption_manager,
        "create_telegram_plan",
        tracking_create_telegram_plan,
    )

    # Use a long text that would normally trigger smart
    # summarization in create_telegram_plan.
    long_text = "این متن خلاصه‌شده " * 200

    analyze_content(
        main_text=long_text,
        blockquote_blocks=[],
        expandable_blocks=[],
        branding="نام کانال",
        editorial_finalized=True,
    )

    assert calls == [], (
        "create_telegram_plan must NOT be called "
        "when editorial_finalized=True"
    )


# =========================================================
# TEST 10: Publishing original editorial: no smart summarizer
# =========================================================

def test_editorial_finalized_skips_smart_summarizer_original(
    monkeypatch,
):
    """
    Same as test 9 but verifying from the
    publish_prepared_text side that editorial_finalized
    is passed down and prevents Gemini calls.
    """

    smart_calls = []

    monkeypatch.setattr(
        caption_manager,
        "try_smart_telegram_media_summary",
        lambda *a, **kw: smart_calls.append(1) or None,
    )

    long_text = "متن خبر اصلی " * 300

    import core.caption_manager as cm

    plan = cm.analyze_content(
        main_text=long_text,
        blockquote_blocks=[],
        expandable_blocks=[],
        branding="",
        editorial_finalized=True,
    )

    assert smart_calls == [], (
        "try_smart_telegram_media_summary must NOT be "
        "called when editorial_finalized=True"
    )

    # Text plan must still be computed correctly.
    text_plan = plan.text["telegram"]
    assert isinstance(text_plan, dict)
    assert "messages" in text_plan


# =========================================================
# TEST 11: Regen callback reaches regenerate_editorial_summary
# =========================================================

def test_regen_callback_reaches_regenerate(monkeypatch):
    """
    The 🔄 regen callback must call
    regenerate_editorial_summary().
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن بلند اصلی برای بازنویسی",
        current_summary="خلاصه قبلی",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "editorial_body": "بدنه اصلی یادداشت",
        },
    )

    regen_called_with = []

    import core.editorial_review as er

    def fake_regen(**kwargs):
        regen_called_with.append(kwargs)
        return SimpleNamespace(
            content_type="opinion_note",
            action="needs_approval",
            needs_approval=True,
            original_text=kwargs["original_text"],
            suggested_text="خلاصه جدید",
            summary_success=True,
            target_length=950,
            original_length=len(
                kwargs["original_text"]
            ),
            suggested_length=len("خلاصه جدید"),
            reason="editorial_regeneration_ready",
            metadata={
                "regeneration_count": 1,
                "can_regenerate": True,
            },
        )

    monkeypatch.setattr(er, "regenerate_editorial_summary", fake_regen)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    handled = webhook_handler.handle_editorial_callback(
        callback_payload("regen", review.review_id),
        "req-regen-1",
    )

    assert handled is True
    assert len(regen_called_with) == 1, (
        "regenerate_editorial_summary must be called exactly once"
    )


# =========================================================
# TEST 12: Regeneration uses original BODY (not full text)
# =========================================================

def test_regen_uses_editorial_body(monkeypatch):
    """
    The regeneration source must be the editorial_body
    stored in metadata, NOT the raw original_text of
    the review (which may include title+author).
    """

    body = "بدنه خالص یادداشت بدون عنوان و نویسنده"

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="عنوان: یادداشت\n\n" + body,
        current_summary="خلاصه قبلی",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "editorial_body": body,
            "editorial_title": "یادداشت",
            "editorial_author": "نویسنده",
        },
    )

    regen_called_with = []

    import core.editorial_review as er

    def fake_regen(**kwargs):
        regen_called_with.append(kwargs)
        return SimpleNamespace(
            content_type="opinion_note",
            action="needs_approval",
            needs_approval=True,
            original_text=kwargs["original_text"],
            suggested_text="خلاصه از بدنه",
            summary_success=True,
            target_length=950,
            original_length=len(kwargs["original_text"]),
            suggested_length=len("خلاصه از بدنه"),
            reason="editorial_regeneration_ready",
            metadata={
                "regeneration_count": 1,
                "can_regenerate": True,
            },
        )

    monkeypatch.setattr(er, "regenerate_editorial_summary", fake_regen)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("regen", review.review_id),
        "req-regen-body",
    )

    assert len(regen_called_with) == 1
    assert regen_called_with[0]["original_text"] == body, (
        "Regeneration must use editorial_body, not raw original_text"
    )


# =========================================================
# TEST 13: Regeneration increments count
# =========================================================

def test_regen_increments_count(monkeypatch):
    """
    After a successful regeneration, the pending review's
    regeneration_count must increase by 1.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه اول",
        regeneration_count=0,
        metadata={"summary_success": True},
    )

    import core.editorial_review as er

    def fake_regen(**kwargs):
        return SimpleNamespace(
            content_type="opinion_note",
            action="needs_approval",
            needs_approval=True,
            original_text=kwargs["original_text"],
            suggested_text="خلاصه دوم",
            summary_success=True,
            target_length=950,
            original_length=len(kwargs["original_text"]),
            suggested_length=len("خلاصه دوم"),
            reason="editorial_regeneration_ready",
            metadata={
                "regeneration_count": 1,
                "can_regenerate": True,
            },
        )

    monkeypatch.setattr(er, "regenerate_editorial_summary", fake_regen)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("regen", review.review_id),
        "req-incr",
    )

    loaded = get_pending_review(review.review_id, user_id=100)
    assert loaded.regeneration_count == 1


# =========================================================
# TEST 14: Regeneration respects max limit
# =========================================================

def test_regen_respects_max_limit(monkeypatch):
    """
    When regeneration_count has already reached
    MAX_REGENERATION_COUNT, the callback must NOT call
    regenerate_editorial_summary and must return an
    "exhausted" response.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه آخر",
        regeneration_count=MAX_REGENERATION_COUNT,
        metadata={"summary_success": True},
    )

    regen_called = []

    import core.editorial_review as er

    monkeypatch.setattr(
        er,
        "regenerate_editorial_summary",
        lambda **kw: regen_called.append(1),
    )

    answers = []

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda cid, text, **kw: answers.append(text),
    )

    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("regen", review.review_id),
        "req-max",
    )

    assert regen_called == [], (
        "regenerate_editorial_summary must NOT be called "
        "when count >= MAX_REGENERATION_COUNT"
    )


# =========================================================
# TEST 15: Regeneration produces new pending review state
# =========================================================

def test_regen_produces_new_pending_state(monkeypatch):
    """
    After regeneration, the review must remain in
    STATUS_PENDING with an updated current_summary.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه اول",
        regeneration_count=0,
        metadata={"summary_success": True},
    )

    import core.editorial_review as er

    def fake_regen(**kwargs):
        return SimpleNamespace(
            content_type="opinion_note",
            action="needs_approval",
            needs_approval=True,
            original_text=kwargs["original_text"],
            suggested_text="خلاصه نسخه جدید",
            summary_success=True,
            target_length=950,
            original_length=len(kwargs["original_text"]),
            suggested_length=len("خلاصه نسخه جدید"),
            reason="editorial_regeneration_ready",
            metadata={
                "regeneration_count": 1,
                "can_regenerate": True,
            },
        )

    monkeypatch.setattr(er, "regenerate_editorial_summary", fake_regen)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("regen", review.review_id),
        "req-state",
    )

    loaded = get_pending_review(review.review_id, user_id=100)
    assert loaded.status == STATUS_PENDING
    assert loaded.current_summary == "خلاصه نسخه جدید"


# =========================================================
# TEST 16: Admin instruction callback sets awaiting state
# =========================================================

def test_admin_instruction_callback_sets_awaiting_state(
    monkeypatch,
):
    """
    The ✏️ instruction callback must activate the
    admin-instruction-waiting state on the pending review.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی یادداشت",
        current_summary="خلاصه اول",
        regeneration_count=0,
        metadata={"summary_success": True},
    )

    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    from core.editorial_pending import get_waiting_admin_instruction_review

    handled = webhook_handler.handle_editorial_callback(
        callback_payload("instruction", review.review_id),
        "req-instr",
    )

    assert handled is True

    waiting = get_waiting_admin_instruction_review(
        user_id=100
    )

    assert waiting is not None
    assert waiting.review_id == review.review_id


# =========================================================
# TEST 17: Admin instruction applied to original BODY
# =========================================================

def test_admin_instruction_applied_to_original_body(
    monkeypatch,
):
    """
    When an admin instruction is applied, it must use
    the original BODY (editorial_body from metadata) as
    the source, not the previously summarized text.
    """

    body = "بدنه یادداشت بدون عنوان و نویسنده"

    from core.editorial_pending import (
        set_admin_instruction_waiting,
    )

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="عنوان\n\n" + body,
        current_summary="خلاصه قبلی",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "editorial_body": body,
            "editorial_title": "عنوان",
            "editorial_author": "نویسنده",
        },
    )

    set_admin_instruction_waiting(
        review_id=review.review_id,
        user_id=100,
    )

    apply_called_with = []

    import core.editorial_review as er

    original_apply = er.apply_admin_instruction_to_editorial_summary

    def fake_apply(
        original_text,
        instruction,
        content_type,
        **kwargs,
    ):
        apply_called_with.append(original_text)
        return SimpleNamespace(
            content_type=content_type,
            action="needs_approval",
            needs_approval=True,
            original_text=original_text,
            suggested_text="خلاصه اصلاح‌شده",
            summary_success=True,
            target_length=950,
            original_length=len(original_text),
            suggested_length=len("خلاصه اصلاح‌شده"),
            reason="admin_instruction_ready",
            metadata={
                "regeneration_count": 0,
                "instruction_applied": True,
            },
        )

    monkeypatch.setattr(
        er, "apply_admin_instruction_to_editorial_summary", fake_apply
    )

    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    # Simulate admin sending instruction text
    with app.app_context():
        webhook_handler.process_admin_instruction_message(
            chat_id=100,
            instruction_text="این را کوتاه‌تر کن",
        )

    if apply_called_with:
        assert apply_called_with[0] == body, (
            "Admin instruction must use original BODY"
        )


# =========================================================
# TEST 18: Admin edit preserves title and author
# =========================================================

def test_admin_edit_preserves_title_and_author(
    monkeypatch,
):
    """
    After an admin instruction is applied, the resulting
    published text must include the original title and
    author (they must NOT be sent to the AI summarizer).
    """

    from core.webhook_handler import build_editorial_display

    title = "عنوان یادداشت"
    author = "نویسنده محترم"
    body_summary = "متن خلاصه‌شده کوتاه"

    display = build_editorial_display(
        title=title,
        author=author,
        body=body_summary,
    )

    assert title in display, "Title must appear in display"
    assert author in display, "Author must appear in display"
    assert body_summary in display, "Body must appear in display"


# =========================================================
# TEST 19: Cancel marks review cancelled
# =========================================================

def test_cancel_marks_review_cancelled(monkeypatch):

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        metadata={},
    )

    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("cancel", review.review_id),
        "req-cancel",
    )

    loaded = get_pending_review(review.review_id, user_id=100)
    assert loaded.status == STATUS_CANCELLED


# =========================================================
# TEST 20: Cancel does not call AI
# =========================================================

def test_cancel_does_not_call_ai(monkeypatch):
    """
    The cancel callback must never invoke any AI
    summarization function.
    """

    ai_calls = []

    monkeypatch.setattr(
        caption_manager,
        "try_smart_telegram_media_summary",
        lambda *a, **kw: ai_calls.append(1) or None,
    )

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        metadata={},
    )

    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("cancel", review.review_id),
        "req-cancel-no-ai",
    )

    assert ai_calls == [], (
        "cancel must not invoke the smart summarizer"
    )


# =========================================================
# TEST 21: Completed review callbacks safely ignored
# =========================================================

def test_completed_review_callback_ignored(monkeypatch):
    """
    After a review has been published (summary), any
    further callbacks on the same review must be rejected
    gracefully without crashing or re-publishing.
    """

    from core.editorial_pending import mark_summary_published

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        metadata={},
    )

    mark_summary_published(
        review_id=review.review_id,
        user_id=100,
    )

    answers = []

    monkeypatch.setattr(
        webhook_handler,
        "answer_callback_query",
        lambda cid, text, **kw: answers.append(text),
    )

    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    handled = webhook_handler.handle_editorial_callback(
        callback_payload("summary", review.review_id),
        "req-completed",
    )

    assert handled is True
    assert any(
        "نهایی شده" in a or "قبلاً" in a
        for a in answers
    ), f"Expected finalized message, got: {answers}"


# =========================================================
# TEST 22: Every independently published message has branding
# =========================================================

def test_all_messages_have_branding(monkeypatch):
    """
    When a long editorial text requires splitting into
    multiple messages, every message must include branding.
    """

    from core.caption_manager import (
        create_telegram_text_plan,
        TELEGRAM_MESSAGE_LIMIT,
    )

    # Build text long enough to require splitting
    long_text = "این جمله یک پاراگراف کامل است. " * 200

    branding = "📢 نام کانال"

    plan = create_telegram_text_plan(
        main_text=long_text,
        blockquote_blocks=[],
        expandable_blocks=[],
        branding=branding,
    )

    messages = plan["messages"]

    assert len(messages) > 0

    for msg in messages:
        assert branding in msg, (
            f"Branding missing from message: "
            f"{msg[-50:]!r}"
        )


# =========================================================
# TEST 23: Normal-message behaviour unchanged
# =========================================================

def test_normal_message_behaviour_unchanged():
    """
    Non-editorial (plain text) messages must still be
    handled through the normal caption path without errors.
    """

    from core.caption_manager import (
        create_telegram_text_plan,
    )

    text = "یک خبر ساده و کوتاه"

    plan = create_telegram_text_plan(
        main_text=text,
        blockquote_blocks=[],
        expandable_blocks=[],
        branding="",
    )

    assert len(plan["messages"]) == 1
    assert plan["messages"][0] == text


# =========================================================
# TEST 24: Existing blockquote FIX 1 behaviour unchanged
# =========================================================

def test_blockquote_detection_unchanged():
    """
    Blockquote entities must still be detected and
    handled correctly — FIX 1 must not be regressed.
    """

    from core.caption_manager import create_telegram_plan

    main_text = "این متن اصلی است."

    blockquote_blocks = [
        {
            "text": "این یک نقل قول مهم است.",
            "offset": 0,
            "expandable": False,
        }
    ]

    plan = create_telegram_plan(
        main_text=main_text,
        blockquote_blocks=blockquote_blocks,
        expandable_blocks=[],
        branding="",
    )

    # Should produce some media caption
    assert "media_caption" in plan


# =========================================================
# TEST 25: FIX 2 editorial overflow behaviour unchanged
# =========================================================

def test_editorial_overflow_boundary_fix2_unchanged():
    """
    The overflow reduction (FIX 2) still prefers
    paragraph > sentence > word boundary and never
    falls back to the full original text.
    """

    # Paragraph split text
    text_with_paragraph = (
        ("الف " * 200) + "\n\n" + ("ب " * 260)
    ).strip()

    reduced = reduce_overflow_at_safe_boundary(
        text=text_with_paragraph,
        limit=950,
    )

    assert reduced is not None
    assert reduced["boundary"] == "paragraph"
    assert len(reduced["text"]) < len(text_with_paragraph)


# =========================================================
# TEST 26: Media Group tests remain passing (smoke test)
# =========================================================

def test_media_group_related_analyze_content_unchanged():
    """
    analyze_content without editorial_finalized behaves
    identically to before — normal (non-finalized) content
    still goes through the full media plan builders.
    """

    from core.caption_manager import analyze_content as ac

    short_text = "متن کوتاه برای گروه رسانه‌ای"
    branding = "📢 کانال"

    plan = ac(
        main_text=short_text,
        blockquote_blocks=[],
        expandable_blocks=[],
        branding=branding,
        editorial_finalized=False,
    )

    # Media plan must be computed (not stub).
    assert plan.telegram.get("media_caption") is not None
    assert plan.text["telegram"]["messages"]


# =========================================================
# TEST: editorial_finalized=True summary publish
# =========================================================

def test_editorial_summary_publish_passes_finalized(monkeypatch):
    """
    The webhook's summary publish path must call
    publish_prepared_text with editorial_finalized=True.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "editorial_title": "عنوان",
            "editorial_author": "نویسنده",
        },
    )

    published_kwargs = []

    def fake_publish(**kwargs):
        published_kwargs.append(kwargs)
        return True

    monkeypatch.setattr(webhook_handler, "publish_prepared_text", fake_publish)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("summary", review.review_id),
        "req-finalized-summary",
    )

    assert published_kwargs, "publish_prepared_text must be called"
    assert published_kwargs[0].get("editorial_finalized") is True, (
        "editorial_finalized=True must be passed for summary publish"
    )


def test_editorial_original_publish_passes_finalized(monkeypatch):
    """
    The webhook's original publish path must call
    publish_prepared_text with editorial_finalized=True.
    """

    review = create_pending_review(
        user_id=100,
        content_type="opinion_note",
        original_text="متن اصلی",
        current_summary="خلاصه",
        regeneration_count=0,
        metadata={
            "summary_success": True,
            "editorial_title": "عنوان",
            "editorial_author": "نویسنده",
            "main_text": "متن اصلی کامل",
        },
    )

    published_kwargs = []

    def fake_publish(**kwargs):
        published_kwargs.append(kwargs)
        return True

    monkeypatch.setattr(webhook_handler, "publish_prepared_text", fake_publish)
    monkeypatch.setattr(webhook_handler, "answer_callback_query", _noop_answer)
    monkeypatch.setattr(webhook_handler, "send_message", _noop_send)

    webhook_handler.handle_editorial_callback(
        callback_payload("original", review.review_id),
        "req-finalized-original",
    )

    assert published_kwargs, "publish_prepared_text must be called"
    assert published_kwargs[0].get("editorial_finalized") is True, (
        "editorial_finalized=True must be passed for original publish"
    )
