"""Regression coverage through real HTTP adapters, registry, chain and pipeline."""
from unittest.mock import Mock

import pytest

from core import translation_pipeline as pipeline
from core import translation_provider as provider
from core import translation_provider_chain as chain
from core import translation_provider_registry as registry
from core import translation_service as service
from core.translation_policy import build_multilingual_policy


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setattr(registry, "_registry", registry.TranslationProviderRegistry())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDFLARE_AI_API_TOKEN", "test-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(pipeline, "detect_pipeline_source_language", lambda text: {
        "language": "en", "detection": None, "provider_detection": None, "detected_by": "test",
    })
    quality = Mock(return_value={"passed": True, "semantic_verified": True})
    monkeypatch.setattr(pipeline, "_quality_check", quality)
    sleep, post = Mock(), Mock()
    monkeypatch.setattr(service.time, "sleep", sleep)
    monkeypatch.setattr(provider, "provider_post", post)
    return post, sleep, quality


def reply(status=200, *, cloudflare=False):
    text = "\u062e\u0628\u0631 \u062a\u0627\u0632\u0647 \u0645\u0646\u062a\u0634\u0631 \u0634\u062f."
    data = ({"success": True, "result": {"response": text}} if cloudflare else
            {"candidates": [{"content": {"parts": [{"text": text}]}}]})
    if status >= 400:
        data = {"error": {"message": "unavailable"}}
    return Mock(ok=status < 400, status_code=status, headers={}, json=lambda: data)


def run():
    return pipeline.run_translation_pipeline(
        text="The latest news was published.",
        policy=build_multilingual_policy(destination_language="fa", fail_closed=True),
    )


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429, 401, 403, 404])
def test_http_failure_tries_cloudflare_before_retrying_gemini(providers, status):
    post, sleep, quality = providers
    post.side_effect = [reply(status), reply(cloudflare=True)]
    result = run()
    assert result.success and not result.blocked
    assert result.output_text == reply(cloudflare=True).json()["result"]["response"]
    assert post.call_count == 2
    assert "generativelanguage.googleapis.com" in post.call_args_list[0].args[0]
    assert "api.cloudflare.com" in post.call_args_list[1].args[0]
    assert chain.provider_in_cooldown("gemini", provider.gemini_translation_provider)
    sleep.assert_not_called()
    quality.assert_called_once()


def test_success_does_not_call_fallback(providers):
    post, sleep, quality = providers
    post.return_value = reply()
    assert run().success
    post.assert_called_once()
    sleep.assert_not_called()
    quality.assert_called_once()


def test_invalid_request_stops_without_fallback(providers):
    post, sleep, quality = providers
    post.return_value = reply(400)
    result = run()
    assert result.blocked and result.output_text == ""
    assert result.metadata["provider_failure"]["category"] == "invalid_request"
    post.assert_called_once()
    sleep.assert_not_called()
    quality.assert_not_called()


def test_last_provider_retains_existing_retry_budget(providers):
    post, sleep, quality = providers
    post.side_effect = [reply(503), reply(503), reply(cloudflare=True)]
    assert run().success
    assert post.call_count == 3
    assert all("api.cloudflare.com" in call.args[0] for call in post.call_args_list[1:])
    sleep.assert_called_once_with(1)
    quality.assert_called_once()


def test_all_providers_fail_closed_without_restarting_gemini(providers):
    post, sleep, quality = providers
    post.return_value = reply(503)
    result = run()
    assert not result.success and result.blocked and not result.requires_review
    assert result.output_text == "" and result.attempts == 1
    assert result.metadata["provider_failure"]["provider"] == "cloudflare"
    assert post.call_count == 4  # Gemini once; final provider's existing three attempts.
    assert all("api.cloudflare.com" in call.args[0] for call in post.call_args_list[1:])
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    quality.assert_not_called()


@pytest.mark.parametrize("unavailable", ["disabled", "cooldown"])
def test_unavailable_fallback_preserves_single_provider_retries(providers, monkeypatch, unavailable):
    post, sleep, quality = providers
    provider.configure_default_translation_providers()
    if unavailable == "disabled":
        registry.register_translation_provider(
            name="cloudflare", provider=provider.cloudflare_translation_provider,
            priority=20, enabled=False, replace=True,
        )
        monkeypatch.setattr(provider, "configure_default_translation_providers", lambda: None)
    else:
        chain.mark_provider_cooldown("cloudflare", provider.TranslationProviderError(
            "transient_server", retryable=True,
        ), provider.cloudflare_translation_provider)
    post.side_effect = [reply(503), reply()]
    assert run().success
    assert post.call_count == 2
    assert all("generativelanguage.googleapis.com" in call.args[0] for call in post.call_args_list)
    sleep.assert_called_once_with(1)
    quality.assert_called_once()
