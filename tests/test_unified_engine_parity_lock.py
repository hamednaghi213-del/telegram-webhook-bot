"""Parity locks for the current unified publication architecture.

These tests deliberately exercise the existing preparation, entity, editorial,
planning, and fan-out functions.  They do not introduce a second test-only
content engine.
"""

from types import SimpleNamespace

import pytest

from core import publication_engine, webhook_handler
from core.caption_manager import analyze_content
from core.content_model import PreparedContent, PublicationTarget
from core.editorial_structure import extract_editorial_structure


SOURCE = {"title": "Source Channel", "username": "source_channel"}
SOURCE_FOOTER = "\n\n🔷 #N\n🔷 @source_channel"


def _utf16_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def _entity(text: str, kind: str, value: str, **extra):
    start = text.index(value)
    result = {
        "type": kind,
        "offset": _utf16_offset(text, start),
        "length": _utf16_offset(text, start + len(value)) - _utf16_offset(text, start),
    }
    result.update(extra)
    return result


def _prepared_from_text(text: str, entities=(), *, files=(), editorial=False):
    prepared = webhook_handler.prepare_text_content(text, list(entities), SOURCE)
    return PreparedContent(
        main_text=prepared["main_text"],
        neutral_text=prepared["neutral_text"],
        blockquote_blocks=prepared["blockquote_blocks"],
        expandable_blocks=prepared["expandable_blocks"],
        other_entities=prepared["other_entities"],
        files=files,
        editorial_finalized=editorial,
        source_key="parity:fixture",
    )


def _semantic_snapshot(prepared: PreparedContent, editorial_kind=None):
    structure = extract_editorial_structure(prepared.neutral_text or prepared.main_text)
    return {
        "content_type": editorial_kind or ("media" if prepared.files else "text"),
        "cleaned_source": prepared.neutral_text,
        "title": structure.title,
        "author": structure.author,
        "body": structure.body,
        "summary_state": "finalized" if prepared.editorial_finalized else "not_finalized",
        "editorial_state": prepared.editorial_finalized,
        "entities": tuple(dict(item) for item in prepared.other_entities),
        "blockquotes": tuple(dict(item) for item in prepared.blockquote_blocks),
        "expandable": tuple(dict(item) for item in prepared.expandable_blocks),
        "media": tuple((item.get("type"), item.get("file_id"), item.get("message_id")) for item in prepared.files),
        "semantic_content": prepared.neutral_text or prepared.main_text,
    }


@pytest.mark.parametrize(
    ("kind", "files", "editorial_kind"),
    [
        ("text", (), None),
        ("photo", ({"type": "photo", "file_id": "p1", "message_id": 1},), None),
        ("video", ({"type": "video", "file_id": "v1", "message_id": 1},), None),
        ("document", ({"type": "document", "file_id": "d1", "message_id": 1},), None),
        (
            "album",
            (
                {"type": "photo", "file_id": "a1", "message_id": 10},
                {"type": "video", "file_id": "a2", "message_id": 11},
            ),
            None,
        ),
        ("opinion", (), "opinion_note"),
        ("long_opinion", (), "opinion_note"),
        ("analysis", (), "news_analysis"),
    ],
)
def test_prepared_content_is_semantically_equal_before_target_branding(kind, files, editorial_kind):
    body = "تیتر نمونه\n\nنویسنده: خبرنگار نمونه\n\n" + ("بدنه خبر. " * (600 if kind == "long_opinion" else 4))
    tagged = ({"opinion_note": "#یادداشت\n", "news_analysis": "#تحلیل\n"}.get(editorial_kind, "") + body)
    # Tag removal belongs to the shared ingress/editorial stage, before either
    # Legacy or Workspace target resolution.
    detected, clean_text, _ = webhook_handler.detect_editorial_admin_tag(tagged)
    assert detected == editorial_kind
    legacy = _prepared_from_text(clean_text + SOURCE_FOOTER, files=files)
    workspace = _prepared_from_text(clean_text + SOURCE_FOOTER, files=files)

    assert _semantic_snapshot(legacy, detected) == _semantic_snapshot(workspace, detected)
    assert "@source_channel" not in legacy.neutral_text
    assert [item.get("message_id") for item in legacy.files] == [item.get("message_id") for item in files]


def test_entity_rich_input_has_identical_shared_interpretation():
    text = (
        "😀 bold italic link @member #topic 🪄\n"
        "normal quote\nexpandable quote" + SOURCE_FOOTER
    )
    entities = [
        _entity(text, "bold", "bold"),
        _entity(text, "italic", "italic"),
        _entity(text, "text_link", "link", url="https://example.test/item"),
        _entity(text, "mention", "@member"),
        _entity(text, "hashtag", "#topic"),
        _entity(text, "custom_emoji", "🪄", custom_emoji_id="emoji-1"),
        _entity(text, "blockquote", "normal quote"),
        _entity(text, "expandable_blockquote", "expandable quote"),
    ]

    legacy = _prepared_from_text(text, entities)
    workspace = _prepared_from_text(text, entities)

    assert _semantic_snapshot(legacy) == _semantic_snapshot(workspace)
    assert len(legacy.blockquote_blocks) == 1
    assert len(legacy.expandable_blocks) == 1
    assert {item["type"] for item in legacy.other_entities} >= {
        "bold", "italic", "text_link", "mention", "hashtag", "custom_emoji"
    }


def _capturing_plan(calls):
    def analyze_content(**kwargs):
        calls.append(kwargs)
        text = kwargs["main_text"]
        branding = kwargs["branding"]
        rendered = f"{text}\n\n{branding}" if branding else text
        return SimpleNamespace(
            telegram={"media_caption": rendered, "followup_messages": [], "blockquote_messages": []},
            bale={"media_caption": rendered, "followup_messages": [], "blockquote_messages": []},
            text={
                "telegram": {"messages": [rendered], "message_parse_modes": [None], "blockquote_messages": []},
                "bale": {"messages": [rendered], "message_parse_modes": [None], "blockquote_messages": []},
            },
        )
    return analyze_content


@pytest.mark.parametrize(
    "files",
    [
        (),
        ({"type": "photo", "file_id": "p"},),
        ({"type": "video", "file_id": "v"},),
        ({"type": "document", "file_id": "d"},),
        ({"type": "photo", "file_id": "a1"}, {"type": "photo", "file_id": "a2"}),
    ],
)
def test_equivalent_branding_produces_one_shared_publication_plan(monkeypatch, files):
    calls = []
    sends = []
    monkeypatch.setattr("core.caption_manager.analyze_content", _capturing_plan(calls))
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_: ("same base", "same brand"))
    monkeypatch.setattr(publication_engine, "_execute_delivery_part", lambda *_args: sends.append(_args[2].key) or {"ok": True, "result": {"message_id": len(sends)}})
    publication_engine.reset_local_idempotency_state()
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20),
    ]

    result = publication_engine.publish_prepared_content(
        1, "api", PreparedContent(main_text="same base", neutral_text="same base", files=files), targets
    )

    assert result["ok"] is True
    assert len(calls) == 1  # plan cache proves equivalent publication semantics
    assert calls[0]["main_text"] == "same base"
    assert calls[0]["branding"] == "same brand"
    assert sends == ["legacy", "workspace"]


@pytest.mark.parametrize(
    "scenario",
    ["text", "photo", "video", "document", "album", "long_note"],
)
def test_real_caption_manager_plan_is_equal_for_equivalent_target_settings(monkeypatch, scenario):
    monkeypatch.setenv("ENABLE_SMART_SUMMARIZER", "false")
    text = "متن پایه یکسان"
    if scenario == "long_note":
        text = "یادداشت بلند و یکسان. " * 300
    kwargs = {
        "main_text": text,
        "blockquote_blocks": [],
        "expandable_blocks": [],
        "other_entities": [],
        "branding": "#برند_یکسان\n@same_channel",
        "editorial_finalized": scenario == "long_note",
    }

    legacy_plan = analyze_content(**kwargs)
    workspace_plan = analyze_content(**kwargs)

    assert legacy_plan.telegram == workspace_plan.telegram
    assert legacy_plan.bale == workspace_plan.bale
    assert legacy_plan.text == workspace_plan.text


LONG_NOTE = (
    "#یادداشت\n"
    "آینده سیاست منطقه و ضرورت تصمیم‌گیری دقیق\n\n"
    "به قلم حامد محمدی\n\n"
    + "این یادداشت یک بند تحلیلی بلند و دارای زمینه، استدلال و نتیجه‌گیری است. " * 120
)


def test_test24_long_note_summary_is_shared_once_and_never_split(monkeypatch):
    kind, clean_text, _ = webhook_handler.detect_editorial_admin_tag(LONG_NOTE)
    assert kind == "opinion_note"
    structure = extract_editorial_structure(clean_text)
    assert structure.title
    assert structure.author == "حامد محمدی"
    calls = []
    sends = []

    def planner(**kwargs):
        calls.append(kwargs)
        if kwargs["branding"] == "":
            message = "خلاصه واحد و معتبر یادداشت"
        else:
            message = kwargs["main_text"]
        return SimpleNamespace(
            telegram={}, bale={},
            text={
                "telegram": {"messages": [message], "message_parse_modes": [None], "blockquote_messages": []},
                "bale": {"messages": [message], "message_parse_modes": [None], "blockquote_messages": []},
            },
        )

    monkeypatch.setattr("core.caption_manager.analyze_content", planner)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_: ("خلاصه واحد و معتبر یادداشت", "برند مقصد"))
    monkeypatch.setattr(publication_engine, "_execute_delivery_part", lambda *_args: sends.append(_args[2].key) or {"ok": True, "result": {"message_id": len(sends)}})
    publication_engine.reset_local_idempotency_state()
    prepared = _prepared_from_text(clean_text, editorial=True)
    prepared = PreparedContent(
        main_text=prepared.main_text,
        neutral_text=prepared.neutral_text,
        other_entities=prepared.other_entities,
        editorial_finalized=True,
        require_single_message=True,
        source_key="test24:long-note:success",
    )
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20),
    ]

    result = publication_engine.publish_prepared_content(1, "api", prepared, targets)

    assert result["ok"] is True
    assert len([call for call in calls if call["branding"] == ""]) == 1
    assert sends == ["legacy", "workspace"]
    assert all(item.followup_message_ids == () for item in result["results"])


def test_test24_long_note_provider_unavailable_is_identical_and_side_effect_free(monkeypatch):
    _kind, clean_text, _ = webhook_handler.detect_editorial_admin_tag(LONG_NOTE)
    calls = []
    side_effects = []
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            telegram={}, bale={},
            text={
                "telegram": {"messages": ["part 1", "part 2", "part 3"]},
                "bale": {"messages": ["part 1", "part 2", "part 3"]},
            },
        ),
    )
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_: side_effects.append("target") or ("x", "y"))
    monkeypatch.setattr(publication_engine, "_execute_delivery_part", lambda *_: side_effects.append("send") or True)
    publication_engine.reset_local_idempotency_state()
    prepared = PreparedContent(
        main_text=clean_text,
        neutral_text=clean_text,
        editorial_finalized=True,
        require_single_message=True,
        source_key="test24:long-note:provider-unavailable",
    )
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20),
    ]

    result = publication_engine.publish_prepared_content(1, "api", prepared, targets)

    assert result == {"ok": False, "results": [], "errors": ["editorial_summary_unavailable"]}
    assert len(calls) == 1
    assert side_effects == []
