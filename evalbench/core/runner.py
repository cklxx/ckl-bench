from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evalbench.adapters.base import GenerateRequest, ModelAdapter

from .cases import EvalCase
from .grading import grade_case
from .reporting import write_html_report


@dataclass(frozen=True)
class RunOptions:
    out_dir: Path
    run_name: str | None = None
    keep_workspaces: bool = False
    include_raw: bool = False


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

    results: list[dict[str, Any]] = []
    with results_path.open("w", encoding="utf-8") as handle:
        for case in cases:
            result = _run_one(case, adapter, options, run_dir)
            results.append(result)
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")
            handle.flush()

    summary = _summarize(run_id, results, adapter)
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


def _run_one(case: EvalCase, adapter: ModelAdapter, options: RunOptions, run_dir: Path) -> dict[str, Any]:
    workspace_path = _prepare_workspace(case)
    started = time.perf_counter()
    response_text = ""
    raw_response: Any = None
    error = None
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
    except Exception as exc:  # noqa: BLE001 - one bad case should produce evidence.
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    grade = grade_case(case, response_text, workspace_path)
    result: dict[str, Any] = {
        "case_id": case.id,
        "title": case.title,
        "type": case.type,
        "capability": case.capability,
        "difficulty": case.difficulty,
        "source": f"{case.source_path}:{case.source_line}",
        "score": grade.score,
        "passed": grade.passed and error is None,
        "checks": [check.as_dict() for check in grade.checks],
        "latency_ms": elapsed_ms,
        "response_text": response_text,
        "error": error,
    }
    if options.include_raw:
        result["raw_response"] = raw_response

    if workspace_path and options.keep_workspaces:
        saved = run_dir / "workspaces" / case.id
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace_path, saved)
        result["workspace_saved"] = str(saved)
    if workspace_path:
        shutil.rmtree(workspace_path, ignore_errors=True)
    return result


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


def _summarize(run_id: str, results: list[dict[str, Any]], adapter: ModelAdapter) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    score = sum(float(result["score"]) for result in results) / total if total else 0.0
    by_capability: dict[str, dict[str, Any]] = {}
    for result in results:
        caps = result.get("capability") or ["uncategorized"]
        for cap in caps:
            bucket = by_capability.setdefault(cap, {"count": 0, "passed": 0, "score_sum": 0.0})
            bucket["count"] += 1
            bucket["passed"] += int(bool(result["passed"]))
            bucket["score_sum"] += float(result["score"])
    for bucket in by_capability.values():
        bucket["score"] = bucket["score_sum"] / bucket["count"]
        del bucket["score_sum"]
    return {
        "run_id": run_id,
        "adapter": getattr(adapter, "name", adapter.__class__.__name__),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "score": score,
        "by_capability": by_capability,
    }
