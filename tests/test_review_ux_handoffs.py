from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import webhook_handler as webhook
from core import translation_controller as controller
from core import translation_state as states
from core import translation_telegram as telegram
from core import editorial_pending as pending
from core.translation_publication import build_translation_publication_payload
from core.external_content_model import NormalizedExternalContent, ExternalMedia
from core.external_review_controller import ExternalReviewController
from core.external_review_state import ExternalReviewStateStore
from core.external_review_telegram import handle_external_review_telegram_callback


@pytest.fixture(autouse=True)
def reset():
    pending.clear_pending_reviews()
    yield
    pending.clear_pending_reviews()


def test_edit_storage_render_and_payload(monkeypatch):
    edited = "پیش‌نمایش ترجمه\nمتن من با https://example.org/evidence در بدنه خبر."
    row = dict(review_id="12345678-review", chat_id=1, user_id=1, status="waiting_edit",
               original_text="Original", translated_text="Machine", edited_text="", metadata={}, target_language="fa")
    def update(rid, **kwargs):
        row.update({key: value for key, value in kwargs.items() if value is not None})
        return dict(row)
    monkeypatch.setattr(states, "_database", lambda: SimpleNamespace(update_persistent_translation_review=update))
    monkeypatch.setattr(states, "get_translation_state", lambda rid: states._state_from_row(row))
    monkeypatch.setattr(controller, "get_active_translation_state", lambda **kwargs: states._state_from_row(row))
    result = controller.submit_translation_edit(chat_id=1, user_id=1, translated_text=edited)
    assert result.success and row["status"] == "preview"
    assert row["original_text"] == "Original" and row["translated_text"] == "Machine"
    assert row["edited_text"] == edited
    send = Mock()
    telegram.render_translation_result(result=result, chat_id=1, send_message=send)
    text = send.call_args.args[1]
    assert "#12345678" in text and "متن اصلاح‌شده برای انتشار" in text
    assert "──────────\n" + edited + "\n──────────" in text
    assert "زبان مقصد:" not in text
    assert send.call_args.kwargs["link_preview_options"] == {"is_disabled": True}
    assert build_translation_publication_payload(result.state)["main_text"] == edited


def test_send_message_option_is_opt_in(monkeypatch):
    monkeypatch.setattr(webhook, "API_URL", "https://telegram.test")
    post = Mock(return_value=SimpleNamespace(status_code=200))
    monkeypatch.setattr(webhook.requests, "post", post)
    assert webhook.send_message(1, "https://example.org")
    assert "link_preview_options" not in post.call_args.kwargs["json"]
    assert webhook.send_message(1, "https://example.org", link_preview_options={"is_disabled": True})
    assert post.call_args.kwargs["json"]["link_preview_options"] == {"is_disabled": True}
    assert post.call_args.kwargs["json"]["text"] == "https://example.org"


@pytest.mark.parametrize("reason,count,phrase", [
    ("provider_error", 0, "سرویس خلاصه‌سازی موقتاً"),
    ("summarizer_unavailable", 0, "سرویس خلاصه‌سازی موقتاً"),
    ("validation_failed", 0, "خلاصه قابل‌اعتماد"),
    ("regeneration_failed", 1, "ساخت مجدد خلاصه"),
    ("regeneration_limit_reached", 3, "تلاش‌های خلاصه‌سازی"),
])
def test_safe_failure_messages(reason, count, phrase):
    keyboard = webhook.build_editorial_keyboard("review", has_summary=False,
        failure_reason=reason, regeneration_count=count)
    buttons = [button for row in keyboard["inline_keyboard"] for button in row]
    assert phrase in buttons[0]["text"]
    assert not any(button["callback_data"] == "ed:summary:review" for button in buttons)
    preview = webhook.build_editorial_preview("news_analysis", "original", 8,
        summary_success=False, failure_reason=reason, regeneration_count=count)
    assert phrase in preview and reason not in preview


def test_failed_summary_stale_callback_cannot_publish(monkeypatch):
    review = pending.create_pending_review(user_id=1, content_type="news_analysis",
        original_text="original", current_summary="failed candidate",
        metadata={"summary_success": False, "summary_failure_reason": "validation_failed"})
    publish = Mock()
    monkeypatch.setattr(webhook, "publish_prepared_text", publish)
    monkeypatch.setattr(webhook, "answer_callback_query", Mock())
    assert webhook.handle_editorial_callback({"id": "cb", "from": {"id": 1},
        "data": f"ed:summary:{review.review_id}"}, req_id="test")
    publish.assert_not_called()


def test_external_editorial_translation_metadata_chain(monkeypatch):
    import core.editorial_review as editorial
    forward = {"source_title": "Source News", "source_username": "SourceNews"}
    content = NormalizedExternalContent(source_type="web_article", content_type="article",
        source_url="https://source.example/article", canonical_url="https://source.example/canonical",
        title="عنوان خبر", lead="لید خبر", body="متن کامل خبر برای بررسی.", source_name="Source News",
        author="Author", published_at="2026-09-12", extraction_confidence=0.95,
        metadata={"forward_source": forward, "source_identity": "known"})
    external = ExternalReviewController(state_store=ExternalReviewStateStore())
    external.create_pending(review_id="external-review", chat_id=1, content=content)
    monkeypatch.setattr(webhook, "send_message", Mock(return_value=True))
    monkeypatch.setattr(webhook, "answer_callback_query", Mock())
    monkeypatch.setattr(editorial, "analyze_editorial_content", lambda original_text, **kwargs: SimpleNamespace(
        content_type="news_analysis", needs_approval=True, suggested_text=original_text,
        summary_success=False, reason="summary_unavailable", metadata={"summary_reason": "provider_error"}))
    queued = []
    def queue(**kwargs):
        queued.append(kwargs)
        return webhook.try_queue_editorial_text_review(**kwargs)
    assert handle_external_review_telegram_callback(
        callback_query={"id": "cb", "data": "extrev:editorial:external-review", "from": {"id": 1}},
        answer_callback_query=Mock(), send_message=Mock(), controller=external, queue_editorial_review=queue)
    assert queued and content.source_url not in queued[0]["text"]
    assert queued[0]["forward_source"] == forward
    records = pending.get_pending_reviews_for_user(1)
    assert len(records) == 1
    review = records[0]
    assert review.metadata["summary_failure_reason"] == "provider_error"
    start = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr(controller, "start_translation", start)
    monkeypatch.setattr(telegram, "render_translation_result", Mock())
    assert webhook.handle_editorial_callback({"id": "cb", "from": {"id": 1},
        "data": f"ed:translate:{review.review_id}"}, req_id="test")
    metadata = start.call_args.kwargs["metadata"]
    assert metadata["forward_source"] == forward
    for key in ("source_url", "canonical_url", "source_name", "author", "published_at"):
        assert metadata["source_metadata"][key] == getattr(content, key)
    assert metadata["source_metadata"]["metadata"] == content.metadata
    assert content.source_url not in start.call_args.kwargs["original_text"]
    body = "این پیوند https://evidence.example/doc در متن خبر است."
    state = states.TranslationState(review_id="translation", chat_id=1, user_id=1,
        original_text="source", translated_text=body + "\n\nhttps://source.example/article", metadata=metadata)
    assert build_translation_publication_payload(state)["main_text"] == body


def test_external_media_metadata_is_json_safe(monkeypatch):
    import json
    external = ExternalReviewController(state_store=ExternalReviewStateStore())
    content = NormalizedExternalContent(source_type="web_article", content_type="article",
        source_url="https://source.example/article", title="عنوان", body="متن خبر",
        metadata={"source_title": "Source", "nested": {"values": ["one"]}},
        media=(ExternalMedia(type="image", source_url="https://source.example/image.jpg",
                             width=640, metadata={"nested": {"values": ["photo"]}}),))
    external.create_pending(review_id="media-review", chat_id=1, content=content)
    queued = Mock(return_value=True)
    import core.external_media_factory as factory
    materializer = SimpleNamespace(build_prepared_files=Mock(return_value=[{"type": "photo", "file_id": "cached-photo"}]))
    monkeypatch.setattr(factory, "build_external_media_materializer", lambda **kwargs: materializer)
    assert handle_external_review_telegram_callback(
        callback_query={"id": "cb", "data": "extrev:editorial:media-review", "from": {"id": 1}},
        answer_callback_query=Mock(), send_message=Mock(), controller=external, queue_editorial_review=queued)
    metadata = queued.call_args.kwargs["source_metadata"]
    json.dumps(metadata)
    assert metadata["metadata"]["nested"]["values"] == ["one"]
    assert metadata["media"][0]["width"] == 640
    assert metadata["media"][0]["metadata"]["nested"]["values"] == ["photo"]
    assert queued.call_args.kwargs["forward_source"]["source_title"] == "Source"

