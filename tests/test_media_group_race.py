from core import media_handler


def setup_function():
    with media_handler.group_lock:
        media_handler.pending_groups.clear()
        media_handler.group_timers.clear()


def test_members_are_unique_by_message_id_and_ordered():
    for message_id in (3, 1, 2, 2):
        media_handler.add_to_pending_group(
            "g", 9, f"file-{message_id}", "photo", message_id=message_id
        )
    group = media_handler.pending_groups[(9, "g")]
    assert [item["message_id"] for item in group["files"]] == [1, 2, 3]
    assert group["generation"] == 3


def test_stale_generation_never_publishes(monkeypatch):
    media_handler.add_to_pending_group("g", 9, "a", "photo", message_id=1)
    media_handler.add_to_pending_group("g", 9, "b", "photo", message_id=2)
    published = []
    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: published.append(1) or {"ok": True},
    )

    assert media_handler.process_media_group("g", 9, expected_generation=1) is False
    assert published == []
    assert (9, "g") in media_handler.pending_groups


def test_failed_publication_keeps_group_for_retry(monkeypatch):
    media_handler.API_URL = "api"
    media_handler.add_to_pending_group("g", 9, "a", "photo", message_id=1)
    media_handler.add_to_pending_group("g", 9, "b", "photo", message_id=2)
    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: {"ok": False},
    )
    monkeypatch.setattr(media_handler, "schedule_processing", lambda *_args, **_kwargs: None)

    assert media_handler.process_media_group("g", 9, expected_generation=2) is False
    assert (9, "g") in media_handler.pending_groups
    assert media_handler.pending_groups[(9, "g")]["is_processing"] is False

