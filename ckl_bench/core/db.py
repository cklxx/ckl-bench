"""SQLite persistence layer for ckl-bench runs.

Stores run metadata and per-case results in a local SQLite database so the
dashboard can list, filter, and sort runs without scanning the filesystem on
every request.  JSON files on disk remain the canonical export; the DB is a
query-optimized cache that can be rebuilt from disk at any time.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'pending',
    adapter       TEXT,
    adapter_display TEXT,
    judge         TEXT,
    reviewer      TEXT,
    verifier      TEXT,
    total         INTEGER DEFAULT 0,
    passed        INTEGER DEFAULT 0,
    failed        INTEGER DEFAULT 0,
    score         REAL DEFAULT 0,
    pass_rate     REAL DEFAULT 0,
    cost_usd      REAL DEFAULT 0,
    total_tokens  INTEGER DEFAULT 0,
    started_at    REAL,
    completed_at  REAL,
    summary_json  TEXT,
    progress_json TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    case_id       TEXT NOT NULL,
    passed        INTEGER,
    score         REAL,
    capability    TEXT,
    difficulty    TEXT,
    checks_json   TEXT,
    response_text TEXT,
    error         TEXT,
    usage_json    TEXT,
    cost_usd      REAL,
    latency_ms    REAL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_run_id ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
"""


class RunDB:
    """Thread-safe SQLite store for run metadata and results."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, _SCHEMA_VERSION):
            self._conn.executescript("DROP TABLE IF EXISTS results; DROP TABLE IF EXISTS runs;")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
        self._closed = False

    # -- Low-level helpers ---------------------------------------------------

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, params_list)

    # -- Runs ----------------------------------------------------------------

    def upsert_run(self, run: dict[str, Any]) -> None:
        """Insert or update a run row from a run-state dict (as returned by
        ``RunManager``).  Only writes fields that are present in *run*."""
        summary = run.get("summary") or {}
        progress = run.get("progress")
        self._execute(
            """
            INSERT INTO runs (
                run_id, status, adapter, adapter_display, judge, reviewer,
                verifier, total, passed, failed, score, pass_rate, cost_usd,
                total_tokens, started_at, completed_at, summary_json,
                progress_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                adapter=excluded.adapter,
                adapter_display=excluded.adapter_display,
                judge=excluded.judge,
                reviewer=excluded.reviewer,
                verifier=excluded.verifier,
                total=excluded.total,
                passed=excluded.passed,
                failed=excluded.failed,
                score=excluded.score,
                pass_rate=excluded.pass_rate,
                cost_usd=excluded.cost_usd,
                total_tokens=excluded.total_tokens,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                summary_json=excluded.summary_json,
                progress_json=excluded.progress_json,
                error=excluded.error
            """,
            (
                run["run_id"],
                run.get("status", "pending"),
                summary.get("adapter") or run.get("adapter"),
                summary.get("adapter_display") or run.get("adapter_display"),
                summary.get("judge"),
                summary.get("reviewer"),
                summary.get("verifier"),
                int(summary.get("total", 0)),
                int(summary.get("passed", 0)),
                int(summary.get("failed", 0)),
                float(summary.get("score", 0)),
                float(summary.get("pass_rate", 0)),
                summary.get("cost_usd", summary.get("estimated_cost_usd")),
                int((summary.get("usage") or {}).get("total_tokens", 0)),
                run.get("started_at"),
                run.get("completed_at"),
                json.dumps(summary, ensure_ascii=True) if summary else None,
                json.dumps(progress, ensure_ascii=True) if progress else None,
                run.get("error"),
            ),
        )

    def update_run_status(self, run_id: str, status: str, **fields: Any) -> None:
        """Update a run's status and optional extra columns."""
        allowed = {
            "adapter", "adapter_display", "total", "passed", "failed",
            "score", "pass_rate", "cost_usd", "total_tokens", "started_at",
            "completed_at", "summary_json", "progress_json", "error",
        }
        sets = ["status = ?"]
        params: list[Any] = [status]
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(value)
        params.append(run_id)
        self._execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?",
            tuple(params),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_run(dict(row))

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT * FROM runs ORDER BY started_at DESC, run_id DESC"
        ).fetchall()
        return [self._row_to_run(dict(row)) for row in rows]

    def delete_run(self, run_id: str) -> None:
        self._execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    # -- Results -------------------------------------------------------------

    def replace_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        """Replace all results for a run (delete + bulk insert)."""
        self._execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        if not results:
            return
        rows = [
            (
                r["run_id"] if "run_id" in r else run_id,
                r.get("case_id", ""),
                int(r.get("passed", False)),
                float(r.get("score", 0)),
                json.dumps(r.get("capability"), ensure_ascii=True)
                if r.get("capability")
                else None,
                r.get("difficulty"),
                json.dumps(r.get("checks"), ensure_ascii=True)
                if r.get("checks")
                else None,
                r.get("response_text"),
                r.get("error"),
                json.dumps(r.get("usage"), ensure_ascii=True)
                if r.get("usage")
                else None,
                float(r.get("cost_usd", 0)) if r.get("cost_usd") is not None else None,
                float(r.get("latency_ms", 0)) if r.get("latency_ms") is not None else None,
            )
            for r in results
        ]
        self._executemany(
            """
            INSERT INTO results (
                run_id, case_id, passed, score, capability, difficulty,
                checks_json, response_text, error, usage_json, cost_usd,
                latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def finish_run(self, run: dict[str, Any], results: list[dict[str, Any]]) -> None:
        """Atomically persist terminal metadata and replace all results."""
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
        self._conn.execute(
            """
            INSERT INTO runs (run_id,status,adapter,adapter_display,judge,reviewer,verifier,total,passed,failed,score,pass_rate,cost_usd,total_tokens,started_at,completed_at,summary_json,progress_json,error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,adapter=excluded.adapter,adapter_display=excluded.adapter_display,judge=excluded.judge,reviewer=excluded.reviewer,verifier=excluded.verifier,total=excluded.total,passed=excluded.passed,failed=excluded.failed,score=excluded.score,pass_rate=excluded.pass_rate,cost_usd=excluded.cost_usd,total_tokens=excluded.total_tokens,started_at=excluded.started_at,completed_at=excluded.completed_at,summary_json=excluded.summary_json,progress_json=excluded.progress_json,error=excluded.error
            """,
            (run["run_id"], run.get("status", "pending"), summary.get("adapter") or run.get("adapter"), summary.get("adapter_display") or run.get("adapter_display"), summary.get("judge"), summary.get("reviewer"), summary.get("verifier"), int(summary.get("total", 0)), int(summary.get("passed", 0)), int(summary.get("failed", 0)), float(summary.get("score", 0)), float(summary.get("pass_rate", 0)), summary.get("cost_usd", summary.get("estimated_cost_usd")), int((summary.get("usage") or {}).get("total_tokens", 0)), run.get("started_at"), run.get("completed_at"), json.dumps(summary, sort_keys=True, separators=(",", ":")) if summary else None, json.dumps(progress, sort_keys=True, separators=(",", ":")) if progress else None, run.get("error")),
        )

    def _replace_results_unlocked(self, run_id: str, results: list[dict[str, Any]]) -> None:
        self._conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        if not results:
            return
        rows = [(run_id, r.get("case_id", ""), int(r.get("passed", False)), float(r.get("score", 0)), json.dumps(r.get("capability"), sort_keys=True, separators=(",", ":")) if r.get("capability") else None, r.get("difficulty"), json.dumps(r.get("checks"), sort_keys=True, separators=(",", ":")) if r.get("checks") else None, r.get("response_text"), r.get("error"), json.dumps(r.get("usage"), sort_keys=True, separators=(",", ":")) if r.get("usage") else None, r.get("cost_usd"), r.get("latency_ms")) for r in results]
        self._conn.executemany("INSERT INTO results (run_id,case_id,passed,score,capability,difficulty,checks_json,response_text,error,usage_json,cost_usd,latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def get_results(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT * FROM results WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d.pop("id", None)
            for key in ("capability", "checks", "usage"):
                col = f"{key}_json"
                if d.get(col) is not None:
                    d[key] = json.loads(d[col])
                d.pop(col, None)
            d["passed"] = bool(d.get("passed"))
            out.append(d)
        return out

    # -- Convenience ---------------------------------------------------------

    def rebuild_from_disk(self, runs_dir: Path) -> int:
        """Re-import all completed runs from disk. Returns count imported."""
        from .run_manager import collect_runs

        imported = 0
        seen: set[str] = set()
        for run in collect_runs(runs_dir):
            run.setdefault("status", "completed")
            run_id = run["run_id"]
            summary_path = runs_dir / run_id / "summary.json"
            if summary_path.exists() and run.get("started_at") is None:
                run["started_at"] = summary_path.stat().st_mtime
            results: list[dict[str, Any]] = []
            results_path = runs_dir / run_id / "results.jsonl"
            if results_path.exists():
                for line in results_path.read_text(encoding="utf-8").splitlines():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            self.finish_run(run, results)
            seen.add(run_id)
            imported += 1
        with self._lock:
            if seen:
                placeholders = ",".join("?" for _ in seen)
                self._conn.execute(f"DELETE FROM runs WHERE run_id NOT IN ({placeholders})", tuple(sorted(seen)))
            else:
                self._conn.execute("DELETE FROM runs")
        return imported

    @staticmethod
    def _row_to_run(row: dict[str, Any]) -> dict[str, Any]:
        summary_json = row.pop("summary_json", None)
        progress_json = row.pop("progress_json", None)
        summary = json.loads(summary_json) if summary_json else {}
        progress = json.loads(progress_json) if progress_json else {}
        return {
            "run_id": row["run_id"],
            "status": row["status"],
            "progress": progress,
            "summary": summary,
            "error": row.get("error"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._conn.close()
            self._closed = True
