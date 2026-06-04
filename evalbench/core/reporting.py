from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


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
        cost = float(summary.get("cost_usd", 0.0))
        cost_text = f"  |  cost ${cost:.4f}" if cost else ""
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
    lines = [
        "",
        f"Diff   {diff['run_a']}  ->  {diff['run_b']}",
        f"Score  {diff['score_a'] * 100:5.1f}%  ->  {diff['score_b'] * 100:5.1f}%  "
        f"({'+' if diff['score_delta'] >= 0 else ''}{diff['score_delta'] * 100:.1f} pts)",
        f"Cases  regressed {counts['regressed']}  |  improved {counts['improved']}  |  "
        f"unchanged {counts['unchanged']}  |  added {counts['added']}  |  removed {counts['removed']}",
    ]
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
    path.write_text(_diff_html(diff), encoding="utf-8")
    return path


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
          <td class="muted">{_ci_text(bucket.get('pass_rate_ci'))}</td>
          <td>{bucket['passed']}/{bucket['count']}</td>
        </tr>
        """
        for capability, bucket in sorted(summary.get("by_capability", {}).items())
    )
    case_rows = "\n".join(_case_row_html(index, result) for index, result in enumerate(results))
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
    h2 {{ font-size:16px; margin:24px 0 4px; }}
    .meta {{ color:var(--muted); }}
    .muted {{ color:var(--muted); }}
    .scoreboard {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap:12px; margin-bottom:18px; }}
    .tile {{ background:white; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .tile.score {{ grid-column: span 2; }}
    .big {{ font-size:34px; font-weight:800; letter-spacing:0; }}
    .sub {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    .bar {{ height:10px; background:#e9edf2; border-radius:99px; overflow:hidden; min-width:120px; }}
    .bar span {{ display:block; height:100%; background:var(--accent); }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); border-radius:8px; overflow:hidden; margin:8px 0 16px; }}
    th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; background:#fbfcfe; }}
    tr:last-child td {{ border-bottom:0; }}
    .pill {{ display:inline-block; min-width:48px; text-align:center; border-radius:999px; padding:2px 8px; color:white; font-size:12px; font-weight:700; }}
    .pill.pass {{ background:var(--ok); }}
    .pill.fail {{ background:var(--bad); }}
    .controls {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:8px 0; }}
    .controls button {{ font:inherit; border:1px solid var(--line); background:white; border-radius:6px; padding:5px 12px; cursor:pointer; }}
    .controls button.active {{ background:var(--accent); color:white; border-color:var(--accent); }}
    .controls input {{ font:inherit; border:1px solid var(--line); border-radius:6px; padding:6px 10px; flex:1; min-width:160px; }}
    tr.case {{ cursor:pointer; }}
    tr.case:hover td {{ background:#f3f7fb; }}
    tr.detail > td {{ background:#fbfcfe; }}
    tr.detail pre {{ white-space:pre-wrap; word-break:break-word; margin:0 0 10px; padding:10px; background:#0f172a; color:#e2e8f0; border-radius:6px; max-height:340px; overflow:auto; font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    .check {{ display:flex; gap:8px; padding:3px 0; }}
    .check .k {{ font-weight:600; min-width:120px; }}
    .hidden {{ display:none; }}
    @media (max-width:760px) {{ main {{ padding:16px; }} header {{ display:block; }} .scoreboard {{ grid-template-columns:repeat(2,1fr); }} .tile.score {{ grid-column: span 2; }} table {{ display:block; overflow-x:auto; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>evalbench report</h1>
      <div class="meta">run {html.escape(str(summary['run_id']))} | adapter {html.escape(str(summary['adapter']))}{_judge_meta(summary)}{_manifest_meta(summary)}</div>
    </div>
    <div class="meta">results.jsonl + summary.json</div>
  </header>
  <section class="scoreboard">
    <div class="tile score"><div class="label">score</div><div class="big">{score * 100:.1f}%</div><div class="bar"><span style="width:{score * 100:.1f}%"></span></div><div class="sub">{_ci_text(summary.get('score_ci'), '95% CI ')}</div></div>
    <div class="tile"><div class="label">passed</div><div class="big">{summary['passed']}</div><div class="sub">{_ci_text(summary.get('pass_rate_ci'), 'rate ')}</div></div>
    <div class="tile"><div class="label">failed</div><div class="big">{summary['failed']}</div></div>
    <div class="tile"><div class="label">total</div><div class="big">{summary['total']}</div></div>
    {_repeat_cost_tiles(summary)}
  </section>
  <h2>Capability</h2>
  <table><thead><tr><th>capability</th><th>score</th><th>%</th><th>95% CI</th><th>pass</th></tr></thead><tbody>{capability_rows}</tbody></table>
  <h2>Cases</h2>
  <div class="controls">
    <button data-filter="all" class="active">All</button>
    <button data-filter="pass">Passed</button>
    <button data-filter="fail">Failed</button>
    <input id="case-search" type="search" placeholder="filter cases by id, capability, or text...">
  </div>
  <table><thead><tr><th>status</th><th>case</th><th>score</th><th>capability</th><th>signal</th></tr></thead><tbody id="case-body">{case_rows}</tbody></table>
  <script type="application/json" id="evalbench-data">{payload}</script>
  <script>
  (function() {{
    var body = document.getElementById('case-body');
    function rows() {{ return Array.prototype.slice.call(body.querySelectorAll('tr.case')); }}
    rows().forEach(function(row) {{
      row.addEventListener('click', function() {{
        var detail = document.getElementById('detail-' + row.dataset.idx);
        if (detail) detail.classList.toggle('hidden');
      }});
    }});
    var filter = 'all', query = '';
    function apply() {{
      rows().forEach(function(row) {{
        var statusOk = filter === 'all' || row.dataset.status === filter;
        var textOk = query === '' || row.dataset.search.indexOf(query) !== -1;
        var show = statusOk && textOk;
        row.classList.toggle('hidden', !show);
        var detail = document.getElementById('detail-' + row.dataset.idx);
        if (detail && !show) detail.classList.add('hidden');
      }});
    }}
    document.querySelectorAll('.controls button').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        document.querySelectorAll('.controls button').forEach(function(b) {{ b.classList.remove('active'); }});
        btn.classList.add('active');
        filter = btn.dataset.filter; apply();
      }});
    }});
    var search = document.getElementById('case-search');
    search.addEventListener('input', function() {{ query = search.value.toLowerCase(); apply(); }});
  }})();
  </script>
</main>
</body>
</html>
"""


def _case_row_html(index: int, result: dict[str, Any]) -> str:
    passed = bool(result["passed"])
    caps = ", ".join(result.get("capability") or [])
    signal = _first_failure_reason(result) if not passed else (result.get("response_text", "") or "")[:160]
    search = " ".join(
        [str(result.get("case_id", "")), caps, str(result.get("response_text", "")), signal]
    ).lower()
    checks_html = "".join(
        f"""<div class="check"><span class="pill {_status_class(bool(check.get('passed')))}">{'PASS' if check.get('passed') else 'FAIL'}</span>"""
        f"""<span class="k">{html.escape(str(check.get('kind', '')))}</span>"""
        f"""<span class="muted">{html.escape(str(check.get('detail', '')))}</span></div>"""
        for check in result.get("checks", [])
    )
    response = result.get("response_text", "") or ""
    error_html = f"<p class=\"muted\">error: {html.escape(str(result['error']))}</p>" if result.get("error") else ""
    repeat_html = ""
    if result.get("repeat"):
        repeat_html = (
            f"<p class=\"muted\">repeats {result['passes']}/{result['repeat']} | "
            f"pass@1 {float(result.get('pass_at_1', 0)) * 100:.0f}% | "
            f"pass^{result['repeat']} {float(result.get('pass_pow_k', 0)) * 100:.0f}%</p>"
        )
    usage = result.get("usage") or {}
    usage_html = ""
    if usage.get("total_tokens"):
        usage_html = f"<p class=\"muted\">{usage['total_tokens']} tokens | ${float(result.get('cost_usd', 0)):.5f} | {result.get('latency_ms', 0)}ms</p>"
    return f"""
        <tr class="case" data-idx="{index}" data-status="{'pass' if passed else 'fail'}" data-search="{html.escape(search)}">
          <td><span class="pill {_status_class(passed)}">{'PASS' if passed else 'FAIL'}</span></td>
          <td>{html.escape(str(result['case_id']))}</td>
          <td>{float(result['score']) * 100:.1f}%</td>
          <td>{html.escape(caps)}</td>
          <td>{html.escape(signal)}</td>
        </tr>
        <tr class="detail hidden" id="detail-{index}">
          <td colspan="5">
            {repeat_html}{usage_html}{error_html}
            <div>{checks_html}</div>
            <p class="muted" style="margin:10px 0 4px">response</p>
            <pre>{html.escape(response[:8000])}</pre>
          </td>
        </tr>
    """


def _ci_text(ci: Any, prefix: str = "") -> str:
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return ""
    return f"{prefix}[{float(ci[0]) * 100:.1f}, {float(ci[1]) * 100:.1f}]"


def _manifest_meta(summary: dict[str, Any]) -> str:
    manifest = summary.get("manifest") or {}
    bits = []
    model = (manifest.get("model") or {}).get("model")
    if model:
        bits.append(html.escape(str(model)))
    if manifest.get("git_sha"):
        bits.append("git " + html.escape(str(manifest["git_sha"])[:8]))
    if manifest.get("repeat", 1) and int(manifest.get("repeat", 1)) > 1:
        bits.append(f"{manifest['repeat']}x")
    return (" | " + " | ".join(bits)) if bits else ""


def _repeat_cost_tiles(summary: dict[str, Any]) -> str:
    tiles = []
    usage = summary.get("usage") or {}
    if usage.get("total_tokens"):
        cost = float(summary.get("cost_usd", 0.0))
        tiles.append(
            f'<div class="tile"><div class="label">tokens</div><div class="big">{usage["total_tokens"]}</div>'
            f'<div class="sub">${cost:.4f}</div></div>'
        )
    if int(summary.get("repeat", 1) or 1) > 1:
        repeat = summary["repeat"]
        tiles.append(
            f'<div class="tile"><div class="label">pass@{repeat}</div>'
            f'<div class="big">{float(summary.get("pass_at_k", 0)) * 100:.0f}%</div>'
            f'<div class="sub">pass^{repeat} {float(summary.get("pass_pow_k", 0)) * 100:.0f}%</div></div>'
        )
    return "\n".join(tiles)


def _judge_meta(summary: dict[str, Any]) -> str:
    if not summary.get("judge"):
        return ""
    return " | judge " + html.escape(str(summary["judge"]))


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


_DIFF_STATUS_CLASS = {
    "regressed": "bad",
    "improved": "ok",
    "added": "neutral",
    "removed": "neutral",
    "unchanged": "muted",
}


def _diff_html(diff: dict[str, Any]) -> str:
    counts = diff["counts"]
    rows = "\n".join(
        f"""
        <tr class="{_DIFF_STATUS_CLASS[case['status']]}">
          <td><span class="tag {_DIFF_STATUS_CLASS[case['status']]}">{html.escape(case['status'])}</span></td>
          <td>{html.escape(str(case['case_id']))}</td>
          <td>{'-' if case['a_score'] is None else f"{case['a_score'] * 100:.1f}%"}</td>
          <td>{'-' if case['b_score'] is None else f"{case['b_score'] * 100:.1f}%"}</td>
          <td>{'' if case['delta'] is None else ('+' if case['delta'] >= 0 else '') + f"{case['delta'] * 100:.1f}"}</td>
        </tr>
        """
        for case in diff["cases"]
    )
    delta = diff["score_delta"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>evalbench diff</title>
  <style>
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f9fb; color:#17202a; }}
    main {{ max-width:1040px; margin:0 auto; padding:28px; }}
    h1 {{ font-size:24px; }}
    .scoreboard {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin:18px 0; }}
    .tile, table {{ background:white; border:1px solid #d8dee9; border-radius:8px; }}
    .tile {{ padding:16px; }}
    .big {{ font-size:30px; font-weight:800; }}
    .label, th {{ color:#5d6d7e; font-size:12px; text-transform:uppercase; }}
    table {{ width:100%; border-collapse:collapse; overflow:hidden; }}
    th, td {{ padding:9px 12px; text-align:left; border-bottom:1px solid #eef2f6; }}
    .tag {{ display:inline-block; border-radius:999px; padding:2px 9px; color:white; font-size:12px; font-weight:700; }}
    .tag.ok {{ background:#1f8a5b; }} .tag.bad {{ background:#c0392b; }} .tag.neutral {{ background:#687385; }} .tag.muted {{ background:#aeb6c2; }}
    tr.bad td {{ background:#fdf3f2; }} tr.ok td {{ background:#f1faf5; }}
  </style>
</head>
<body>
<main>
  <h1>evalbench diff</h1>
  <p class="label">{html.escape(str(diff['run_a']))} &rarr; {html.escape(str(diff['run_b']))}</p>
  <section class="scoreboard">
    <div class="tile"><div class="label">score delta</div><div class="big">{'+' if delta >= 0 else ''}{delta * 100:.1f}</div><div class="label">{diff['score_a'] * 100:.1f}% &rarr; {diff['score_b'] * 100:.1f}%</div></div>
    <div class="tile"><div class="label">regressed</div><div class="big">{counts['regressed']}</div></div>
    <div class="tile"><div class="label">improved</div><div class="big">{counts['improved']}</div></div>
    <div class="tile"><div class="label">unchanged</div><div class="big">{counts['unchanged']}</div></div>
    <div class="tile"><div class="label">added / removed</div><div class="big">{counts['added']}/{counts['removed']}</div></div>
  </section>
  <table><thead><tr><th>status</th><th>case</th><th>A</th><th>B</th><th>&Delta; pts</th></tr></thead><tbody>{rows}</tbody></table>
</main>
</body>
</html>
"""
