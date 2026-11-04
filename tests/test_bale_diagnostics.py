"""Regression coverage for rejected Bale replies and credential-safe logs."""

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class BaleDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "_bale_diagnostics_test", Path(__file__).parents[1] / "core/bale_diagnostics.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        self.http = SimpleNamespace(get=Mock())
        with patch.dict(sys.modules, {"requests": self.http}):
            spec.loader.exec_module(self.module)
        self.env = patch.dict(os.environ, {"BALE_BOT_TOKEN": "private-test-token"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, status, body):
        return SimpleNamespace(status_code=status, json=lambda: body)

    def test_rejected_reply_is_logged_and_token_redacted(self):
        response = self.response(401, {"ok": False, "error_code": 401, "description": "invalid private-test-token"})
        with self.assertLogs(self.module.logger, level="ERROR") as logs:
            self.assertFalse(self.module.bale_response_ok(response, "sendMessage"))
        output = " ".join(logs.output)
        self.assertIn("status=401", output)
        self.assertIn("[REDACTED]", output)
        self.assertNotIn("private-test-token", output)

    def test_http_200_without_success_flag_is_not_success(self):
        with self.assertLogs(self.module.logger, level="ERROR"):
            self.assertFalse(self.module.bale_response_ok(self.response(200, {}), "sendMessage"))
        self.assertTrue(self.module.bale_response_ok(self.response(200, {"ok": True}), "sendMessage"))

    def test_invalid_json_is_reported(self):
        response = SimpleNamespace(status_code=502, json=Mock(side_effect=ValueError("bad JSON")))
        with self.assertLogs(self.module.logger, level="ERROR") as logs:
            self.assertFalse(self.module.bale_response_ok(response, "sendMessage"))
        self.assertIn("invalid JSON response", " ".join(logs.output))

    def test_startup_check_only_reads_bot_and_webhook(self):
        self.http.get.side_effect = [
            self.response(200, {"ok": True, "result": {"username": "test_bot", "id": 1}}),
            self.response(200, {"ok": True, "result": {"url": "https://example.test/bale/webhook?secret=hidden", "pending_update_count": 0}}),
        ]
        with self.assertLogs(self.module.logger, level="INFO") as logs:
            self.module.check_bale_connection()
        self.assertEqual([c.args[0].rsplit("/", 1)[-1] for c in self.http.get.call_args_list], ["getMe", "getWebhookInfo"])
        output = " ".join(logs.output)
        self.assertIn("bot_username=test_bot", output)
        self.assertNotIn("private-test-token", output)
        self.assertNotIn("secret=hidden", output)

    def test_transport_exception_does_not_expose_credential_url(self):
        self.http.get.side_effect = RuntimeError("https://tapi.bale.ai/botprivate-test-token/getMe")
        with self.assertLogs(self.module.logger, level="ERROR") as logs:
            self.module.check_bale_connection()
        self.assertIn("exception_type=RuntimeError", " ".join(logs.output))
        self.assertNotIn("private-test-token", " ".join(logs.output))

    def test_missing_token_does_not_make_requests(self):
        with patch.dict(os.environ, {"BALE_BOT_TOKEN": ""}):
            with self.assertLogs(self.module.logger, level="WARNING"):
                self.module.check_bale_connection()
        self.http.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
