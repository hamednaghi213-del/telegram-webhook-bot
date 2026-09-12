import logging
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from core import ai_runtime as runtime
from core import translation_pipeline as pipeline
from core import automatic_translation_review as automatic
from core import caption_manager as captions
from core import translation_quality_provider as quality
from core.translation_policy import build_multilingual_policy


@pytest.fixture
def detection(monkeypatch):
    monkeypatch.setattr(pipeline, "_detect_language", lambda text: None)
    monkeypatch.setattr(pipeline, "_deterministic_language", lambda result: "auto")
    provider = Mock(return_value={"success": True, "language": "en"})
    monkeypatch.setattr(pipeline, "_provider_language_detection", provider)
    return provider


def test_exact_detection_reuse_is_operation_local(detection):
    with pipeline.reuse_language_detection():
        first = pipeline.detect_pipeline_source_language("Original")
        assert pipeline.detect_pipeline_source_language("Original") == first
        assert detection.call_count == 1
        pipeline.detect_pipeline_source_language("Edited")
        pipeline.detect_pipeline_source_language("Original ")
        assert detection.call_count == 3
    # A later retranslation has to detect again, even with the same original.
    with pipeline.reuse_language_detection():
        pipeline.detect_pipeline_source_language("Original")
    assert detection.call_count == 4


def test_distinct_article_fields_do_not_share_language(detection):
    with pipeline.reuse_language_detection():
        for text in ("Title\n\nLead\n\nBody", "Title", "Lead", "Body", "Lead"):
            pipeline.detect_pipeline_source_language(text)
    assert detection.call_count == 4


@pytest.mark.parametrize("language", ["auto", "unknown", "und", "uncertain", ""])
def test_uncertain_result_is_not_cached_and_gate_stays_closed(detection, language):
    detection.return_value = {"success": True, "language": language}
    with pipeline.reuse_language_detection():
        assert automatic.automatic_translation_required("Uncertain").action == automatic.ACTION_BLOCKED
        assert automatic.automatic_translation_required("Uncertain").action == automatic.ACTION_BLOCKED
    assert detection.call_count == 2


def test_automatic_gate_and_real_pipeline_detect_only_once(monkeypatch, detection):
    monkeypatch.setattr(automatic, "start_translation", Mock(return_value=SimpleNamespace(success=True, review_id="review")))
    monkeypatch.setattr(pipeline, "_default_translation_provider", lambda: Mock())
    monkeypatch.setattr(pipeline, "_translate", Mock(return_value={"success": True, "translated_text": "خبر تازه منتشر شد."}))
    monkeypatch.setattr(pipeline, "_quality_check", Mock(return_value={"passed": True, "semantic_verified": True}))

    def select(**kwargs):
        result = pipeline.run_manual_translation_pipeline(
            text="The latest news was published.", target_language="Persian",
            policy=build_multilingual_policy(destination_language="fa", fail_closed=True),
        )
        assert result.success, (result.reason, result.metadata)
        return SimpleNamespace(success=True, action=automatic.RESULT_PREVIEW,
                               review_id="review", translated_text=result.output_text)
    monkeypatch.setattr(automatic, "select_translation_language", select)
    result = automatic.start_automatic_persian_translation_review(
        chat_id=1, user_id=1, original_text="The latest news was published.",
    )
    assert result.success
    assert detection.call_count == 1
    # The operation's cache is gone after preview, including on later retries.
    pipeline.detect_pipeline_source_language("The latest news was published.")
    assert detection.call_count == 2


@pytest.mark.parametrize("kind,unused", [("text", "create_telegram_plan"), ("media", "create_telegram_text_plan")])
def test_unused_plan_cannot_trigger_ai(monkeypatch, kind, unused):
    monkeypatch.setenv("ENABLE_SMART_SUMMARIZER", "true")
    monkeypatch.setattr(captions, unused, Mock(side_effect=AssertionError("unused AI-capable plan")))
    plan = captions.analyze_content("Headline\nBody", output_kind=kind)
    if kind == "text":
        assert plan.text["telegram"]["messages"]
        assert not plan.telegram["media_caption"]
    else:
        assert plan.telegram["media_caption"]
        assert not plan.text["telegram"]["messages"]


@pytest.mark.parametrize("kind", ["text", "media"])
def test_selected_output_matches_existing_both_plan(kind):
    kwargs = dict(main_text="🟢 Headline\nBody", branding="#News",
                  expandable_blocks=[{"text": "More details", "offset": 50}])
    both = captions.analyze_content(**kwargs)
    selected = captions.analyze_content(**kwargs, output_kind=kind)
    if kind == "text":
        assert selected.text == both.text
    else:
        assert selected.telegram == both.telegram
        assert selected.bale == both.bale


def test_sessions_reused_within_thread_but_not_across_threads(monkeypatch):
    monkeypatch.delattr(runtime._sessions, "session", raising=False)
    factory = Mock(side_effect=lambda: Mock())
    monkeypatch.setattr(runtime.requests, "Session", factory)
    kwargs = dict(json={"text": "private"}, params={"key": "secret"}, timeout=(5, 30))
    runtime.provider_post("endpoint", **kwargs)
    session = runtime._sessions.session
    runtime.provider_post("endpoint", **kwargs)
    assert factory.call_count == 1
    assert session.post.call_count == 2
    assert session.post.call_args.kwargs == kwargs
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(runtime.provider_post, "endpoint", **kwargs).result()
    assert factory.call_count == 2
    monkeypatch.delattr(runtime._sessions, "session")


@pytest.mark.parametrize("statuses,expected_delays", [
    ([200], []), ([503, 200], [1]), ([429, 200], [1]),
    ([503, 503, 503], [1, 2]), ([400], []), ([401], []), ([403], []),
])
def test_quality_pooling_keeps_retry_and_timeout_contract(monkeypatch, statuses, expected_delays):
    monkeypatch.delattr(runtime._sessions, "session", raising=False)
    replies = [Mock(status_code=status) for status in statuses]
    session = Mock()
    session.post.side_effect = replies
    monkeypatch.setattr(runtime.requests, "Session", Mock(return_value=session))
    sleep = Mock()
    monkeypatch.setattr(quality.time, "sleep", sleep)
    result = quality._post_quality_request("endpoint", api_key="secret", payload={}, timeout=45, model="model")
    assert result is replies[-1]
    assert session.post.call_count == len(statuses)
    assert [c.kwargs["timeout"] for c in session.post.call_args_list] == [45] + [10] * (len(statuses) - 1)
    assert [c.args[0] for c in sleep.call_args_list] == expected_delays
    assert all(reply.close.call_count == 1 for reply in replies[:-1])
    monkeypatch.delattr(runtime._sessions, "session")


def test_session_adds_no_implicit_transport_retries():
    with requests.Session() as session:
        assert session.get_adapter("https://example.com").max_retries.total == 0


def test_timing_logs_on_failure_without_content_or_secrets(caplog):
    @runtime.timed_stage("test", provider="gemini", model=lambda: "model")
    def failing(text, key):
        raise ValueError("failure")
    with caplog.at_level(logging.INFO), pytest.raises(ValueError):
        failing("PRIVATE CONTENT", "SECRET KEY")
    assert "stage=test" in caplog.text and "elapsed_ms=" in caplog.text
    assert "model=model" in caplog.text
    assert "PRIVATE CONTENT" not in caplog.text and "SECRET KEY" not in caplog.text


def test_exhausted_quality_transport_still_fails_closed(monkeypatch, detection):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "_default_translation_provider", lambda: Mock())
    monkeypatch.setattr(pipeline, "_translate", Mock(return_value={"success": True, "translated_text": "خبر تازه امروز منتشر شد و مقام‌ها این گزارش را تأیید کردند."}))
    response = Mock(ok=False, status_code=503, json=lambda: {"error": {"message": "unavailable"}})
    post = Mock(return_value=response)
    monkeypatch.setattr(quality, "provider_post", post)
    monkeypatch.setattr(quality.time, "sleep", Mock())
    result = pipeline.run_translation_pipeline(
        text="The latest news was published today and officials confirmed the report.",
        policy=build_multilingual_policy(destination_language="fa", fail_closed=True),
        quality_retries=0,
    )
    assert not result.success and result.blocked and not result.requires_review
    assert post.call_count == 3


@pytest.mark.parametrize("fields,expected_calls", [
    ({"body": "Body"}, 1),
    ({"title": "Title", "lead": "Body", "body": "Body"}, 3),
    ({"title": "Title", "lead": "Lead", "body": "Body"}, 4),
])
def test_external_helper_only_reuses_exact_fields(monkeypatch, detection, fields, expected_calls):
    from core.webhook_handler import translate_external_content_to_persian
    from core.external_content_model import NormalizedExternalContent
    content = NormalizedExternalContent(source_type="web", source_url="https://example.com/article", **fields)

    def translate(**kwargs):
        pipeline.detect_pipeline_source_language(kwargs["text"])
        return SimpleNamespace(success=True, blocked=False, output_text="متن ترجمه", reason="")
    monkeypatch.setattr(pipeline, "run_translation_pipeline", translate)
    result, error = translate_external_content_to_persian(content)
    assert error is None and result.source_url == content.source_url
    assert detection.call_count == expected_calls


def test_detection_scope_resets_after_failure(detection):
    with pytest.raises(RuntimeError):
        with pipeline.reuse_language_detection():
            pipeline.detect_pipeline_source_language("Original")
            raise RuntimeError("failed operation")
    pipeline.detect_pipeline_source_language("Original")
    assert detection.call_count == 2
