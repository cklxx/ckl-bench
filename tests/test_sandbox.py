from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evalbench.core.sandbox import run_python_script


class SandboxTests(unittest.TestCase):
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

        os.environ["EVB_SECRET_PROBE"] = "should-not-leak"
        try:
            result = run_python_script(
                "import os; print(os.environ.get('EVB_SECRET_PROBE', 'absent'))"
            )
        finally:
            os.environ.pop("EVB_SECRET_PROBE", None)
        self.assertIn("absent", result.stdout)

    def test_no_pycache_left_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
            run_python_script("import mod\n", cwd=workspace, timeout_s=10)
            self.assertFalse((workspace / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
