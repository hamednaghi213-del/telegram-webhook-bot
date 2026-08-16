import json
import logging
import os

from typing import (
    Any,
    Dict,
    Optional,
)

import requests


logger = logging.getLogger(__name__)


# =========================================================
# GEMINI PROVIDER CONFIG
# =========================================================

DEFAULT_GEMINI_MODEL = (
    "gemini-2.5-flash-lite"
)

DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 45


# =========================================================
# EXCEPTIONS
# =========================================================

class AISummarizerProviderError(
    RuntimeError
):
    pass


# =========================================================
# ENV HELPERS
# =========================================================

def get_gemini_api_key() -> str:

    value = (
        os.getenv(
            "GEMINI_API_KEY",
            ""
        )
        or ""
    ).strip()

    return value


def get_gemini_model() -> str:

    value = (
        os.getenv(
            "GEMINI_SUMMARIZER_MODEL",
            ""
        )
        or ""
    ).strip()

    if value:
        return value

    return DEFAULT_GEMINI_MODEL


# =========================================================
# PROVIDER AVAILABILITY
# =========================================================

def gemini_provider_configured() -> bool:

    return bool(
        get_gemini_api_key()
    )


# =========================================================
# REQUEST URL
# =========================================================

def build_generate_content_url(
    model: Optional[str] = None
) -> str:

    selected_model = (
        model
        or get_gemini_model()
    ).strip()

    if not selected_model:

        selected_model = (
            DEFAULT_GEMINI_MODEL
        )

    return (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{selected_model}:generateContent"
    )


# =========================================================
# PAYLOAD
# =========================================================

def build_gemini_payload(
    original_text: str,
    instruction: str,
    target_length: int
) -> Dict[str, Any]:

    original_text = (
        str(
            original_text
            or ""
        )
    )

    instruction = (
        str(
            instruction
            or ""
        )
    )

    prompt = (
        instruction
        + "\n\n"
        + "متن اصلی خبر:\n"
        + original_text
    )

    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": (
                max(
                    256,
                    min(
                        2048,
                        target_length
                        * 2
                    )
                )
            )
        }
    }


# =========================================================
# RESPONSE EXTRACTION
# =========================================================

def extract_gemini_text(
    data: Dict[str, Any]
) -> str:

    if not isinstance(
        data,
        dict
    ):

        raise AISummarizerProviderError(
            "invalid_response_type"
        )

    candidates = (
        data.get(
            "candidates"
        )
        or []
    )

    if not candidates:

        raise AISummarizerProviderError(
            "no_candidates"
        )

    first_candidate = (
        candidates[0]
    )

    if not isinstance(
        first_candidate,
        dict
    ):

        raise AISummarizerProviderError(
            "invalid_candidate"
        )

    content = (
        first_candidate.get(
            "content"
        )
        or {}
    )

    parts = (
        content.get(
            "parts"
        )
        or []
    )

    if not parts:

        raise AISummarizerProviderError(
            "no_parts"
        )

    text_parts = []

    for part in parts:

        if not isinstance(
            part,
            dict
        ):
            continue

        value = (
            part.get(
                "text"
            )
        )

        if value:

            text_parts.append(
                str(
                    value
                )
            )

    result = (
        "\n".join(
            text_parts
        )
        .strip()
    )

    if not result:

        raise AISummarizerProviderError(
            "empty_text_response"
        )

    return result


# =========================================================
# GEMINI SUMMARIZER
#
# Signature دقیقاً با smart_summarizer سازگار است:
#
# summarizer(
#     original_text,
#     instruction,
#     target_length
# )
# =========================================================

def summarize_with_gemini(
    original_text: str,
    instruction: str,
    target_length: int
) -> str:

    api_key = (
        get_gemini_api_key()
    )

    if not api_key:

        raise AISummarizerProviderError(
            "GEMINI_API_KEY is not configured"
        )

    model = (
        get_gemini_model()
    )

    url = (
        build_generate_content_url(
            model
        )
    )

    payload = (
        build_gemini_payload(
            original_text=original_text,
            instruction=instruction,
            target_length=target_length
        )
    )

    headers = {
        "Content-Type": (
            "application/json"
        ),
        "x-goog-api-key": (
            api_key
        )
    }

    logger.info(
        f"🤖 Gemini summarizer request | "
        f"model={model} | "
        f"input_length="
        f"{len(original_text or '')} | "
        f"target={target_length}"
    )

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=(
                DEFAULT_CONNECT_TIMEOUT,
                DEFAULT_READ_TIMEOUT
            )
        )

    except requests.exceptions.Timeout as e:

        raise AISummarizerProviderError(
            f"gemini_timeout: {e}"
        ) from e

    except requests.exceptions.ConnectionError as e:

        raise AISummarizerProviderError(
            f"gemini_connection_error: {e}"
        ) from e

    except requests.exceptions.RequestException as e:

        raise AISummarizerProviderError(
            f"gemini_request_error: {e}"
        ) from e

    if response.status_code != 200:

        body_preview = (
            response.text[:1500]
            if response.text
            else ""
        )

        logger.error(
            f"❌ Gemini HTTP error | "
            f"status={response.status_code} | "
            f"body={body_preview}"
        )

        raise AISummarizerProviderError(
            "gemini_http_error_"
            f"{response.status_code}"
        )

    try:

        data = (
            response.json()
        )

    except json.JSONDecodeError as e:

        raise AISummarizerProviderError(
            "gemini_invalid_json"
        ) from e

    except Exception as e:

        raise AISummarizerProviderError(
            f"gemini_json_error: {e}"
        ) from e

    result = (
        extract_gemini_text(
            data
        )
    )

    logger.info(
        f"✅ Gemini summarizer response | "
        f"model={model} | "
        f"output_length={len(result)}"
    )

    return result
