from pathlib import Path


WEBHOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "webhook_handler.py"
)


def _source() -> str:
    return WEBHOOK_PATH.read_text(
        encoding="utf-8"
    )


def test_external_review_callback_route_exists():
    source = _source()

    assert (
        'callback_data.startswith(\n'
        '                "extrev:"'
        in source
    )

    assert (
        "handle_external_review_telegram_callback"
        in source
    )


def test_external_review_route_passes_callback_query():
    source = _source()

    assert (
        "callback_query=callback_query"
        in source
    )


def test_external_review_route_passes_existing_telegram_helpers():
    source = _source()

    assert (
        "answer_callback_query=("
        in source
    )

    assert (
        "send_message=("
        in source
    )


def test_external_review_route_returns_before_workspace_route():
    source = _source()

    external_position = source.index(
        "# EXTERNAL CONTENT REVIEW CALLBACK"
    )

    workspace_position = source.index(
        "# Workspace publication callbacks (Phase 4B)"
    )

    assert (
        external_position
        < workspace_position
    )


def test_workspace_route_is_preserved():
    source = _source()

    assert (
        ').startswith(("wp:", "ws:")):'
        in source
    )


def test_editorial_callback_route_is_preserved():
    source = _source()

    assert (
        "handle_editorial_callback("
        in source
    )


def test_external_route_does_not_call_publication_engine_directly():
    source = _source()

    start = source.index(
        "# EXTERNAL CONTENT REVIEW CALLBACK"
    )

    end = source.index(
        "# Workspace publication callbacks (Phase 4B)",
        start,
    )

    external_block = source[
        start:end
    ]

    assert (
        "publish_prepared_content("
        not in external_block
    )

    assert (
        "publish_reviewed_external_content("
        not in external_block
    )


def test_external_route_is_namespaced_and_does_not_claim_other_callbacks():
    source = _source()

    start = source.index(
        "# EXTERNAL CONTENT REVIEW CALLBACK"
    )

    end = source.index(
        "# Workspace publication callbacks (Phase 4B)",
        start,
    )

    external_block = source[
        start:end
    ]

    assert '"extrev:"' in external_block

    assert '"wp:"' not in external_block
    assert '"ws:"' not in external_block
    assert '"dup:publish:"' not in external_block
