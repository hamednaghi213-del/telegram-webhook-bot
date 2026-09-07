"""Factory for configured external-media materialization."""

from __future__ import annotations

import os

from typing import Optional

from core.external_fetcher import (
    FetchPolicy,
    SafeExternalFetcher,
)
from core.external_media_materializer import (
    ExternalMediaAcquirer,
    ExternalMediaMaterializer,
)
from core.telegram_external_media_materializer import (
    TelegramExternalMediaMaterializer,
)

# =========================================================
# DEFAULT LIMITS
# =========================================================

DEFAULT_EXTERNAL_MEDIA_MAX_BYTES = (
    25 * 1024 * 1024
)

# =========================================================
# ENVIRONMENT
# =========================================================

EXTERNAL_MEDIA_STAGING_CHAT_ID_ENV = (
    "EXTERNAL_MEDIA_STAGING_CHAT_ID"
)

# =========================================================
# FACTORY
# =========================================================

def build_external_media_materializer(
    *,
    api_url: str,
    staging_chat_id: Optional[str] = None,
    max_bytes: int = (
        DEFAULT_EXTERNAL_MEDIA_MAX_BYTES
    ),
    timeout_seconds: int = 300,
    fetcher: Optional[
        SafeExternalFetcher
    ] = None,
    telegram_session=None,
) -> ExternalMediaMaterializer:
    """
    Build the production external-media materialization pipeline.

    Flow:
        ExternalMedia
        -> SafeExternalFetcher
        -> ExternalMediaAcquirer
        -> Telegram staging transport
        -> reusable Telegram file_id
        -> PreparedContent.files

    This factory does not publish anything to a destination.

    staging_chat_id resolution:
        1. explicit argument
        2. EXTERNAL_MEDIA_STAGING_CHAT_ID environment variable
    """

    normalized_api_url = str(
        api_url
        or ""
    ).strip()

    if not normalized_api_url:
        raise ValueError(
            "api_url is required"
        )

    # =====================================================
    # STAGING CHAT
    # =====================================================

    resolved_staging_chat_id = str(
        staging_chat_id
        or os.getenv(
            EXTERNAL_MEDIA_STAGING_CHAT_ID_ENV,
            "",
        )
        or ""
    ).strip()

    if not resolved_staging_chat_id:
        raise ValueError(
            "external media staging chat is not configured"
        )

    # =====================================================
    # LIMITS
    # =====================================================

    resolved_max_bytes = int(
        max_bytes
    )

    if resolved_max_bytes <= 0:
        raise ValueError(
            "max_bytes must be > 0"
        )

    resolved_timeout = int(
        timeout_seconds
    )

    if resolved_timeout <= 0:
        raise ValueError(
            "timeout_seconds must be > 0"
        )

    # =====================================================
    # FETCHER
    # =====================================================

    if fetcher is None:
        fetcher = SafeExternalFetcher(
            policy=FetchPolicy(
                max_bytes=(
                    resolved_max_bytes
                )
            )
        )

    # =====================================================
    # ACQUIRER
    # =====================================================

    acquirer = ExternalMediaAcquirer(
        fetcher=fetcher,
        max_bytes=resolved_max_bytes,
    )

    # =====================================================
    # TELEGRAM STAGING TRANSPORT
    # =====================================================

    telegram_transport = (
        TelegramExternalMediaMaterializer(
            api_url=normalized_api_url,
            staging_chat_id=(
                resolved_staging_chat_id
            ),
            timeout_seconds=(
                resolved_timeout
            ),
            session=telegram_session,
        )
    )

    # =====================================================
    # MATERIALIZER
    # =====================================================

    return ExternalMediaMaterializer(
        acquirer=acquirer,
        transports=(
            telegram_transport,
        ),
    )
