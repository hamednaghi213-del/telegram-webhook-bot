from types import SimpleNamespace

import pytest

from core import publication_engine
from core.content_model import PreparedContent, PublicationTarget
from core.publication_state import InMemoryPublicationStateStore


def _media_plan(media_type="photo"):
    return SimpleNamespace(
        telegram={
            "media_caption": "<b>تیتر</b>\nمتن نهایی",
            "media_parse_mode": "HTML",
            "media_caption_entities": [],
            "followup_messages": [],
            "blockquote_messages": ["<blockquote expandable>ادامه</blockquote>"],
            "document_fallback": False,
        },
        bale={"media_caption": "متن", "followup_messages": [], "blockquote_messages": []},
        text={"telegram": {"messages": []}, "bale": {"messages": []}},
    )


def test_expandable_content_participates_in_shared_summary_capacity(monkeypatch):
    calls = []

    def analyze(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            telegram={
                "media_caption": "خلاصه",
                "followup_messages": [],
                "blockquote_messages": [],
                "_semantic_summary": {
                    "main_text": "خلاصه",
                    "blockquote_blocks": [],
                    "expandable_blocks": [],
                },
            },
            bale={}, text={"telegram": {"messages": ["خلاصه"]}},
        )

    monkeypatch.setattr("core.caption_manager.analyze_content", analyze)
    prepared = PreparedContent(
        main_text="کوتاه",
        neutral_text="کوتاه",
        expandable_blocks=[{"type": "expandable_blockquote", "text": "ب" * 1200}],
        files=[{"type": "photo", "file_id": "p"}],
    )

    analyzed = publication_engine._shared_content_analysis(prepared)

    assert len(calls) == 1
    assert calls[0]["main_text"] == "کوتاه"
    assert len(calls[0]["expandable_blocks"][0]["text"]) == 1200
    assert analyzed.main_text == "خلاصه"


def test_rendered_expandable_html_never_reenters_prepared_content(monkeypatch):
    rendered = "<blockquote expandable>" + ("متن فارسی 😀 " * 90) + "</blockquote>"

    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_: SimpleNamespace(
            telegram={
                "media_caption": rendered[:1019],
                "media_parse_mode": "HTML",
                "media_caption_entities": [],
                "followup_messages": [],
                "blockquote_messages": [rendered],
            },
            bale={},
            text={"telegram": {"messages": []}},
        ),
    )
    prepared = PreparedContent(
        main_text="تیتر کوتاه",
        neutral_text="تیتر کوتاه",
        expandable_blocks=[{
            "type": "expandable_blockquote",
            "text": "متن فارسی 😀 " * 90,
        }],
        files=[{"type": "photo", "file_id": "p"}],
    )

    analyzed = publication_engine._shared_content_analysis(prepared)

    assert analyzed is prepared
    assert "<blockquote" not in analyzed.main_text
    assert len(analyzed.expandable_blocks) == 1


def test_semantic_summary_replaces_blocks_without_html_leak(monkeypatch):
    calls = []

    def analyze(**kwargs):
        calls.append(kwargs)
        if kwargs["branding"] == "":
            return SimpleNamespace(
                telegram={
                    "media_caption": "خلاصه\n\nنقل‌قول کوتاه",
                    "media_parse_mode": None,
                    "media_caption_entities": [{"type": "expandable_blockquote", "offset": 8, "length": 15}],
                    "followup_messages": [],
                    "blockquote_messages": [],
                    "_semantic_summary": {
                        "main_text": "خلاصه",
                        "blockquote_blocks": [],
                        "expandable_blocks": [{
                            "type": "expandable_blockquote",
                            "text": "نقل‌قول کوتاه",
                        }],
                    },
                },
                bale={},
                text={"telegram": {"messages": []}},
            )
        return _media_plan()

    monkeypatch.setattr("core.caption_manager.analyze_content", analyze)
    prepared = PreparedContent(
        main_text="تیتر کوتاه",
        neutral_text="تیتر کوتاه",
        expandable_blocks=[{
            "type": "expandable_blockquote",
            "text": "متن فارسی 😀 " * 90,
        }],
        files=[{"type": "photo", "file_id": "p"}],
    )

    analyzed = publication_engine._shared_content_analysis(prepared)

    assert len(calls) == 1
    assert analyzed.main_text == "خلاصه"
    assert analyzed.expandable_blocks[0]["text"] == "نقل‌قول کوتاه"
    assert "<blockquote" not in analyzed.main_text


def test_real_one_message_policy_preserves_main_and_adapts_expandable_once(monkeypatch):
    calls = []

    monkeypatch.setenv("ENABLE_SMART_SUMMARIZER", "true")
    monkeypatch.setattr("core.caption_manager.gemini_provider_configured", lambda: True)

    def summarize_text_safely(**kwargs):
        calls.append(kwargs)
        assert kwargs["original_text"] == "ب" * 1021
        assert kwargs["target_length"] == 651
        return SimpleNamespace(
            success=True,
            summary_text="ب" * 620,
            metadata={"content_type": "normal_news"},
        )

    monkeypatch.setattr(
        "core.caption_manager.summarize_text_safely",
        summarize_text_safely,
    )

    from core.caption_manager import try_smart_telegram_media_summary

    plan = try_smart_telegram_media_summary(
        main_text="م" * 371,
        blockquote_blocks=[],
        expandable_blocks=[{
            "type": "expandable_blockquote",
            "text": "ب" * 1021,
        }],
        branding="",
        caption_limit=1024,
    )

    assert len(calls) == 1
    assert plan is not None
    assert plan["followup_messages"] == []
    assert plan["blockquote_messages"] == []
    assert len(plan["media_caption"]) <= 1024
    assert "<blockquote" not in plan["media_caption"]
    assert any(
        entity["type"] == "expandable_blockquote"
        for entity in plan["media_caption_entities"]
    )
    semantic = plan["_semantic_summary"]
    assert semantic["main_text"] == "م" * 371
    assert semantic["expandable_blocks"][0]["text"] == "ب" * 620


@pytest.mark.parametrize("media_type", ["photo", "video", "document"])
@pytest.mark.parametrize("kind", ["legacy", "workspace"])
def test_single_media_uses_stable_plan_executor(monkeypatch, media_type, kind):
    calls = []
    monkeypatch.setattr(
        "core.workspace_publisher._send_media_to_destination",
        lambda *_args, **_kwargs: pytest.fail("raw Workspace sender bypassed PublicationPlan"),
    )
    monkeypatch.setattr(
        "core.media_handler.execute_telegram_plan",
        lambda files, plan, **kwargs: calls.append((files, plan, kwargs)) or {
            "ok": True, "message_id": 71, "status_code": 200,
            "operation": {"photo": "sendPhoto", "video": "sendVideo", "document": "sendDocument"}[media_type],
        },
    )
    target = PublicationTarget(
        kind, kind, "telegram", "@destination",
        1 if kind == "workspace" else None,
        2 if kind == "workspace" else None,
    )

    result = publication_engine._send_media_target(
        9, "api", target, [{"type": media_type, "file_id": "f"}], _media_plan(media_type).telegram
    )

    assert result.success is True
    assert result.primary_message_id == 71
    assert len(calls) == 1
    assert calls[0][1]["media_parse_mode"] == "HTML"
    assert calls[0][1]["blockquote_messages"]
    assert calls[0][2]["return_result"] is True
    assert calls[0][2]["channel_id"] == (None if kind == "legacy" else "@destination")


def test_telegram_400_details_reach_delivery_result(monkeypatch):
    target = PublicationTarget("workspace", "workspace", "telegram", "@destination", 1, 2)
    monkeypatch.setattr(publication_engine, "_shared_content_analysis", lambda prepared: prepared)
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_: ("متن", "برند"))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_: _media_plan())
    class Response:
        status_code = 400
        text = '{"ok":false,"error_code":400,"description":"Bad Request: caption is too long"}'

        def json(self):
            return {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: caption is too long",
            }

    monkeypatch.setattr("core.media_handler.telegram_post", lambda *_args, **_kwargs: Response())

    result = publication_engine.publish_prepared_content(
        9, "api",
        PreparedContent(main_text="متن", files=[{"type": "photo", "file_id": "f"}], source_key="media:400"),
        [target], InMemoryPublicationStateStore(),
    )

    delivery = result["results"][0]
    assert result["ok"] is False
    assert delivery.status_code == 400
    assert delivery.error_code == 400
    assert delivery.error == "Bad Request: caption is too long"
    assert delivery.failed_part == "primary"
    assert delivery.operation == "sendPhoto"


def test_short_media_does_not_trigger_shared_summary(monkeypatch):
    monkeypatch.setattr(
        "core.caption_manager.analyze_content",
        lambda **_: pytest.fail("short media must not invoke shared summary"),
    )
    prepared = PreparedContent(
        main_text="خبر کوتاه 😀",
        expandable_blocks=[{"text": "ادامه کوتاه"}],
        files=[{"type": "photo", "file_id": "f"}],
    )
    assert publication_engine._shared_content_analysis(prepared) is prepared
