from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ckl_bench.core.cases import EvalCase
from ckl_bench.core.run_manager import RunManager, RunState


class RunManagerContractTests(unittest.TestCase):
    def test_progress_preserves_attempt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = RunManager(root / "runs", root / "cases")
            manager._states["r1"] = RunState(run_id="r1", status="running")
            manager._on_progress("r1", {
                "type": "run_started", "run_id": "r1", "total_cases": 1,
                "repeat": 2, "planned_attempts": 2,
            })
            manager._on_progress("r1", {
                "type": "attempt_started", "run_id": "r1", "case_id": "case",
                "attempt": 1,
            })
            manager._on_progress("r1", {
                "type": "attempt_completed", "run_id": "r1", "case_id": "case",
                "attempt": 1, "status": "error", "score": None, "passed": None,
                "error": "RuntimeError: boom", "error_type": "RuntimeError",
            })
            progress = manager.get_run("r1")["progress"]
            self.assertEqual(progress["planned_attempts"], 2)
            self.assertEqual(progress["error_attempts"], 1)
            self.assertEqual(progress["attempts"]["case:1"]["score"], None)

    def test_db_failure_cannot_skip_cleanup_or_terminal_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = RunManager(root / "runs", root / "cases")
            manager._db = unittest.mock.Mock()
            manager._db.finish_run.side_effect = RuntimeError("db secret detail")
            state = RunState(run_id="r1", status="pending")
            manager._states["r1"] = state
            manager._threads["r1"] = threading.current_thread()
            manager._cancel_flags["r1"] = threading.Event()
            events: list[dict[str, object]] = []
            manager.add_listener(events.append)
            case = EvalCase(
                id="c.v1", title="c", type="chat", input={"prompt": "x"},
                expectations=[], capability=[], difficulty=None, timeout_s=None,
                metadata={}, source_path=Path("inline.jsonl"), source_line=1,
            )
            result = {"summary": {"run_id": "r1"}, "results": []}
            with patch("ckl_bench.core.run_manager.run_cases", return_value=result):
                manager._run_worker("r1", [case], object(), unittest.mock.Mock(), threading.Event())
            self.assertNotIn("r1", manager._threads)
            self.assertNotIn("r1", manager._cancel_flags)
            self.assertEqual(events[-1]["type"], "run_finished")
            self.assertIn("persistence failed: RuntimeError", state.error or "")
            self.assertNotIn("secret detail", state.error or "")


if __name__ == "__main__":
    unittest.main()
