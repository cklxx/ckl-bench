from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ckl_bench.core.sandbox import run_python_script


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._unsafe = os.environ.get("CKL_ALLOW_UNSAFE_LOCAL_EXECUTION")
        os.environ["CKL_ALLOW_UNSAFE_LOCAL_EXECUTION"] = "1"

    def tearDown(self) -> None:
        if self._unsafe is None:
            os.environ.pop("CKL_ALLOW_UNSAFE_LOCAL_EXECUTION", None)
        else:
            os.environ["CKL_ALLOW_UNSAFE_LOCAL_EXECUTION"] = self._unsafe

    def test_fails_closed_without_backend_or_opt_in(self) -> None:
        os.environ.pop("CKL_ALLOW_UNSAFE_LOCAL_EXECUTION", None)
        with mock.patch("ckl_bench.core.sandbox._container_backend", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "no container backend"):
                run_python_script("print('blocked')")
        os.environ["CKL_ALLOW_UNSAFE_LOCAL_EXECUTION"] = "1"

    def test_container_timeout_forcibly_removes_container(self) -> None:
        os.environ.pop("CKL_ALLOW_UNSAFE_LOCAL_EXECUTION", None)
        calls: list[list[str]] = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[1] == "run":
                cid_path = Path(command[command.index("--cidfile") + 1])
                cid_path.write_text("container-123\n", encoding="utf-8")
                raise __import__("subprocess").TimeoutExpired(command, 0.1)
            return mock.Mock(returncode=0)

        with mock.patch("ckl_bench.core.sandbox._container_backend", return_value="docker"), mock.patch(
            "ckl_bench.core.sandbox.subprocess.run", side_effect=fake_run
        ):
            result = run_python_script("while True: pass", timeout_s=0.1)
        self.assertTrue(result.timed_out)
        self.assertEqual(calls[1], ["docker", "rm", "-f", "container-123"])
        os.environ["CKL_ALLOW_UNSAFE_LOCAL_EXECUTION"] = "1"

    def test_runs_and_captures_stdout(self) -> None:
        result = run_python_script("print('hello')")
        self.assertTrue(result.ok)
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello", result.stdout)
        self.assertFalse(result.timed_out)

    def test_nonzero_exit_is_not_ok(self) -> None:
        result = run_python_script("raise SystemExit(3)")
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 3)

    def test_assertion_failure_surfaces(self) -> None:
        result = run_python_script("assert 1 == 2, 'boom'")
        self.assertFalse(result.ok)
        self.assertIn("boom", result.stderr)

    def test_timeout(self) -> None:
        result = run_python_script("import time; time.sleep(5)", timeout_s=0.3)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)

    def test_can_import_candidate_file_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "solution.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            test = (
                "from solution import add\n"
                "assert add(2, 3) == 5\n"
                "print('PASS')\n"
            )
            result = run_python_script(test, cwd=workspace, timeout_s=10)
            self.assertTrue(result.ok, result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_credentials_are_scrubbed(self) -> None:
        import os

        os.environ["CKL_SECRET_PROBE"] = "should-not-leak"
        try:
            result = run_python_script(
                "import os; print(os.environ.get('CKL_SECRET_PROBE', 'absent'))"
            )
        finally:
            os.environ.pop("CKL_SECRET_PROBE", None)
        self.assertIn("absent", result.stdout)

    def test_no_pycache_left_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
            run_python_script("import mod\n", cwd=workspace, timeout_s=10)
            self.assertFalse((workspace / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
