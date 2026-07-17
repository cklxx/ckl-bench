"""RunManager: launch, track, and broadcast progress for evaluation runs.

The manager runs each evaluation in a background thread and exposes a simple
API for the dashboard server: start a run, list runs, get a run's current
progress, and cancel a run.  Progress is also pushed to registered listeners
(e.g. WebSocket clients) in real time.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ckl_bench.adapters import build_adapter
from ckl_bench.core.cache import ResponseCache
from ckl_bench.core.cases import CaseValidationError, EvalCase, load_cases
from ckl_bench.core.db import RunDB
from ckl_bench.core.runner import RunOptions, run_cases

_log = logging.getLogger(__name__)

#: Default judge target when ``--judge`` / ``CKL_JUDGE`` / settings judge are
#: all unset.  dsx is a capable, dependency-light command agent that works out
#: of the box via ``scripts/dsx_wrapper.py``.
DEFAULT_JUDGE_TARGET = "dsx"


def _normalize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every result has a well-formed ``capability`` list.

    Older runs or external result files may store ``capability`` as a plain
    string or omit it entirely.  Normalising here guarantees the frontend
    (which calls ``capability.map``) always receives a list.
    """
    for r in results:
        cap = r.get("capability")
        if cap is None:
            r["capability"] = []
        elif isinstance(cap, str):
            r["capability"] = [cap]
        elif not isinstance(cap, list):
            r["capability"] = []
    return results


def collect_runs(runs_dir: Path) -> list[dict[str, Any]]:
    """Scan *runs_dir* for summary.json files and return run dicts.

    Shared by the CLI ``dashboard`` command and the server.
    """
    runs: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return runs
    for summary_path in sorted(runs_dir.rglob("summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        run_id = str(summary.get("run_id") or summary_path.parent.name)
        runs.append({"run_id": run_id, "summary": summary})
    return runs


def _resolve(target: str | None) -> Any | None:
    """Build an adapter for *target*, or None for 'same'/'self'/empty."""
    if not target or target in {"same", "self"}:
        return None
    from ckl_bench.core.providers import load_provider

    provider = load_provider(target)
    if provider is None:
        return None
    return build_adapter(provider["adapter"], dict(provider.get("config", {})))


class RunConflictError(RuntimeError):
    """Raised when a requested run ID is already reserved."""


@dataclass
class RunState:
    run_id: str
    status: str = "pending"  # pending | running | completed | failed | cancelled
    progress: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    case_paths: list[str] = field(default_factory=list)


class RunManager:
    """Launch and track evaluation runs with real-time progress broadcast."""

    def __init__(
        self,
        runs_dir: Path,
        cases_dir: Path,
        db_path: Path | None = None,
    ) -> None:
        self._runs_dir = runs_dir
        self._cases_dir = cases_dir
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._states: dict[str, RunState] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        # SQLite persistence: query-optimized cache over the JSON files on disk
        # (which remain the canonical export).  Rebuild from disk on first run.
        self._db: RunDB | None = None
        if db_path is not None:
            self._db = RunDB(db_path)
            self._db.rebuild_from_disk(runs_dir)

    # -- Listener management ------------------------------------------------

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    def _broadcast(self, event: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event)
            except Exception:  # noqa: BLE001 - listeners are a side channel
                _log.exception("progress listener failed")

    # -- Run operations -----------------------------------------------------

    def start_run(
        self,
        *,
        adapter_name: str,
        adapter_config: dict[str, Any] | None = None,
        case_paths: list[str] | None = None,
        case_ids: list[str] | None = None,
        repeat: int = 1,
        concurrency: int = 1,
        seed: int = 0,
        judge_target: str | None = None,
        reviewer_target: str | None = None,
        verifier_target: str | None = None,
        cache_dir: str | None = None,
        run_name: str | None = None,
    ) -> str:
        """Launch a run in a background thread and return its *run_id*."""
        run_id = run_name or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

        # Resolve case paths (default to all cases).
        paths = case_paths or [str(self._cases_dir)]

        # Load and optionally filter cases.
        cases = load_cases(paths)
        if case_ids:
            id_set = set(case_ids)
            cases = [c for c in cases if c.id in id_set]
        if not cases:
            raise CaseValidationError("no cases selected for run")

        # Build adapter.
        config = dict(adapter_config or {})
        adapter = build_adapter(adapter_name, config)

        # Judge/reviewer/verifier adapters (reviewer & verifier are optional
        # adversarial-pipeline stages that challenge and finalise the judge).
        # The judge defaults to dsx when no target is specified, so quality
        # expectations are graded out of the box.
        judge_target = judge_target or DEFAULT_JUDGE_TARGET
        judge_adapter = _resolve(judge_target)
        reviewer_adapter = _resolve(reviewer_target)
        verifier_adapter = _resolve(verifier_target)

        # Cache (stateless requests only).
        cache = ResponseCache(Path(cache_dir)) if cache_dir else None

        # Atomically reserve the identity only after validation/build succeeds.
        try:
            (self._runs_dir / run_id).mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise RunConflictError(f"run already exists: {run_id}") from exc

        state = RunState(run_id=run_id)
        state.case_paths = list(paths)
        cancel_flag = threading.Event()

        with self._lock:
            self._states[run_id] = state
            self._cancel_flags[run_id] = cancel_flag

        options = RunOptions(
            out_dir=self._runs_dir,
            run_name=run_id,
            repeat=repeat,
            concurrency=concurrency,
            seed=seed,
            judge_adapter=judge_adapter,
            judge_name=judge_target,
            reviewer_adapter=reviewer_adapter,
            reviewer_name=reviewer_target,
            verifier_adapter=verifier_adapter,
            verifier_name=verifier_target,
            cache=cache,
            on_progress=lambda event: self._on_progress(run_id, event),
            cancellation_event=cancel_flag,
            run_dir_precreated=True,
        )

        thread = threading.Thread(
            target=self._run_worker,
            args=(run_id, cases, adapter, options, cancel_flag),
            name=f"ckl-run-{run_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[run_id] = thread
        thread.start()
        # Persist initial run state so the dashboard sees it immediately.
        if self._db is not None:
            self._db.upsert_run(self._state_to_dict(state))
        return run_id

    def _run_worker(
        self,
        run_id: str,
        cases: list[EvalCase],
        adapter: Any,
        options: RunOptions,
        cancel_flag: threading.Event,
    ) -> None:
        state = self._states[run_id]
        state.status = "running"
        result: dict[str, Any] | None = None
        try:
            result = run_cases(cases, adapter, options)
            state.summary = result["summary"]
            if state.summary is not None:
                manifest = state.summary.setdefault("manifest", {})
                manifest["case_paths"] = state.case_paths
            state.status = "cancelled" if cancel_flag.is_set() else "completed"
        except Exception as exc:  # noqa: BLE001 - record and surface
            state.status = "failed"
            state.error = f"{type(exc).__name__}: {exc}"
            _log.exception("run %s failed", run_id)
        finally:
            state.completed_at = time.time()
            # Persist final state and results to SQLite.
            if self._db is not None:
                if result is not None:
                    self._db.finish_run(self._state_to_dict(state), result.get("results", []))
                else:
                    self._db.upsert_run(self._state_to_dict(state))
            with self._lock:
                self._threads.pop(run_id, None)
                self._cancel_flags.pop(run_id, None)
            self._broadcast(
                {
                    "type": "run_finished",
                    "run_id": run_id,
                    "status": state.status,
                    "summary": state.summary,
                    "error": state.error,
                }
            )

    def _on_progress(self, run_id: str, event: dict[str, Any]) -> None:
        """Update in-memory progress and broadcast to listeners."""
        with self._lock:
            state = self._states.get(run_id)
            if state is None:
                return
            progress = state.progress
            if event["type"] == "run_started":
                total = event.get("total_cases", 0) * event.get("repeat", 1)
                progress.update({"total": total, "started": 0, "completed": 0,
                                 "passed": 0, "failed": 0, "error": 0,
                                 "cancelled": 0, "repeat": event.get("repeat", 1),
                                 "cases": {}})
            elif event["type"] == "case_started":
                progress["started"] = progress.get("started", 0) + 1
                attempts = progress.setdefault("cases", {}).setdefault(event["case_id"], {})
                attempts[str(event.get("attempt", 0))] = {"status": "running"}
            elif event["type"] == "case_completed":
                progress["completed"] = progress.get("completed", 0) + 1
                if event.get("error"):
                    progress["error"] = progress.get("error", 0) + 1
                elif event.get("passed"):
                    progress["passed"] = progress.get("passed", 0) + 1
                else:
                    progress["failed"] = progress.get("failed", 0) + 1
                attempts = progress.setdefault("cases", {}).setdefault(event["case_id"], {})
                attempts[str(event.get("attempt", 0))] = {
                    "status": "error" if event.get("error") else "completed",
                    "score": event.get("score"), "passed": event.get("passed"),
                    "error": event.get("error"),
                }
            elif event["type"] == "run_completed":
                pass  # handled in _run_worker
        # Broadcast outside the lock to avoid reentrant deadlock.
        self._broadcast(event)

    # -- Query API ----------------------------------------------------------

    def list_runs(self) -> list[dict[str, Any]]:
        """Return all runs: in-memory active runs plus completed runs from DB."""
        with self._lock:
            active = {
                run_id: self._state_to_dict(state)
                for run_id, state in self._states.items()
            }
        # Completed runs from SQLite (or disk as fallback) merged with active.
        if self._db is not None:
            completed = self._db.list_runs()
        else:
            completed = collect_runs(self._runs_dir)
        for run in completed:
            rid = run["run_id"]
            if rid not in active:
                active[rid] = run
        return sorted(active.values(), key=lambda r: (r.get("started_at") or 0, r.get("run_id", "")), reverse=True)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a single run's state, progress, and summary."""
        with self._lock:
            state = self._states.get(run_id)
            if state is not None:
                return self._state_to_dict(state)
        # Fall back to SQLite, then disk.
        if self._db is not None:
            run = self._db.get_run(run_id)
            if run is not None:
                return run
        for run in collect_runs(self._runs_dir):
            if run["run_id"] == run_id:
                return {
                    "run_id": run_id,
                    "status": "completed",
                    "progress": {},
                    "summary": run["summary"],
                    "error": None,
                }
        return None

    def get_run_results(self, run_id: str) -> list[dict[str, Any]]:
        """Load results for a completed run (from SQLite, then disk)."""
        if self._db is not None:
            results = self._db.get_results(run_id)
            if results:
                return _normalize_results(results)
        results_path = self._runs_dir / run_id / "results.jsonl"
        if not results_path.exists():
            return []
        results: list[dict[str, Any]] = []
        with results_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return _normalize_results(results)

    def cancel_run(self, run_id: str) -> bool:
        """Signal a running run to stop. Returns True if the run was active."""
        with self._lock:
            flag = self._cancel_flags.get(run_id)
            state = self._states.get(run_id)
            if flag is None or state is None:
                return False
            if state.status not in {"pending", "running"}:
                return False
            flag.set()
            state.status = "cancellation_requested"
            return True

    def close(self, timeout: float = 5.0) -> None:
        """Request active runs to stop, join them boundedly, and close storage."""
        with self._lock:
            flags = list(self._cancel_flags.values())
            threads = list(self._threads.values())
        for flag in flags:
            flag.set()
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        if self._db is not None:
            self._db.close()
            self._db = None

    def _state_to_dict(self, state: RunState) -> dict[str, Any]:
        return {
            "run_id": state.run_id,
            "status": state.status,
            "progress": state.progress,
            "summary": state.summary,
            "error": state.error,
            "started_at": state.started_at,
            "completed_at": state.completed_at,
        }
