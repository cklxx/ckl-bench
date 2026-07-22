"""SQLite cache for benchmark runs; JSON artifacts remain canonical."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 2
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    adapter TEXT,
    adapter_display TEXT,
    judge TEXT,
    reviewer TEXT,
    verifier TEXT,
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    score REAL,
    pass_rate REAL,
    cost_usd REAL,
    total_tokens INTEGER DEFAULT 0,
    started_at REAL,
    completed_at REAL,
    summary_json TEXT,
    progress_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT,
    passed INTEGER,
    score REAL,
    capability TEXT,
    difficulty TEXT,
    result_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_results_run_id ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_case_id ON results(case_id);
CREATE INDEX IF NOT EXISTS idx_results_status ON results(status);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _nullable_bool(value: Any) -> int | None:
    return None if value is None else int(bool(value))


def _nullable_float(value: Any) -> float | None:
    return None if value is None else float(value)


class RunDB:
    """Thread-safe SQLite store rebuildable from canonical JSON artifacts."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema()
        self._closed = False

    def _create_schema(self) -> None:
        for statement in _SCHEMA.split(";"):
            if statement.strip():
                self._conn.execute(statement)

    def _initialize_schema(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            self._create_schema()
            self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            return
        if version == 1:
            self._migrate_v1_to_v2()
            return
        if version != _SCHEMA_VERSION:
            raise RuntimeError(f"unsupported database schema version: {version}")
        self._create_schema()

    def _migrate_v1_to_v2(self) -> None:
        """Preserve every v1 row while replacing its lossy result projection."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute("ALTER TABLE results RENAME TO results_v1")
            self._create_schema()
            rows = self._conn.execute("SELECT * FROM results_v1 ORDER BY id").fetchall()
            for row in rows:
                old = dict(row)
                result: dict[str, Any] = {
                    "case_id": old["case_id"],
                    "passed": None if old["passed"] is None else bool(old["passed"]),
                    "score": old["score"],
                }
                for key in ("capability", "checks", "usage"):
                    raw = old.get(f"{key}_json") if f"{key}_json" in old else old.get(key)
                    if raw is not None:
                        result[key] = json.loads(raw)
                for key in ("difficulty", "response_text", "error", "cost_usd", "latency_ms"):
                    if old.get(key) is not None:
                        result[key] = old[key]
                self._insert_result(old["run_id"], result)
            self._conn.execute("DROP TABLE results_v1")
            self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def upsert_run(self, run: dict[str, Any]) -> None:
        with self._lock:
            self._upsert_run_unlocked(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else self._row_to_run(dict(row))

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._execute("SELECT * FROM runs ORDER BY started_at DESC, run_id DESC").fetchall()
        return [self._row_to_run(dict(row)) for row in rows]

    def replace_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        with self._lock:
            self._replace_results_unlocked(run_id, results)

    def finish_run(self, run: dict[str, Any], results: list[dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._upsert_run_unlocked(run)
                self._replace_results_unlocked(run["run_id"], results)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _upsert_run_unlocked(self, run: dict[str, Any]) -> None:
        summary = run.get("summary") or {}
        progress = run.get("progress")
        values = (
            run["run_id"], run.get("status", "pending"),
            summary.get("adapter") or run.get("adapter"),
            summary.get("adapter_display") or run.get("adapter_display"),
            summary.get("judge"), summary.get("reviewer"), summary.get("verifier"),
            int(summary.get("total", 0)), int(summary.get("passed", 0)), int(summary.get("failed", 0)),
            _nullable_float(summary.get("score")), _nullable_float(summary.get("pass_rate")),
            summary.get("cost_usd", summary.get("estimated_cost_usd")),
            int((summary.get("usage") or {}).get("total_tokens", 0)),
            run.get("started_at"), run.get("completed_at"),
            _json(summary) if summary else None, _json(progress) if progress else None, run.get("error"),
        )
        self._conn.execute(
            """INSERT INTO runs
            (run_id,status,adapter,adapter_display,judge,reviewer,verifier,total,passed,failed,score,pass_rate,cost_usd,total_tokens,started_at,completed_at,summary_json,progress_json,error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
            status=excluded.status,adapter=excluded.adapter,adapter_display=excluded.adapter_display,
            judge=excluded.judge,reviewer=excluded.reviewer,verifier=excluded.verifier,total=excluded.total,
            passed=excluded.passed,failed=excluded.failed,score=excluded.score,pass_rate=excluded.pass_rate,
            cost_usd=excluded.cost_usd,total_tokens=excluded.total_tokens,started_at=excluded.started_at,
            completed_at=excluded.completed_at,summary_json=excluded.summary_json,
            progress_json=excluded.progress_json,error=excluded.error""",
            values,
        )

    def _replace_results_unlocked(self, run_id: str, results: list[dict[str, Any]]) -> None:
        self._conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        for result in results:
            self._insert_result(run_id, result)

    def _insert_result(self, run_id: str, result: dict[str, Any]) -> None:
        capability = result.get("capability")
        self._conn.execute(
            """INSERT INTO results
            (run_id,case_id,status,passed,score,capability,difficulty,result_json)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                run_id, str(result.get("case_id", "")), result.get("status"),
                _nullable_bool(result.get("passed")), _nullable_float(result.get("score")),
                _json(capability) if capability is not None else None,
                result.get("difficulty"), _json(result),
            ),
        )

    def get_results(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT result_json FROM results WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid persisted result JSON for run {run_id}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"persisted result for run {run_id} is not an object")
            results.append(value)
        return results

    def run_ids(self) -> set[str]:
        return {row[0] for row in self._execute("SELECT run_id FROM runs").fetchall()}

    def rebuild_from_disk(self, runs_dir: Path) -> int:
        from .run_manager import collect_runs

        seen: set[str] = set()
        for run in collect_runs(runs_dir):
            self._import_run_from_disk(runs_dir, run)
            seen.add(run["run_id"])
        with self._lock:
            if seen:
                placeholders = ",".join("?" for _ in seen)
                self._conn.execute(
                    f"DELETE FROM runs WHERE run_id NOT IN ({placeholders})", tuple(sorted(seen))
                )
            else:
                self._conn.execute("DELETE FROM runs")
        return len(seen)

    def sync_from_disk(self, runs_dir: Path) -> int:
        from .run_manager import collect_runs

        existing = self.run_ids()
        imported = 0
        for run in collect_runs(runs_dir):
            if run["run_id"] not in existing:
                self._import_run_from_disk(runs_dir, run)
                imported += 1
        return imported

    def _import_run_from_disk(self, runs_dir: Path, run: dict[str, Any]) -> None:
        run.setdefault("status", "completed")
        run_id = run["run_id"]
        summary_path = runs_dir / run_id / "summary.json"
        if run.get("started_at") is None:
            try:
                run["started_at"] = summary_path.stat().st_mtime
            except OSError:
                pass
        results: list[dict[str, Any]] = []
        results_path = runs_dir / run_id / "results.jsonl"
        if results_path.exists():
            with results_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"invalid JSON in {results_path} at line {line_number}"
                        ) from exc
                    if not isinstance(value, dict):
                        raise ValueError(f"result in {results_path} at line {line_number} is not an object")
                    results.append(value)
        self.finish_run(run, results)

    @staticmethod
    def _row_to_run(row: dict[str, Any]) -> dict[str, Any]:
        summary = json.loads(row.pop("summary_json", None) or "{}")
        progress = json.loads(row.pop("progress_json", None) or "{}")
        return {
            "run_id": row["run_id"], "status": row["status"], "progress": progress,
            "summary": summary, "error": row.get("error"),
            "started_at": row.get("started_at"), "completed_at": row.get("completed_at"),
        }

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True
