"""Tests for the SQLite persistence layer (RunDB) and its integration with
RunManager."""

from __future__ import annotations

import json
import sqlite3
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

    def test_nullable_cost_roundtrip(self) -> None:
        db = RunDB(self._db_path)
        db.upsert_run({
            "run_id": "r1",
            "status": "completed",
            "summary": {"adapter": "mock", "cost_usd": None, "estimated_cost_usd": None},
        })
        db.replace_results(
            "r1",
            [{"case_id": "a", "passed": True, "score": 1.0, "cost_usd": None}],
        )
        fetched = db.get_run("r1")
        assert fetched is not None
        self.assertIsNone(fetched["summary"]["cost_usd"])
        self.assertIsNone(db.get_results("r1")[0]["cost_usd"])
        db.close()

    def test_lossless_nullable_result_roundtrip(self) -> None:
        db = RunDB(self._db_path)
        db.upsert_run({
            "run_id": "r1",
            "status": "completed",
            "summary": {"score": None, "pass_rate": None},
        })
        result = {
            "case_id": "a",
            "status": "error",
            "passed": None,
            "score": None,
            "attempt": 2,
            "raw_response": {"future": [1, 2]},
            "unknown_future_field": {"kept": True},
        }
        db.replace_results("r1", [result])
        self.assertEqual(db.get_results("r1"), [result])
        db.close()

    def test_v1_migration_preserves_rows_and_is_idempotent(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
            adapter TEXT, adapter_display TEXT, judge TEXT, reviewer TEXT, verifier TEXT,
            total INTEGER DEFAULT 0, passed INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
            score REAL DEFAULT 0, pass_rate REAL DEFAULT 0, cost_usd REAL DEFAULT 0,
            total_tokens INTEGER DEFAULT 0, started_at REAL, completed_at REAL,
            summary_json TEXT, progress_json TEXT, error TEXT
        );
        CREATE TABLE results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
            passed INTEGER, score REAL, capability TEXT, difficulty TEXT, checks_json TEXT,
            response_text TEXT, error TEXT, usage_json TEXT, cost_usd REAL, latency_ms REAL
        );
        INSERT INTO runs (run_id,status,summary_json) VALUES ('r1','completed','{"score":null}');
        INSERT INTO results
            (run_id,case_id,passed,score,capability,checks_json,response_text,error)
            VALUES ('r1','c1',NULL,NULL,'["code"]','[]','answer','timeout');
        PRAGMA user_version=1;
        """)
        conn.close()
        db = RunDB(self._db_path)
        self.assertEqual(db.get_results("r1")[0]["passed"], None)
        self.assertEqual(db.get_results("r1")[0]["capability"], ["code"])
        db.close()
        reopened = RunDB(self._db_path)
        self.assertEqual(len(reopened.get_results("r1")), 1)
        reopened.close()

    def test_unknown_schema_is_not_destroyed(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript("CREATE TABLE marker(value TEXT); INSERT INTO marker VALUES ('keep'); PRAGMA user_version=99;")
        conn.close()
        with self.assertRaisesRegex(RuntimeError, "unsupported database schema"):
            RunDB(self._db_path)
        conn = sqlite3.connect(self._db_path)
        self.assertEqual(conn.execute("SELECT value FROM marker").fetchone()[0], "keep")
        conn.close()

    def test_rebuild_rejects_malformed_results(self) -> None:
        runs_dir = Path(self._tmp.name) / "malformed"
        _write_run(runs_dir, "r1")
        (runs_dir / "r1" / "results.jsonl").write_text("{not-json}\n")
        db = RunDB(self._db_path)
        with self.assertRaisesRegex(ValueError, "line 1"):
            db.rebuild_from_disk(runs_dir)
        db.close()

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


class NormalizeResultsTests(unittest.TestCase):
    """Results loaded from stale DB rows or result files may store
    ``capability`` as a plain string or omit it.  The normalisation step
    must guarantee the frontend always receives a list."""

    def setUp(self) -> None:
        from ckl_bench.core.run_manager import _normalize_results

        self._normalize = _normalize_results

    def test_string_capability_becomes_list(self) -> None:
        results = [{"case_id": "c1", "capability": "code"}]
        norm = self._normalize(results)
        self.assertEqual(norm[0]["capability"], ["code"])

    def test_missing_capability_becomes_empty_list(self) -> None:
        results = [{"case_id": "c1"}]
        norm = self._normalize(results)
        self.assertEqual(norm[0]["capability"], [])

    def test_none_capability_becomes_empty_list(self) -> None:
        results = [{"case_id": "c1", "capability": None}]
        norm = self._normalize(results)
        self.assertEqual(norm[0]["capability"], [])

    def test_non_list_capability_becomes_empty_list(self) -> None:
        results = [{"case_id": "c1", "capability": 42}]
        norm = self._normalize(results)
        self.assertEqual(norm[0]["capability"], [])

    def test_list_capability_unchanged(self) -> None:
        results = [{"case_id": "c1", "capability": ["code", "math"]}]
        norm = self._normalize(results)
        self.assertEqual(norm[0]["capability"], ["code", "math"])


if __name__ == "__main__":
    unittest.main()
