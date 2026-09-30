"""X publication adapter. OAuth lifecycle remains owned by core.x_oauth."""
import mimetypes
import time
from html.parser import HTMLParser

import requests

from core.content_model import ExecutorResult

API = "https://api.x.com/2"
UNKNOWN = "x_delivery_unknown: inspect the X account before retrying"
MAX_VIDEO_BYTES = 512 * 1024 * 1024


class XPublicationError(Exception):
    def __init__(self, message, status=None, uncertain=False):
        super().__init__(message)
        self.status = status
        self.uncertain = uncertain


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")
        if tag == "a":
            self.links.append((dict(attrs).get("href", ""), len(self.parts)))

    def handle_endtag(self, tag):
        if tag == "a" and self.links:
            url, start = self.links.pop()
            label = "".join(self.parts[start:])
            if url.startswith(("https://", "http://")) and url != label:
                self.parts.append(" (" + url + ")")
        if tag in {"p", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(text, mode=None):
    if mode != "HTML":
        return str(text or "")
    parser = _PlainHTML()
    parser.feed(str(text or ""))
    parser.close()
    return "".join(parser.parts).strip()


def build_x_plan(plan, entities=()):
    """Reuse the established caption/entity plan, flattening unsupported styling."""
    # The full text plan also carries a media item's caption, quotes and links.
    # Telegram's media plan may be empty for finalized editorial content or
    # may contain a shortened caption; never use that shortened form for X.
    source = plan.text["telegram"]
    modes = source.get("message_parse_modes") or []
    chunks = [plain_text(item, modes[i] if i < len(modes) else None)
              for i, item in enumerate(source.get("messages") or [])]
    chunks.extend(plain_text(item, "HTML") for item in source.get("blockquote_messages", ()))
    text = "\n\n".join(chunk for chunk in chunks if chunk.strip())
    from core.caption_manager import remap_preserved_entities
    from core.content_entities import utf16_to_python_index
    links = remap_preserved_entities(text, [
        dict(entity) for entity in entities if entity.get("type") == "text_link"
    ])
    for entity in sorted(links, key=lambda item: item["offset"], reverse=True):
        url = str(entity.get("url") or "")
        if url.startswith(("http://", "https://")) and url not in text:
            end = utf16_to_python_index(text, entity["offset"] + entity["length"])
            text = text[:end] + " (" + url + ")" + text[end:]
    return {"x_text": text}



class XClient:
    def __init__(self, destination_id):
        from core.x_oauth import get_valid_x_access_token
        self.destination_id = destination_id
        self.token = get_valid_x_access_token(destination_id)
        self.refreshed = False

    def request(self, method, path, *, publishing=False, **kwargs):
        # Never log response bodies or request exceptions: they can contain secrets.
        for attempt in range(3):
            try:
                response = requests.request(
                    method, API + path,
                    headers={"Authorization": "Bearer " + self.token},
                    timeout=(10, 60), allow_redirects=False, **kwargs,
                )
            except requests.RequestException:
                raise XPublicationError(
                    UNKNOWN if publishing else "x_media_transport_failed",
                    uncertain=publishing,
                ) from None
            status = response.status_code
            if status == 401 and not self.refreshed:
                from core.x_oauth import refresh_x_oauth_connection
                self.refreshed = True
                self.token = refresh_x_oauth_connection(self.destination_id).access_token
                continue
            if status == 401:
                from core.database import update_x_oauth_connection_status
                update_x_oauth_connection_status(
                    self.destination_id, "reconnect_required",
                    last_error="X publication authentication rejected",
                )
            # A create-post 5xx may follow a committed write; never replay it.
            if publishing and status >= 500:
                raise XPublicationError(UNKNOWN, status, uncertain=True)
            if status == 429 or (status >= 500 and not publishing):
                delay = 2 ** attempt
                try:
                    delay = max(delay, float(response.headers.get("Retry-After", 0)),
                                float(response.headers.get("x-rate-limit-reset", 0)) - time.time())
                except (TypeError, ValueError):
                    pass
                if attempt < 2 and delay <= 5:
                    time.sleep(max(0, delay))
                    continue
                raise XPublicationError("x_rate_limited" if status == 429 else "x_media_unavailable", status)
            if not 200 <= status < 300:
                raise XPublicationError("x_http_" + str(status), status)
            if status == 204:
                return {}
            try:
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError()
                return body
            except ValueError:
                raise XPublicationError(
                    UNKNOWN if publishing else "x_invalid_media_response",
                    status, uncertain=publishing,
                ) from None
        raise XPublicationError("x_request_retry_exhausted")


def _media_spec(content, filename):
    mime = mimetypes.guess_type(filename or "")[0]
    if content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        mime = "image/webp"
    elif content[4:8] == b"ftyp":
        mime = "video/mp4"
    if mime in {"image/jpeg", "image/png", "image/webp"}:
        category, limit = "tweet_image", 5 * 1024 * 1024
    elif mime == "image/gif":
        category, limit = "tweet_gif", 15 * 1024 * 1024
    elif mime == "video/mp4":
        category, limit = "tweet_video", MAX_VIDEO_BYTES
    else:
        raise XPublicationError("x_unsupported_media")
    if len(content) > limit:
        raise XPublicationError("x_media_too_large")
    return mime, category


def download_media(file_id):
    from core.bale_media import is_bale_media_ref, download_bale_media
    if is_bale_media_ref(file_id):
        return download_bale_media(file_id)
    from core.bale_forwarder import download_file_from_telegram
    return download_file_from_telegram(file_id)


def upload_media(client, content, filename, mime, category):
    data = client.request("POST", "/media/upload/initialize", json={
        "total_bytes": len(content), "media_type": mime, "media_category": category,
    }).get("data") or {}
    media_id = str(data.get("id") or "")
    if not media_id.isdigit():
        raise XPublicationError("x_missing_media_id")
    chunk_size = 4 * 1024 * 1024
    for index, start in enumerate(range(0, len(content), chunk_size)):
        client.request("POST", "/media/upload/" + media_id + "/append",
                       data={"segment_index": str(index)},
                       files={"media": (filename, content[start:start + chunk_size], mime)})
    data = client.request("POST", "/media/upload/" + media_id + "/finalize").get("data") or {}
    if not data:
        raise XPublicationError("x_invalid_media_response")
    if not data.get("processing_info"):
        if str(data.get("id") or "") != media_id:
            raise XPublicationError("x_missing_media_id")
        return media_id
    for _ in range(12):
        info = data.get("processing_info") or {}
        if info.get("state") == "succeeded":
            return media_id
        if info.get("state") == "failed":
            raise XPublicationError("x_media_processing_failed")
        if info.get("state") not in {"pending", "in_progress"}:
            raise XPublicationError("x_invalid_media_processing_state")
        delay = max(1, float(info.get("check_after_secs") or 1))
        if delay > 5:
            raise XPublicationError("x_media_processing_pending")
        time.sleep(delay)
        data = client.request("GET", "/media/upload",
                              params={"command": "STATUS", "media_id": media_id}).get("data") or {}
    raise XPublicationError("x_media_processing_pending")


def publish_x(target, text, files, before_send, release_send):
    """Create one post; the engine owns destination claims and success persistence."""
    from core.x_oauth import XOAuthRefreshError
    armed = False
    try:
        from core.database import get_x_oauth_connection
        if target.kind != "workspace" or target.destination_id is None:
            raise XPublicationError("x_workspace_destination_required")
        connection = get_x_oauth_connection(target.destination_id) or {}
        if connection.get("connection_status") != "connected":
            raise XPublicationError("x_reconnect_required")
        account = str(connection.get("x_user_id") or "")
        # The existing OAuth callback stores destinations as x:<immutable user ID>.
        # A changed username must not break publishing or select another account.
        if not account or str(target.external_id).strip() != "x:" + account:
            raise XPublicationError("x_destination_account_mismatch")
        scopes = set(connection.get("granted_scopes") or [])
        required = {"tweet.write"} | ({"media.write"} if files else set())
        if not required.issubset(scopes):
            raise XPublicationError("x_missing_scope: reconnect X with publication permissions")
        if not text.strip() and not files:
            raise XPublicationError("x_empty_post")
        if len(files) > 4:
            raise XPublicationError("x_too_many_media")
        if any(item.get("type") not in {"photo", "video", "animation", "document"} for item in files):
            raise XPublicationError("x_unsupported_media")
        media = []
        for item in files:
            content, filename = download_media(item.get("file_id"))
            if not content:
                raise XPublicationError("x_media_download_failed")
            mime, category = _media_spec(content, filename)
            media.append((content, filename or "media", mime, category))
        if len(media) > 1 and any(item[3] != "tweet_image" for item in media):
            raise XPublicationError("x_invalid_media_combination")
        client = XClient(target.destination_id)
        ids = [upload_media(client, *item) for item in media]
        payload = {}
        if text.strip():
            payload["text"] = text
        if ids:
            payload["media"] = {"media_ids": ids}
        if not before_send():
            raise XPublicationError(UNKNOWN, uncertain=True)
        armed = True
        body = client.request("POST", "/tweets", publishing=True, json=payload)
        post_id = str((body.get("data") or {}).get("id") or "")
        if not post_id.isdigit() or int(post_id) <= 0:
            raise XPublicationError(UNKNOWN, uncertain=True)
        return ExecutorResult(True, int(post_id), (int(post_id),),
                              raw_result={"chat_id": account, "message_url": "https://x.com/i/status/" + post_id},
                              operation="x_create_post")
    except XPublicationError as exc:
        if armed and not exc.uncertain:
            release_send()
        return ExecutorResult(False, status_code=exc.status, error=str(exc), operation="x_create_post")
    except XOAuthRefreshError as exc:
        if armed:
            release_send()  # Refresh is attempted only after an explicit 401 rejection.
        return ExecutorResult(False, error="x_reconnect_required" if exc.reconnect_required else "x_refresh_failed",
                              operation="x_create_post")
    except Exception:
        # Keep an armed marker if an unexpected exception followed a possible write.
        return ExecutorResult(False, error=UNKNOWN if armed else "x_publication_setup_failed",
                              operation="x_create_post")
