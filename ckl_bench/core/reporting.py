from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Location of the pre-built React single-file app, relative to the package.
_WEB_TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "index.html"


def _render_react_page(data: dict[str, Any]) -> str:
    """Inject *data* into the pre-built React app template.

    The template is a self-contained HTML file (JS/CSS inlined by
    vite-plugin-singlefile).  We inject ``window.__CKL_BENCH_DATA__`` so the
    React app knows which page to render and what data to use.
    """
    template = _load_web_template()
    payload = json.dumps(data, ensure_ascii=False, default=str)
    injection = (
        "<script>\n"
        "  window.__CKL_BENCH_DATA__ = " + payload + ";\n"
        "</script>\n"
    )
    # Insert the data script right after <body> so it is available before the
    # React bundle executes.
    if "<body>" in template:
        return template.replace("<body>", "<body>\n" + injection, 1)
    # Fallback: prepend (template should always have <body>).
    return injection + template


def _load_web_template() -> str:
    """Load the built React template, falling back to the repo web/dist/."""
    if _WEB_TEMPLATE.exists():
        return _WEB_TEMPLATE.read_text(encoding="utf-8")
    # Fallback: repo-level build output (development).
    repo_template = (
        Path(__file__).resolve().parent.parent.parent / "web" / "dist" / "index.html"
    )
    if repo_template.exists():
        return repo_template.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "Web template not found. Run 'cd web && npm install && npm run build' "
        "to build the frontend, then copy web/dist/index.html to "
        "ckl_bench/web/index.html."
    )


def render_terminal_report(summary: dict[str, Any], results: list[dict[str, Any]], run_dir: str) -> str:
    score = float(summary.get("score", 0.0))
    lines = [
        "",
        f"Score  {_bar(score, 28)}  {score * 100:5.1f}%{_ci_suffix(summary.get('score_ci'))}",
        f"Cases  {summary['passed']}/{summary['total']} passed  |  failed {summary['failed']}  |  run {run_dir}",
    ]
    repeat = int(summary.get("repeat", 1) or 1)
    if repeat > 1:
        lines.append(
            f"Reps   {repeat}x  |  pass@1 {summary.get('pass_at_1', 0.0) * 100:4.1f}%  "
            f"pass@{repeat} {summary.get('pass_at_k', 0.0) * 100:4.1f}%  "
            f"pass^{repeat} {summary.get('pass_pow_k', 0.0) * 100:4.1f}%"
        )
    usage = summary.get("usage") or {}
    if usage.get("total_tokens"):
        cost = summary.get("estimated_cost_usd", summary.get("cost_usd"))
        if cost is None:
            cost_text = "  |  estimated cost unknown"
        else:
            cost_text = f"  |  estimated cost ${float(cost):.4f}"
        lines.append(f"Usage  {usage['total_tokens']} tokens ({usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out){cost_text}")
    if summary.get("judge"):
        lines.append(f"Judge  {summary['judge']}")
    capability_lines = _capability_lines(summary.get("by_capability", {}))
    if capability_lines:
        lines.append("")
        lines.append("Capability")
        lines.extend(capability_lines)
    failed = [result for result in results if not result.get("passed")]
    if failed:
        lines.append("")
        lines.append("Failures")
        for result in failed[:8]:
            reason = _first_failure_reason(result)
            lines.append(f"- {result['case_id']}  score={float(result['score']):.2f}  {reason}")
    lines.append("")
    return "\n".join(lines)


def render_probe_terminal(rows: list[dict[str, Any]], report_path: Path | None = None) -> str:
    widths = {
        "target": max([len("target"), *(len(row["target"]) for row in rows)]),
        "kind": max([len("kind"), *(len(row["kind"]) for row in rows)]),
        "status": max([len("status"), *(len(row["status"]) for row in rows)]),
    }
    lines = ["", "Probe", f"{'target'.ljust(widths['target'])}  kind   status   score   detail"]
    lines.append(f"{'-' * widths['target']}  ----   ------   -----   ------")
    for row in rows:
        score = row.get("score")
        score_text = "-" if score is None else f"{float(score) * 100:5.1f}%"
        lines.append(
            f"{row['target'].ljust(widths['target'])}  "
            f"{row['kind'].ljust(5)}  "
            f"{row['status'].ljust(7)}  "
            f"{score_text}  {row['detail']}"
        )
    if report_path:
        lines.append(f"\nreport: {report_path}")
    lines.append("")
    return "\n".join(lines)


def render_diff_terminal(diff: dict[str, Any]) -> str:
    counts = diff["counts"]
    comparability = diff.get("comparability") or {"status": "unknown", "differences": []}
    status = comparability.get("status", "unknown")
    delta = diff.get("score_delta")
    if delta is None:
        score_line = (
            f"Score  {diff['score_a'] * 100:5.1f}%  ->  {diff['score_b'] * 100:5.1f}%  "
            "(aggregate verdict suppressed)"
        )
    else:
        score_line = (
            f"Score  {diff['score_a'] * 100:5.1f}%  ->  {diff['score_b'] * 100:5.1f}%  "
            f"({'+' if delta >= 0 else ''}{delta * 100:.1f} pts)"
        )
    lines = [
        "",
        f"Diff   {diff['run_a']}  ->  {diff['run_b']}",
        f"Comparable  {status}",
        score_line,
        f"Cases  regressed {counts['regressed']}  |  improved {counts['improved']}  |  "
        f"unchanged {counts['unchanged']}  |  added {counts['added']}  |  removed {counts['removed']}",
    ]
    warning = comparability.get("warning")
    if warning:
        lines.append(f"Warning  {warning}")
    differences = comparability.get("differences") or []
    for difference in differences[:5]:
        lines.append(f"  differs: {difference.get('path')}")
    changed = [c for c in diff["cases"] if c["status"] in {"regressed", "improved", "added", "removed"}]
    if changed:
        lines.append("")
        for case in changed[:20]:
            a = "-" if case["a_score"] is None else f"{case['a_score'] * 100:5.1f}%"
            b = "-" if case["b_score"] is None else f"{case['b_score'] * 100:5.1f}%"
            mark = {"regressed": "DOWN", "improved": "UP  ", "added": "NEW ", "removed": "GONE"}[case["status"]]
            lines.append(f"  {mark}  {a} -> {b}  {case['case_id']}")
        if len(changed) > 20:
            lines.append(f"  ... and {len(changed) - 20} more changed cases")
    lines.append("")
    return "\n".join(lines)


def write_diff_html_report(path: Path, diff: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    page = _render_react_page({"page": "diff", "diff": diff})
    path.write_text(page, encoding="utf-8")
    return path


def write_html_report(run_dir: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> Path:
    path = run_dir / "report.html"
    page = _render_react_page({
        "page": "report",
        "summary": summary,
        "results": results,
    })
    path.write_text(page, encoding="utf-8")
    return path


def write_probe_html_report(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in rows if row["status"] == "pass")
    failed = sum(1 for row in rows if row["status"] == "fail")
    skipped = sum(1 for row in rows if row["status"] == "skip")
    avg_scores = [float(row["score"]) for row in rows if row.get("score") is not None]
    score = sum(avg_scores) / len(avg_scores) if avg_scores else 0.0
    summary = {
        "run_id": path.parent.name,
        "adapter": "probe",
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "score": score,
    }
    page = _render_react_page({
        "page": "probe",
        "probe_summary": summary,
        "probe_rows": rows,
    })
    path.write_text(page, encoding="utf-8")
    return path


def write_dashboard(out_path: Path, runs: list[dict[str, Any]]) -> Path:
    """Generate an interactive HTML dashboard from a list of run summaries.

    Each entry in *runs* is a dict with at least: run_id, summary (the parsed
    summary.json), and optionally results (list of result dicts).  The
    dashboard shows an overview table, a score trend sparkline, a capability
    heatmap, and automatic data analysis (strongest / weakest / improving /
    regressing capabilities).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort runs by creation time (fall back to run_id lexical order)
    def _sort_key(r: dict[str, Any]) -> str:
        s = r.get("summary", {})
        created = (s.get("manifest", {}) or {}).get("created_at", "")
        return created or str(s.get("run_id", r.get("run_id", "")))

    runs = sorted(runs, key=_sort_key)
    summaries = [r.get("summary", {}) for r in runs]

    page = _render_react_page({
        "page": "dashboard",
        "runs": summaries,
    })
    out_path.write_text(page, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Terminal-only helpers
# ---------------------------------------------------------------------------


def _bar(score: float, width: int = 18) -> str:
    clamped = max(0.0, min(1.0, score))
    filled = round(clamped * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _ci_suffix(ci: Any) -> str:
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return ""
    low, high = float(ci[0]), float(ci[1])
    return f"  95% CI [{low * 100:.1f}, {high * 100:.1f}]"


def _capability_lines(by_capability: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for capability, bucket in sorted(by_capability.items()):
        score = float(bucket["score"])
        lines.append(
            f"- {capability.ljust(22)} {_bar(score)} "
            f"{score * 100:5.1f}%  {bucket['passed']}/{bucket['count']}"
        )
    return lines


def _first_failure_reason(result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])
    for check in result.get("checks", []):
        if not check.get("passed"):
            return str(check.get("detail", "failed check"))
    return "failed"
