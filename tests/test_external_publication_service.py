import pytest

from core.content_model import (
    PreparedContent,
    PublicationTarget,
)
from core.external_content_model import (
    ExternalMedia,
    NormalizedExternalContent,
)
from core.external_content_review import (
    ExternalReviewResult,
)
from core.external_publication_service import (
    ExternalPublicationResult,
    ExternalTransformationRequired,
    publish_reviewed_external_content,
)


# =========================================================
# HELPERS
# =========================================================


def _content(
    *,
    source_type="web_article",
    source_url="https://example.com/news/1",
    canonical_url="https://example.com/news/1",
    language="en",
    media=(),
):
    return NormalizedExternalContent(
        source_type=source_type,
        source_url=source_url,
        canonical_url=canonical_url,
        content_type="article",
        title="Headline",
        lead="Lead",
        body="Article body.",
        original_language=language,
        source_name="Example News",
        media=tuple(media),
        extraction_confidence=0.94,
    )


def _review(
    *,
    media=(),
    requires_smart_summary=False,
    requires_editorial_rewrite=False,
):
    return ExternalReviewResult(
        title="Headline",
        lead="Lead",
        body="Article body.",
        media=tuple(media),
        requires_smart_summary=(
            requires_smart_summary
        ),
        requires_editorial_rewrite=(
            requires_editorial_rewrite
        ),
    )


def _target():
    return PublicationTarget(
        key="external-test-target",
        kind="workspace",
        platform="telegram",
        external_id="@test",
        workspace_id=1,
        destination_id=1,
    )


# =========================================================
# SHARED ENGINE ROUTING
# =========================================================


def test_external_publication_uses_shared_engine(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        chat_id,
        api_url,
        prepared,
        *args,
        **kwargs,
    ):
        captured["chat_id"] = chat_id
        captured["api_url"] = api_url
        captured["prepared"] = prepared
        captured["args"] = args
        captured["kwargs"] = kwargs

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    result = publish_reviewed_external_content(
        77,
        "https://api.telegram.org/botTEST",
        _content(),
        _review(),
    )

    assert isinstance(
        result,
        ExternalPublicationResult,
    )

    assert captured[
        "chat_id"
    ] == 77

    assert captured[
        "api_url"
    ] == (
        "https://api.telegram.org/botTEST"
    )

    assert isinstance(
        captured["prepared"],
        PreparedContent,
    )

    assert result.ok is True


def test_service_does_not_send_directly(
    monkeypatch,
):
    calls = []

    def fake_publish(
        *_args,
        **_kwargs,
    ):
        calls.append(
            "shared_engine"
        )

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    publish_reviewed_external_content(
        1,
        "api",
        _content(),
        _review(),
    )

    assert calls == [
        "shared_engine",
    ]


# =========================================================
# PREPARED CONTENT
# =========================================================


def test_reviewed_text_reaches_prepared_content(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        prepared,
        *_args,
        **_kwargs,
    ):
        captured[
            "prepared"
        ] = prepared

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    result = publish_reviewed_external_content(
        1,
        "api",
        _content(),
        _review(),
    )

    prepared = captured[
        "prepared"
    ]

    assert (
        prepared
        is result.prepared_content
    )

    assert "Headline" in (
        prepared.main_text
    )

    assert "Lead" in (
        prepared.main_text
    )

    assert "Article body." in (
        prepared.main_text
    )


def test_external_source_key_reaches_shared_engine(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        prepared,
        *_args,
        **_kwargs,
    ):
        captured[
            "source_key"
        ] = prepared.source_key

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    result = publish_reviewed_external_content(
        1,
        "api",
        _content(),
        _review(),
    )

    assert captured[
        "source_key"
    ].startswith(
        "external:web_article:"
    )

    assert (
        captured["source_key"]
        == result.publication_identity
    )


def test_explicit_source_key_is_preserved(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        prepared,
        *_args,
        **_kwargs,
    ):
        captured[
            "prepared"
        ] = prepared

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    publish_reviewed_external_content(
        1,
        "api",
        _content(),
        _review(),
        source_key=(
            "external:custom:abc"
        ),
    )

    assert (
        captured[
            "prepared"
        ].source_key
        == "external:custom:abc"
    )


# =========================================================
# TARGETS
# =========================================================


def test_explicit_targets_are_forwarded_to_shared_engine(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        _prepared,
        *args,
        **kwargs,
    ):
        captured[
            "args"
        ] = args

        captured[
            "kwargs"
        ] = kwargs

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    target = _target()

    publish_reviewed_external_content(
        1,
        "api",
        _content(),
        _review(),
        targets=(
            target,
        ),
    )

    forwarded = (
        captured[
            "kwargs"
        ].get(
            "targets"
        )
    )

    if forwarded is None:
        forwarded = (
            captured[
                "args"
            ][
                0
            ]
        )

    assert len(
        forwarded
    ) == 1

    assert (
        forwarded[
            0
        ].key
        == target.key
    )


# =========================================================
# MEDIA
# =========================================================


def test_materialized_external_media_reaches_shared_engine(
    monkeypatch,
):
    media = (
        ExternalMedia(
            type="photo",
            source_url=(
                "https://example.com/photo.jpg"
            ),
        ),
    )

    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        prepared,
        *_args,
        **_kwargs,
    ):
        captured[
            "prepared"
        ] = prepared

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    publish_reviewed_external_content(
        1,
        "api",
        _content(
            media=media
        ),
        _review(
            media=media
        ),
        prepared_files=(
            {
                "type": "photo",
                "file_id": (
                    "materialized-file-1"
                ),
            },
        ),
    )

    files = (
        captured[
            "prepared"
        ].files
    )

    assert len(
        files
    ) == 1

    assert (
        files[
            0
        ][
            "file_id"
        ]
        == "materialized-file-1"
    )


def test_external_url_is_not_forwarded_as_file_id(
    monkeypatch,
):
    media = (
        ExternalMedia(
            type="photo",
            source_url=(
                "https://example.com/photo.jpg"
            ),
        ),
    )

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: {
            "ok": True,
        },
    )

    with pytest.raises(
        Exception,
    ):
        publish_reviewed_external_content(
            1,
            "api",
            _content(
                media=media
            ),
            _review(
                media=media
            ),
            prepared_files=(
                {
                    "type": "photo",
                    "file_id": (
                        "https://example.com/photo.jpg"
                    ),
                },
            ),
        )


# =========================================================
# SMART SUMMARY
# =========================================================


def test_short_review_fails_closed_until_shared_summary_applied(
    monkeypatch,
):
    called = []

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: (
            called.append(
                True
            )
            or {
                "ok": True,
            }
        ),
    )

    with pytest.raises(
        ExternalTransformationRequired,
        match="Smart Summary",
    ):
        publish_reviewed_external_content(
            1,
            "api",
            _content(),
            _review(
                requires_smart_summary=True,
            ),
        )

    assert called == []


def test_short_review_can_publish_after_shared_summary_is_applied(
    monkeypatch,
):
    called = []

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: (
            called.append(
                True
            )
            or {
                "ok": True,
            }
        ),
    )

    result = (
        publish_reviewed_external_content(
            1,
            "api",
            _content(),
            _review(
                requires_smart_summary=True,
            ),
            smart_summary_applied=True,
        )
    )

    assert result.ok is True
    assert called == [
        True,
    ]


# =========================================================
# EDITORIAL
# =========================================================


def test_editorial_review_fails_closed_until_shared_editorial_applied(
    monkeypatch,
):
    called = []

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: (
            called.append(
                True
            )
            or {
                "ok": True,
            }
        ),
    )

    with pytest.raises(
        ExternalTransformationRequired,
        match="Editorial",
    ):
        publish_reviewed_external_content(
            1,
            "api",
            _content(),
            _review(
                requires_editorial_rewrite=True,
            ),
        )

    assert called == []


def test_editorial_finalized_flag_is_set_after_shared_editorial(
    monkeypatch,
):
    captured = {}

    def fake_publish(
        _chat_id,
        _api_url,
        prepared,
        *_args,
        **_kwargs,
    ):
        captured[
            "prepared"
        ] = prepared

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        fake_publish,
    )

    result = (
        publish_reviewed_external_content(
            1,
            "api",
            _content(),
            _review(
                requires_editorial_rewrite=True,
            ),
            editorial_rewrite_applied=True,
        )
    )

    assert (
        captured[
            "prepared"
        ].editorial_finalized
        is True
    )

    assert (
        result
        .prepared_content
        .editorial_finalized
        is True
    )


# =========================================================
# RESULT
# =========================================================


@pytest.mark.parametrize(
    (
        "publication_result",
        "expected",
    ),
    (
        (
            {
                "ok": True,
            },
            True,
        ),
        (
            {
                "ok": False,
            },
            False,
        ),
        (
            True,
            True,
        ),
        (
            False,
            False,
        ),
    ),
)
def test_result_ok_reflects_shared_engine_result(
    monkeypatch,
    publication_result,
    expected,
):
    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: (
            publication_result
        ),
    )

    result = (
        publish_reviewed_external_content(
            1,
            "api",
            _content(),
            _review(),
        )
    )

    assert result.ok is expected


# =========================================================
# LANGUAGE / TRANSLATION
# =========================================================


def test_original_language_is_preserved_without_translation(
    monkeypatch,
):
    monkeypatch.setattr(
        "core.publication_engine.publish_prepared_content",
        lambda *_args, **_kwargs: {
            "ok": True,
        },
    )

    result = (
        publish_reviewed_external_content(
            1,
            "api",
            _content(
                language="en"
            ),
            _review(),
        )
    )

    assert (
        result.bridge.original_language
        == "en"
    )

    assert not hasattr(
        result,
        "translated_text",
    )
