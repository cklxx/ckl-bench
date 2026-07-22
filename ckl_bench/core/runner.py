from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ckl_bench.adapters.base import GenerateRequest, ModelAdapter

from . import stats
from .cache import NullCache, ResponseCache, cache_key
from .cases import EvalCase, case_to_dict
from .grading import grade_case
from .paths import UnsafePathError, copy_tree_safely, safe_join, validate_owned_path
from .reporting import write_html_report
from .usage import Usage, estimate_cost, load_pricing, normalize_usage

# Bumped when the shape of summary.json / results.jsonl changes in a way that
# makes older runs non-comparable. Reproducibility tooling reads this.
SCHEMA_VERSION = "1.4"
SCORING_POLICY_VERSION = "1.0"
ERROR_POLICY_VERSION = "1.1"
REPEAT_POLICY_VERSION = "1.1"
COMPARABILITY_POLICY_VERSION = "1.0"
CACHE_POLICY_VERSION = "1.1"

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|authorization|token|secret|password|credential|cookie)", re.I)
_SECRET_ARG_RE = re.compile(
    r"(?i)(--?(?:api[_-]?key|token|secret|password|authorization)(?:=|\s+))([^\s]+)"
)
_ADAPTER_BEHAVIOR_FIELDS = (
    "model", "temperature", "max_tokens", "extra_body", "base_url", "endpoint",
    "timeout_s", "text_path", "command", "shell", "trusted_shell", "cwd", "version",
    "headers", "extra_env", "trusted_local",
)

_log = logging.getLogger(__name__)


def _emit_progress(options: "RunOptions", event: dict[str, Any]) -> None:
    """Best-effort progress emission; never breaks the run."""
    cb = options.on_progress
    if cb is None:
        return
    try:
        cb(event)
    except Exception:  # noqa: BLE001 - progress is a side channel
        _log.exception("on_progress callback failed")


@dataclass(frozen=True)
class RunOptions:
    out_dir: Path
    run_name: str | None = None
    keep_workspaces: bool = False
    include_raw: bool = False
    judge_adapter: ModelAdapter | None = None
    judge_name: str | None = None
    reviewer_adapter: ModelAdapter | None = None
    reviewer_name: str | None = None
    verifier_adapter: ModelAdapter | None = None
    verifier_name: str | None = None
    repeat: int = 1
    concurrency: int = 1
    seed: int = 0
    cache: ResponseCache | NullCache | None = None
    on_progress: Callable[[dict[str, Any]], None] | None = None
    cancellation_event: threading.Event | None = None
    run_dir_precreated: bool = False


def filter_cases(
    cases: Iterable[EvalCase],
    case_ids: set[str] | None = None,
    capabilities: set[str] | None = None,
    limit: int | None = None,
) -> list[EvalCase]:
    selected: list[EvalCase] = []
    for case in cases:
        if case_ids and case.id not in case_ids:
            continue
        if capabilities and not capabilities.intersection(case.capability):
            continue
        selected.append(case)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def run_cases(cases: list[EvalCase], adapter: ModelAdapter, options: RunOptions) -> dict[str, Any]:
    run_id = options.run_name or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = options.out_dir / run_id
    if not options.run_dir_precreated:
        run_dir.mkdir(parents=True, exist_ok=False)
    results_path = run_dir / "results.jsonl"

    repeat = max(1, int(options.repeat))
    cache = options.cache or NullCache()
    pricing = load_pricing()

    _emit_progress(
        options,
        {
            "type": "run_started",
            "run_id": run_id,
            "total_cases": len(cases),
            "repeat": repeat,
            "planned_attempts": len(cases) * repeat,
        },
    )

    results = _execute(cases, adapter, options, run_dir, run_id, repeat, cache, pricing)

    with results_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    summary = _summarize(run_id, cases, results, adapter, options, repeat)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    report_path = write_html_report(run_dir, summary, results)

    _emit_progress(
        options,
        {"type": "run_completed", "run_id": run_id, "summary": summary},
    )

    return {
        "run_dir": str(run_dir),
        "results_path": str(results_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "summary": summary,
        "results": results,
    }


def _execute(
    cases: list[EvalCase],
    adapter: ModelAdapter,
    options: RunOptions,
    run_dir: Path,
    run_id: str,
    repeat: int,
    cache: ResponseCache | NullCache,
    pricing: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    tasks = iter((ci, ai) for ci in range(len(cases)) for ai in range(repeat))
    grid: dict[int, dict[int, dict[str, Any]]] = {ci: {} for ci in range(len(cases))}

    def run_task(task: tuple[int, int]) -> tuple[int, int, dict[str, Any]]:
        case_index, attempt_index = task
        case = cases[case_index]
        _emit_progress(
            options,
            {
                "type": "attempt_started",
                "run_id": run_id,
                "case_id": case.id,
                "case_index": case_index,
                "attempt": attempt_index,
            },
        )
        attempt = _run_attempt(
            case, adapter, options, run_dir, attempt_index, repeat, cache, pricing
        )
        _emit_progress(
            options,
            {
                "type": "attempt_completed",
                "run_id": run_id,
                "case_id": case.id,
                "case_index": case_index,
                "attempt": attempt_index,
                "status": attempt["status"],
                "score": attempt["score"],
                "passed": attempt["passed"],
                "error": attempt.get("error"),
                "error_type": attempt.get("error_type"),
            },
        )
        return case_index, attempt_index, attempt

    concurrency = max(1, int(options.concurrency))
    cancelled = options.cancellation_event
    if concurrency == 1:
        for task in tasks:
            if cancelled is not None and cancelled.is_set():
                break
            ci, ai, attempt = run_task(task)
            grid[ci][ai] = attempt
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            pending: dict[Future[tuple[int, int, dict[str, Any]]], tuple[int, int]] = {}
            while True:
                while len(pending) < concurrency and not (cancelled is not None and cancelled.is_set()):
                    try:
                        task = next(tasks)
                    except StopIteration:
                        break
                    pending[pool.submit(run_task, task)] = task
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future, None)
                    ci, ai, attempt = future.result()
                    grid[ci][ai] = attempt

    results: list[dict[str, Any]] = []
    for ci, case in enumerate(cases):
        attempts = [grid[ci][ai] for ai in sorted(grid[ci])]
        if attempts:
            result = _aggregate_case(case, attempts, repeat)
            if len(attempts) < repeat:
                result.update(
                    status="cancelled",
                    passed=None,
                    cancelled=True,
                    incomplete=True,
                    scheduled_attempts=len(attempts),
                )
                for key in ("pass_at_1", "pass_at_k", "pass_pow_k"):
                    result[key] = None
            results.append(result)
        else:
            results.append(_cancelled_case(case, repeat))
    return results


def _cancelled_case(case: EvalCase, repeat: int) -> dict[str, Any]:
    return {
        "case_id": case.id, "title": case.title, "type": case.type,
        "capability": case.capability, "difficulty": case.difficulty,
        "source": f"{case.source_path}:{case.source_line}", "status": "cancelled",
        "score": None, "passed": None, "checks": [], "latency_ms": 0.0,
        "response_text": "", "error": None, "error_type": None,
        "error_message": None, "usage": Usage().as_dict(),
        "estimated_cost_usd": 0.0, "cost_usd": 0.0, "provider_cost_usd": 0.0,
        "cost_status": "estimated", "model": None, "cancelled": True,
        "incomplete": True, "attempt_count": 0, "completed_count": 0,
        "passed_count": 0, "error_count": 0, "scheduled_attempts": 0,
        "planned_repeat": repeat, "repeat": repeat, "pass_at_1": None,
        "pass_at_k": None, "pass_pow_k": None, "attempts": [],
    }


def _run_attempt(
    case: EvalCase,
    adapter: ModelAdapter,
    options: RunOptions,
    run_dir: Path,
    attempt_index: int,
    repeat: int,
    cache: ResponseCache | NullCache,
    pricing: dict[str, dict[str, float]],
) -> dict[str, Any]:
    workspace_path = _prepare_workspace(case)
    owned_workspace = workspace_path
    try:
        return _run_attempt_body(
            case, adapter, options, run_dir, attempt_index, repeat,
            cache, pricing, workspace_path, owned_workspace,
        )
    finally:
        if owned_workspace:
            shutil.rmtree(owned_workspace, ignore_errors=True)


def _run_attempt_body(
    case: EvalCase,
    adapter: ModelAdapter,
    options: RunOptions,
    run_dir: Path,
    attempt_index: int,
    repeat: int,
    cache: ResponseCache | NullCache,
    pricing: dict[str, dict[str, float]],
    workspace_path: Path | None,
    owned_workspace: Path | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    response_text = ""
    raw_response: Any = None
    usage = Usage()
    model = getattr(adapter, "model", None)
    error = None
    cache_hit = False

    # Caching is only safe for stateless (no-workspace) requests: agent cases
    # grade the mutated workspace, which a cached text reply would never produce.
    key = None
    if not isinstance(cache, NullCache) and workspace_path is None:
        key = _attempt_cache_key(adapter, case, attempt_index)
        cached = cache.get(key)
        if cached is not None:
            response_text = str(cached.get("text", ""))
            usage = Usage(**cached.get("usage", {})) if cached.get("usage") else Usage()
            model = cached.get("model", model)
            cache_hit = True

    if not cache_hit:
        try:
            response = adapter.generate(
                GenerateRequest(
                    case_id=case.id,
                    messages=case.messages,
                    prompt=case.prompt,
                    workspace_path=workspace_path,
                    metadata={**case.metadata, "case_type": case.type},
                    timeout_s=case.timeout_s,
                )
            )
            response_text = response.text
            raw_response = response.raw
            usage = _usage_from_response(response)
            model = (response.metadata or {}).get("model", model)
            # Command agents may create their own workspace and write files
            # there; use it for grading so code_test can read agent artifacts
            # instead of trying to extract code from the response text.
            if response.workspace_path is not None:
                if owned_workspace is None:
                    raise UnsafePathError("adapter returned a workspace for a non-workspace case")
                workspace_path = validate_owned_path(
                    owned_workspace,
                    response.workspace_path,
                    label="adapter workspace",
                )
        except Exception as exc:  # noqa: BLE001 - one bad attempt should produce evidence.
            error = f"{type(exc).__name__}: {exc}"
        if key is not None and error is None:
            cache.put(key, {"text": response_text, "usage": usage.as_dict(), "model": model})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if error is None:
        grade = grade_case(
            case, response_text, workspace_path,
            options.judge_adapter, options.reviewer_adapter, options.verifier_adapter,
        )
        score = grade.score
        passed = grade.passed
        checks = [check.as_dict() for check in grade.checks]
        status = "completed"
        error_type = None
        error_message = None
    else:
        error_type, _, error_message = error.partition(": ")
        score = None
        passed = None
        checks = []
        status = "error"
    estimated_cost = estimate_cost(usage, model, pricing)
    cost_status = "estimated" if estimated_cost is not None else "unknown_pricing"
    provider_cost = 0.0 if cache_hit else estimated_cost

    attempt: dict[str, Any] = {
        "attempt": attempt_index,
        "status": status,
        "score": score,
        "passed": passed,
        "checks": checks,
        "latency_ms": elapsed_ms,
        "response_text": response_text,
        "error": error,
        "error_type": error_type,
        "error_message": error_message,
        "usage": usage.as_dict(),
        "estimated_cost_usd": estimated_cost,
        "cost_usd": estimated_cost,
        "provider_cost_usd": provider_cost,
        "cost_status": "cache_hit" if cache_hit else cost_status,
        "model": model,
        "cache_hit": cache_hit,
    }
    if options.include_raw:
        attempt["raw_response"] = raw_response
    if workspace_path and options.keep_workspaces:
        saved = safe_join(
            run_dir,
            Path("workspaces") / case.id / f"attempt-{attempt_index}",
            label="retained workspace",
        )
        saved.parent.mkdir(parents=True, exist_ok=True)
        copy_tree_safely(workspace_path, saved)
        attempt["workspace_saved"] = str(saved)
    return attempt


def _aggregate_case(
    case: EvalCase,
    attempts: list[dict[str, Any]],
    repeat: int,
) -> dict[str, Any]:
    rep = attempts[0]  # representative attempt for drill-down evidence
    # Exclude errored attempts from score and pass metrics: a 0.0 from a
    # timeout is an infrastructure failure, not a model score.
    completed = [a for a in attempts if not _is_error(a)]
    scores = [float(a["score"]) for a in completed]
    passes = [bool(a["passed"]) for a in completed]
    n = len(attempts)
    c = sum(passes)
    error_count = n - len(completed)
    completed_count = len(completed)
    agg_score = stats.mean(scores) if scores else None

    total_usage = Usage()
    for a in attempts:
        total_usage = total_usage + Usage(**a.get("usage", {}))
    model = rep.get("model")
    estimated_cost, provider_cost, known_cost_count, unknown_cost_count = _sum_costs(attempts)
    first_error = next((a["error"] for a in attempts if a.get("error")), None)

    complete = n == repeat
    status = "error" if error_count else ("completed" if complete else "incomplete")
    aggregate_passed: bool | None = None if not complete or error_count else all(passes)

    result: dict[str, Any] = {
        "case_id": case.id,
        "title": case.title,
        "type": case.type,
        "capability": case.capability,
        "difficulty": case.difficulty,
        "source": f"{case.source_path}:{case.source_line}",
        "status": status,
        "score": agg_score,
        "passed": aggregate_passed,
        "checks": rep["checks"],
        "latency_ms": round(stats.mean([float(a["latency_ms"]) for a in attempts]), 2),
        "response_text": rep["response_text"],
        "error": first_error,
        "error_type": next((a.get("error_type") for a in attempts if a.get("error_type")), None),
        "error_message": next((a.get("error_message") for a in attempts if a.get("error_message")), None),
        "attempt_count": n,
        "planned_repeat": repeat,
        "incomplete": not complete,
        "completed_count": completed_count,
        "passed_count": c,
        "error_count": error_count,
        "usage": total_usage.as_dict(),
        "estimated_cost_usd": estimated_cost,
        "cost_usd": estimated_cost,
        "provider_cost_usd": provider_cost,
        "cost_status": "estimated" if estimated_cost is not None else "unknown_pricing",
        "known_cost_attempts": known_cost_count,
        "unknown_cost_attempts": unknown_cost_count,
        "model": model,
    }
    if any(a.get("cache_hit") for a in attempts):
        result["cache_hits"] = sum(1 for a in attempts if a.get("cache_hit"))
    if "raw_response" in rep:
        result["raw_response"] = rep["raw_response"]
    if "workspace_saved" in rep:
        result["workspace_saved"] = rep["workspace_saved"]

    if repeat > 1:
        result["repeat"] = repeat
        result["passes"] = c
        result["score_values"] = scores
        if complete and error_count == 0:
            result["pass_at_1"] = round(c / repeat, 6)
            result["pass_at_k"] = round(stats.pass_at_k(repeat, c, repeat), 6)
            result["pass_pow_k"] = round(stats.pass_pow_k(repeat, c, repeat), 6)
        else:
            result["pass_at_1"] = None
            result["pass_at_k"] = None
            result["pass_pow_k"] = None
        result["attempts"] = [
            {
                "attempt": a["attempt"],
                "status": a.get("status", "error" if a.get("error") else "completed"),
                "score": a["score"],
                "passed": a["passed"],
                "latency_ms": a["latency_ms"],
                "error": a.get("error"),
                "error_type": a.get("error_type"),
                "error_message": a.get("error_message"),
                "cache_hit": a.get("cache_hit", False),
                "estimated_cost_usd": a.get("estimated_cost_usd", a.get("cost_usd")),
                "provider_cost_usd": a.get("provider_cost_usd"),
                "cost_status": a.get("cost_status"),
            }
            for a in attempts
        ]
    return result


def _bucket_stats(
    results: list[dict[str, Any]], key: str, default: str
) -> dict[str, dict[str, Any]]:
    """Group results by ``key`` and compute count/passed/score/CI per bucket.

    Errored results (infrastructure failures) are counted separately so they
    don't drag down the pass rate / score of the model's actual attempts.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for result in results:
        values = result.get(key) or [default]
        if not isinstance(values, list):
            values = [values]
        is_error = _is_error(result)
        for value in values:
            bucket = buckets.setdefault(
                str(value),
                {"count": 0, "passed": 0, "errored": 0, "scores": []},
            )
            bucket["count"] += 1
            if is_error:
                bucket["errored"] += 1
            else:
                bucket["passed"] += int(bool(result["passed"]))
                bucket["scores"].append(float(result["score"]))
    for bucket in buckets.values():
        scores = bucket.pop("scores")
        bucket["score"] = stats.mean(scores) if scores else None
        denom = bucket["count"] - bucket["errored"]
        low, high = stats.wilson_interval(bucket["passed"], denom)
        bucket["pass_rate_ci"] = [round(low, 4), round(high, 4)]
    return buckets


def _is_error(item: dict[str, Any]) -> bool:
    """True when an attempt/result is an infrastructure failure, not a model score.

    A single predicate so the error policy (which fields count) lives in one
    place instead of being re-decided in _aggregate_case, _bucket_stats, and
    _summarize.
    """
    return item.get("status") == "error" or bool(item.get("error"))


def _sum_costs(items: list[dict[str, Any]]) -> tuple[float | None, float | None, int, int]:
    """Sum estimated and provider costs across items.

    Returns ``(estimated_cost, provider_cost, known_count, unknown_count)``.
    Estimated cost is ``None`` when any item has unknown pricing so the
    dashboard can distinguish "free" from "could not price".
    """
    estimated_costs = [i.get("estimated_cost_usd", i.get("cost_usd")) for i in items]
    known = sum(c is not None for c in estimated_costs)
    unknown = len(items) - known
    estimated = (
        round(sum(float(c) for c in estimated_costs if c is not None), 6)
        if unknown == 0
        else None
    )
    provider_costs = [i.get("provider_cost_usd") for i in items]
    provider = (
        round(sum(float(c) for c in provider_costs if c is not None), 6)
        if all(c is not None for c in provider_costs)
        else None
    )
    return estimated, provider, known, unknown


def _usage_from_response(response: Any) -> Usage:
    """Extract usage from a response via the shared shape-agnostic normalizer."""
    meta = getattr(response, "metadata", None)
    return normalize_usage(meta) if isinstance(meta, dict) else Usage()


def _attempt_cache_key(adapter: ModelAdapter, case: EvalCase, attempt_index: int) -> str:
    request = GenerateRequest(
        case_id=case.id,
        messages=case.messages,
        prompt=case.prompt,
        workspace_path=None,
        metadata={**case.metadata, "case_type": case.type},
        timeout_s=case.timeout_s,
    )
    return cache_key(
        {
            "cache_policy_version": CACHE_POLICY_VERSION,
            "adapter": _adapter_policy(adapter),
            "request": {
                "case_id": request.case_id,
                "messages": request.messages,
                "prompt": request.prompt,
                "metadata": request.metadata,
                "timeout_s": request.timeout_s,
                "workspace": False,
                "attempt": attempt_index,
            },
        }
    )


def _prepare_workspace(case: EvalCase) -> Path | None:
    workspace = case.input.get("workspace")
    if not workspace:
        return None
    files = workspace.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"{case.id}: input.workspace.files must be an object")
    root = Path(tempfile.mkdtemp(prefix="ckl-bench-workspace-"))
    try:
        for relative_name, content in files.items():
            target = safe_join(root, str(relative_name), label=f"{case.id} workspace path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def _summarize(
    run_id: str,
    cases: list[EvalCase],
    results: list[dict[str, Any]],
    adapter: ModelAdapter,
    options: RunOptions,
    repeat: int,
) -> dict[str, Any]:
    total = len(results)
    # Separate infrastructure errors (timeouts, API failures) from model
    # failures so the dashboard can show "3 passed / 1 failed / 1 errored"
    # instead of burying errors in the failed count.
    errored = sum(1 for r in results if _is_error(r))
    cancelled = sum(1 for r in results if r.get("status") == "cancelled")
    incomplete = sum(1 for r in results if r.get("status") == "incomplete")
    passed = sum(1 for r in results if r.get("passed") is True)
    failed = sum(1 for r in results if r.get("passed") is False and not _is_error(r))
    case_scores = [float(r["score"]) for r in results if r.get("score") is not None and not _is_error(r)]
    completed = total - errored - cancelled - incomplete

    # When no cases were evaluated, score/pass_rate are null (not 0.0) so the
    # dashboard can distinguish "not run" from "scored 0".
    score = stats.mean(case_scores) if case_scores else None
    pass_rate = round(passed / completed, 6) if completed else None

    by_capability = _bucket_stats(results, "capability", "uncategorized")
    by_difficulty = _bucket_stats(results, "difficulty", "unspecified")

    total_usage = Usage()
    for result in results:
        total_usage = total_usage + Usage(**result.get("usage", {}))
    total_cost, provider_cost, known_cost_count, unknown_cost_count = _sum_costs(results)

    if completed:
        pass_low, pass_high = stats.wilson_interval(passed, completed)
        score_low, score_high = stats.bootstrap_mean_ci(case_scores, seed=options.seed)
        pass_rate_ci: list[float] | None = [round(pass_low, 4), round(pass_high, 4)]
        score_ci: list[float] | None = [round(score_low, 4), round(score_high, 4)]
    else:
        pass_rate_ci = None
        score_ci = None

    summary: dict[str, Any] = {
        "run_id": run_id,
        "adapter": getattr(adapter, "name", adapter.__class__.__name__),
        "adapter_display": getattr(adapter, "display_name", None)
        or getattr(adapter, "name", adapter.__class__.__name__),
        "judge": options.judge_name,
        "reviewer": options.reviewer_name,
        "verifier": options.verifier_name,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "cancelled": cancelled,
        "incomplete": incomplete,
        "completed": completed,
        "score": score,
        "pass_rate": pass_rate,
        "pass_rate_ci": pass_rate_ci,
        "score_ci": score_ci,
        "by_capability": by_capability,
        "by_difficulty": by_difficulty,
        "usage": total_usage.as_dict(),
        "estimated_cost_usd": total_cost,
        "cost_usd": total_cost,
        "provider_cost_usd": provider_cost,
        "cost_status": "estimated" if total_cost is not None else "unknown_pricing",
        "known_cost_cases": known_cost_count,
        "unknown_cost_cases": unknown_cost_count,
        "latency_ms_total": round(sum(float(r.get("latency_ms", 0.0)) for r in results), 2),
        "manifest": _build_manifest(cases, adapter, options, repeat),
    }
    if repeat > 1:
        valid_repeat_results = [
            r for r in results
            if r.get("status") == "completed"
            and all(r.get(key) is not None for key in ("pass_at_1", "pass_at_k", "pass_pow_k"))
        ]
        summary["repeat"] = repeat
        summary["planned_attempts"] = len(cases) * repeat
        summary["attempted_attempts"] = sum(int(r.get("attempt_count", 0)) for r in results)
        summary["completed_attempts"] = sum(int(r.get("completed_count", 0)) for r in results)
        if len(valid_repeat_results) == total:
            summary["pass_at_1"] = round(stats.mean([float(r["pass_at_1"]) for r in valid_repeat_results]), 6)
            summary["pass_at_k"] = round(stats.mean([float(r["pass_at_k"]) for r in valid_repeat_results]), 6)
            summary["pass_pow_k"] = round(stats.mean([float(r["pass_pow_k"]) for r in valid_repeat_results]), 6)
        else:
            summary["pass_at_1"] = None
            summary["pass_at_k"] = None
            summary["pass_pow_k"] = None
    return summary


def _build_manifest(
    cases: list[EvalCase],
    adapter: ModelAdapter,
    options: RunOptions,
    repeat: int,
) -> dict[str, Any]:
    sources = sorted({str(case.source_path) for case in cases})
    comparability = _comparability_policy(cases, adapter, options, repeat)
    canonical = json.dumps(comparability, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
        "error_policy_version": ERROR_POLICY_VERSION,
        "repeat_policy_version": REPEAT_POLICY_VERSION,
        "comparability_policy_version": COMPARABILITY_POLICY_VERSION,
        "cache_policy_version": CACHE_POLICY_VERSION,
        "comparability_signature": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "comparability": comparability,
        "ckl_bench_version": _ckl_bench_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "seed": options.seed,
        "repeat": repeat,
        "concurrency": max(1, int(options.concurrency)),
        "cache": not isinstance(options.cache, (type(None), NullCache)),
        "model": _adapter_policy(adapter),
        "dataset": {
            "files": _dataset_fingerprint(sources),
            "case_count": len(cases),
        },
    }


def _comparability_policy(
    cases: list[EvalCase],
    adapter: ModelAdapter,
    options: RunOptions,
    repeat: int,
) -> dict[str, Any]:
    return {
        "policy_version": COMPARABILITY_POLICY_VERSION,
        "policies": {
            "schema": SCHEMA_VERSION,
            "scoring": SCORING_POLICY_VERSION,
            "error": ERROR_POLICY_VERSION,
            "repeat": REPEAT_POLICY_VERSION,
            "cache": CACHE_POLICY_VERSION,
        },
        "cases": [_sanitize(case_to_dict(case)) for case in cases],
        "primary_adapter": _adapter_policy(adapter),
        "judge": _named_adapter_policy(options.judge_name, options.judge_adapter),
        "reviewer": _named_adapter_policy(options.reviewer_name, options.reviewer_adapter),
        "verifier": _named_adapter_policy(options.verifier_name, options.verifier_adapter),
        "repeat": repeat,
        "seed": options.seed,
    }


def _named_adapter_policy(name: str | None, adapter: ModelAdapter | None) -> dict[str, Any] | None:
    if adapter is None and name is None:
        return None
    policy = _adapter_policy(adapter) if adapter is not None else {}
    return {"identity": name, **policy}


def _adapter_policy(adapter: ModelAdapter) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "adapter": getattr(adapter, "name", adapter.__class__.__name__),
        "display_name": getattr(adapter, "display_name", None),
    }
    for field in _ADAPTER_BEHAVIOR_FIELDS:
        if hasattr(adapter, field):
            policy[field] = getattr(adapter, field)
    return _sanitize(policy)


def _sanitize(value: Any, key: str = "") -> Any:
    """Return stable JSON-safe policy data with secret-bearing fields redacted."""
    if _SECRET_KEY_RE.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(k): _sanitize(v, str(k))
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _SECRET_ARG_RE.sub(r"\1<redacted>", value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return repr(value)


def _dataset_fingerprint(sources: list[str]) -> dict[str, str]:
    fingerprint: dict[str, str] = {}
    for source in sources:
        path = Path(source)
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fingerprint[source] = f"sha256:{digest[:16]}"
    return fingerprint


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha or None


def _ckl_bench_version() -> str:
    try:
        from importlib.metadata import version

        return version("ckl-bench")
    except Exception:  # noqa: BLE001 - version is best-effort metadata.
        return "0.1.0"
