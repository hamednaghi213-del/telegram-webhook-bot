from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock

import pytest
import requests

from core import translation_provider as provider
from core import translation_service as service
from core import translation_pipeline as pipeline
from core.translation_policy import build_multilingual_policy


def response(status=200, *, headers=None, details=None):
    data = ({"candidates": [{"content": {"parts": [{"text": "خبر تازه منتشر شد."}]}}]}
            if status == 200 else {"error": {"details": details or []}})
    return Mock(ok=status < 400, status_code=status, headers=headers or {}, json=lambda: data)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    post = Mock()
    sleep = Mock()
    monkeypatch.setattr(provider, "provider_post", post)
    monkeypatch.setattr(service.time, "sleep", sleep)
    monkeypatch.setattr(pipeline, "detect_pipeline_source_language", lambda text: {
        "language": "en", "detection": None, "provider_detection": None, "detected_by": "test",
    })
    quality = Mock(return_value={"passed": True, "semantic_verified": True})
    monkeypatch.setattr(pipeline, "_quality_check", quality)
    return post, sleep, quality


def run():
    return pipeline.run_translation_pipeline(
        text="The latest news was published.",
        policy=build_multilingual_policy(destination_language="fa", fail_closed=True),
    )


@pytest.mark.parametrize("reply,category", [
    (response(429, headers={"Retry-After": "41"}), "rate_limited"),
    (response(429, details=[{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaMetric": "free_tier_requests"}]},
                           {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]), "quota_unavailable"),
    (response(429), "rate_limited"),
    (response(401), "authentication"),
    (response(403), "authentication"),
    (response(400), "invalid_request"),
    (response(404), "configuration"),
])
def test_non_immediate_failures_suppress_both_retry_layers(harness, reply, category):
    post, sleep, quality = harness
    post.return_value = reply
    result = run()
    assert not result.success and result.blocked and not result.requires_review
    assert result.output_text == "" and result.original_text
    assert result.attempts == 1 and post.call_count == 1
    assert result.metadata["provider_failure"]["category"] == category
    sleep.assert_not_called()
    quality.assert_not_called()
    if category in {"rate_limited", "quota_unavailable"}:
        assert result.metadata["provider_failure"]["deferred"]


@pytest.mark.parametrize("first", [response(429, headers={"Retry-After": "1"}),
    response(503), requests.Timeout(), requests.ConnectionError()])
def test_transient_failure_then_success(harness, first):
    post, sleep, quality = harness
    post.side_effect = [first, response()]
    result = run()
    assert result.success and post.call_count == 2 and quality.call_count == 1
    sleep.assert_called_once_with(1)


def test_exhausted_transport_budget_does_not_restart_generation(harness):
    post, sleep, quality = harness
    post.return_value = response(503)
    result = run()
    assert not result.success and result.output_text == "" and result.attempts == 1
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    quality.assert_not_called()


def test_total_wait_budget(harness):
    post, sleep, _ = harness
    post.return_value = response(429, headers={"Retry-After": "2"})
    assert not run().success
    assert post.call_count == 2
    sleep.assert_called_once_with(2)


def test_success_unchanged(harness):
    post, sleep, _ = harness
    post.return_value = response()
    assert run().output_text == "خبر تازه منتشر شد."
    assert post.call_count == 1
    sleep.assert_not_called()


def test_malformed_success_no_retry(harness):
    post, sleep, _ = harness
    reply = response()
    reply.json = lambda: {"candidates": [None]}
    post.return_value = reply
    result = run()
    assert not result.success and post.call_count == 1
    assert result.metadata["provider_failure"]["category"] == "invalid_response"
    sleep.assert_not_called()


def test_missing_key_structured(harness, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(provider.TranslationProviderError) as error:
        provider.gemini_translation_provider(text="source", instruction="", source_language="en", target_language="fa")
    assert error.value.category == "configuration"
    harness[0].assert_not_called()


def test_retry_metadata_parsing():
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": {"seconds": "41", "nanos": 500000000}}]
    reply = response(429, headers={"Retry-After": "2"}, details=details)
    assert provider._http_provider_error(reply, reply.json(), "model").retry_after_seconds == 41.5
    reply = response(429, headers={"Retry-After": format_datetime(datetime.now(timezone.utc) + timedelta(seconds=45))})
    assert 43 <= provider._http_provider_error(reply, reply.json(), "model").retry_after_seconds <= 45


def test_candidate_validation_still_regenerates(harness):
    post, sleep, _ = harness
    invalid = response()
    # A valid HTTP candidate with an invented number fails content validation.
    invalid.json = lambda: {"candidates": [{"content": {"parts": [{"text": "خبر 999 منتشر شد."}]}}]}
    post.side_effect = [invalid, response()]
    assert run().success
    assert post.call_count == 2
    sleep.assert_not_called()


@pytest.mark.parametrize("first", [requests.exceptions.SSLError(), requests.exceptions.ProxyError(), RuntimeError("unexpected")])
def test_non_transient_exception_not_retried(harness, first):
    post, sleep, _ = harness
    post.side_effect = first
    result = run()
    assert not result.success and post.call_count == 1
    sleep.assert_not_called()


def test_structured_authentication_and_delay(harness):
    post, sleep, _ = harness
    post.return_value = response(400, details=[{
        "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID",
    }])
    assert run().metadata["provider_failure"]["category"] == "authentication"
    assert post.call_count == 1
    sleep.assert_not_called()


def test_long_retry_delay_preserved(harness):
    post, sleep, _ = harness
    post.return_value = response(429, details=[{
        "@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s",
    }])
    result = run()
    assert result.metadata["provider_failure"]["retry_after_seconds"] == 41
    assert result.metadata["provider_failure"]["deferred"]
    assert post.call_count == 1 and result.output_text == ""
    sleep.assert_not_called()
