from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_terminal_report(summary: dict[str, Any], results: list[dict[str, Any]], run_dir: str) -> str:
    score = float(summary.get("score", 0.0))
    lines = [
        "",
        f"Score  {_bar(score, 28)}  {score * 100:5.1f}%",
        f"Cases  {summary['passed']}/{summary['total']} passed  |  failed {summary['failed']}  |  run {run_dir}",
    ]
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


def write_html_report(run_dir: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> Path:
    path = run_dir / "report.html"
    path.write_text(_html_report(summary, results), encoding="utf-8")
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
    path.write_text(_probe_html(summary, rows), encoding="utf-8")
    return path


def _bar(score: float, width: int = 18) -> str:
    clamped = max(0.0, min(1.0, score))
    filled = round(clamped * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


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


def _status_class(passed: bool) -> str:
    return "pass" if passed else "fail"


def _html_report(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    score = float(summary["score"])
    capability_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(capability)}</td>
          <td><div class="bar"><span style="width:{float(bucket['score']) * 100:.1f}%"></span></div></td>
          <td>{float(bucket['score']) * 100:.1f}%</td>
          <td>{bucket['passed']}/{bucket['count']}</td>
        </tr>
        """
        for capability, bucket in sorted(summary.get("by_capability", {}).items())
    )
    case_rows = "\n".join(
        f"""
        <tr>
          <td><span class="pill {_status_class(bool(result['passed']))}">{'PASS' if result['passed'] else 'FAIL'}</span></td>
          <td>{html.escape(result['case_id'])}</td>
          <td>{float(result['score']) * 100:.1f}%</td>
          <td>{html.escape(', '.join(result.get('capability') or []))}</td>
          <td>{html.escape(_first_failure_reason(result) if not result['passed'] else result.get('response_text', '')[:160])}</td>
        </tr>
        """
        for result in results
    )
    payload = html.escape(json.dumps({"summary": summary, "results": results}, ensure_ascii=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>evalbench report</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#5d6d7e; --line:#d8dee9; --ok:#1f8a5b; --bad:#c0392b; --accent:#2f6f9f; --bg:#f7f9fb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width:1120px; margin:0 auto; padding:28px; }}
    header {{ display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:22px; }}
    h1 {{ margin:0; font-size:28px; font-weight:750; }}
    .meta {{ color:var(--muted); }}
    .scoreboard {{ display:grid; grid-template-columns: 1.2fr repeat(3, 1fr); gap:12px; margin-bottom:18px; }}
    .tile {{ background:white; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .big {{ font-size:40px; font-weight:800; letter-spacing:0; }}
    .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    .bar {{ height:10px; background:#e9edf2; border-radius:99px; overflow:hidden; min-width:120px; }}
    .bar span {{ display:block; height:100%; background:var(--accent); }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); border-radius:8px; overflow:hidden; margin:16px 0; }}
    th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; background:#fbfcfe; }}
    tr:last-child td {{ border-bottom:0; }}
    .pill {{ display:inline-block; min-width:48px; text-align:center; border-radius:999px; padding:2px 8px; color:white; font-size:12px; font-weight:700; }}
    .pill.pass {{ background:var(--ok); }}
    .pill.fail {{ background:var(--bad); }}
    @media (max-width:760px) {{ main {{ padding:16px; }} header,.scoreboard {{ display:block; }} .tile {{ margin-bottom:10px; }} table {{ display:block; overflow-x:auto; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>evalbench report</h1>
      <div class="meta">run {html.escape(str(summary['run_id']))} | adapter {html.escape(str(summary['adapter']))}</div>
    </div>
    <div class="meta">results.jsonl + summary.json</div>
  </header>
  <section class="scoreboard">
    <div class="tile"><div class="label">score</div><div class="big">{score * 100:.1f}%</div><div class="bar"><span style="width:{score * 100:.1f}%"></span></div></div>
    <div class="tile"><div class="label">passed</div><div class="big">{summary['passed']}</div></div>
    <div class="tile"><div class="label">failed</div><div class="big">{summary['failed']}</div></div>
    <div class="tile"><div class="label">total</div><div class="big">{summary['total']}</div></div>
  </section>
  <h2>Capability</h2>
  <table><thead><tr><th>capability</th><th>score</th><th>%</th><th>pass</th></tr></thead><tbody>{capability_rows}</tbody></table>
  <h2>Cases</h2>
  <table><thead><tr><th>status</th><th>case</th><th>score</th><th>capability</th><th>signal</th></tr></thead><tbody>{case_rows}</tbody></table>
  <script type="application/json" id="evalbench-data">{payload}</script>
</main>
</body>
</html>
"""


def _probe_html(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    row_html = "\n".join(
        f"""
        <tr>
          <td><span class="pill {html.escape(row['status'])}">{html.escape(row['status'].upper())}</span></td>
          <td>{html.escape(row['target'])}</td>
          <td>{html.escape(row['kind'])}</td>
          <td>{html.escape(_probe_score_text(row))}</td>
          <td>{html.escape(row['detail'])}</td>
        </tr>
        """
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>evalbench probe</title>
  <style>
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f9fb; color:#17202a; }}
    main {{ max-width:1040px; margin:0 auto; padding:28px; }}
    .scoreboard {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin:18px 0; }}
    .tile, table {{ background:white; border:1px solid #d8dee9; border-radius:8px; }}
    .tile {{ padding:16px; }}
    .big {{ font-size:36px; font-weight:800; }}
    .label, th {{ color:#5d6d7e; font-size:12px; text-transform:uppercase; }}
    table {{ width:100%; border-collapse:collapse; overflow:hidden; }}
    th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #d8dee9; }}
    tr:last-child td {{ border-bottom:0; }}
    .pill {{ display:inline-block; min-width:52px; text-align:center; border-radius:999px; padding:2px 8px; color:white; font-size:12px; font-weight:700; }}
    .pass {{ background:#1f8a5b; }} .fail {{ background:#c0392b; }} .skip {{ background:#687385; }}
  </style>
</head>
<body>
<main>
  <h1>evalbench probe</h1>
  <section class="scoreboard">
    <div class="tile"><div class="label">score</div><div class="big">{float(summary['score']) * 100:.1f}%</div></div>
    <div class="tile"><div class="label">passed</div><div class="big">{summary['passed']}</div></div>
    <div class="tile"><div class="label">failed</div><div class="big">{summary['failed']}</div></div>
    <div class="tile"><div class="label">skipped</div><div class="big">{summary['skipped']}</div></div>
  </section>
  <table><thead><tr><th>status</th><th>target</th><th>kind</th><th>score</th><th>detail</th></tr></thead><tbody>{row_html}</tbody></table>
</main>
</body>
</html>
"""


def _probe_score_text(row: dict[str, Any]) -> str:
    if row.get("score") is None:
        return "-"
    return f"{float(row['score']) * 100:.1f}%"
