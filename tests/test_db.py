"""Tests for the SQLite persistence layer (RunDB) and its integration with
RunManager."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ckl_bench.core.db import RunDB
from ckl_bench.core.run_manager import RunManager


def _write_run(runs_dir: Path, run_id: str, **summary_kwargs: object) -> None:
    """Create a minimal completed run on disk."""
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    summary: dict[str, object] = {
        "run_id": run_id,
        "adapter": "command",
        "adapter_display": "dsx",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "score": 1.0,
        "pass_rate": 1.0,
        "by_capability": {"code": {"count": 1, "passed": 1, "score": 1.0}},
    }
    summary.update(summary_kwargs)
    (run_dir / "summary.json").write_text(json.dumps(summary))
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "case_id": "c1",
                "passed": True,
                "score": 1.0,
                "capability": ["code"],
                "checks": [],
            }
        )
        + "\n"
    )


class RunDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_upsert_and_get_run(self) -> None:
        db = RunDB(self._db_path)
        run = {
            "run_id": "r1",
            "status": "completed",
            "summary": {"adapter": "mock", "adapter_display": "mock"},
        }
        db.upsert_run(run)
        fetched = db.get_run("r1")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["status"], "completed")
        self.assertEqual(fetched["summary"]["adapter"], "mock")
        db.close()

    def test_replace_results(self) -> None:
        db = RunDB(self._db_path)
        db.upsert_run({"run_id": "r1", "status": "completed"})
        db.replace_results(
            "r1",
            [
                {"case_id": "a", "passed": True, "score": 1.0},
                {"case_id": "b", "passed": False, "score": 0.0},
            ],
        )
        results = db.get_results("r1")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["case_id"], "a")
        # Replace again — should overwrite, not append.
        db.replace_results("r1", [{"case_id": "c", "passed": True, "score": 0.5}])
        self.assertEqual(len(db.get_results("r1")), 1)
        db.close()

    def test_rebuild_from_disk(self) -> None:
        runs_dir = Path(self._tmp.name) / "runs"
        runs_dir.mkdir()
        _write_run(runs_dir, "20240101T000000Z")
        db = RunDB(self._db_path)
        count = db.rebuild_from_disk(runs_dir)
        self.assertEqual(count, 1)
        self.assertIsNotNone(db.get_run("20240101T000000Z"))
        db.close()


class RunManagerDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._runs_dir = Path(self._tmp.name) / "runs"
        self._cases_dir = Path(self._tmp.name) / "cases"
        self._runs_dir.mkdir()
        self._cases_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_runs_from_db(self) -> None:
        _write_run(self._runs_dir, "20240101T000000Z")
        mgr = RunManager(
            self._runs_dir,
            self._cases_dir,
            db_path=self._runs_dir / "ckl-bench.db",
        )
        runs = mgr.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["summary"]["adapter_display"], "dsx")

    def test_get_run_from_db(self) -> None:
        _write_run(self._runs_dir, "20240101T000000Z")
        mgr = RunManager(
            self._runs_dir,
            self._cases_dir,
            db_path=self._runs_dir / "ckl-bench.db",
        )
        run = mgr.get_run("20240101T000000Z")
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["summary"]["adapter_display"], "dsx")

    def test_get_run_results_from_db(self) -> None:
        _write_run(self._runs_dir, "20240101T000000Z")
        mgr = RunManager(
            self._runs_dir,
            self._cases_dir,
            db_path=self._runs_dir / "ckl-bench.db",
        )
        results = mgr.get_run_results("20240101T000000Z")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["case_id"], "c1")

    def test_no_db_falls_back_to_disk(self) -> None:
        _write_run(self._runs_dir, "20240101T000000Z")
        mgr = RunManager(self._runs_dir, self._cases_dir)
        runs = mgr.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["summary"]["adapter_display"], "dsx")


if __name__ == "__main__":
    unittest.main()
