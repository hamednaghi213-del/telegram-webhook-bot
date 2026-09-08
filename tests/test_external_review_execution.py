from types import SimpleNamespace

import pytest

from core.external_content_model import NormalizedExternalContent
from core.external_content_review import ExternalReviewResult
from core.external_review_controller import ExternalReviewDecision
from core.external_review_execution import (
    EXTERNAL_SHORT_MAX_REDUCTION_RATIO,
    ExternalReviewExecutionError,
    execute_external_review_decision,
)


def _decision(*, short=False):
    content = NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/story",
        canonical_url="https://example.com/story",
        content_type="article",
        title="Headline",
        source_name="Source",
        body="x" * 17525,
    )
    review = ExternalReviewResult(
        title=content.title,
        body=content.body,
        requires_smart_summary=short,
    )
    return ExternalReviewDecision(
        review_id="review-1",
        chat_id=123,
        content=content,
        review=review,
    )


def test_long_external_short_uses_caption_safe_aggressive_policy(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        "core.external_review_execution.gemini_provider_configured",
        lambda: True,
    )

    def fake_summarize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            success=True,
            validation_passed=True,
            summary_text="safe summary",
        )

    monkeypatch.setattr(
        "core.external_review_execution.summarize_text_safely",
        fake_summarize,
    )
    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: SimpleNamespace(ok=True),
    )

    result = execute_external_review_decision(
        decision=_decision(short=True),
        api_url="https://api.telegram.test",
    )

    assert result.published is True
    assert captured["target_length"] < 940
    assert captured["aggressive_max_reduction_ratio"] == (
        EXTERNAL_SHORT_MAX_REDUCTION_RATIO
    )
    assert len(captured["original_text"]) >= 17525


def test_unconfirmed_publication_is_retryable_failure(monkeypatch):
    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: SimpleNamespace(ok=False),
    )

    with pytest.raises(
        ExternalReviewExecutionError,
        match="did not confirm",
    ):
        execute_external_review_decision(
            decision=_decision(),
            api_url="https://api.telegram.test",
        )


def test_external_short_requests_bounded_overshoot_retries(monkeypatch):
    """
    Requirement A: the External Review SHORT path must opt in to the
    bounded adaptive overshoot retry budget (max 3 total attempts),
    validated against the original 940-char caption-safe target.
    """

    captured = {}

    monkeypatch.setattr(
        "core.external_review_execution.gemini_provider_configured",
        lambda: True,
    )

    def fake_summarize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            success=True,
            validation_passed=True,
            summary_text="safe summary",
        )

    monkeypatch.setattr(
        "core.external_review_execution.summarize_text_safely",
        fake_summarize,
    )
    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: SimpleNamespace(ok=True),
    )

    execute_external_review_decision(
        decision=_decision(short=True),
        api_url="https://api.telegram.test",
    )

    from core.external_review_execution import (
        EXTERNAL_SHORT_MAX_OVERSHOOT_RETRIES,
    )

    assert (
        captured["max_overshoot_retries"]
        == EXTERNAL_SHORT_MAX_OVERSHOOT_RETRIES
    )
    # 2 retries after the first attempt == 3 total attempts.
    assert EXTERNAL_SHORT_MAX_OVERSHOOT_RETRIES == 2
    assert captured["target_length"] < 940


def test_external_short_final_includes_metadata_and_respects_target(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        "core.external_review_execution.gemini_provider_configured",
        lambda: True,
    )

    def fake_summarize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            success=True,
            validation_passed=True,
            summary_text="ب" * kwargs["target_length"],
        )

    monkeypatch.setattr(
        "core.external_review_execution.summarize_text_safely",
        fake_summarize,
    )
    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: (
            captured.update({"published_review": kwargs["review"]})
            or SimpleNamespace(ok=True)
        ),
    )

    execute_external_review_decision(
        decision=_decision(short=True),
        api_url="https://api.telegram.test",
    )

    text = captured["published_review"].body
    assert text.startswith("Headline\n\n")
    assert "به گزارش Source،" in text
    assert "منبع:" not in text
    assert len(text) <= 940


def test_publish_decision_forwards_media_presentation_mode(monkeypatch):
    """
    Requirement C: the resolved decision's media_presentation_mode
    must reach publish_reviewed_external_content unchanged, so the
    ExternalPrepared bridge can route ALBUM/NORMAL correctly.
    """

    captured = {}

    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: (
            captured.update(kwargs)
            or SimpleNamespace(ok=True)
        ),
    )

    decision = _decision()
    decision = ExternalReviewDecision(
        review_id=decision.review_id,
        chat_id=decision.chat_id,
        content=decision.content,
        review=decision.review,
        media_presentation_mode="album",
    )

    result = execute_external_review_decision(
        decision=decision,
        api_url="https://api.telegram.test",
    )

    assert result.published is True
    assert captured["media_presentation_mode"] == "album"


def test_publish_decision_forwards_default_normal_mode(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "core.external_review_execution.publish_reviewed_external_content",
        lambda **kwargs: (
            captured.update(kwargs)
            or SimpleNamespace(ok=True)
        ),
    )

    execute_external_review_decision(
        decision=_decision(),
        api_url="https://api.telegram.test",
    )

    assert captured["media_presentation_mode"] == "normal"
