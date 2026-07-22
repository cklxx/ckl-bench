from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ckl_bench.adapters import build_adapter
from ckl_bench.core.cache import ResponseCache
from ckl_bench.core.cases import CaseValidationError, load_cases
from ckl_bench.core.compare import compare_runs, load_run
from ckl_bench.core.env import EnvFileError, load_default_env
from ckl_bench.core.providers import (
    ProviderRegistryError,
    load_namespace,
    load_namespaces,
    load_provider,
    provider_probe_target,
    redacted_namespace,
)
from ckl_bench.core.reporting import (
    render_diff_terminal,
    render_probe_terminal,
    render_terminal_report,
    write_dashboard,
    write_diff_html_report,
    write_probe_html_report,
)
from ckl_bench.core.run_manager import collect_runs
from ckl_bench.core.runner import RunOptions, filter_cases, run_cases
from ckl_bench.resources import resource_path

CASE_ALIASES = {
    "all": str(resource_path("cases")),
    "chat": str(resource_path("cases/chat")),
    "agent": str(resource_path("cases/agent")),
    "doc-writing": str(resource_path("cases/doc-writing")),
    "infra-code": str(resource_path("cases/infra-code")),
    "paper-reading": str(resource_path("cases/paper-reading")),
}

MOCK_CONFIG_PATH = resource_path("configs/mock.responses.json")
COMMAND_AGENT_EXAMPLE = f"{sys.executable} -m ckl_bench.wrappers.example"
CLAUDE_CODE_WRAPPER = f"{sys.executable} -m ckl_bench.wrappers.claude_code"
CODEX_WRAPPER = f"{sys.executable} -m ckl_bench.wrappers.codex"
DSX_WRAPPER = f"{sys.executable} -m ckl_bench.wrappers.dsx"
CLAUDE_CODE_KEY_ENVS = ["CKL_CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "DSV4_API_KEY", "DEEPSEEK_API_KEY"]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"


def main(argv: list[str] | None = None) -> int:
    try:
        load_default_env()
    except EnvFileError as exc:
        print(f"env file error: {exc}", file=sys.stderr)
        return 2

    invoked_as = Path(sys.argv[0]).name
    prog = invoked_as if invoked_as in {"ckl", "ckl-bench", "evb", "evalbench"} else "ckl"
    parser = _build_parser(prog=prog)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CaseValidationError as exc:
        print(f"case validation error: {exc}", file=sys.stderr)
        return 2
    except ProviderRegistryError as exc:
        print(f"provider registry error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI should return readable failures.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _build_parser(prog: str = "ckl") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "ckl's personal benchmark for doc writing, infra code, and paper reading.\n"
            "Use 'ckl' as the short command; 'ckl-bench' and 'evb' remain available as "
            "aliases.\n"
            "One-click testing of the latest models via TUI coding CLIs, with "
            "interactive reports and auto analysis."
        ),
        epilog=f"""Quick commands:
  {prog} smoke                         validate + run built-in chat/agent smoke
  {prog} list                          list all cases
  {prog} list chat                     list chat cases only
  {prog} run chat                      run chat cases with built-in mock responses
  {prog} run command agent             run agent cases with the example command wrapper
  {prog} probe                         check mainstream APIs and agent wrappers
  {prog} namespaces                    list registered model namespaces

Mainstream APIs:
  # API keys live in .env or shell env. JSON uses placeholders only.
  OPENAI_API_KEY=...     {prog} run openai:gpt-4.1-mini chat
  ANTHROPIC_API_KEY=...  {prog} run anthropic:claude-3-5-haiku-latest chat
  GEMINI_API_KEY=...     {prog} run gemini:gemini-3.5-flash chat
  OPENROUTER_API_KEY=... {prog} run openrouter:openai/gpt-4.1-mini chat
  CKL_LOCAL_BASE_URL=http://127.0.0.1:8000/v1 {prog} run local chat
  DSV4_BASE_URL=https://api.deepseek.com       {prog} run deepseekv4 chat

Agents:
  {prog} run command agent --command "python path/to/wrapper.py"
  {prog} run claude-code agent          run agent cases with claude code CLI
  {prog} run codex agent                run agent cases with codex CLI
  {prog} run dsx agent                  run agent cases with dsx CLI
  CKL_AGENT_COMMAND="python path/to/wrapper.py" {prog} probe agent
  CKL_CODEX_COMMAND="python wrappers/codex.py"  {prog} probe agent
  CKL_DSX_COMMAND="python wrappers/dsx.py"      {prog} probe agent

Dashboard:
  {prog} dashboard                       generate interactive HTML dashboard from runs/

Judge:
  {prog} run deepseekv4 chat --judge deepseekv4
  CKL_JUDGE=deepseekv4 {prog} run deepseekv4 chat

Outputs:
  runs/<run-id>/results.jsonl     per-case evidence
  runs/<run-id>/summary.json      machine-readable score summary
  runs/<run-id>/report.html       visual scorecard
  runs/probe-*/probe.html         API/agent readiness dashboard

Case sets:
  all, chat, agent, or any JSONL file/directory path

Docs:
  docs/CASE_SCHEMA.md
  docs/ADAPTERS.md
  docs/PROBES.md
  docs/ENV.md
""",
    )
    subparsers = parser.add_subparsers(required=True)

    namespaces_parser = subparsers.add_parser(
        "namespaces",
        aliases=["providers"],
        help="List registered model namespaces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Examples:
  {prog} namespaces
  {prog} namespaces deepseekv4
  {prog} run deepseekv4 chat
  {prog} probe deepseekv4
""",
    )
    namespaces_parser.add_argument("namespace", nargs="?", help="Namespace id to print as redacted JSON")
    namespaces_parser.set_defaults(func=_cmd_namespaces)

    list_parser = subparsers.add_parser(
        "list",
        help="List available cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Examples:
  {prog} list
  {prog} list chat
  {prog} list agent
  {prog} list --cases cases/chat/hard_programming.jsonl
""",
    )
    _add_case_set_arg(list_parser)
    _add_case_args(list_parser)
    list_parser.set_defaults(func=_cmd_list)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate case files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Examples:
  {prog} validate
  {prog} validate chat
  {prog} validate --cases cases/agent
""",
    )
    _add_case_set_arg(validate_parser)
    _add_case_args(validate_parser)
    validate_parser.set_defaults(func=_cmd_validate)

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="Validate and run built-in smoke cases",
        description="Validate all cases, then run built-in mock chat and command-agent smoke tests.",
    )
    smoke_parser.set_defaults(func=_cmd_smoke)

    probe_parser = subparsers.add_parser(
        "probe",
        help="Probe mainstream APIs and agent bridges",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Check API keys, local OpenAI-compatible endpoints, and command-agent wrappers.",
        epilog=f"""Examples:
  {prog} probe
  {prog} probe api
  {prog} probe agent
  {prog} probe --out runs --run-name api-check
  {prog} probe deepseekv4

API env:
  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY
  CKL_LOCAL_BASE_URL, CKL_LOCAL_MODEL, CKL_LOCAL_API_KEY
  DSV4_BASE_URL, DSV4_MODEL, DSV4_API_KEY

Agent wrapper env:
  CKL_AGENT_COMMAND, CKL_CODEX_COMMAND, CKL_CLAUDE_COMMAND, CKL_GEMINI_COMMAND

Judge model env:
  CKL_JUDGE=deepseekv4
""",
    )
    probe_parser.add_argument("target", nargs="?", default="all", help="all, api, agent, or registered provider id")
    probe_parser.add_argument("--out", default="runs", help="Output directory")
    probe_parser.add_argument("--run-name", help="Stable probe directory name")
    probe_parser.add_argument("--live-agents", action="store_true", help="Run discovered agent CLIs")
    probe_parser.add_argument("--fail-on-failed", action="store_true", help="Return non-zero when a probe fails")
    probe_parser.set_defaults(func=_cmd_probe)

    run_parser = subparsers.add_parser(
        "run",
        help="Run cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Run a case set against a model API, mock adapter, HTTP adapter, or command agent.",
        epilog=f"""Short forms:
  {prog} run chat
  {prog} run command agent
  {prog} run claude-code agent
  {prog} run openai:gpt-4.1-mini chat
  {prog} run anthropic:claude-3-5-haiku-latest chat
  {prog} run gemini:gemini-3.5-flash chat
  {prog} run openrouter:openai/gpt-4.1-mini chat
  {prog} run local chat
  {prog} run deepseekv4 chat
  {prog} run deepseekv4 chat --judge deepseekv4

Full forms:
  {prog} run --adapter mock --cases cases/chat
  {prog} run --adapter command --command "python wrapper.py" agent
  {prog} run --adapter http-json --endpoint http://127.0.0.1:8000/generate chat
  {prog} run --adapter mypkg.adapters:MyAdapter --config config.json chat
""",
    )
    run_parser.add_argument(
        "target",
        nargs="?",
        help="Short target: mock, command, openai, openai:MODEL, or MODEL",
    )
    _add_case_set_arg(run_parser)
    _add_case_args(run_parser)
    run_parser.add_argument("--adapter", default="mock", help="Adapter name or module:Class")
    run_parser.add_argument("--config", help="JSON adapter config")
    run_parser.add_argument("--model", help="Model name for API adapters")
    run_parser.add_argument("--base-url", help="OpenAI-compatible base URL")
    run_parser.add_argument("--endpoint", help="Generic HTTP JSON endpoint")
    run_parser.add_argument("--header", action="append", default=[], help="HTTP header as KEY=VALUE")
    run_parser.add_argument("--command", help="Command for command adapter")
    run_parser.add_argument("--temperature", type=float, help="Sampling temperature")
    run_parser.add_argument("--max-tokens", type=int, help="Max output tokens")
    run_parser.add_argument("--case-id", action="append", default=[], help="Run only this case id")
    run_parser.add_argument("--capability", action="append", default=[], help="Run cases with capability")
    run_parser.add_argument("--limit", type=int, help="Limit number of selected cases")
    run_parser.add_argument("--judge", help="Judge target for judge expectations, for example deepseekv4")
    run_parser.add_argument("--reviewer", help="Reviewer target (adversarial pipeline: challenges the judge)")
    run_parser.add_argument("--verifier", help="Verifier target (adversarial pipeline: final verdict)")
    run_parser.add_argument("--out", default="runs", help="Output directory")
    run_parser.add_argument("--run-name", help="Stable run directory name")
    run_parser.add_argument("--keep-workspaces", action="store_true", help="Save final agent workspaces")
    run_parser.add_argument("--include-raw", action="store_true", help="Include raw adapter responses")
    run_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run each case N times for pass@k / pass^k reliability metrics",
    )
    run_parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of cases to run in parallel (thread pool). Default 1",
    )
    run_parser.add_argument("--seed", type=int, default=0, help="Seed for deterministic bootstrap CIs")
    run_parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable the content-addressed response cache (chat cases only)",
    )
    run_parser.add_argument(
        "--cache-dir",
        help="Cache directory (default .ckl_bench_cache or CKL_CACHE_DIR)",
    )
    run_parser.add_argument(
        "--fail-on-failed-cases",
        action="store_true",
        help="Return exit code 3 when any case fails",
    )
    run_parser.add_argument(
        "--fail-under",
        type=float,
        help="Return exit code 3 when the overall score is below this fraction (CI gate)",
    )
    run_parser.set_defaults(func=_cmd_run)

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two runs and flag regressions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Diff two runs by case: regressed, improved, unchanged, added, removed.",
        epilog=f"""Examples:
  {prog} diff runs/RUN_A runs/RUN_B
  {prog} diff runs/RUN_A/summary.json runs/RUN_B/summary.json --out runs/diff.html
  {prog} diff runs/RUN_A runs/RUN_B --fail-on-regression
""",
    )
    diff_parser.add_argument("run_a", help="Baseline run dir, summary.json, or results.jsonl")
    diff_parser.add_argument("run_b", help="Candidate run dir, summary.json, or results.jsonl")
    diff_parser.add_argument("--out", help="Write an HTML diff report to this path")
    diff_parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Return exit code 3 when any case regressed",
    )
    diff_parser.set_defaults(func=_cmd_diff)

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Generate an interactive HTML dashboard from all runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Scan the runs/ directory, aggregate every run summary, and write an "
            "interactive HTML dashboard with score trends, a capability heatmap, "
            "and automatic data analysis (strongest/weakest capabilities, "
            "improving/regressing trends, cost summary)."
        ),
        epilog=f"""Examples:
  {prog} dashboard
  {prog} dashboard --runs runs
  {prog} dashboard --out runs/dashboard.html
  {prog} dashboard --open
""",
    )
    dashboard_parser.add_argument("--runs", default="runs", help="Runs directory to scan (default: runs)")
    dashboard_parser.add_argument("--out", help="Output HTML path (default: <runs>/dashboard.html)")
    dashboard_parser.add_argument("--open", action="store_true", dest="open_browser", help="Open the dashboard in a browser")
    dashboard_parser.set_defaults(func=_cmd_dashboard)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the dashboard server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Start the ckl-bench dashboard server with a REST API and WebSocket "
            "for live progress. View and edit cases, launch evaluations, watch "
            "progress in real time, and see auto-classified results."
        ),
        epilog=f"""Examples:
  {prog} serve                         start server at http://127.0.0.1:8765
  {prog} serve --host 0.0.0.0 --port 9000
  {prog} serve --open                  open browser after start
  {prog} serve stop                    stop background server
  {prog} serve status                  check if server is running
""",
    )
    serve_parser.add_argument("action", nargs="?", default="start", choices=["start", "stop", "status"])
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    serve_parser.add_argument("--runs", default="runs", help="Runs directory (default: runs)")
    serve_parser.add_argument("--cases", default="cases", help="Cases directory (default: cases)")
    serve_parser.add_argument(
        "--origin",
        help="Exact browser Origin allowed by the HTTP and WebSocket servers",
    )
    serve_parser.add_argument("--open", action="store_true", dest="open_browser", help="Open browser after start")
    serve_parser.add_argument("--daemon", action="store_true", help="Run in background")
    serve_parser.set_defaults(func=_cmd_serve)

    # --- demo: one-click start + demo run + open browser ---------------------
    demo_parser = subparsers.add_parser(
        "demo",
        help="One-click demo: start server, run a sample eval, open browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Start the dashboard server, auto-launch a demo evaluation with the "
            "mock adapter, and open the browser to the live progress page — "
            "all with a single command."
        ),
        epilog=f"""Examples:
  {prog} demo
  {prog} demo --port 9000
  {prog} demo --cases 5
""",
    )
    demo_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    demo_parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    demo_parser.add_argument("--runs", default="runs", help="Runs directory (default: runs)")
    demo_parser.add_argument("--cases", default="cases", help="Cases directory (default: cases)")
    demo_parser.add_argument("--cases-count", type=int, default=3, help="Number of cases to run (default: 3)")
    demo_parser.set_defaults(func=_cmd_demo)

    return parser


def _add_case_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cases",
        action="append",
        default=[],
        help="Case file or directory. Defaults to ./cases or positional case set",
    )


def _add_case_set_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "case_set",
        nargs="?",
        default="all",
        help="Case set alias or path: all, chat, agent. Defaults to all",
    )


def _case_paths(args: argparse.Namespace) -> list[str]:
    if args.cases:
        return args.cases
    case_set = getattr(args, "case_set", "all") or "all"
    return [CASE_ALIASES.get(case_set, case_set)]


def _cmd_list(args: argparse.Namespace) -> int:
    cases = load_cases(_case_paths(args))
    if not cases:
        print("no cases found")
        return 0
    rows = [
        (case.id, case.type, ",".join(case.capability), case.title)
        for case in cases
    ]
    widths = [max(len(str(row[i])) for row in rows + [("id", "type", "capability", "title")]) for i in range(4)]
    print(_format_row(("id", "type", "capability", "title"), widths))
    print(_format_row(tuple("-" * width for width in widths), widths))  # type: ignore[arg-type]
    for row in rows:
        print(_format_row(row, widths))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    cases = load_cases(_case_paths(args))
    print(f"validated {len(cases)} cases")
    return 0


def _cmd_namespaces(args: argparse.Namespace) -> int:
    if args.namespace:
        namespace = load_namespace(args.namespace)
        if namespace is None:
            raise ValueError(f"unknown namespace: {args.namespace}")
        print(json.dumps(redacted_namespace(namespace), indent=2, ensure_ascii=True))
        return 0

    namespaces = load_namespaces()
    if not namespaces:
        print("no namespaces registered")
        return 0
    rows = [
        (
            namespace["namespace"],
            ",".join(namespace["aliases"]),
            str(namespace.get("default", "")),
            str(_default_provider(namespace).get("config", {}).get("model", "")),
            str(_default_provider(namespace).get("config", {}).get("base_url", "")),
        )
        for namespace in namespaces
    ]
    widths = [
        max(len(str(row[index])) for row in rows + [("namespace", "aliases", "target", "model", "base_url")])
        for index in range(5)
    ]
    print(_format_row5(("namespace", "aliases", "target", "model", "base_url"), widths))
    print(_format_row5(tuple("-" * width for width in widths), widths))  # type: ignore[arg-type]
    for row in rows:
        print(_format_row5(row, widths))
    return 0


def _cmd_smoke(_args: argparse.Namespace) -> int:
    _run_smoke_step("validate", "all")
    with tempfile.TemporaryDirectory(prefix="ckl-bench-smoke-") as tmp:
        chat_result = _run_smoke_step(
            "mock chat",
            "chat",
            adapter_name="mock",
            config=_load_default_mock_config(),
            out_dir=Path(tmp),
            run_name="chat",
        )
        agent_result = _run_smoke_step(
            "command agent",
            "agent",
            adapter_name="command",
            config={"command": COMMAND_AGENT_EXAMPLE},
            out_dir=Path(tmp),
            run_name="agent",
        )
    total = chat_result["summary"]["total"] + agent_result["summary"]["total"]
    passed = chat_result["summary"]["passed"] + agent_result["summary"]["passed"]
    failed = total - passed
    print(f"smoke: cases={total} passed={passed} failed={failed}")
    return 0 if failed == 0 else 3


def _cmd_run(args: argparse.Namespace) -> int:
    _apply_target_shorthand(args)
    cases = load_cases(_case_paths(args))
    selected = filter_cases(
        cases,
        case_ids=set(args.case_id) or None,
        capabilities=set(args.capability) or None,
        limit=args.limit,
    )
    if not selected:
        print("no cases selected", file=sys.stderr)
        return 2
    config = _adapter_config(args)
    adapter = build_adapter(args.adapter, config)
    judge_target = args.judge or os.environ.get("CKL_JUDGE")
    judge_adapter = adapter if judge_target in {"same", "self"} else _build_target_adapter(judge_target)
    reviewer_target = getattr(args, "reviewer", None) or os.environ.get("CKL_REVIEWER")
    reviewer_adapter = (
        adapter if reviewer_target in {"same", "self"} else _build_target_adapter(reviewer_target)
    )
    verifier_target = getattr(args, "verifier", None) or os.environ.get("CKL_VERIFIER")
    verifier_adapter = (
        adapter if verifier_target in {"same", "self"} else _build_target_adapter(verifier_target)
    )
    result = run_cases(
        selected,
        adapter,
        RunOptions(
            out_dir=Path(args.out),
            run_name=args.run_name,
            keep_workspaces=args.keep_workspaces,
            include_raw=args.include_raw,
            judge_adapter=judge_adapter,
            judge_name=judge_target,
            reviewer_adapter=reviewer_adapter,
            reviewer_name=reviewer_target,
            verifier_adapter=verifier_adapter,
            verifier_name=verifier_target,
            repeat=getattr(args, "repeat", 1),
            concurrency=getattr(args, "concurrency", 1),
            seed=getattr(args, "seed", 0),
            cache=_build_cache(args),
        ),
    )
    summary = result["summary"]
    print(
        render_terminal_report(summary, result["results"], result["run_dir"])
        + f"report: {result['report_path']}"
    )
    unhealthy = any(summary.get(key, 0) for key in ("failed", "errored", "cancelled", "incomplete"))
    if args.fail_on_failed_cases and unhealthy:
        return 3
    score = summary.get("score")
    if args.fail_under is not None and (score is None or score < args.fail_under):
        return 3
    return 0


def _build_cache(args: argparse.Namespace):
    enabled = getattr(args, "cache", False) or os.environ.get("CKL_CACHE") in {"1", "true", "yes"}
    if not enabled:
        return None
    cache_dir = getattr(args, "cache_dir", None) or os.environ.get("CKL_CACHE_DIR") or ".ckl_bench_cache"
    return ResponseCache(Path(cache_dir))


def _cmd_diff(args: argparse.Namespace) -> int:
    summary_a, results_a = load_run(args.run_a)
    summary_b, results_b = load_run(args.run_b)
    diff = compare_runs(summary_a, results_a, summary_b, results_b)
    output = render_diff_terminal(diff)
    if args.out:
        report_path = write_diff_html_report(Path(args.out), diff)
        output += f"report: {report_path}\n"
    print(output)
    if args.fail_on_regression and (
        diff.get("comparability", {}).get("status") != "compatible"
        or diff["counts"]["regressed"]
    ):
        return 3
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs)
    if not runs_dir.is_dir():
        print(f"no runs directory: {runs_dir}", file=sys.stderr)
        return 2
    runs = collect_runs(runs_dir)
    if not runs:
        print(f"no run summaries found under {runs_dir}", file=sys.stderr)
        return 2
    out_path = Path(args.out) if args.out else runs_dir / "dashboard.html"
    report_path = write_dashboard(out_path, runs)
    print(f"dashboard: {report_path} ({len(runs)} run(s))")
    if args.open_browser:
        import webbrowser
        webbrowser.open(report_path.resolve().as_uri())
    return 0


# ---------------------------------------------------------------------------
# Serve command (dashboard server)
# ---------------------------------------------------------------------------

_PID_DIR = Path.home() / ".ckl_bench"
_PID_FILE = _PID_DIR / "server.pid"


def _cmd_serve(args: argparse.Namespace) -> int:
    action = getattr(args, "action", "start")

    if action == "stop":
        return _serve_stop()
    if action == "status":
        return _serve_status()

    # Start the server.
    if _is_server_running():
        pid = _read_pid()
        print(f"server already running (pid {pid})", file=sys.stderr)
        return 1

    # Configure logging so server activity is visible on the console.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from ckl_bench.core.server import BenchServer

    server = BenchServer(
        host=args.host,
        port=args.port,
        runs_dir=args.runs,
        cases_dir=args.cases,
        origin=args.origin,
    )

    if args.daemon:
        _serve_daemon(server, args)
    else:
        _write_pid(os.getpid())
        if args.open_browser:
            import webbrowser
            webbrowser.open(f"http://{args.host}:{args.port}")
        try:
            server.start(blocking=True)
        finally:
            _remove_pid()
    return 0


def _serve_daemon(server: Any, args: argparse.Namespace) -> None:
    """Fork and run the server in the background."""
    import subprocess

    _PID_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _PID_DIR / "server.log"
    cmd = [
        sys.executable, "-m", "ckl_bench.cli", "serve",
        "--host", args.host, "--port", str(args.port),
        "--runs", args.runs, "--cases", args.cases,
    ]
    if args.origin:
        cmd.extend(["--origin", args.origin])
    if args.open_browser:
        cmd.append("--open")
    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            cmd, stdout=log, stderr=log,
            start_new_session=True,
        )
    _write_pid(proc.pid)
    print(f"server started in background (pid {proc.pid}); log: {log_file}")


def _serve_stop() -> int:
    pid = _read_pid()
    if pid is None:
        print("server not running")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        print(f"pid {pid} not found (stale PID file)")
    except OSError as exc:
        print(f"failed to stop pid {pid}: {exc}", file=sys.stderr)
        return 1
    _remove_pid()
    return 0


def _serve_status() -> int:
    pid = _read_pid()
    if pid is None:
        print("server not running")
        return 0
    if _pid_alive(pid):
        print(f"server running (pid {pid})")
        return 0
    print(f"pid {pid} not running (stale PID file)")
    _remove_pid()
    return 1


def _is_server_running() -> bool:
    pid = _read_pid()
    return pid is not None and _pid_alive(pid)


def _read_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        return int(_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int) -> None:
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(pid))


def _remove_pid() -> None:
    try:
        _PID_FILE.unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _cmd_demo(args: argparse.Namespace) -> int:
    """One-click demo: start server, launch a mock run, open browser."""
    import threading
    import urllib.request
    import webbrowser

    host = args.host
    port = args.port
    base = f"http://{host}:{port}"

    # Step 1: start the server in a background thread if not already running.
    if not _is_server_running():
        from ckl_bench.core.server import BenchServer

        print("Starting ckl-bench dashboard server...")
        server = BenchServer(
            host=host, port=port,
            runs_dir=args.runs, cases_dir=args.cases,
        )
        _write_pid(os.getpid())
        thread = threading.Thread(
            target=server.start, kwargs={"blocking": True},
            name="ckl-demo-server", daemon=True,
        )
        thread.start()
        # Wait for the server to be ready.
        import time as _time
        deadline = _time.time() + 15
        while _time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}/api/config", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
            _time.sleep(0.3)
        else:
            print("error: server did not start in time", file=sys.stderr)
            return 1
        print(f"Server running at {base}")
    else:
        pid = _read_pid()
        print(f"Server already running at {base} (pid {pid})")

    # Step 2: fetch available cases and pick a few.
    try:
        with urllib.request.urlopen(f"{base}/api/cases", timeout=5) as resp:
            cases = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"error: could not fetch cases: {exc}", file=sys.stderr)
        return 1

    count = min(args.cases_count, len(cases))
    case_ids = [c["id"] for c in cases[:count]]
    print(f"Selected {count} cases: {', '.join(case_ids)}")

    # Step 3: launch a demo run with the mock adapter.
    body = json.dumps({
        "adapter": "mock",
        "adapter_config": {},
        "case_ids": case_ids,
        "repeat": 1,
        "concurrency": 1,
        "seed": 42,
    }).encode()
    req = urllib.request.Request(
        f"{base}/api/runs", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"error: could not launch demo run: {exc}", file=sys.stderr)
        return 1

    run_id = result.get("run_id")
    print(f"Launched demo run: {run_id}")

    # Step 4: open the browser.
    url = f"{base}/"
    webbrowser.open(url)
    print(f"Opened dashboard in browser: {url}")
    print("\nThe demo run is executing. Watch live progress in the Progress page.")
    print("Press Ctrl+C to stop the server.")

    # Keep the process alive so the server thread keeps running.
    try:
        while True:
            import time as _time
            _time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        _remove_pid()
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    run_name = args.run_name or datetime.now(timezone.utc).strftime("probe-%Y%m%dT%H%M%SZ")
    base_dir = Path(args.out) / run_name
    if base_dir.exists() and args.run_name:
        raise ValueError(f"probe run directory already exists: {base_dir}")
    base_dir.mkdir(parents=True, exist_ok=not bool(args.run_name))

    rows: list[dict[str, Any]] = []
    if args.target in {"all", "api"}:
        for target in _api_probe_targets():
            rows.append(_run_probe_target(target, base_dir))
    if args.target in {"all", "agent"}:
        for target in _agent_probe_targets(args.live_agents):
            rows.append(_run_probe_target(target, base_dir))
    if args.target not in {"all", "api", "agent"}:
        provider = load_provider(args.target)
        if provider is None:
            raise ValueError(f"unknown probe target or provider: {args.target}")
        rows.append(_run_probe_target(provider_probe_target(provider), base_dir))

    report_path = write_probe_html_report(base_dir / "probe.html", rows)
    print(render_probe_terminal(rows, report_path))
    has_failure = any(row["status"] == "fail" for row in rows)
    return 4 if has_failure and args.fail_on_failed else 0


def _adapter_config(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    provider_config = getattr(args, "_provider_config", None)
    if provider_config:
        config.update(provider_config)
    if args.config:
        config.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    elif args.adapter == "mock":
        config.update(_load_default_mock_config())
    for key in ("model", "command", "endpoint", "temperature", "max_tokens"):
        value = getattr(args, key)
        if value is not None:
            config[key] = value
    if args.base_url:
        config["base_url"] = args.base_url
    if config.get("base_url") == OPENROUTER_BASE_URL:
        config.setdefault("api_key_env", "OPENROUTER_API_KEY")
    headers = dict(config.get("headers", {}))
    for header in args.header:
        if "=" not in header:
            raise ValueError(f"--header must be KEY=VALUE: {header}")
        key, value = header.split("=", 1)
        headers[key] = value
    if headers:
        config["headers"] = headers
    if args.adapter == "command" and not config.get("command"):
        config["command"] = COMMAND_AGENT_EXAMPLE
    return config


def _build_target_adapter(target: str | None):
    if not target:
        return None
    spec = argparse.Namespace(
        target=target,
        case_set="all",
        adapter="mock",
        config=None,
        model=None,
        base_url=None,
        endpoint=None,
        command=None,
        temperature=None,
        max_tokens=None,
        header=[],
    )
    _apply_target_shorthand(spec)
    return build_adapter(spec.adapter, _adapter_config(spec))


def _apply_target_shorthand(args: argparse.Namespace) -> None:
    target = args.target
    if not target:
        return
    provider = load_provider(target)
    if provider is not None:
        missing = _missing_required_env(provider.get("required_env", []))
        if missing:
            raise ValueError(f"provider '{target}' requires env: {', '.join(missing)}")
        any_env = provider.get("required_env_any", [])
        if any_env and not _has_any_env(any_env):
            raise ValueError(f"provider '{target}' requires one of env: {', '.join(any_env)}")
        args.adapter = provider["adapter"]
        args._provider_config = dict(provider.get("config", {}))
        return
    if target in CASE_ALIASES and args.case_set == "all":
        args.case_set = target
        return
    if target in {"mock", "command", "http-json", "openai", "openai-compatible", "anthropic", "gemini"}:
        args.adapter = target
        return
    if target == "claude-code":
        args.adapter = "command"
        args.command = os.environ.get("CKL_CLAUDE_COMMAND") or CLAUDE_CODE_WRAPPER
        return
    if target == "codex":
        args.adapter = "command"
        args.command = os.environ.get("CKL_CODEX_COMMAND") or CODEX_WRAPPER
        return
    if target == "dsx":
        args.adapter = "command"
        args.command = os.environ.get("CKL_DSX_COMMAND") or DSX_WRAPPER
        return
    if target == "openrouter":
        args.adapter = "openai"
        args.base_url = OPENROUTER_BASE_URL
        args.model = os.environ.get("OPENROUTER_MODEL") or "openai/gpt-4.1-mini"
        return
    if target == "local":
        args.adapter = "openai"
        args.base_url = os.environ.get("CKL_LOCAL_BASE_URL", LOCAL_BASE_URL)
        args.model = os.environ.get("CKL_LOCAL_MODEL", "local-model")
        args._provider_config = {"trusted_local": True}
        return
    if target.startswith("openai:"):
        args.adapter = "openai"
        args.model = target.split(":", 1)[1]
        return
    if target.startswith("anthropic:"):
        args.adapter = "anthropic"
        args.model = target.split(":", 1)[1]
        return
    if target.startswith("gemini:"):
        args.adapter = "gemini"
        args.model = target.split(":", 1)[1]
        return
    if target.startswith("openrouter:"):
        args.adapter = "openai"
        args.base_url = OPENROUTER_BASE_URL
        args.model = target.split(":", 1)[1]
        return
    if target.startswith("local:"):
        args.adapter = "openai"
        args.base_url = os.environ.get("CKL_LOCAL_BASE_URL", LOCAL_BASE_URL)
        args.model = target.split(":", 1)[1]
        args._provider_config = {"trusted_local": True}
        return
    if target.startswith("command:"):
        args.adapter = "command"
        args.command = target.split(":", 1)[1]
        return
    args.adapter = "openai"
    args.model = target


def _load_default_mock_config() -> dict[str, Any]:
    if MOCK_CONFIG_PATH.exists():
        return json.loads(MOCK_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def _api_probe_targets() -> list[dict[str, Any]]:
    return [
        {
            "target": "openai",
            "kind": "api",
            "adapter": "openai",
            "config": {
                "model": os.environ.get("OPENAI_MODEL") or os.environ.get("CKL_OPENAI_MODEL") or "gpt-4.1-mini",
                "max_tokens": 128,
            },
            "required_env": ["OPENAI_API_KEY", "CKL_OPENAI_API_KEY"],
        },
        {
            "target": "anthropic",
            "kind": "api",
            "adapter": "anthropic",
            "config": {
                "model": os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest",
                "max_tokens": 128,
            },
            "required_env": ["ANTHROPIC_API_KEY"],
        },
        {
            "target": "gemini",
            "kind": "api",
            "adapter": "gemini",
            "config": {
                "model": os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash",
                "max_tokens": 128,
            },
            "required_env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        },
        {
            "target": "openrouter",
            "kind": "api",
            "adapter": "openai",
            "config": {
                "base_url": OPENROUTER_BASE_URL,
                "api_key_env": "OPENROUTER_API_KEY",
                "model": os.environ.get("OPENROUTER_MODEL") or "openai/gpt-4.1-mini",
                "max_tokens": 128,
            },
            "required_env": ["OPENROUTER_API_KEY"],
        },
        {
            "target": "local-openai",
            "kind": "api",
            "adapter": "openai",
            "config": {
                "base_url": os.environ.get("CKL_LOCAL_BASE_URL", LOCAL_BASE_URL),
                "api_key": os.environ.get("CKL_LOCAL_API_KEY", "local"),
                "model": os.environ.get("CKL_LOCAL_MODEL", "local-model"),
                "max_tokens": 128,
                "trusted_local": True,
            },
            "required_env": ["CKL_LOCAL_BASE_URL"],
        },
    ]


def _agent_probe_targets(live_agents: bool) -> list[dict[str, Any]]:
    targets = [
        {
            "target": "command-example",
            "kind": "agent",
            "adapter": "command",
            "config": {"command": COMMAND_AGENT_EXAMPLE},
            "case_set": "agent",
            "required_env": [],
        }
    ]
    for target_name, env_name, default_command in (
        ("env-agent", "CKL_AGENT_COMMAND", ""),
        ("codex-wrapper", "CKL_CODEX_COMMAND", CODEX_WRAPPER if shutil.which("codex") else ""),
        ("dsx-wrapper", "CKL_DSX_COMMAND", DSX_WRAPPER if shutil.which("dsx") else ""),
        ("claude-wrapper", "CKL_CLAUDE_COMMAND", CLAUDE_CODE_WRAPPER if shutil.which("claude") else ""),
        ("gemini-wrapper", "CKL_GEMINI_COMMAND", ""),
    ):
        command = os.environ.get(env_name) or default_command
        if command:
            required_env = [env_name] if not default_command else []
            required_env_any = CLAUDE_CODE_KEY_ENVS if env_name == "CKL_CLAUDE_COMMAND" else []
            targets.append(
                {
                    "target": target_name,
                    "kind": "agent",
                    "adapter": "command",
                    "config": {"command": command},
                    "case_set": "agent",
                    "required_env": required_env,
                    "required_env_any": required_env_any,
                }
            )
        else:
            targets.append(
                {
                    "target": target_name,
                    "kind": "agent",
                    "skip_detail": f"set {env_name} to a JSON-stdin wrapper command",
                    "required_env": ["__missing_binary__"],
                }
            )
    discovered = [
        ("codex-cli", "codex"),
        ("dsx-cli", "dsx"),
        ("claude-code", "claude"),
        ("gemini-cli", "gemini"),
    ]
    for name, binary in discovered:
        if shutil.which(binary):
            detail = f"found {binary}; set a wrapper env command to run safely"
        else:
            detail = f"{binary} not found on PATH"
        targets.append(
            {
                "target": name,
                "kind": "agent",
                "skip_detail": detail,
                "required_env": ["__missing_binary__"],
            }
        )
    if live_agents and not any(os.environ.get(name) for name in ("CKL_AGENT_COMMAND", "CKL_CODEX_COMMAND", "CKL_DSX_COMMAND", "CKL_CLAUDE_COMMAND", "CKL_GEMINI_COMMAND")):
        targets.append(
            {
                "target": "live-agents",
                "kind": "agent",
                "status": "skip",
                "skip_detail": "--live-agents needs one wrapper env command",
                "required_env": ["__missing_binary__"],
            }
        )
    return targets


def _run_probe_target(target: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    if target.get("requires_live_agents"):
        return _probe_skip(target, target["skip_detail"])
    missing = [name for name in target.get("required_env", []) if name != "__missing_binary__" and not os.environ.get(name)]
    if "__missing_binary__" in target.get("required_env", []):
        return _probe_skip(target, target["skip_detail"])
    if target.get("required_env_any") and not any(os.environ.get(name) for name in target["required_env_any"]):
        return _probe_skip(target, "set one of: " + ", ".join(target["required_env_any"]))
    if missing:
        return _probe_skip(target, "set: " + ", ".join(missing))

    case_set = target.get("case_set", "chat")
    try:
        cases = filter_cases(load_cases([CASE_ALIASES.get(case_set, case_set)]), limit=target.get("limit", 1))
        adapter = build_adapter(target["adapter"], target.get("config", {}))
        result = run_cases(
            cases,
            adapter,
            RunOptions(out_dir=base_dir, run_name=_slug(target["target"])),
        )
        summary = result["summary"]
        detail = f"{summary['passed']}/{summary['total']} cases | {result['run_dir']}"
        failed = any(summary.get(key, 0) for key in ("failed", "errored", "cancelled", "incomplete"))
        reason = _probe_failure_reason(result.get("results", [])) if failed else ""
        if reason:
            detail = f"{detail} | {reason}"
        return {
            "target": target["target"],
            "kind": target["kind"],
            "status": "fail" if failed or summary.get("score") is None else "pass",
            "score": summary.get("score"),
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 - probe must report every target.
        return {
            "target": target["target"],
            "kind": target["kind"],
            "status": "fail",
            "score": None,
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _probe_skip(target: dict[str, Any], detail: str) -> dict[str, Any]:
    return {
        "target": target["target"],
        "kind": target["kind"],
        "status": "skip",
        "score": None,
        "detail": detail,
    }


def _missing_required_env(names: list[str]) -> list[str]:
    return [name for name in names if not os.environ.get(name)]


def _has_any_env(names: list[str]) -> bool:
    return any(os.environ.get(name) for name in names)


def _probe_failure_reason(results: list[dict[str, Any]]) -> str:
    for result in results:
        if result.get("error"):
            return str(result["error"])
        for check in result.get("checks", []):
            if not check.get("passed"):
                return str(check.get("detail", "failed check"))
    return ""


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value).strip("-").lower()


def _run_smoke_step(
    label: str,
    case_set: str,
    adapter_name: str | None = None,
    config: dict[str, Any] | None = None,
    out_dir: Path | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    cases = load_cases([CASE_ALIASES[case_set]])
    if adapter_name is None:
        print(f"{label}: validated {len(cases)} cases")
        return {"summary": {"total": len(cases), "passed": len(cases), "failed": 0}}
    smoke_cases = [case for case in cases if case.metadata.get("smoke")]
    if smoke_cases:
        cases = smoke_cases
    adapter = build_adapter(adapter_name, config or {})
    result = run_cases(
        cases,
        adapter,
        RunOptions(out_dir=out_dir or Path("runs"), run_name=run_name),
    )
    summary = result["summary"]
    score = summary.get("score")
    score_text = "N/A" if score is None else f"{float(score):.3f}"
    print(
        f"{label}: cases={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} score={score_text}"
    )
    return result


def _format_row(row: tuple[str, str, str, str], widths: list[int]) -> str:
    return "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))


def _format_row5(row: tuple[str, str, str, str, str], widths: list[int]) -> str:
    return "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))


def _default_provider(namespace: dict[str, Any]) -> dict[str, Any]:
    provider = load_provider(namespace["namespace"])
    if provider is None:
        raise ValueError(f"namespace has no default provider: {namespace['namespace']}")
    return provider
