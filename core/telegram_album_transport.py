"""Run album HTTP requests in a bounded, killable process.

Socket timeouts do not bound DNS resolution or an entire response. A child
process gives an album a real deadline without leaving abandoned sender
threads which could send the same album after a retry.
"""

import json
import pickle
import subprocess
import sys
import threading

import requests

from core.transport_errors import DeliveryOutcomeUnknown

ALBUM_REQUEST_DEADLINE = 75
_slots = threading.BoundedSemaphore(2)


def post_album(url, request_kwargs, socket_timeout):
    if not _slots.acquire(blocking=False):
        raise RuntimeError("album transport busy; no request submitted")
    try:
        request = pickle.dumps((url, request_kwargs, socket_timeout))
        try:
            result = subprocess.run(
                [sys.executable, "-m", "core.telegram_album_transport"],
                input=request, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=ALBUM_REQUEST_DEADLINE, check=False,
            )
        except subprocess.TimeoutExpired:
            # subprocess.run kills AND reaps the child before raising.
            raise DeliveryOutcomeUnknown("Telegram album exceeded its wall-clock deadline") from None
        try:
            body = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise DeliveryOutcomeUnknown("album transport exited without a response") from None
        if body.get("not_sent"):
            raise requests.exceptions.ConnectTimeout("album connection timed out before sending")
        if body.get("unknown") or result.returncode != 0:
            raise DeliveryOutcomeUnknown("Telegram album response was not confirmed")
        response = requests.Response()
        response.status_code = int(body["status"])
        response._content = body["text"].encode("utf-8")
        response.encoding = "utf-8"
        return response
    finally:
        _slots.release()


def _worker():
    # stdin contains only the parent process's own trusted request, never a
    # network response. Credentials are not passed in command-line arguments.
    url, kwargs, timeout = pickle.load(sys.stdin.buffer)
    try:
        response = requests.post(url, **kwargs, timeout=timeout)
        result = {"status": response.status_code, "text": response.text}
    except requests.exceptions.ConnectTimeout:
        result = {"not_sent": True}
    except Exception:
        # Exceptions can contain credential-bearing URLs: never serialize them.
        result = {"unknown": True}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    _worker()
