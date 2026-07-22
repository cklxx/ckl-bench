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


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _classify(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str:
    if a is None:
        return "added"
    if b is None:
        return "removed"
    a_pass, b_pass = a.get("passed"), b.get("passed")
    a_score, b_score = _number(a.get("score")), _number(b.get("score"))
    if a_pass is None or b_pass is None or a_score is None or b_score is None:
        return "indeterminate"
    if a_pass != b_pass:
        return "improved" if b_pass else "regressed"
    delta = b_score - a_score
    if delta > SCORE_EPSILON:
        return "improved"
    if delta < -SCORE_EPSILON:
        return "regressed"
    return "unchanged"


# Sort order: regressions first (most actionable), then improvements, etc.
_ORDER = {"regressed": 0, "indeterminate": 1, "improved": 2, "added": 3, "removed": 4, "unchanged": 5}


def _comparability(
    summary_a: dict[str, Any], summary_b: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], str | None]:
    manifest_a = summary_a.get("manifest") or {}
    manifest_b = summary_b.get("manifest") or {}
    signature_a = manifest_a.get("comparability_signature")
    signature_b = manifest_b.get("comparability_signature")
    if not signature_a or not signature_b:
        return "unknown", [], "one or both runs predate comparability signatures"
    if signature_a == signature_b:
        return "compatible", [], None
    differences = _policy_differences(
        manifest_a.get("comparability"), manifest_b.get("comparability")
    )
    if not differences:
        differences = [{"path": "comparability_signature", "a": signature_a, "b": signature_b}]
    return "incompatible", differences, "run policies differ; aggregate verdict suppressed"


def _policy_differences(a: Any, b: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(a, dict) and isinstance(b, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(a) | set(b)):
            child = f"{path}.{key}" if path else str(key)
            differences.extend(_policy_differences(a.get(key), b.get(key), child))
        return differences
    if isinstance(a, list) and isinstance(b, list):
        differences = []
        for index in range(max(len(a), len(b))):
            child = f"{path}[{index}]"
            left = a[index] if index < len(a) else None
            right = b[index] if index < len(b) else None
            differences.extend(_policy_differences(left, right, child))
        return differences
    return [] if a == b else [{"path": path or "comparability", "a": a, "b": b}]


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
    counts = {status: 0 for status in _ORDER}
    for case_id in all_ids:
        a, b = by_a.get(case_id), by_b.get(case_id)
        status = _classify(a, b)
        counts[status] += 1
        a_score = _number(a.get("score")) if a else None
        b_score = _number(b.get("score")) if b else None
        cases.append(
            {
                "case_id": case_id,
                "status": status,
                "a_score": a_score,
                "b_score": b_score,
                "a_passed": a.get("passed") if a else None,
                "b_passed": b.get("passed") if b else None,
                "delta": (b_score - a_score) if (a_score is not None and b_score is not None) else None,
            }
        )
    cases.sort(key=lambda c: (_ORDER[c["status"]], -(abs(c["delta"]) if c["delta"] is not None else 0)))
    comparability_status, comparability_differences, comparability_warning = _comparability(
        summary_a, summary_b
    )
    score_a = _number(summary_a.get("score"))
    score_b = _number(summary_b.get("score"))
    aggregate_verdict = None
    comparable = comparability_status == "compatible" and score_a is not None and score_b is not None
    if comparable:
        delta = score_b - score_a
        aggregate_verdict = (
            "improved" if delta > SCORE_EPSILON
            else "regressed" if delta < -SCORE_EPSILON
            else "unchanged"
        )
    elif comparability_status == "compatible":
        comparability_status = "indeterminate"
        comparability_warning = "one or both runs are incomplete or unscored"

    return {
        "run_a": summary_a.get("run_id", "A"),
        "run_b": summary_b.get("run_id", "B"),
        "adapter_a": summary_a.get("adapter"),
        "adapter_b": summary_b.get("adapter"),
        "score_a": score_a,
        "score_b": score_b,
        "score_delta": (score_b - score_a) if comparable else None,
        "aggregate_verdict": aggregate_verdict,
        "comparability": {
            "status": comparability_status,
            "differences": comparability_differences,
            "warning": comparability_warning,
        },
        "score_ci_a": summary_a.get("score_ci"),
        "score_ci_b": summary_b.get("score_ci"),
        "passed_a": summary_a.get("passed"),
        "passed_b": summary_b.get("passed"),
        "counts": counts,
        "cases": cases,
    }
