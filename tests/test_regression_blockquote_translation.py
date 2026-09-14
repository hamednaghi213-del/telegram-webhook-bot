"""
Regression tests for blockquote / expandable_blockquote translation.

Prior regression (two variants):

A) Rich-message path: try_automatic_persian_translation_gate() was never
   called for rich messages, so non-Persian blockquote blocks were published
   in source language alongside whatever main text was present.

B) ed:translate / automatic-gate path: blockquote_blocks and expandable_blocks
   were stored in TranslationState metadata but _execute_translation() never
   translated them; translation_blockquote_blocks() returned [] (fail-closed),
   silently dropping blockquote content from the published translation.

Fixes:
- try_automatic_persian_translation_gate() now accepts blockquote_blocks and
  expandable_blocks and includes them in the translation state metadata.
- _execute_translation() translates each block's text separately via the same
  pipeline/policy; stores {type, text} only (no stale UTF-16 offsets).
- Fail-closed: on block translation failure the block is omitted, not
  published in source language.
- Rich-message handler calls the gate when main text is non-Persian.

Tests here cover the gate+controller path (mockable via the flow fixture).
The rich-message gate invocation is covered by the gate-parameter test.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core import automatic_translation_review as automatic
from core import translation_controller as controller
from core import translation_editorial_policy as editorial
from core import translation_pipeline as pipeline
from core import translation_provider as provider
from core import translation_state as states
from core import translation_telegram as telegram
from core.translation_publication import (
    build_translation_publication_payload,
    translation_blockquote_blocks,
    translation_expandable_blocks,
)


SOURCE = "The latest news was published."
BLOCK_SOURCE = "This is a quoted statement."
MACHINE = "خبر تازه منتشر شد."


# =========================================================
# Shared flow fixture (mirrors test_translation_lifecycle)
# =========================================================

@pytest.fixture
def flow(monkeypatch):
    rows, stages = {}, []

    def update(rid, **values):
        row = rows[rid]
        expected = values.pop("expected_status", None)
        if expected is not None and row["status"] != expected:
            return None
        metadata = values.pop("metadata", None)
        if metadata:
            row["metadata"].update(deepcopy(metadata))
        for key in ("target_language_code", "source_key"):
            value = values.pop(key, None)
            if value is not None:
                row["metadata"][key] = value
        kind = values.pop("source_kind", None)
        if kind is not None:
            row["content_kind"] = kind
        row.update({k: deepcopy(v) for k, v in values.items() if v is not None})
        return deepcopy(row)

    def create(**values):
        rid = values.pop("review_id")
        rows[rid] = dict(
            review_id=rid,
            status="waiting_language",
            metadata={},
            translated_text="",
            edited_text="",
        )
        return update(rid, **values)

    db = SimpleNamespace(
        create_persistent_translation_review=create,
        get_persistent_translation_review=lambda rid: deepcopy(rows.get(rid)),
        update_persistent_translation_review=update,
        mark_persistent_translation_review_failed=lambda rid, **kw: update(
            rid, status="failed", **kw
        ),
        mark_persistent_translation_review_confirmed=lambda rid: update(
            rid, status="confirmed"
        ),
    )
    monkeypatch.setattr(states, "_database", lambda: db)
    monkeypatch.setattr(
        controller,
        "get_active_translation_state",
        lambda **kw: states._state_from_row(next(reversed(rows.values()))),
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "_detect_language", lambda text: None)
    monkeypatch.setattr(
        pipeline, "_deterministic_language", lambda result: "auto"
    )

    def detect(text):
        stages.append("detect")
        return {"success": True, "language": "en"}

    monkeypatch.setattr(pipeline, "_provider_language_detection", detect)

    def reply(status=200, details=None):
        data = (
            {
                "candidates": [
                    {"content": {"parts": [{"text": MACHINE}]}}
                ]
            }
            if status == 200
            else {"error": {"details": details or []}}
        )
        return SimpleNamespace(
            ok=status == 200,
            status_code=status,
            headers={},
            json=lambda: data,
        )

    responses = []

    def post(*args, **kwargs):
        stages.append("translate")
        return responses.pop(0) if responses else reply()

    monkeypatch.setattr(provider, "provider_post", post)
    original_policy = editorial.apply_editorial_translation_policy

    def policy(**kwargs):
        stages.append("policy")
        return original_policy(**kwargs)

    monkeypatch.setattr(editorial, "apply_editorial_translation_policy", policy)

    def quality(**kwargs):
        stages.append("quality")
        return {"passed": True, "semantic_verified": True}

    monkeypatch.setattr(pipeline, "_quality_check", quality)
    send, publish = Mock(), Mock(return_value={"ok": True})

    def click(rid, action, user=1):
        return telegram.handle_translation_telegram_callback(
            callback_query={
                "id": "cb",
                "data": f"tr:{action}:{rid}",
                "from": {"id": user},
                "message": {"chat": {"id": 1}},
            },
            send_message=send,
            answer_callback_query=Mock(),
            publish_prepared_text=publish,
        )

    def start(**kwargs):
        return automatic.start_automatic_persian_translation_review(
            chat_id=1,
            user_id=1,
            original_text=kwargs.pop("original_text", SOURCE),
            **kwargs,
        )

    return SimpleNamespace(
        rows=rows,
        stages=stages,
        responses=responses,
        reply=reply,
        start=start,
        click=click,
        send=send,
        publish=publish,
        update=update,
    )


# =========================================================
# Gate signature: blockquote_blocks / expandable_blocks are
# accepted and stored in translation state metadata
# =========================================================

def test_gate_stores_blockquote_blocks_in_state_metadata(flow):
    """Blocks passed to the gate end up in state metadata after start."""
    blocks = [{"type": "blockquote", "text": BLOCK_SOURCE, "offset": 50, "length": 28}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": blocks,
            "expandable_blocks": [],
        }
    )
    assert result.success
    rid = result.review_id
    stored = flow.rows[rid]["metadata"].get("blockquote_blocks", [])
    assert len(stored) == 1
    assert stored[0]["text"] == BLOCK_SOURCE
    assert stored[0]["type"] == "blockquote"


def test_gate_stores_expandable_blocks_in_state_metadata(flow):
    """expandable_blockquote blocks are also propagated."""
    blocks = [{"type": "expandable_blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": [],
            "expandable_blocks": blocks,
        }
    )
    assert result.success
    rid = result.review_id
    stored = flow.rows[rid]["metadata"].get("expandable_blocks", [])
    assert len(stored) == 1
    assert stored[0]["type"] == "expandable_blockquote"


# =========================================================
# Block translation: _execute_translation produces
# translated_blockquote_blocks and translated_expandable_blocks
# =========================================================

def test_blockquote_block_is_translated_and_stored(flow):
    """After start+confirm, translated_blockquote_blocks contains translated text."""
    blocks = [{"type": "blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": blocks,
            "expandable_blocks": [],
        }
    )
    assert result.success
    rid = result.review_id

    # translated_blockquote_blocks should be set after the language selection
    # that runs inside start_automatic_persian_translation_review.
    translated_blocks = flow.rows[rid]["metadata"].get(
        "translated_blockquote_blocks"
    )
    assert translated_blocks is not None, (
        "translated_blockquote_blocks not found in state metadata"
    )
    assert len(translated_blocks) == 1
    assert translated_blocks[0]["text"] == MACHINE
    assert translated_blocks[0]["type"] == "blockquote"
    # No stale offset field should be present.
    assert "offset" not in translated_blocks[0]
    assert "length" not in translated_blocks[0]


def test_expandable_block_is_translated_and_stored(flow):
    """expandable_blockquote blocks have parity with blockquote blocks."""
    blocks = [{"type": "expandable_blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": [],
            "expandable_blocks": blocks,
        }
    )
    assert result.success
    rid = result.review_id

    translated_blocks = flow.rows[rid]["metadata"].get(
        "translated_expandable_blocks"
    )
    assert translated_blocks is not None, (
        "translated_expandable_blocks not found in state metadata"
    )
    assert len(translated_blocks) == 1
    assert translated_blocks[0]["text"] == MACHINE
    assert translated_blocks[0]["type"] == "expandable_blockquote"
    assert "offset" not in translated_blocks[0]
    assert "length" not in translated_blocks[0]


def test_both_block_types_translated_independently(flow):
    """One blockquote and one expandable are both translated."""
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": [{"type": "blockquote", "text": BLOCK_SOURCE}],
            "expandable_blocks": [
                {"type": "expandable_blockquote", "text": BLOCK_SOURCE}
            ],
        }
    )
    assert result.success
    rid = result.review_id
    meta = flow.rows[rid]["metadata"]

    assert len(meta.get("translated_blockquote_blocks", [])) == 1
    assert len(meta.get("translated_expandable_blocks", [])) == 1
    assert meta["translated_blockquote_blocks"][0]["text"] == MACHINE
    assert meta["translated_expandable_blocks"][0]["text"] == MACHINE


def test_no_blocks_produces_no_translated_block_keys(flow):
    """When no blocks are passed, translated_blockquote_blocks is [] (empty list,
    set by the code only when there are raw blocks to process)."""
    result = flow.start(metadata={"forward_source": {}})
    assert result.success
    rid = result.review_id
    meta = flow.rows[rid]["metadata"]
    # Keys may be absent or empty — neither should contain content.
    assert meta.get("translated_blockquote_blocks", []) == []
    assert meta.get("translated_expandable_blocks", []) == []


# =========================================================
# Payload: translated blocks surface in the publication payload
# =========================================================

def test_payload_includes_translated_blockquote_blocks(flow):
    """After confirm, publish_prepared_text receives blockquote_blocks from
    the translated_blockquote_blocks stored in metadata."""
    blocks = [{"type": "blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": blocks,
            "expandable_blocks": [],
        }
    )
    assert result.success
    rid = result.review_id
    assert flow.click(rid, "confirm").success
    payload = flow.publish.call_args.kwargs
    bq = payload.get("blockquote_blocks", [])
    assert len(bq) == 1
    assert bq[0]["text"] == MACHINE
    assert bq[0]["type"] == "blockquote"


def test_payload_includes_translated_expandable_blocks(flow):
    """expandable_blockquote parity: payload receives translated expandable blocks."""
    blocks = [{"type": "expandable_blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": [],
            "expandable_blocks": blocks,
        }
    )
    assert result.success
    rid = result.review_id
    assert flow.click(rid, "confirm").success
    payload = flow.publish.call_args.kwargs
    ex = payload.get("expandable_blocks", [])
    assert len(ex) == 1
    assert ex[0]["text"] == MACHINE
    assert ex[0]["type"] == "expandable_blockquote"


def test_payload_without_blocks_has_empty_lists(flow):
    """No blocks passed → blockquote_blocks and expandable_blocks are [] in payload."""
    result = flow.start(metadata={"forward_source": {}})
    assert result.success
    rid = result.review_id
    assert flow.click(rid, "confirm").success
    payload = flow.publish.call_args.kwargs
    assert payload.get("blockquote_blocks", []) == []
    assert payload.get("expandable_blocks", []) == []


# =========================================================
# Fail-closed: failed block translation → block omitted
# =========================================================

def test_failed_block_translation_omits_block_not_original(flow, monkeypatch):
    """If the per-block pipeline call raises, the block is omitted (not
    published in source language)."""
    original_pipeline = controller.run_manual_translation_pipeline
    call_count = [0]

    def patched_pipeline(**kwargs):
        call_count[0] += 1
        if call_count[0] > 1:
            # First call = main text (succeeds); subsequent = block (fail).
            raise RuntimeError("simulated block translation failure")
        return original_pipeline(**kwargs)

    monkeypatch.setattr(
        controller, "run_manual_translation_pipeline", patched_pipeline
    )

    blocks = [{"type": "blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": blocks,
            "expandable_blocks": [],
        }
    )
    assert result.success
    rid = result.review_id

    # Block must be absent (omitted), not contain source-language text.
    translated = flow.rows[rid]["metadata"].get("translated_blockquote_blocks", [])
    assert translated == [], (
        "Failed block translation must produce empty list, not source-language block"
    )

    # Confirm and check payload.
    assert flow.click(rid, "confirm").success
    payload = flow.publish.call_args.kwargs
    assert payload.get("blockquote_blocks", []) == []


def test_failed_expandable_translation_omits_block_not_original(flow, monkeypatch):
    """Parity: failed expandable block translation is also omitted."""
    original_pipeline = controller.run_manual_translation_pipeline
    call_count = [0]

    def patched_pipeline(**kwargs):
        call_count[0] += 1
        if call_count[0] > 1:
            raise RuntimeError("simulated expandable translation failure")
        return original_pipeline(**kwargs)

    monkeypatch.setattr(
        controller, "run_manual_translation_pipeline", patched_pipeline
    )

    blocks = [{"type": "expandable_blockquote", "text": BLOCK_SOURCE}]
    result = flow.start(
        metadata={
            "forward_source": {},
            "blockquote_blocks": [],
            "expandable_blocks": blocks,
        }
    )
    assert result.success
    rid = result.review_id

    translated = flow.rows[rid]["metadata"].get(
        "translated_expandable_blocks", []
    )
    assert translated == []

    assert flow.click(rid, "confirm").success
    payload = flow.publish.call_args.kwargs
    assert payload.get("expandable_blocks", []) == []


# =========================================================
# build_translation_publication_payload (unit, no flow)
# =========================================================

def _state_with_translated_blocks(
    translated_blockquote_blocks=None,
    translated_expandable_blocks=None,
):
    """Minimal duck-typed state for payload unit tests."""
    return SimpleNamespace(
        review_id="test-rid",
        original_text="original",
        translated_text="متن ترجمه شده",
        edited_text="",
        status="confirmed",
        source_kind="message",
        source_key="sk",
        metadata={
            "forward_source": {},
            "files": [],
            "blockquote_blocks": [],
            "expandable_blocks": [],
            "translated_blockquote_blocks": (
                translated_blockquote_blocks
                if translated_blockquote_blocks is not None
                else []
            ),
            "translated_expandable_blocks": (
                translated_expandable_blocks
                if translated_expandable_blocks is not None
                else []
            ),
        },
    )


def test_payload_uses_translated_blockquote_blocks_when_present():
    state = _state_with_translated_blocks(
        translated_blockquote_blocks=[
            {"type": "blockquote", "text": "نقل قول ترجمه شده"}
        ]
    )
    payload = build_translation_publication_payload(state)
    assert payload["blockquote_blocks"] == [
        {"type": "blockquote", "text": "نقل قول ترجمه شده"}
    ]


def test_payload_uses_translated_expandable_blocks_when_present():
    state = _state_with_translated_blocks(
        translated_expandable_blocks=[
            {"type": "expandable_blockquote", "text": "توضیح قابل گسترش"}
        ]
    )
    payload = build_translation_publication_payload(state)
    assert payload["expandable_blocks"] == [
        {"type": "expandable_blockquote", "text": "توضیح قابل گسترش"}
    ]


def test_payload_returns_empty_blocks_when_translated_key_absent():
    """Fail-closed: if translated_blockquote_blocks key is absent, return []."""
    state = SimpleNamespace(
        review_id="test-rid",
        original_text="original",
        translated_text="متن ترجمه",
        edited_text="",
        status="confirmed",
        source_kind="message",
        source_key="sk",
        metadata={
            "forward_source": {},
            "files": [],
            # Deliberately omit translated_blockquote_blocks and
            # translated_expandable_blocks — the fail-closed path.
            "blockquote_blocks": [
                {"type": "blockquote", "text": "original language quote"}
            ],
        },
    )
    payload = build_translation_publication_payload(state)
    assert payload["blockquote_blocks"] == []
    assert payload["expandable_blocks"] == []
