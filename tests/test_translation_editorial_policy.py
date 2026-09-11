from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.translation_editorial_policy import (
    EditorialTerminologyRule, EditorialTranslationPolicy, PERSIAN_NEWSROOM_POLICY,
    apply_editorial_translation_policy as apply,
)
from core import translation_pipeline as pipeline
from core.translation_policy import build_multilingual_policy


def run(source, candidate, **kwargs):
    return apply(source_text=source, translated_text=candidate, target_language="fa", **kwargs)


@pytest.mark.parametrize("source", [
    "terror group Houthis captured the city",
    "terrorist Houthis captured the city",
    "Houthi terrorist group captured the city",
])
def test_explicit_label_normalizes_entity_only(source):
    result = run(source, "گروه تروریستی حوثی‌ها شهر را تصرف کردند.")
    assert result.status == "normalized"
    assert result.output_text == "حوثی‌ها شهر را تصرف کردند."
    assert "رسانه" not in result.output_text
    assert "تروریست" not in result.output_text
    assert run(source, result.output_text).output_text == result.output_text


def test_houthis_and_middle_east():
    result = run("Houthis in the Middle East", "حوثی ها در خاورمیانه")
    assert result.output_text == "حوثی‌ها در غرب آسیا"
    assert result.normalized_rules == ("houthi_entity", "west_asia")


def test_facts_tokens_attribution_paragraphs_and_modality_survive():
    original = "Houthis may move in the Middle East, officials said."
    candidate = (
        "مقام‌ها گفتند حوثی ها ممکن است حرکت کنند.\n\n"
        "در خاورمیانه: 42 نفر در 2026-09-11، https://example.com/MiddleEast "
        "@Houthis #خاورمیانه و ۱۲۳."
    )
    expected = candidate.replace("حوثی ها", "حوثی‌ها").replace("در خاورمیانه:", "در غرب آسیا:")
    assert run(original, candidate).output_text == expected


@pytest.mark.parametrize("candidate", [
    "خبر عادی بدون تغییر.",
    "خاورمیانه‌ای و پیشاحوثی ها نباید تغییر کنند.",
    "https://example.com/Houthis @Houthis #Houthis",
])
def test_ordinary_text_and_boundaries(candidate):
    assert run("Ordinary news", candidate).output_text == candidate


def test_unknown_sensitive_entity_requires_review():
    candidate = "گروه تروریستی ناشناس شهر را تصرف کرد."
    result = run("Unknown terrorist group captured the city", candidate)
    assert result.status == "review_required"
    assert result.output_text == candidate


def test_unrelated_sensitive_statement_not_hidden_by_known_rule():
    result = run("terror group Houthis advanced. Another terrorist escaped.",
                 "گروه تروریستی حوثی‌ها پیشروی کردند. فرد دیگری فرار کرد.")
    assert result.requires_review


def test_factual_designation_is_not_silently_removed():
    candidate = "دولت گروه تروریستی حوثی‌ها را در فهرست قرار داد."
    result = run("The government designated Houthis a terrorist group", candidate)
    assert result.requires_review
    assert result.output_text == candidate


def test_quotation_requires_review_without_rewriting():
    candidate = "او گفت: «گروه تروریستی حوثی‌ها»"
    result = run('He said "terror group Houthis"', candidate)
    assert result.requires_review
    assert result.output_text == candidate


def test_added_attribution_commentary_blocks_instead_of_guessing_deletion():
    result = run("terror group Houthis captured the city",
                 "حوثی‌ها شهر را تصرف کردند. رسانه مبدأ آن را تروریستی خوانده است.")
    assert result.blocked
    assert not result.output_text


def test_configurable_policy_context_and_disable():
    rule = EditorialTerminologyRule("region", ("Middle East",), "غرب آسیا",
                                    ("خاورمیانه",), context_expressions=("region",))
    policy = EditorialTranslationPolicy(rules=(rule,))
    assert run("Middle East", "خاورمیانه", policy=policy).requires_review
    assert run("Middle East region", "خاورمیانه", policy=policy).output_text == "غرب آسیا"
    assert run("Middle East", "خاورمیانه", policy=replace(policy, enabled=False)).output_text == "خاورمیانه"
    assert run("Houthis", "حوثی ها", policy=replace(PERSIAN_NEWSROOM_POLICY, rules=())).output_text == "حوثی ها"


def test_other_target_language_unaffected():
    result = apply(source_text="Middle East", translated_text="Middle East", target_language="en")
    assert result.status == "accepted"
    assert result.output_text == "Middle East"


def test_misconfigured_rule_cannot_invent_protected_content():
    policy = EditorialTranslationPolicy(rules=(
        EditorialTerminologyRule("bad", ("Middle East",), "غرب آسیا 42", ("خاورمیانه",)),
    ))
    result = run("Middle East", "خاورمیانه", policy=policy)
    assert result.blocked and not result.output_text


@pytest.fixture
def pipeline_mocks(monkeypatch):
    monkeypatch.setattr(pipeline, "detect_pipeline_source_language", lambda text: {
        "language": "en", "detection": None, "provider_detection": None, "detected_by": "test",
    })
    monkeypatch.setattr(pipeline, "_default_translation_provider", lambda: object())
    translate = Mock(return_value={"success": True, "translated_text": "گروه تروریستی حوثی‌ها شهر را تصرف کردند."})
    quality = Mock(return_value={"passed": True, "status": "passed", "semantic_verified": True})
    monkeypatch.setattr(pipeline, "_translate", translate)
    monkeypatch.setattr(pipeline, "_quality_check", quality)
    return translate, quality


def invoke(**kwargs):
    return pipeline.run_translation_pipeline(
        text="terror group Houthis captured the city",
        policy=build_multilingual_policy(destination_language="fa"), **kwargs,
    )


def test_quality_receives_post_policy_text_and_original_source(pipeline_mocks):
    translate, quality = pipeline_mocks
    result = invoke()
    assert result.success
    assert result.output_text == "حوثی‌ها شهر را تصرف کردند."
    assert quality.call_args.kwargs["translated_text"] == result.output_text
    assert quality.call_args.kwargs["source_text"] == result.original_text
    assert "house style" in quality.call_args.kwargs["editorial_instruction"]
    assert result.metadata["editorial_policy"]["status"] == "normalized"
    assert translate.call_count == 1


def test_ambiguous_policy_routes_to_existing_review(pipeline_mocks):
    translate, quality = pipeline_mocks
    translate.return_value["translated_text"] = "تروریست ناشناس فرار کرد."
    result = invoke()
    assert result.success and result.requires_review and not result.blocked
    assert result.status == pipeline.PIPELINE_REVIEW_REQUIRED
    assert quality.call_count == 1


def test_policy_error_fails_closed_before_quality(pipeline_mocks):
    result = invoke(editorial_policy=EditorialTranslationPolicy(rules=(
        EditorialTerminologyRule("bad", (), ""),
    )))
    assert result.blocked and not result.success
    pipeline_mocks[1].assert_not_called()


def test_editorial_failure_cannot_enable_original_text_fallback(pipeline_mocks):
    result = pipeline.run_translation_pipeline(
        text="Houthis", policy=build_multilingual_policy(destination_language="fa", fail_closed=False),
        editorial_policy=EditorialTranslationPolicy(rules=(EditorialTerminologyRule("bad", (), ""),)),
    )
    assert result.blocked and not result.success and result.output_text == ""


def test_quality_rejection_still_blocks(pipeline_mocks):
    pipeline_mocks[1].return_value = {"passed": False, "semantic_verified": False}
    result = invoke(quality_retries=0)
    assert result.blocked and result.reason == "translation_quality_failed"


def test_actual_quality_retry_still_uses_original_source(pipeline_mocks, monkeypatch):
    translate, quality = pipeline_mocks
    quality.side_effect = [
        {"passed": False, "semantic_verified": True, "grammar_ok": False},
        {"passed": True, "status": "passed", "semantic_verified": True},
    ]
    monkeypatch.setattr(pipeline, "_quality_should_retry", lambda result: True)
    result = invoke()
    assert result.success and result.attempts == 2
    assert translate.call_count == 2
    for call in translate.call_args_list:
        assert call.kwargs["text"] == "terror group Houthis captured the city"
    for call in quality.call_args_list:
        assert call.kwargs["translated_text"] == "حوثی‌ها شهر را تصرف کردند."


def test_injected_disabled_policy_leaves_candidate_unchanged(pipeline_mocks):
    result = invoke(editorial_policy=replace(PERSIAN_NEWSROOM_POLICY, enabled=False))
    assert result.output_text == pipeline_mocks[0].return_value["translated_text"]
    assert pipeline_mocks[1].call_args.kwargs["editorial_instruction"] == ""


def test_quality_provider_gets_explicit_exceptions(monkeypatch):
    import core.translation_quality as quality
    import core.translation_quality_provider as provider
    adapter = Mock(return_value="quality response")
    monkeypatch.setattr(provider, "get_default_translation_quality_provider", lambda: adapter)
    def check(**kwargs):
        assert kwargs["translated_text"] == "post-policy text"
        return kwargs["provider"](text=kwargs["translated_text"], instruction="Check fidelity.")
    monkeypatch.setattr(quality, "check_translation_quality", check)
    assert pipeline._quality_check(source_text="source", translated_text="post-policy text",
        source_language="en", target_language="fa", semantic_quality=True,
        editorial_instruction="Only explicit house-style substitutions.") == "quality response"
    assert adapter.call_args.kwargs["instruction"] == "Check fidelity.\n\nOnly explicit house-style substitutions."


def test_manual_edited_state_remains_authoritative_on_confirmation(monkeypatch):
    from core import translation_state as states, translation_controller as controller
    from core.translation_publication import build_translation_publication_payload
    row = dict(review_id="review-1", chat_id=1, user_id=1, status="preview",
               original_text="source", translated_text="machine translation",
               edited_text="خاورمیانه؛ متن انتخاب‌شده توسط کاربر.", target_language="fa",
               metadata={})
    state = states._state_from_row(row)
    monkeypatch.setattr(controller, "get_translation_state", lambda rid: state)
    monkeypatch.setattr(states, "get_translation_state", lambda rid: state)
    database = SimpleNamespace(mark_persistent_translation_review_confirmed=lambda rid: dict(row, status="confirmed"))
    monkeypatch.setattr(states, "_database", lambda: database)
    forbidden = Mock(side_effect=AssertionError("must not translate or apply policy after edit"))
    monkeypatch.setattr(pipeline, "run_translation_pipeline", forbidden)
    monkeypatch.setattr("core.translation_editorial_policy.apply_editorial_translation_policy", forbidden)
    result = controller.confirm_translation(review_id="review-1", chat_id=1, user_id=1)
    assert result.success
    assert build_translation_publication_payload(result.state)["main_text"] == row["edited_text"]
    forbidden.assert_not_called()
