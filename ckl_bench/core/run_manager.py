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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ckl_bench.adapters import build_adapter
from ckl_bench.core.cache import ResponseCache
from ckl_bench.core.cases import CaseValidationError, EvalCase, load_cases
from ckl_bench.core.runner import RunOptions, run_cases

_log = logging.getLogger(__name__)


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

    def __init__(self, runs_dir: Path, cases_dir: Path) -> None:
        self._runs_dir = runs_dir
        self._cases_dir = cases_dir
        self._lock = threading.Lock()
        self._states: dict[str, RunState] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

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
        cache_dir: str | None = None,
        run_name: str | None = None,
    ) -> str:
        """Launch a run in a background thread and return its *run_id*."""
        run_id = run_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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

        # Judge adapter (for judge/llm_judge expectations).
        judge_adapter = None
        if judge_target and judge_target not in {"same", "self"}:
            from ckl_bench.core.providers import load_provider

            provider = load_provider(judge_target)
            if provider is not None:
                judge_adapter = build_adapter(
                    provider["adapter"], dict(provider.get("config", {}))
                )

        # Cache (stateless requests only).
        cache = ResponseCache(Path(cache_dir)) if cache_dir else None

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
            cache=cache,
            on_progress=lambda event: self._on_progress(run_id, event),
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
        try:
            result = run_cases(cases, adapter, options)
            if cancel_flag.is_set():
                state.status = "cancelled"
            else:
                state.status = "completed"
                state.summary = result["summary"]
                if state.summary is not None:
                    manifest = state.summary.setdefault("manifest", {})
                    manifest["case_paths"] = state.case_paths
        except Exception as exc:  # noqa: BLE001 - record and surface
            state.status = "failed"
            state.error = f"{type(exc).__name__}: {exc}"
            _log.exception("run %s failed", run_id)
        finally:
            state.completed_at = time.time()
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
                progress["total_cases"] = event.get("total_cases", 0)
                progress["repeat"] = event.get("repeat", 1)
                progress["cases"] = {}
            elif event["type"] == "case_started":
                cases_progress = progress.setdefault("cases", {})
                cases_progress[event["case_id"]] = {
                    "status": "running",
                    "attempt": event.get("attempt", 0),
                }
            elif event["type"] == "case_completed":
                cases_progress = progress.setdefault("cases", {})
                cases_progress[event["case_id"]] = {
                    "status": "completed" if not event.get("error") else "failed",
                    "attempt": event.get("attempt", 0),
                    "score": event.get("score"),
                    "passed": event.get("passed"),
                    "error": event.get("error"),
                }
            elif event["type"] == "run_completed":
                pass  # handled in _run_worker
        # Broadcast outside the lock to avoid reentrant deadlock.
        self._broadcast(event)

    # -- Query API ----------------------------------------------------------

    def list_runs(self) -> list[dict[str, Any]]:
        """Return all runs: in-memory active runs plus completed runs on disk."""
        with self._lock:
            active = {
                run_id: self._state_to_dict(state)
                for run_id, state in self._states.items()
            }
        # Completed runs from disk (merged with active so we don't double up).
        for run in collect_runs(self._runs_dir):
            rid = run["run_id"]
            if rid not in active:
                active[rid] = {
                    "run_id": rid,
                    "status": "completed",
                    "progress": {},
                    "summary": run["summary"],
                    "error": None,
                }
        return sorted(active.values(), key=lambda r: r.get("run_id", ""), reverse=True)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a single run's state, progress, and summary."""
        with self._lock:
            state = self._states.get(run_id)
            if state is not None:
                return self._state_to_dict(state)
        # Fall back to disk.
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
        """Load results.jsonl for a completed run."""
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
        return results

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
            state.status = "cancelled"
            return True

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
