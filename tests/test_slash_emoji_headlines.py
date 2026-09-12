import pytest

from core.cleaner import clean_media_footer, clean_all_trailing_content, remove_all_emojis
from core.formatter import format_news, remove_source_signature
from core.caption_manager import (
    PublicationPlan, _first_line_headline, _ensure_telegram_headline_bold_entity,
    _bold_headlines_in_plan, _bold_html_headline, analyze_content,
)


def units(text):
    return len(text.encode("utf-16-le")) // 2


@pytest.mark.parametrize("text", [
    "فوری / خبر", "فوری / News Agency", "فوری / ادامه خبر",
    "فوری / خبر\nمتن گزارش", "تیتر\nمتن / ادامه گزارش", "تیتر\nپایان / خبر",
    "سند https://example.com/article/123", "/start", "مسیر /var/news/latest",
])
@pytest.mark.parametrize("clean", [clean_media_footer, clean_all_trailing_content])
def test_ordinary_slash_suffix_is_preserved_and_idempotent(text, clean):
    assert clean(text) == text
    assert clean(clean(text)) == text


def test_contextual_source_footer_is_still_removed():
    body = "فوری / خبر\nسند https://example.com/article در متن گزارش آمده است."
    source = body + "\n\nhttps://www.c14news.com/article/1500798/\n@C14English"
    cleaned = remove_source_signature(source, source_title="Channel 14", source_username="C14English")
    assert cleaned == body
    assert remove_source_signature(cleaned, source_username="C14English") == body


@pytest.mark.parametrize("icon", ["🟢", "🔴", "🚨", "⚡", "📌", "🔹", "🟢 🚨", "👩‍💻", "🇮🇷", "👍🏽", "☑️"])
@pytest.mark.parametrize("body", ["", "\n\nمتن گزارش"])
def test_original_decoration_survives_formatting_and_full_utf16_bold(icon, body):
    headline = icon + " تیتر خبر"
    formatted = format_news(headline + body)
    assert formatted.splitlines()[0] == headline
    # A one-line title requires source headline formatting, not just an icon.
    entities = [] if body else [{
        "type": "bold", "text": "تیتر خبر", "offset": units(icon + " "),
        "length": units("تیتر خبر"),
    }]
    assert _first_line_headline(formatted, entities) == headline
    plan = analyze_content(main_text=formatted, branding="", other_entities=entities)
    assert {"type": "bold", "offset": 0, "length": units(headline)} in plan.telegram["media_caption_entities"]
    assert f"<b>{headline}</b>" in plan.text["telegram"]["messages"][0]


def test_body_emoji_cleanup_and_plain_title_default_remain():
    assert remove_all_emojis("🟢 تیتر خبر\nمتن 🚨 گزارش") == "🟢 تیتر خبر\nمتن گزارش"
    assert format_news("تیتر خبر").startswith("❇️ تیتر خبر")


@pytest.mark.parametrize("text", ["---", "🟢 ⚡", "***\nمتن", "پیام ساده",
                                 "🟢 پیام ساده", "❇️ متن فارسی خبر", "\n🟢 پیام ساده\n"])
def test_non_headlines_remain_unclassified(text):
    assert _first_line_headline(text) == ""


def test_leading_whitespace_and_repeated_headline_offsets():
    headline = "🟢 تیتر خبر"
    text = "\n  " + headline + "\n\n" + headline
    assert _first_line_headline(text) == headline
    assert _ensure_telegram_headline_bold_entity(text, [], headline) == [
        {"type": "bold", "offset": 3, "length": 11}
    ]


@pytest.mark.parametrize("existing", [
    [{"type": "bold", "offset": 3, "length": 8}],
    [{"type": "bold", "offset": 0, "length": 11}],
    [{"type": "bold", "offset": 0, "length": 5}, {"type": "bold", "offset": 3, "length": 8}],
])
def test_bold_union_preserves_unrelated_entities(existing):
    text = "🟢 تیتر خبر\n@person #خبر سند"
    unrelated = [
        {"type": "italic", "offset": 3, "length": 8},
        {"type": "text_link", "offset": 3, "length": 8, "url": "https://example.com"},
        {"type": "custom_emoji", "offset": 0, "length": 2, "custom_emoji_id": "123"},
        {"type": "mention", "offset": 12, "length": 7},
        {"type": "hashtag", "offset": 20, "length": 4},
    ]
    result = _ensure_telegram_headline_bold_entity(text, existing + unrelated, "🟢 تیتر خبر")
    assert [e for e in result if e["type"] == "bold"] == [{"type": "bold", "offset": 0, "length": 11}]
    assert all(e in result for e in unrelated)


@pytest.mark.parametrize("quote", ["blockquote", "blockquote expandable"])
def test_html_nesting_escaping_and_quotes_are_preserved(quote):
    headline = "🟢 تیتر & خبر"
    source = f'<i>🟢 </i><a href="https://example.com">تیتر &amp; خبر</a>\n<{quote}>متن</blockquote>'
    result = _bold_html_headline(source, headline)
    assert result == f'<i><b>🟢 </b></i><a href="https://example.com"><b>تیتر </b><b>&amp;</b><b> خبر</b></a>\n<{quote}>متن</blockquote>'
    assert _bold_html_headline(result, headline) == result


@pytest.mark.parametrize("html", [False, True])
def test_caption_and_text_plan_both_bold_headline(html):
    headline = "🟢 فوری / خبر"
    plan = PublicationPlan()
    plan.telegram["media_caption"] = headline + "\nمتن"
    plan.telegram["media_parse_mode"] = "HTML" if html else None
    plan.text["telegram"]["messages"] = [headline + "\nمتن"]
    plan.text["telegram"]["message_parse_modes"] = ["HTML" if html else None]
    _bold_headlines_in_plan(plan, headline=headline)
    assert plan.text["telegram"]["messages"][0] == f"<b>{headline}</b>\nمتن"
    if html:
        assert plan.telegram["media_caption"] == f"<b>{headline}</b>\nمتن"
    else:
        assert plan.telegram["media_caption"] == headline + "\nمتن"
        assert plan.telegram["media_caption_entities"] == [{"type": "bold", "offset": 0, "length": units(headline)}]


@pytest.mark.parametrize("file_count", [0, 1, 3])
def test_real_planning_preserves_slash_and_headline_for_legacy_and_workspace(monkeypatch, file_count):
    from core import publication_engine
    from core.content_model import PreparedContent, PublicationTarget

    headline = "🟢 فوری / خبر"
    content = format_news(headline + "\n\nمتن / ادامه گزارش")
    sent = []
    # Keep actual shared planning; isolate destination configuration and transport.
    monkeypatch.setattr(publication_engine, "_target_content_and_branding", lambda *_: (content, ""))
    monkeypatch.setattr(publication_engine, "_send_text_target", lambda *args: sent.append(args[-1]) or True)
    monkeypatch.setattr(publication_engine, "_send_media_target", lambda *args: sent.append(args[-1]) or True)
    publication_engine.reset_local_idempotency_state()
    prepared = PreparedContent(
        main_text=content, neutral_text=content, source_key=f"slash-icons:{file_count}",
        files=[{"type": "photo", "file_id": f"f{i}"} for i in range(file_count)],
    )
    targets = [
        PublicationTarget("legacy", "legacy", "telegram", "@legacy"),
        PublicationTarget("workspace", "workspace", "telegram", "@workspace", 2, 20),
    ]
    result = publication_engine.publish_prepared_content(1, "api", prepared, targets)
    assert result["ok"]
    assert len(sent) == 2
    assert sent[0] == sent[1]
    if file_count:
        assert "متن / ادامه گزارش" in sent[0]["media_caption"]
        assert {"type": "bold", "offset": 0, "length": units(headline)} in sent[0]["media_caption_entities"]
    else:
        assert "متن / ادامه گزارش" in sent[0]["messages"][0]
        assert f"<b>{headline}</b>" in sent[0]["messages"][0]
