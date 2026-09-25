"""
Regression tests for source/footer URL cleanup for confirmed forwarded content.

Prior regression: remove_source_signature() only stripped a trailing standalone
URL when source_title or source_username was non-empty. For messages forwarded
from private/hidden channels (no public username, no title extracted), both
fields are empty strings, so the guard was False and the URL survived in the
translated output.

Fix: is_forwarded: bool = False added to remove_source_signature(); the
positional URL check is now also unlocked when is_forwarded=True.
build_translation_publication_payload() passes is_forwarded from
forward_source["is_forwarded"].

All named-source identity checks (is_source_line, promotional footer,
adjacent-label) remain gated on source_title/source_username — unchanged.
"""
from core.formatter import remove_source_signature
from core.translation_publication import build_translation_publication_payload


# =========================================================
# remove_source_signature — is_forwarded flag
# =========================================================

def test_trailing_url_removed_for_anonymous_forward():
    """is_forwarded=True, no title/username → URL on last line is stripped."""
    text = "متن خبر ترجمه شده\n\nhttps://ara.tv/mehm1"
    result = remove_source_signature(text, is_forwarded=True)
    assert "https://ara.tv/mehm1" not in result
    assert "متن خبر" in result


def test_body_url_preserved_for_anonymous_forward():
    """URL embedded mid-text is never on the last non-empty line → preserved."""
    text = "برای جزئیات https://ara.tv/mehm1 ببینید.\n\nادامه متن خبر."
    result = remove_source_signature(text, is_forwarded=True)
    assert "https://ara.tv/mehm1" in result


def test_url_only_message_not_emptied_for_anonymous_forward():
    """Single-line URL: len(non_empty_indexes) < 2 → guard fails → preserved."""
    text = "https://ara.tv/mehm1"
    result = remove_source_signature(text, is_forwarded=True)
    assert result == text


def test_named_forward_still_removes_url():
    """Existing named-source path unchanged."""
    text = "متن ترجمه شده\n\nhttps://ara.tv/mehm1"
    result = remove_source_signature(text, source_title="Ara News")
    assert "https://ara.tv/mehm1" not in result
    assert "متن ترجمه شده" in result


def test_no_forward_context_preserves_url():
    """No args at all → URL must not be touched."""
    text = "متن\n\nhttps://ara.tv/mehm1"
    result = remove_source_signature(text)
    assert "https://ara.tv/mehm1" in result


def test_is_forwarded_false_does_not_remove_url():
    """Explicit is_forwarded=False + no title/username → no removal."""
    text = "متن\n\nhttps://ara.tv/mehm1"
    result = remove_source_signature(text, is_forwarded=False)
    assert "https://ara.tv/mehm1" in result


def test_is_forwarded_does_not_remove_mid_body_url():
    """is_forwarded=True cannot remove a URL that is not the final non-empty line."""
    text = "لینک https://ara.tv/mehm1 در اینجا آمده است.\n\nادامه متن."
    result = remove_source_signature(text, is_forwarded=True)
    assert "https://ara.tv/mehm1" in result


def test_is_forwarded_does_not_remove_mid_text_channel_mention():
    """is_forwarded=True must only unlock the positional trailing-URL check.

    A @handle that appears inline in the body (not on a standalone trailing
    line) must not be removed — it is a real body mention, not a footer.
    """
    text = "گزارش @some_journalist از تهران منتشر شد.\n\nادامه متن خبر."
    result = remove_source_signature(text, is_forwarded=True)
    assert "@some_journalist" in result


def test_promotional_footer_not_removed_without_source_title():
    """Promotional footer detection requires source_title — is_forwarded alone
    must not trigger it.
    """
    text = "متن\n\n🔷 یک کانال را در فضای مجازی دنبال کنید:"
    result = remove_source_signature(text, is_forwarded=True)

    # Not removed — promotional footer detection requires source_title.
    assert "دنبال کنید" in result


# =========================================================
# domain / URL + @username trailing source pair regression
# =========================================================

def test_trailing_bare_domain_then_source_username_are_removed_together():
    """A bare source domain immediately followed by its source handle is one footer."""
    text = "متن خبر\n\nasriran.com\n@MyAsriran"

    result = remove_source_signature(
        text,
        source_username="MyAsriran",
        is_forwarded=True,
    )

    assert result == "متن خبر"
    assert "asriran.com" not in result
    assert "@MyAsriran" not in result


def test_trailing_source_username_then_bare_domain_are_removed_together():
    """The same source-footer pair is removed when handle appears before domain."""
    text = "متن خبر\n\n@MyAsriran\nasriran.com"

    result = remove_source_signature(
        text,
        source_username="MyAsriran",
        is_forwarded=True,
    )

    assert result == "متن خبر"
    assert "asriran.com" not in result
    assert "@MyAsriran" not in result


def test_trailing_https_url_then_source_username_are_removed_together():
    """A full HTTPS source URL followed by the matching source handle is removed."""
    text = "متن خبر\n\nhttps://asriran.com\n@MyAsriran"

    result = remove_source_signature(
        text,
        source_username="MyAsriran",
        is_forwarded=True,
    )

    assert result == "متن خبر"
    assert "https://asriran.com" not in result
    assert "@MyAsriran" not in result


def test_trailing_source_username_then_https_url_are_removed_together():
    """A matching source handle followed by a full HTTPS URL is removed."""
    text = "متن خبر\n\n@MyAsriran\nhttps://asriran.com"

    result = remove_source_signature(
        text,
        source_username="MyAsriran",
        is_forwarded=True,
    )

    assert result == "متن خبر"
    assert "https://asriran.com" not in result
    assert "@MyAsriran" not in result


def test_body_domain_and_mention_are_not_removed_when_not_trailing_footer():
    """Domain and mention used in ordinary body text must remain untouched."""
    text = (
        "در گزارش asriran.com به مطلب @MyAsriran اشاره شده است.\n\n"
        "ادامه متن اصلی خبر."
    )

    result = remove_source_signature(
        text,
        source_username="MyAsriran",
        is_forwarded=True,
    )

    assert "asriran.com" in result
    assert "@MyAsriran" in result
    assert "ادامه متن اصلی خبر." in result


# =========================================================
# build_translation_publication_payload — integration
# =========================================================

def _make_state(forward_source, translated_text):
    """Build a minimal duck-typed translation state for payload tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        review_id="test-rid",
        original_text="original",
        translated_text=translated_text,
        edited_text="",
        status="confirmed",
        source_kind="message",
        source_key="sk",
        metadata={
            "forward_source": forward_source,
            "files": [],
            "blockquote_blocks": [],
            "expandable_blocks": [],
        },
    )


def test_payload_removes_trailing_url_for_anonymous_forward():
    state = _make_state(
        forward_source={
            "is_forwarded": True,
            "source_title": "",
            "source_username": "",
        },
        translated_text="متن خبر\n\nhttps://ara.tv/mehm1",
    )

    payload = build_translation_publication_payload(state)

    assert "https://ara.tv/mehm1" not in payload["main_text"]
    assert "متن خبر" in payload["main_text"]


def test_payload_preserves_body_url_for_anonymous_forward():
    state = _make_state(
        forward_source={
            "is_forwarded": True,
            "source_title": "",
            "source_username": "",
        },
        translated_text=(
            "جزئیات در https://ara.tv/mehm1 موجود است.\n\n"
            "متن ادامه."
        ),
    )

    payload = build_translation_publication_payload(state)

    assert "https://ara.tv/mehm1" in payload["main_text"]


def test_payload_preserves_url_when_no_forward_context():
    state = _make_state(
        forward_source={},
        translated_text="متن\n\nhttps://ara.tv/mehm1",
    )

    payload = build_translation_publication_payload(state)

    assert "https://ara.tv/mehm1" in payload["main_text"]


def test_payload_url_only_text_not_emptied():
    state = _make_state(
        forward_source={
            "is_forwarded": True,
            "source_title": "",
            "source_username": "",
        },
        translated_text="https://ara.tv/mehm1",
    )

    payload = build_translation_publication_payload(state)

    assert payload["main_text"] == "https://ara.tv/mehm1"


def test_payload_named_source_still_removes_url():
    state = _make_state(
        forward_source={
            "is_forwarded": True,
            "source_title": "Ara News",
            "source_username": "",
        },
        translated_text="متن\n\nhttps://ara.tv/mehm1",
    )

    payload = build_translation_publication_payload(state)

    assert "https://ara.tv/mehm1" not in payload["main_text"]


def test_payload_removes_trailing_domain_username_pair():
    """Shared translation publication path must reuse the same source cleanup."""
    state = _make_state(
        forward_source={
            "is_forwarded": True,
            "source_title": "Asr Iran",
            "source_username": "MyAsriran",
        },
        translated_text=(
            "متن خبر ترجمه شده\n\n"
            "asriran.com\n"
            "@MyAsriran"
        ),
    )

    payload = build_translation_publication_payload(state)

    assert payload["main_text"] == "متن خبر ترجمه شده"
    assert "asriran.com" not in payload["main_text"]
    assert "@MyAsriran" not in payload["main_text"]
