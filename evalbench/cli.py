from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evalbench.adapters import build_adapter
from evalbench.core.cases import CaseValidationError, load_cases
from evalbench.core.env import EnvFileError, load_default_env
from evalbench.core.providers import (
    ProviderRegistryError,
    load_namespace,
    load_namespaces,
    load_provider,
    load_providers,
    provider_probe_target,
    redacted_namespace,
    redacted_provider,
)
from evalbench.core.reporting import render_probe_terminal, render_terminal_report, write_probe_html_report
from evalbench.core.runner import RunOptions, filter_cases, run_cases


CASE_ALIASES = {
    "all": "cases",
    "chat": "cases/chat",
    "agent": "cases/agent",
}

MOCK_CONFIG_PATH = Path("configs/mock.responses.json")
COMMAND_AGENT_EXAMPLE = "python scripts/command_agent_example.py"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"


def main(argv: list[str] | None = None) -> int:
    try:
        load_default_env()
    except EnvFileError as exc:
        print(f"env file error: {exc}", file=sys.stderr)
        return 2

    invoked_as = Path(sys.argv[0]).name
    prog = invoked_as if invoked_as in {"evb", "evalbench"} else "evb"
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


def _build_parser(prog: str = "evb") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Private LLM and agent evaluation runner.\n"
            "Use 'evb' as the short command; 'evalbench' remains available as "
            "the long alias.\n"
            "Fast local cases, mainstream API probes, command-agent bridges, "
            "and one-glance HTML reports."
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
  EVAL_LOCAL_BASE_URL=http://127.0.0.1:8000/v1 {prog} run local chat
  DSV4_BASE_URL=https://api.deepseek.com       {prog} run deepseekv4 chat

Agents:
  {prog} run command agent --command "python path/to/wrapper.py"
  EVAL_AGENT_COMMAND="python path/to/wrapper.py" {prog} probe agent
  EVAL_CODEX_COMMAND="python wrappers/codex.py"  {prog} probe agent

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
  {prog} list --cases cases/chat/private_reasoning.jsonl
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
  EVAL_LOCAL_BASE_URL, EVAL_LOCAL_MODEL, EVAL_LOCAL_API_KEY
  DSV4_BASE_URL, DSV4_MODEL, DSV4_API_KEY

Agent wrapper env:
  EVAL_AGENT_COMMAND, EVAL_CODEX_COMMAND, EVAL_CLAUDE_COMMAND, EVAL_GEMINI_COMMAND
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
  {prog} run openai:gpt-4.1-mini chat
  {prog} run anthropic:claude-3-5-haiku-latest chat
  {prog} run gemini:gemini-3.5-flash chat
  {prog} run openrouter:openai/gpt-4.1-mini chat
  {prog} run local chat
  {prog} run deepseekv4 chat

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
    run_parser.add_argument("--out", default="runs", help="Output directory")
    run_parser.add_argument("--run-name", help="Stable run directory name")
    run_parser.add_argument("--keep-workspaces", action="store_true", help="Save final agent workspaces")
    run_parser.add_argument("--include-raw", action="store_true", help="Include raw adapter responses")
    run_parser.add_argument(
        "--fail-on-failed-cases",
        action="store_true",
        help="Return exit code 3 when any case fails",
    )
    run_parser.set_defaults(func=_cmd_run)

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
    print(_format_row(tuple("-" * width for width in widths), widths))
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
    print(_format_row5(tuple("-" * width for width in widths), widths))
    for row in rows:
        print(_format_row5(row, widths))
    return 0


def _cmd_smoke(_args: argparse.Namespace) -> int:
    _run_smoke_step("validate", "all")
    with tempfile.TemporaryDirectory(prefix="evalbench-smoke-") as tmp:
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
            config={"command": COMMAND_AGENT_EXAMPLE, "shell": True},
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
    result = run_cases(
        selected,
        adapter,
        RunOptions(
            out_dir=Path(args.out),
            run_name=args.run_name,
            keep_workspaces=args.keep_workspaces,
            include_raw=args.include_raw,
        ),
    )
    summary = result["summary"]
    print(
        render_terminal_report(summary, result["results"], result["run_dir"])
        + f"report: {result['report_path']}"
    )
    if args.fail_on_failed_cases and summary["failed"]:
        return 3
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
        config["shell"] = True
    return config


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
    if target == "openrouter":
        args.adapter = "openai"
        args.base_url = OPENROUTER_BASE_URL
        args.model = os.environ.get("OPENROUTER_MODEL") or "openai/gpt-4.1-mini"
        return
    if target == "local":
        args.adapter = "openai"
        args.base_url = os.environ.get("EVAL_LOCAL_BASE_URL", LOCAL_BASE_URL)
        args.model = os.environ.get("EVAL_LOCAL_MODEL", "local-model")
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
        args.base_url = os.environ.get("EVAL_LOCAL_BASE_URL", LOCAL_BASE_URL)
        args.model = target.split(":", 1)[1]
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
                "model": os.environ.get("OPENAI_MODEL") or os.environ.get("EVAL_OPENAI_MODEL") or "gpt-4.1-mini",
                "max_tokens": 128,
            },
            "required_env": ["OPENAI_API_KEY", "EVAL_OPENAI_API_KEY"],
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
                "base_url": os.environ.get("EVAL_LOCAL_BASE_URL", LOCAL_BASE_URL),
                "api_key": os.environ.get("EVAL_LOCAL_API_KEY", "local"),
                "model": os.environ.get("EVAL_LOCAL_MODEL", "local-model"),
                "max_tokens": 128,
            },
            "required_env": ["EVAL_LOCAL_BASE_URL"],
        },
    ]


def _agent_probe_targets(live_agents: bool) -> list[dict[str, Any]]:
    targets = [
        {
            "target": "command-example",
            "kind": "agent",
            "adapter": "command",
            "config": {"command": COMMAND_AGENT_EXAMPLE, "shell": True},
            "case_set": "agent",
            "required_env": [],
        }
    ]
    for target_name, env_name in (
        ("env-agent", "EVAL_AGENT_COMMAND"),
        ("codex-wrapper", "EVAL_CODEX_COMMAND"),
        ("claude-wrapper", "EVAL_CLAUDE_COMMAND"),
        ("gemini-wrapper", "EVAL_GEMINI_COMMAND"),
    ):
        command = os.environ.get(env_name)
        if command:
            targets.append(
                {
                    "target": target_name,
                    "kind": "agent",
                    "adapter": "command",
                    "config": {"command": command, "shell": True},
                    "case_set": "agent",
                    "required_env": [env_name],
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
    if live_agents and not any(os.environ.get(name) for name in ("EVAL_AGENT_COMMAND", "EVAL_CODEX_COMMAND", "EVAL_CLAUDE_COMMAND", "EVAL_GEMINI_COMMAND")):
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
        if summary["failed"]:
            reason = _probe_failure_reason(result.get("results", []))
            if reason:
                detail = f"{detail} | {reason}"
        return {
            "target": target["target"],
            "kind": target["kind"],
            "status": "pass" if summary["failed"] == 0 else "fail",
            "score": summary["score"],
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 - probe must report every target.
        return {
            "target": target["target"],
            "kind": target["kind"],
            "status": "fail",
            "score": 0.0,
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
    print(
        f"{label}: cases={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} score={summary['score']:.3f}"
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
