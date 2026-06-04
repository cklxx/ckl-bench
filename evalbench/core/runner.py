from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evalbench.adapters.base import GenerateRequest, ModelAdapter

from . import stats
from .cache import NullCache, ResponseCache, cache_key
from .cases import EvalCase
from .grading import grade_case
from .reporting import write_html_report
from .usage import Usage, estimate_cost, load_pricing

# Bumped when the shape of summary.json / results.jsonl changes in a way that
# makes older runs non-comparable. Reproducibility tooling reads this.
SCHEMA_VERSION = "1.1"


@dataclass(frozen=True)
class RunOptions:
    out_dir: Path
    run_name: str | None = None
    keep_workspaces: bool = False
    include_raw: bool = False
    judge_adapter: ModelAdapter | None = None
    judge_name: str | None = None
    repeat: int = 1
    concurrency: int = 1
    seed: int = 0
    cache: ResponseCache | NullCache | None = None


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
    run_id = options.run_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = options.out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    results_path = run_dir / "results.jsonl"

    repeat = max(1, int(options.repeat))
    cache = options.cache or NullCache()
    pricing = load_pricing()

    results = _execute(cases, adapter, options, run_dir, repeat, cache, pricing)

    with results_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    summary = _summarize(run_id, results, adapter, options, repeat)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    report_path = write_html_report(run_dir, summary, results)
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
    repeat: int,
    cache: ResponseCache | NullCache,
    pricing: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    tasks = [(ci, ai) for ci in range(len(cases)) for ai in range(repeat)]
    grid: dict[int, dict[int, dict[str, Any]]] = {ci: {} for ci in range(len(cases))}

    def run_task(task: tuple[int, int]) -> tuple[int, int, dict[str, Any]]:
        case_index, attempt_index = task
        attempt = _run_attempt(
            cases[case_index], adapter, options, run_dir, attempt_index, repeat, cache, pricing
        )
        return case_index, attempt_index, attempt

    concurrency = max(1, int(options.concurrency))
    if concurrency == 1:
        for task in tasks:
            ci, ai, attempt = run_task(task)
            grid[ci][ai] = attempt
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for ci, ai, attempt in pool.map(run_task, tasks):
                grid[ci][ai] = attempt

    return [
        _aggregate_case(cases[ci], [grid[ci][ai] for ai in range(repeat)], repeat, pricing)
        for ci in range(len(cases))
    ]


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
        except Exception as exc:  # noqa: BLE001 - one bad attempt should produce evidence.
            error = f"{type(exc).__name__}: {exc}"
        if key is not None and error is None:
            cache.put(key, {"text": response_text, "usage": usage.as_dict(), "model": model})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    grade = grade_case(case, response_text, workspace_path, options.judge_adapter)
    cost = estimate_cost(usage, model, pricing)

    attempt: dict[str, Any] = {
        "attempt": attempt_index,
        "score": grade.score,
        "passed": grade.passed and error is None,
        "checks": [check.as_dict() for check in grade.checks],
        "latency_ms": elapsed_ms,
        "response_text": response_text,
        "error": error,
        "usage": usage.as_dict(),
        "cost_usd": cost,
        "model": model,
        "cache_hit": cache_hit,
    }
    if options.include_raw:
        attempt["raw_response"] = raw_response
    if workspace_path and options.keep_workspaces and attempt_index == 0:
        suffix = case.id if repeat == 1 else f"{case.id}/attempt-{attempt_index}"
        saved = run_dir / "workspaces" / suffix
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace_path, saved)
        attempt["workspace_saved"] = str(saved)
    if workspace_path:
        shutil.rmtree(workspace_path, ignore_errors=True)
    return attempt


def _aggregate_case(
    case: EvalCase,
    attempts: list[dict[str, Any]],
    repeat: int,
    pricing: dict[str, dict[str, float]],
) -> dict[str, Any]:
    rep = attempts[0]  # representative attempt for drill-down evidence
    scores = [float(a["score"]) for a in attempts]
    passes = [bool(a["passed"]) for a in attempts]
    n = len(attempts)
    c = sum(passes)
    threshold = float(case.metadata.get("pass_threshold", 1.0))
    agg_score = stats.mean(scores)

    total_usage = Usage()
    for a in attempts:
        total_usage = total_usage + Usage(**a.get("usage", {}))
    model = rep.get("model")
    cost = round(sum(float(a.get("cost_usd", 0.0)) for a in attempts), 6)
    first_error = next((a["error"] for a in attempts if a.get("error")), None)

    result: dict[str, Any] = {
        "case_id": case.id,
        "title": case.title,
        "type": case.type,
        "capability": case.capability,
        "difficulty": case.difficulty,
        "source": f"{case.source_path}:{case.source_line}",
        "score": agg_score,
        "passed": agg_score >= threshold,
        "checks": rep["checks"],
        "latency_ms": round(stats.mean([float(a["latency_ms"]) for a in attempts]), 2),
        "response_text": rep["response_text"],
        "error": first_error,
        "usage": total_usage.as_dict(),
        "cost_usd": cost,
        "model": model,
    }
    if any(a.get("cache_hit") for a in attempts):
        result["cache_hits"] = sum(1 for a in attempts if a.get("cache_hit"))
    if "raw_response" in rep:
        result["raw_response"] = rep["raw_response"]
    if "workspace_saved" in rep:
        result["workspace_saved"] = rep["workspace_saved"]

    if repeat > 1:
        result["repeat"] = n
        result["passes"] = c
        result["score_values"] = scores
        result["pass_at_1"] = round(c / n, 6)
        result["pass_at_k"] = round(stats.pass_at_k(n, c, n), 6)
        result["pass_pow_k"] = round(stats.pass_pow_k(n, c, n), 6)
        result["attempts"] = [
            {
                "attempt": a["attempt"],
                "score": a["score"],
                "passed": a["passed"],
                "latency_ms": a["latency_ms"],
                "error": a.get("error"),
                "cache_hit": a.get("cache_hit", False),
            }
            for a in attempts
        ]
    return result


def _usage_from_response(response: Any) -> Usage:
    meta = getattr(response, "metadata", None) or {}
    usage_dict = meta.get("usage")
    if isinstance(usage_dict, dict) and usage_dict:
        return Usage(
            input_tokens=int(usage_dict.get("input_tokens", 0)),
            output_tokens=int(usage_dict.get("output_tokens", 0)),
            total_tokens=int(usage_dict.get("total_tokens", 0)),
        )
    return Usage()


def _attempt_cache_key(adapter: ModelAdapter, case: EvalCase, attempt_index: int) -> str:
    return cache_key(
        {
            "adapter": getattr(adapter, "name", adapter.__class__.__name__),
            "model": getattr(adapter, "model", None),
            "temperature": getattr(adapter, "temperature", None),
            "max_tokens": getattr(adapter, "max_tokens", None),
            "extra_body": getattr(adapter, "extra_body", None),
            "messages": case.messages,
            "prompt": case.prompt,
            "attempt": attempt_index,
        }
    )


def _prepare_workspace(case: EvalCase) -> Path | None:
    workspace = case.input.get("workspace")
    if not workspace:
        return None
    files = workspace.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"{case.id}: input.workspace.files must be an object")
    root = Path(tempfile.mkdtemp(prefix=f"evalbench-{case.id}-"))
    for relative_name, content in files.items():
        relative = Path(str(relative_name))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{case.id}: unsafe workspace path {relative}")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    return root


def _summarize(
    run_id: str,
    results: list[dict[str, Any]],
    adapter: ModelAdapter,
    options: RunOptions,
    repeat: int,
) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    case_scores = [float(result["score"]) for result in results]
    score = stats.mean(case_scores)

    by_capability: dict[str, dict[str, Any]] = {}
    for result in results:
        caps = result.get("capability") or ["uncategorized"]
        for cap in caps:
            bucket = by_capability.setdefault(cap, {"count": 0, "passed": 0, "scores": []})
            bucket["count"] += 1
            bucket["passed"] += int(bool(result["passed"]))
            bucket["scores"].append(float(result["score"]))
    for bucket in by_capability.values():
        bucket_scores = bucket.pop("scores")
        bucket["score"] = stats.mean(bucket_scores)
        low, high = stats.wilson_interval(bucket["passed"], bucket["count"])
        bucket["pass_rate_ci"] = [round(low, 4), round(high, 4)]

    total_usage = Usage()
    for result in results:
        total_usage = total_usage + Usage(**result.get("usage", {}))
    total_cost = round(sum(float(result.get("cost_usd", 0.0)) for result in results), 6)

    pass_low, pass_high = stats.wilson_interval(passed, total) if total else (0.0, 0.0)
    score_low, score_high = stats.bootstrap_mean_ci(case_scores, seed=options.seed) if total else (0.0, 0.0)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "adapter": getattr(adapter, "name", adapter.__class__.__name__),
        "judge": options.judge_name,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "score": score,
        "pass_rate": round(passed / total, 6) if total else 0.0,
        "pass_rate_ci": [round(pass_low, 4), round(pass_high, 4)],
        "score_ci": [round(score_low, 4), round(score_high, 4)],
        "by_capability": by_capability,
        "usage": total_usage.as_dict(),
        "cost_usd": total_cost,
        "latency_ms_total": round(sum(float(r.get("latency_ms", 0.0)) for r in results), 2),
        "manifest": _build_manifest(results, adapter, options, repeat),
    }
    if repeat > 1:
        summary["repeat"] = repeat
        summary["pass_at_1"] = round(stats.mean([float(r.get("pass_at_1", 0.0)) for r in results]), 6)
        summary["pass_at_k"] = round(stats.mean([float(r.get("pass_at_k", 0.0)) for r in results]), 6)
        summary["pass_pow_k"] = round(stats.mean([float(r.get("pass_pow_k", 0.0)) for r in results]), 6)
    return summary


def _build_manifest(
    results: list[dict[str, Any]],
    adapter: ModelAdapter,
    options: RunOptions,
    repeat: int,
) -> dict[str, Any]:
    sources = sorted({str(r.get("source", "")).rsplit(":", 1)[0] for r in results if r.get("source")})
    return {
        "schema_version": SCHEMA_VERSION,
        "evalbench_version": _evalbench_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "seed": options.seed,
        "repeat": repeat,
        "concurrency": max(1, int(options.concurrency)),
        "cache": not isinstance(options.cache, (type(None), NullCache)),
        "model": {
            "adapter": getattr(adapter, "name", adapter.__class__.__name__),
            "model": getattr(adapter, "model", None),
            "temperature": getattr(adapter, "temperature", None),
            "max_tokens": getattr(adapter, "max_tokens", None),
        },
        "dataset": {
            "files": _dataset_fingerprint(sources),
            "case_count": len(results),
        },
    }


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


def _evalbench_version() -> str:
    try:
        from importlib.metadata import version

        return version("personal-evalbench")
    except Exception:  # noqa: BLE001 - version is best-effort metadata.
        return "0.1.0"
