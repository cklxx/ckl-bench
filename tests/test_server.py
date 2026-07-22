from __future__ import annotations

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ckl_bench.core.server import BenchServer, _make_handler
from ckl_bench.core.settings import settings_from_dict


class _Manager:
    def __init__(self) -> None:
        self.started: dict[str, object] | None = None
        self.cancelled: list[str] = []

    def list_runs(self):
        return []

    def get_run(self, run_id: str):
        if run_id == "missing":
            return None
        return {"run_id": run_id, "status": "failed", "progress": {}}

    def get_run_results(self, run_id: str):
        return [{"case_id": "case", "score": None, "passed": None}]

    def start_run(self, **kwargs):
        self.started = kwargs
        return "run-1"

    def cancel_run(self, run_id: str):
        self.cancelled.append(run_id)
        return True


class ServerSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.server = BenchServer.__new__(BenchServer)
        self.server.host = "127.0.0.1"
        self.server.port = 0
        self.server.token = "test-token"
        self.server.origin = "http://dashboard.test"
        self.server.runs_dir = root / "runs"
        self.server.cases_dir = root / "cases"
        self.server.runs_dir.mkdir()
        self.server.cases_dir.mkdir()
        self.server.manager = _Manager()
        self.server.settings = settings_from_dict({})
        self.server._case_lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.server))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, method: str, path: str, body=None, *, token=True, origin=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer test-token"
        if origin is not None:
            headers["Origin"] = origin
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port)
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        result = response.status, dict(response.getheaders()), raw
        conn.close()
        return result

    def test_api_requires_bearer_and_exact_origin(self) -> None:
        status, headers, _ = self.request("GET", "/api/runs", token=False)
        self.assertEqual(status, 401)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

        status, _, _ = self.request(
            "GET", "/api/runs", origin="http://evil.test"
        )
        self.assertEqual(status, 403)

        status, headers, _ = self.request(
            "GET", "/api/runs", origin=self.server.origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.server.origin)
        self.assertEqual(headers["Vary"], "Origin")

    def test_preflight_requires_authentication(self) -> None:
        status, _, _ = self.request(
            "OPTIONS", "/api/runs", token=False, origin=self.server.origin
        )
        self.assertEqual(status, 401)
        status, headers, _ = self.request(
            "OPTIONS", "/api/runs", origin=self.server.origin
        )
        self.assertEqual(status, 204)
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])

    def test_dashboard_rejects_dynamic_adapter_config_and_paths(self) -> None:
        for body in (
            {"adapter": "module:Class"},
            {"adapter": "mock", "config": {"command": "sh -c id"}},
            {"adapter": "mock", "case_paths": ["/tmp"]},
            {"adapter": "mock", "cache_dir": "/tmp/cache"},
        ):
            status, _, raw = self.request("POST", "/api/runs", body)
            self.assertEqual(status, 400, raw)
        self.assertIsNone(self.server.manager.started)

    def test_trusted_mock_launch_and_cancel(self) -> None:
        status, _, raw = self.request(
            "POST", "/api/runs", {"adapter": "mock", "repeat": 2}
        )
        self.assertEqual(status, 202, raw)
        self.assertEqual(self.server.manager.started["adapter_name"], "mock")

        self.server.manager.get_run = lambda run_id: {
            "run_id": run_id,
            "status": "running",
            "progress": {},
        }
        status, _, raw = self.request("POST", "/api/runs/run-1/cancel", {})
        self.assertEqual(status, 202, raw)
        self.assertEqual(self.server.manager.cancelled, ["run-1"])

    def test_failed_run_includes_partial_results(self) -> None:
        status, _, raw = self.request("GET", "/api/runs/run-1")
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual(data["results"][0]["score"], None)

    def test_settings_reject_executable_and_endpoint_overrides(self) -> None:
        status, _, raw = self.request(
            "PUT",
            "/api/settings",
            {"adapters": {"codex": {"command": "sh -c id"}}},
        )
        self.assertEqual(status, 400, raw)
        status, _, raw = self.request(
            "POST",
            "/api/settings/test",
            {"adapter_name": "codex", "config": {"base_url": "http://127.0.0.1"}},
        )
        self.assertEqual(status, 400, raw)

    def test_internal_errors_are_sanitized(self) -> None:
        self.server.manager.list_runs = lambda: (_ for _ in ()).throw(
            RuntimeError("secret filesystem detail")
        )
        status, _, raw = self.request("GET", "/api/runs")
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(raw), {"error": "internal server error"})
        self.assertNotIn(b"secret", raw)

    def test_bootstrap_is_not_cached(self) -> None:
        with patch(
            "ckl_bench.core.server._render_react_page",
            return_value="<html>ok</html>",
        ) as render:
            status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(render.call_args.args[0]["api_token"], "test-token")


if __name__ == "__main__":
    unittest.main()
