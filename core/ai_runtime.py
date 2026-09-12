"""Transport reuse and content-free timing for synchronous AI providers."""

import logging
import os
import threading
import time
from functools import wraps

import requests

logger = logging.getLogger(__name__)
_sessions = threading.local()


def provider_post(*args, **kwargs):
    # A Session is never shared by concurrent worker threads. Request payloads,
    # credentials and timeouts stay on each call, not on the Session.
    session = getattr(_sessions, "session", None)
    if session is None or getattr(_sessions, "pid", None) != os.getpid():
        session = _sessions.session = requests.Session()
        _sessions.pid = os.getpid()
    # Default adapters have zero retries; provider-specific policy owns retries.
    return session.post(*args, **kwargs)


def timed_stage(stage, *, provider="local", model=None):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                logger.info(
                    "AI-TIMING | stage=%s | elapsed_ms=%.1f | provider=%s | model=%s",
                    stage, (time.perf_counter() - started) * 1000,
                    provider, model() if model else "-",
                )
        return measured
    return decorate
