import pytest

from core.ai_summarizer_provider import (
    AISummarizerProviderError,
    DEFAULT_GEMINI_MODEL,
    build_generate_content_url,
    build_gemini_payload,
    extract_gemini_text,
    gemini_provider_configured,
    get_gemini_api_key,
    get_gemini_model,
    summarize_with_gemini,
)


# =========================================================
# TEST 01
# DEFAULT MODEL
# =========================================================

def test_default_model(
    monkeypatch
):

    monkeypatch.delenv(
        "GEMINI_SUMMARIZER_MODEL",
        raising=False
    )

    assert (
        get_gemini_model()
        == DEFAULT_GEMINI_MODEL
    )
    assert DEFAULT_GEMINI_MODEL == "gemini-3.5-flash-lite"


# =========================================================
# TEST 02
# ENV MODEL OVERRIDE
# =========================================================

def test_model_from_env(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_SUMMARIZER_MODEL",
        "custom-model"
    )

    assert (
        get_gemini_model()
        == "custom-model"
    )


# =========================================================
# TEST 03
# API KEY
# =========================================================

def test_api_key_from_env(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-key"
    )

    assert (
        get_gemini_api_key()
        == "test-key"
    )


# =========================================================
# TEST 04
# PROVIDER CONFIGURED
# =========================================================

def test_provider_configured(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-key"
    )

    assert (
        gemini_provider_configured()
        is True
    )


# =========================================================
# TEST 05
# PROVIDER NOT CONFIGURED
# =========================================================

def test_provider_not_configured(
    monkeypatch
):

    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False
    )

    assert (
        gemini_provider_configured()
        is False
    )


# =========================================================
# TEST 06
# URL
# =========================================================

def test_build_generate_content_url():

    url = (
        build_generate_content_url(
            "gemini-2.5-flash-lite"
        )
    )

    assert (
        "gemini-2.5-flash-lite"
        in url
    )

    assert (
        url.endswith(
            ":generateContent"
        )
    )


# =========================================================
# TEST 07
# PAYLOAD
# =========================================================

def test_build_payload():

    payload = (
        build_gemini_payload(
            original_text="متن اصلی خبر",
            instruction="فقط خلاصه کن",
            target_length=900
        )
    )

    assert (
        "contents"
        in payload
    )

    assert (
        payload[
            "contents"
        ][0][
            "parts"
        ][0][
            "text"
        ]
    )

    prompt = (
        payload[
            "contents"
        ][0][
            "parts"
        ][0][
            "text"
        ]
    )

    assert (
        "فقط خلاصه کن"
        in prompt
    )

    assert (
        "متن اصلی خبر"
        in prompt
    )

    assert (
        payload[
            "generationConfig"
        ][
            "temperature"
        ]
        == 0.1
    )


# =========================================================
# TEST 08
# RESPONSE EXTRACTION
# =========================================================

def test_extract_gemini_text():

    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "خلاصه امن خبر"
                            )
                        }
                    ]
                }
            }
        ]
    }

    result = (
        extract_gemini_text(
            data
        )
    )

    assert (
        result
        == "خلاصه امن خبر"
    )


# =========================================================
# TEST 09
# EMPTY CANDIDATES
# =========================================================

def test_extract_rejects_no_candidates():

    with pytest.raises(
        AISummarizerProviderError
    ):

        extract_gemini_text(
            {
                "candidates": []
            }
        )


# =========================================================
# TEST 10
# NO API KEY
# =========================================================

def test_summarize_without_api_key(
    monkeypatch
):

    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False
    )

    with pytest.raises(
        AISummarizerProviderError
    ):

        summarize_with_gemini(
            "متن خبر",
            "خلاصه کن",
            100
        )


# =========================================================
# TEST 11
# SUCCESSFUL REQUEST
# =========================================================

def test_successful_request(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "fake-key"
    )

    class FakeResponse:

        status_code = 200
        text = ""

        def json(
            self
        ):

            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "خلاصه معتبر"
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(
        *args,
        **kwargs
    ):

        return (
            FakeResponse()
        )

    monkeypatch.setattr(
        "core.ai_summarizer_provider.requests.post",
        fake_post
    )

    result = (
        summarize_with_gemini(
            "متن اصلی خبر طولانی است.",
            "بدون تحریف خلاصه کن.",
            100
        )
    )

    assert (
        result
        == "خلاصه معتبر"
    )


def test_gemini_35_flash_lite_override_uses_existing_contract(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "fake-key"
    )
    monkeypatch.setenv(
        "GEMINI_SUMMARIZER_MODEL",
        "gemini-3.5-flash-lite"
    )

    captured = {}

    class FakeResponse:

        status_code = 200
        text = ""

        def json(self):

            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "خلاصه معتبر"
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):

        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        "core.ai_summarizer_provider.requests.post",
        fake_post
    )

    result = summarize_with_gemini(
        "متن اصلی خبر طولانی است.",
        "بدون تحریف خلاصه کن.",
        100
    )

    assert result == "خلاصه معتبر"
    assert captured["url"].endswith(
        "/v1beta/models/gemini-3.5-flash-lite:generateContent"
    )
    assert captured["headers"]["x-goog-api-key"] == "fake-key"
    assert captured["json"]["contents"][0]["role"] == "user"


# =========================================================
# TEST 12
# HTTP ERROR
# =========================================================

def test_http_error(
    monkeypatch
):

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "fake-key"
    )

    class FakeResponse:

        status_code = 429
        text = (
            "rate limit"
        )

        def json(
            self
        ):

            return {}

    def fake_post(
        *args,
        **kwargs
    ):

        return (
            FakeResponse()
        )

    monkeypatch.setattr(
        "core.ai_summarizer_provider.requests.post",
        fake_post
    )

    with pytest.raises(
        AISummarizerProviderError
    ):

        summarize_with_gemini(
            "متن خبر",
            "خلاصه کن",
            100
        )
