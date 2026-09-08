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
    assert "منبع: Example" in view.text
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
    assert "extrev:media:r1:0" in callbacks
    assert "extrev:media:r1:1" in callbacks
    assert "extrev:media:r1:2" in callbacks
    assert "extrev:nomedia:r1" in callbacks
    assert "extrev:editorial:r1" in callbacks
    assert "extrev:cancel:r1" in callbacks


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
    assert "🖼 تصویر 2" in labels


def test_keyboard_marks_explicit_no_media():
    keyboard = build_external_review_keyboard(
        review_id="r1",
        media_count=2,
        selected_media_indexes=(),
        media_selection_explicit=True,
    )

    labels = [
        button["text"]
        for row in keyboard["inline_keyboard"]
        for button in row
    ]

    assert "🚫 بدون تصویر ✅" in labels


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
