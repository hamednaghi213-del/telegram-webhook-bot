"""Transport-qualified Bale media references and the Bale file resolver.

The reference is JSON-safe so pending editorial items and album members can be
stored and retried without persisting temporary files or large byte strings.
"""

import os
from pathlib import PurePosixPath
from urllib.parse import quote

import requests


BALE_MEDIA_PREFIX = "bale-file://"
BALE_API_BASE = "https://tapi.bale.ai/bot"
BALE_FILE_BASE = "https://tapi.bale.ai/file/bot"


def bale_media_ref(file_id):
    """Mark an inbound file ID as Bale-owned before shared processing."""
    value = str(file_id or "")
    return value if value.startswith(BALE_MEDIA_PREFIX) else BALE_MEDIA_PREFIX + value


def is_bale_media_ref(value):
    return isinstance(value, str) and value.startswith(BALE_MEDIA_PREFIX)


def bale_file_id(value):
    return value[len(BALE_MEDIA_PREFIX):] if is_bale_media_ref(value) else None


def download_bale_media(value, *, token=None):
    """Resolve a Bale-owned reference to uploadable bytes and a safe name.

    Bale's getFile path is only used with the inbound bot token. Never pass a
    Bale file ID to Telegram's getFile endpoint.
    """
    file_id = bale_file_id(value)
    bot_token = token or os.getenv("BALE_BOT_TOKEN")
    if not file_id or not bot_token:
        return None, None
    try:
        metadata = requests.get(
            f"{BALE_API_BASE}{bot_token}/getFile",
            params={"file_id": file_id},
            timeout=30,
        )
        metadata.raise_for_status()
        data = metadata.json()
        path = (data.get("result") or {}).get("file_path") if data.get("ok") else None
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
            return None, None
        response = requests.get(
            f"{BALE_FILE_BASE}{bot_token}/{quote(path, safe='/')}",
            timeout=120,
        )
        response.raise_for_status()
        return response.content, PurePosixPath(path).name or "bale-media"
    except (requests.RequestException, ValueError, TypeError):
        return None, None
