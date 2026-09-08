from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_content_review import (
    build_external_content_preview,
)
from core.external_review_preview import (
    CONTROL_TEXT_LIMIT,
    build_external_review_keyboard,
    build_external_review_preview,
)


def _content(
    *,
    media=(),
    body=(
        "پاراگراف اول\n\n"
        "پاراگراف دوم"
    ),
):
    return NormalizedExternalContent(
        source_type="web_article",
        source_url="https://example.com/news",
        canonical_url="https://example.com/news",
        content_type="article",
        title="عنوان خبر",
        lead="لید خبر",
        body=body,
        source_name="Example",
        extraction_confidence=0.95,
        media=media,
    )


def _media(count=2):
    return tuple(
        ExternalMedia(
            type="image",
            source_url=(
                f"https://example.com/{index}.jpg"
            ),
            position=index,
        )
        for index in range(count)
    )


def _callbacks(keyboard):
    return [
        button["callback_data"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]


# =========================================================
# CONTROL TEXT
# =========================================================


def test_preview_contains_heading_metadata_and_body():
    content = _content()
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
    )

    assert "🔎 پیش‌نمایش مطلب" in view.text
    assert "عنوان خبر" in view.text
    assert "لید خبر" in view.text
    assert "پاراگراف اول" in view.text
    # The old "منبع:" source footer is removed; the source appears
    # exactly once as the "به گزارش {source}،" body lead instead.
    assert "منبع:" not in view.text
    assert "تیتر اصلی:" not in view.text
    assert "اطمینان استخراج" in view.text


def test_preview_text_is_capped_for_single_message():
    content = _content(
        body="\n\n".join(
            f"پاراگراف شماره {index} " + "متن " * 80
            for index in range(40)
        )
    )

    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
    )

    assert len(view.text) <= 4096
    assert len(view.text) <= (
        CONTROL_TEXT_LIMIT + 64
    )

    # Capping is presentation-only; stored content is intact.
    assert "پاراگراف شماره 39" in content.body


def test_preview_without_media_reports_no_media():
    content = _content(media=())
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
    )

    assert "تصویر معتبری" in view.text
    assert view.media == ()

    callbacks = _callbacks(
        view.reply_markup
    )

    assert not any(
        ":media:" in item
        for item in callbacks
    )

    assert not any(
        ":nomedia:" in item
        for item in callbacks
    )


# =========================================================
# KEYBOARD
# =========================================================


def test_keyboard_preserves_callback_contract():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=3,
    )

    callbacks = _callbacks(keyboard)

    assert "extrev:standard:r1" in callbacks
    assert "extrev:short:r1" in callbacks
    assert "extrev:headline:r1" in callbacks
    assert "extrev:lead:r1" in callbacks
    assert "extrev:para_start:r1" in callbacks
    assert "extrev:manual:r1:waiting" in callbacks
    assert "extrev:manual:r1:primary" in callbacks
    assert "extrev:manual:r1:none" in callbacks
    assert "extrev:editorial:r1" in callbacks
    assert "extrev:cancel:r1" in callbacks

    # Per-candidate media buttons and the album/normal toggle are
    # intentionally hidden from the simplified keyboard.
    assert not any(
        callback.startswith("extrev:media:")
        for callback in callbacks
    )
    assert not any(
        callback.startswith("extrev:mode:")
        for callback in callbacks
    )
    assert not any(
        callback.startswith("extrev:nomedia:")
        for callback in callbacks
    )


def test_keyboard_marks_selected_media():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=2,
        selected_media_indexes=(0,),
        media_selection_explicit=True,
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "🖼 تصویر اصلی ✅" in labels


def test_keyboard_marks_explicit_no_media():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=2,
        selected_media_indexes=(),
        manual_image_source="none",
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "🚫 بدون تصویر ✅" in labels


def test_keyboard_manual_button_offers_add_when_no_file():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=0,
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "➕ افزودن تصویر دستی" in labels


def test_keyboard_manual_button_offers_cancel_while_waiting():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=0,
        manual_image_waiting=True,
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "⏳ لغو انتظار عکس" in labels


def test_keyboard_manual_button_shows_active_replace_state():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=0,
        manual_image_source="replace",
        manual_image_file_id="manual-1",
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "🔁 تصویر دستی ✅" in labels


def test_keyboard_manual_button_offers_restore_when_inactive():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=0,
        manual_image_source="primary",
        manual_image_file_id="manual-1",
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "🔁 بازگرداندن تصویر دستی" in labels


# =========================================================
# MEDIA RESOLUTION
# =========================================================


def test_default_selection_shows_all_media():
    content = _content(media=_media(2))
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
    )

    assert len(view.media) == 2


def test_explicit_selection_shows_only_selected_media():
    content = _content(media=_media(3))
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
        selected_media_indexes=(2,),
        media_selection_explicit=True,
    )

    assert len(view.media) == 1

    assert (
        view.media[0].source_url
        == "https://example.com/2.jpg"
    )

    assert "تصاویر آلبوم انتشار: 3" in view.text


def test_explicit_no_media_hides_panel():
    content = _content(media=_media(2))
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
        selected_media_indexes=(),
        media_selection_explicit=True,
    )

    assert view.media == ()
    assert "بدون تصویر" in view.text


def test_manual_replacement_preview_uses_uploaded_photo_file_id():
    content = _content(media=_media(1))
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
        manual_image_source="replace",
        manual_image_file_id="manual-photo-1",
    )

    assert len(view.media) == 1
    assert view.media_file_ids == ("manual-photo-1",)
    assert "تصویر دستی" in view.text


# =========================================================
# SIMPLIFIED KEYBOARD: TECHNICAL MEDIA UI IS HIDDEN
# =========================================================


def test_keyboard_never_shows_mode_toggle():
    keyboard_no_media = build_external_review_keyboard(
        review_id="r1",
        media_count=0,
    )

    keyboard_multi_media = build_external_review_keyboard(
        review_id="r1",
        media_count=3,
    )

    for keyboard in (
        keyboard_no_media,
        keyboard_multi_media,
    ):
        callbacks = _callbacks(keyboard)

        assert not any(
            callback.startswith("extrev:mode:")
            for callback in callbacks
        )

        assert not any(
            callback.startswith("extrev:media:")
            for callback in callbacks
        )


def test_preview_omits_presentation_mode_status_text():
    content = _content(media=_media(2))
    preview = build_external_content_preview(content)

    view = build_external_review_preview(
        review_id="r1",
        content=content,
        preview=preview,
        media_presentation_mode="album",
    )

    assert "حالت انتشار" not in view.text


# =========================================================
# SOURCE FORMAT (no "منبع:" footer / no "تیتر اصلی:" duplicate)
# =========================================================


def test_short_draft_preview_has_single_body_lead_source():
    from core.external_review_preview import (
        build_external_review_short_preview,
    )

    content = _content()
    preview = build_external_content_preview(content)

    view = build_external_review_short_preview(
        review_id="r1",
        content=content,
        preview=preview,
        draft_text="متن کوتاه خبر",
    )

    assert "منبع:" not in view.text
    assert "تیتر اصلی:" not in view.text
    assert "به گزارش Example،" in view.text
    assert view.text.count("Example") == 1


def test_short_draft_preview_does_not_duplicate_existing_attribution():
    from core.external_review_preview import (
        build_external_review_short_preview,
    )

    content = _content()
    preview = build_external_content_preview(content)

    view = build_external_review_short_preview(
        review_id="r1",
        content=content,
        preview=preview,
        draft_text="به گزارش Example، متن کوتاه خبر",
    )

    assert view.text.count("به گزارش") == 1
    assert view.text.count("Example") == 1


def test_paragraph_draft_preview_has_single_body_lead_source():
    from core.external_review_preview import (
        build_external_review_paragraph_preview,
    )

    content = _content()
    preview = build_external_content_preview(content)

    view = build_external_review_paragraph_preview(
        review_id="r1",
        content=content,
        preview=preview,
        draft_text="عنوان خبر\n\nپاراگراف اول",
    )

    assert "منبع:" not in view.text
    assert "تیتر اصلی:" not in view.text
    assert "به گزارش Example،" in view.text
    # Headline stays at the top; never repeated as metadata below it.
    assert view.text.count("عنوان خبر") == 1


def test_preview_and_final_output_share_the_same_formatter():
    """
    The SHORT draft preview body and the final publishable text must
    come from the same composition, so what is approved is exactly
    what is published.
    """

    from core.external_content_bridge import (
        compose_reviewed_publication_text,
    )
    from core.external_content_review import (
        ExternalReviewResult,
    )
    from core.external_review_preview import (
        build_external_review_short_preview,
    )

    content = _content()
    preview = build_external_content_preview(content)

    view = build_external_review_short_preview(
        review_id="r1",
        content=content,
        preview=preview,
        draft_text="متن کوتاه خبر",
    )

    final_text = compose_reviewed_publication_text(
        ExternalReviewResult(body="متن کوتاه خبر"),
        content.source_name,
    )

    assert final_text in view.text
    assert "به گزارش Example،" in final_text
    assert "منبع:" not in final_text
    assert "تیتر اصلی:" not in final_text


def test_raw_duplicate_source_is_normalized_to_single_clean_name():
    from core.external_content_bridge import (
        compose_reviewed_publication_text,
    )
    from core.external_content_review import (
        ExternalReviewResult,
    )

    text = compose_reviewed_publication_text(
        ExternalReviewResult(body="متن خبر"),
        "TABNAK | تابناک",
    )

    assert text.startswith("به گزارش تابناک،")
    assert "TABNAK" not in text
    assert "منبع:" not in text
    assert text.count("تابناک") == 1
