import json

import pytest

from core.caption_manager import analyze_content
from core import media_handler


MAIN_TEXT = (
    "❇️ گواهی امنیتی برخی سایت‌های بانک مرکزی لغو شد\n\n"
    "🔹 اطلاعیه بانک مرکزی درباره گواهی امنیتی پایگاه‌های اطلاع‌رسانی"
)
EXPANDABLE_TEXT = (
    "در پی اقدامات خصمانه در حوزه‌های نظامی و سایبری، "
    "گواهی امنیتی برخی پایگاه‌های اطلاع‌رسانی لغو شده است."
)
HASHTAG = "#دنیا_۲۴_نیوز"
MENTION = "@Donya24News"
BRANDING = f"{HASHTAG}\n{MENTION}"


class _Response:
    status_code = 200
    text = '{"ok": true}'

    def __init__(self, result):
        self._result = result

    def json(self):
        return {"ok": True, "result": self._result}


def _utf16_slice(text, entity):
    encoded = text.encode("utf-16-le")
    start = entity["offset"] * 2
    end = start + entity["length"] * 2
    return encoded[start:end].decode("utf-16-le")


def _capture_executor_payload(monkeypatch, files, plan):
    captured = {}

    def fake_post(endpoint, payload, api_url=None):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        if endpoint == "sendMediaGroup":
            result = [{"message_id": 901}, {"message_id": 902}]
        else:
            result = {"message_id": 900}
        return _Response(result)

    monkeypatch.setattr(media_handler, "telegram_post", fake_post)
    outcome = media_handler.execute_telegram_plan(
        files,
        plan,
        channel_id="@audit_channel",
        api_url="https://api.telegram.invalid/botTEST",
        return_result=True,
    )
    assert outcome is True or outcome.get("ok") is True
    return captured


@pytest.mark.parametrize(
    ("files", "expected_endpoint"),
    [
        ([{"type": "photo", "file_id": "PHOTO"}], "sendPhoto"),
        ([{"type": "video", "file_id": "VIDEO"}], "sendVideo"),
        (
            [
                {"type": "photo", "file_id": "PHOTO_1"},
                {"type": "video", "file_id": "VIDEO_2"},
            ],
            "sendMediaGroup",
        ),
    ],
)
def test_final_executor_payload_preserves_expandable_branding_entities(
    monkeypatch, files, expected_endpoint
):
    plan = analyze_content(
        main_text=MAIN_TEXT,
        expandable_blocks=[{"text": EXPANDABLE_TEXT, "offset": 100}],
        branding=BRANDING,
    ).telegram
    captured = _capture_executor_payload(monkeypatch, files, plan)
    assert captured["endpoint"] == expected_endpoint

    if expected_endpoint == "sendMediaGroup":
        final_item = captured["payload"]["media"][0]
        for later_item in captured["payload"]["media"][1:]:
            assert "caption" not in later_item
            assert "caption_entities" not in later_item
    else:
        final_item = captured["payload"]

    caption = final_item["caption"]
    entities = final_item["caption_entities"]
    decoded = [(item["type"], _utf16_slice(caption, item)) for item in entities]

    assert caption == plan["media_caption"]
    assert entities == plan["media_caption_entities"]
    assert "parse_mode" not in final_item
    assert decoded == [
        ("expandable_blockquote", EXPANDABLE_TEXT),
    ]
    assert HASHTAG in caption
    assert MENTION in caption
    assert caption[caption.index(EXPANDABLE_TEXT) + len(EXPANDABLE_TEXT):].startswith("\n\n")

    print(json.dumps({
        "endpoint": expected_endpoint,
        "caption_repr": repr(caption),
        "caption_utf16_length": len(caption.encode("utf-16-le")) // 2,
        "parse_mode": final_item.get("parse_mode"),
        "entities": [
            {**entity, "decoded": decoded[index][1]}
            for index, entity in enumerate(entities)
        ],
    }, ensure_ascii=True, indent=2))


def test_executor_payload_comparison_without_expandable(monkeypatch):
    expandable_plan = analyze_content(
        main_text=MAIN_TEXT,
        expandable_blocks=[{"text": EXPANDABLE_TEXT, "offset": 100}],
        branding=BRANDING,
    ).telegram
    normal_plan = analyze_content(main_text=MAIN_TEXT, branding=BRANDING).telegram

    expandable = _capture_executor_payload(
        monkeypatch, [{"type": "photo", "file_id": "EXPANDABLE"}], expandable_plan
    )["payload"]
    normal = _capture_executor_payload(
        monkeypatch, [{"type": "photo", "file_id": "NORMAL"}], normal_plan
    )["payload"]

    assert expandable["caption"].endswith(BRANDING)
    assert normal["caption"].endswith(BRANDING)
    assert expandable["caption_entities"] == expandable_plan["media_caption_entities"]
    assert "caption_entities" not in normal
    assert "parse_mode" not in expandable
    assert "parse_mode" not in normal


def test_expandable_english_branding_keeps_explicit_entities(monkeypatch):
    english_hashtag = "#World_News"
    branding = f"{english_hashtag}\n{MENTION}"
    plan = analyze_content(
        main_text=MAIN_TEXT,
        expandable_blocks=[{"text": EXPANDABLE_TEXT, "offset": 100}],
        branding=branding,
    ).telegram

    payload = _capture_executor_payload(
        monkeypatch,
        [{"type": "photo", "file_id": "ENGLISH"}],
        plan,
    )["payload"]
    decoded = [
        (entity["type"], _utf16_slice(payload["caption"], entity))
        for entity in payload["caption_entities"]
    ]

    assert decoded == [
        ("expandable_blockquote", EXPANDABLE_TEXT),
        ("hashtag", english_hashtag),
        ("mention", MENTION),
    ]
