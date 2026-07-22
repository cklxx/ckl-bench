from __future__ import annotations

import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ckl_bench.adapters._http import (
    HTTPRequestError,
    _PolicyRedirectHandler,
    request_json,
    safe_url_label,
    validate_outbound_url,
)
from ckl_bench.adapters.command import CommandAdapter
from ckl_bench.core.paths import UnsafePathError, copy_tree_safely, safe_join, validate_owned_path


class PathSecurityTests(unittest.TestCase):
    def test_safe_join_rejects_parent_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            self.assertRaises(UnsafePathError, safe_join, root, "../escape")
            (root / "link").symlink_to(outside, target_is_directory=True)
            self.assertRaises(UnsafePathError, safe_join, root, "link/file")

    def test_validate_owned_path_rejects_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as owned, tempfile.TemporaryDirectory() as external:
            self.assertRaises(UnsafePathError, validate_owned_path, Path(owned), Path(external))

    def test_safe_copy_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as parent:
            source = Path(src)
            (source / "ok.txt").write_text("ok", encoding="utf-8")
            (source / "leak").symlink_to("/etc/passwd")
            destination = Path(parent) / "copy"
            copy_tree_safely(source, destination)
            self.assertTrue((destination / "ok.txt").exists())
            self.assertFalse((destination / "leak").exists())


class CommandSecurityTests(unittest.TestCase):
    def test_string_command_is_argv_and_shell_false(self) -> None:
        adapter = CommandAdapter({"command": "python -V"})
        self.assertEqual(adapter.command, ["python", "-V"])
        self.assertFalse(adapter.shell)

    def test_shell_requires_explicit_trust(self) -> None:
        with self.assertRaisesRegex(ValueError, "trusted_shell"):
            CommandAdapter({"command": "python -V", "shell": True})
        adapter = CommandAdapter({"command": "python -V", "shell": True, "trusted_shell": True})
        self.assertTrue(adapter.shell)


class HTTPPolicyTests(unittest.TestCase):
    @mock.patch("socket.getaddrinfo")
    def test_public_https_allowed(self, getaddrinfo: mock.Mock) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        self.assertEqual(validate_outbound_url("https://example.com/api"), "https://example.com/api")

    @mock.patch("socket.getaddrinfo")
    def test_private_and_http_rejected_by_default(self, getaddrinfo: mock.Mock) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with self.assertRaisesRegex(HTTPRequestError, "non-public"):
            validate_outbound_url("https://localhost/api")
        with self.assertRaisesRegex(HTTPRequestError, "HTTPS"):
            validate_outbound_url("http://example.com/api")

    @mock.patch("socket.getaddrinfo")
    def test_explicit_trusted_local_policy(self, getaddrinfo: mock.Mock) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]
        self.assertEqual(
            validate_outbound_url("http://127.0.0.1:8000/v1", trusted_local=True),
            "http://127.0.0.1:8000/v1",
        )

    def test_safe_label_strips_credentials_query_and_fragment(self) -> None:
        self.assertEqual(
            safe_url_label("https://user:secret@example.com/path?token=secret#x"),
            "https://example.com/path",
        )

    @mock.patch("ckl_bench.adapters._http.validate_outbound_url")
    def test_cross_origin_redirect_strips_credentials(self, validate: mock.Mock) -> None:
        handler = _PolicyRedirectHandler(False)
        request = __import__("urllib.request").request.Request(
            "https://api.example/start",
            data=b"{}",
            headers={"Authorization": "Bearer secret", "Cookie": "a=b", "X-Test": "ok"},
            method="POST",
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://other.example/next"
        )
        self.assertIsNotNone(redirected)
        lowered = {key.lower() for key in redirected.headers}
        self.assertNotIn("authorization", lowered)
        self.assertNotIn("cookie", lowered)
        self.assertIn("x-test", lowered)
        validate.assert_called_once()

    @mock.patch.dict(os.environ, {"CKL_MAX_RETRIES": "1", "CKL_RETRY_BASE_DELAY": "0"})
    @mock.patch("ckl_bench.adapters._http.validate_outbound_url")
    @mock.patch("ckl_bench.adapters._http.urllib.request.build_opener")
    def test_retryable_http_error_retries(self, build_opener: mock.Mock, validate: mock.Mock) -> None:
        error = urllib.error.HTTPError(
            "https://example.com", 503, "unavailable", {}, io.BytesIO(b"retry")
        )
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        opener = build_opener.return_value
        opener.open.side_effect = [error, response]
        result = request_json("https://example.com", data=b"{}", headers={})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(opener.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
