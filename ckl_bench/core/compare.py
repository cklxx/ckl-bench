"""Compare two runs and classify each case as improved / regressed / unchanged.

Run-vs-run diffing is the Braintrust differentiator: it turns "model A scores 71%,
model B scores 68%" into "these 4 cases regressed, these 2 improved." That is what
makes an eval suite a regression gate rather than a vanity number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# A score change smaller than this is treated as noise (cases with the same
# pass/fail verdict and near-equal score are "unchanged").
SCORE_EPSILON = 1e-9


def load_run(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load (summary, results) from a run directory, summary.json, or results.jsonl."""
    p = Path(path)
    if p.is_dir():
        summary_path = p / "summary.json"
        results_path = p / "results.jsonl"
    elif p.name == "summary.json":
        summary_path = p
        results_path = p.parent / "results.jsonl"
    elif p.name == "results.jsonl":
        summary_path = p.parent / "summary.json"
        results_path = p
    else:
        raise FileNotFoundError(f"not a run dir or summary/results file: {path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    results: list[dict[str, Any]] = []
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return summary, results


def _classify(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str:
    if a is None:
        return "added"
    if b is None:
        return "removed"
    a_pass, b_pass = bool(a["passed"]), bool(b["passed"])
    if a_pass != b_pass:
        return "improved" if b_pass else "regressed"
    delta = float(b["score"]) - float(a["score"])
    if delta > SCORE_EPSILON:
        return "improved"
    if delta < -SCORE_EPSILON:
        return "regressed"
    return "unchanged"


# Sort order: regressions first (most actionable), then improvements, etc.
_ORDER = {"regressed": 0, "improved": 1, "added": 2, "removed": 3, "unchanged": 4}


def compare_runs(
    summary_a: dict[str, Any],
    results_a: list[dict[str, Any]],
    summary_b: dict[str, Any],
    results_b: list[dict[str, Any]],
) -> dict[str, Any]:
    by_a = {r["case_id"]: r for r in results_a}
    by_b = {r["case_id"]: r for r in results_b}
    all_ids = list(by_a.keys()) + [cid for cid in by_b if cid not in by_a]

    cases: list[dict[str, Any]] = []
    counts = {"improved": 0, "regressed": 0, "unchanged": 0, "added": 0, "removed": 0}
    for case_id in all_ids:
        a, b = by_a.get(case_id), by_b.get(case_id)
        status = _classify(a, b)
        counts[status] += 1
        a_score = float(a["score"]) if a else None
        b_score = float(b["score"]) if b else None
        cases.append(
            {
                "case_id": case_id,
                "status": status,
                "a_score": a_score,
                "b_score": b_score,
                "a_passed": bool(a["passed"]) if a else None,
                "b_passed": bool(b["passed"]) if b else None,
                "delta": (b_score - a_score) if (a_score is not None and b_score is not None) else None,
            }
        )
    cases.sort(key=lambda c: (_ORDER[c["status"]], -(abs(c["delta"]) if c["delta"] is not None else 0)))

    return {
        "run_a": summary_a.get("run_id", "A"),
        "run_b": summary_b.get("run_id", "B"),
        "adapter_a": summary_a.get("adapter"),
        "adapter_b": summary_b.get("adapter"),
        "score_a": float(summary_a.get("score", 0.0)),
        "score_b": float(summary_b.get("score", 0.0)),
        "score_delta": float(summary_b.get("score", 0.0)) - float(summary_a.get("score", 0.0)),
        "score_ci_a": summary_a.get("score_ci"),
        "score_ci_b": summary_b.get("score_ci"),
        "passed_a": summary_a.get("passed"),
        "passed_b": summary_b.get("passed"),
        "counts": counts,
        "cases": cases,
    }
