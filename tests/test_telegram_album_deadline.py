import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from core import telegram_album_transport as transport
from core.transport_errors import DeliveryOutcomeUnknown


def test_album_preserves_payload_and_telegram_response(monkeypatch):
    captured = []

    def run(command, **kwargs):
        import pickle
        captured.append(pickle.loads(kwargs["input"]))
        assert "secret-token" not in " ".join(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": 200, "text": json.dumps({"ok": True, "result": [{"message_id": 41}, {"message_id": 42}]}),
        }).encode())

    monkeypatch.setattr(transport.subprocess, "run", run)
    payload = {"chat_id": "@target", "media": [
        {"type": "photo", "media": "first", "caption": "متن", "caption_entities": [{"type": "bold", "offset": 0, "length": 3}]},
        {"type": "photo", "media": "second"},
    ]}
    response = transport.post_album("https://example.test/botsecret-token/sendMediaGroup", {"json": payload}, (10, 60))
    assert captured[0][1]["json"] == payload
    assert response.json()["result"] == [{"message_id": 41}, {"message_id": 42}]


def test_deadline_does_not_retry_or_expose_token_and_releases_slot(monkeypatch):
    calls = []

    def hung(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("secret-token", kwargs["timeout"])

    monkeypatch.setattr(transport.subprocess, "run", hung)
    for _ in range(3):
        with pytest.raises(DeliveryOutcomeUnknown) as error:
            transport.post_album("secret-token", {"json": {}}, (10, 60))
        assert "secret-token" not in str(error.value)
    assert len(calls) == 3  # Exactly one attempt per call; slots never leak.


def test_real_stalled_response_is_killed_within_wall_clock_deadline(monkeypatch):
    received = threading.Event()
    release = threading.Event()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            received.set()
            self.send_response(200)
            self.send_header("Content-Length", "999")
            self.end_headers()
            release.wait(5)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(transport, "ALBUM_REQUEST_DEADLINE", 1.5)
    started = time.monotonic()
    try:
        with pytest.raises(DeliveryOutcomeUnknown):
            transport.post_album(f"http://127.0.0.1:{server.server_port}/sendMediaGroup", {"json": {"media": []}}, (10, 60))
        assert received.is_set()
        assert time.monotonic() - started < 4
        assert len(calls) == 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()


def test_uncertain_destination_is_terminal_without_blocking_other_targets():
    from core.publication_state import InMemoryPublicationStateStore

    store = InMemoryPublicationStateStore()
    first = store.begin_attempt("album:1", "first")
    assert first is not None
    store.mark_failed("album:1", "first", str(DeliveryOutcomeUnknown("no confirmation")))
    assert store.get_delivery("album:1", "first").status == "failed_terminal"
    assert store.begin_attempt("album:1", "first") is None
    assert store.begin_attempt("album:1", "second") is not None


@pytest.mark.parametrize("status", [200, 400])
def test_real_worker_returns_api_response_without_altering_album(status):
    captured = []
    api_body = {"ok": status == 200, "result": [{"message_id": 41}, {"message_id": 42}]}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps(api_body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    payload = {"chat_id": "@target", "media": [{"type": "photo", "media": "one"}, {"type": "photo", "media": "two"}]}
    try:
        response = transport.post_album(f"http://127.0.0.1:{server.server_port}/sendMediaGroup", {"json": payload}, (10, 60))
        assert response.status_code == status
        assert response.json() == api_body
        assert captured == [payload]
    finally:
        server.shutdown()
        server.server_close()


def test_pipeline_continues_after_unknown_album_and_does_not_resend(monkeypatch):
    from core import publication_engine as engine
    from core.content_model import PreparedContent, PublicationTarget
    from core.publication_state import InMemoryPublicationStateStore

    calls = []
    targets = [PublicationTarget(f"target:{i}", "workspace", "telegram", f"@target{i}", i, i) for i in (1, 2)]
    prepared = PreparedContent(main_text="متن", source_key="album:deadline", files=[{"type": "photo", "file_id": "one"}, {"type": "photo", "file_id": "two"}])
    plan = {"media_caption": "متن", "followup_messages": [], "blockquote_messages": []}
    monkeypatch.setattr(engine, "_shared_content_analysis", lambda p: p)
    monkeypatch.setattr(engine, "_target_content_and_branding", lambda *_: ("متن", ""))
    monkeypatch.setattr("core.caption_manager.analyze_content", lambda **_: SimpleNamespace(telegram=plan, bale=plan, text={}))

    def execute(chat, api, target, *args):
        calls.append(target.destination_id)
        if target.destination_id == 1:
            raise DeliveryOutcomeUnknown("deadline")
        return {"ok": True, "message_id": 42, "message_ids": (42, 43)}

    monkeypatch.setattr(engine, "_execute_delivery_part", execute)
    store = InMemoryPublicationStateStore()
    engine.publish_prepared_content(1, "api", prepared, targets, store)
    engine.publish_prepared_content(1, "api", prepared, targets, store)
    assert calls == [1, 2]
