#!/usr/bin/env python3
"""Claude Code CLI wrapper for ckl-bench command-agent evaluation.

Reads a JSON payload from stdin, invokes the Claude Code CLI in an isolated
workspace, and writes a JSON response to stdout.  Unlike the dsx/codex
wrappers, Claude Code speaks JSON natively (usage is in stdout) and needs
Anthropic-format env vars set.

Configuration via env vars:
  CKL_CLAUDE_COMMAND       claude binary or full command (default: "claude")
  CKL_CLAUDE_MODEL         model name passed to --model
  CKL_CLAUDE_TIMEOUT_S     per-case timeout in seconds (default: 300)
  CKL_CLAUDE_WORKSPACE_DIR root for isolated workspaces (default: .tmp-runs/claude-code-workspaces)
  CKL_CLAUDE_API_KEY       API key (also falls back to ANTHROPIC_API_KEY, etc.)
  CKL_CLAUDE_ANTHROPIC_BASE_URL  base URL
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from _common import build_prompt, extract_text, prepare_workspace, sync_workspace

KEY_ENVS = ("CKL_CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "DSV4_API_KEY", "DEEPSEEK_API_KEY")
BASE_URL_ENVS = ("CKL_CLAUDE_ANTHROPIC_BASE_URL", "ANTHROPIC_BASE_URL", "DSV4_ANTHROPIC_BASE_URL")
MODEL_ENVS = ("CKL_CLAUDE_MODEL", "ANTHROPIC_MODEL", "DSV4_MODEL")


def main() -> int:
    payload = json.loads(sys.stdin.read())
    case_id = str(payload.get("case_id") or "case")
    source_workspace = Path(payload["workspace_path"]) if payload.get("workspace_path") else None
    workspace = prepare_workspace(
        case_id, source_workspace, "CKL_CLAUDE_WORKSPACE_DIR", ".tmp-runs/claude-code-workspaces"
    )

    env = _claude_env()
    missing = _missing_env(env)
    if missing:
        print(json.dumps({"text": missing}, ensure_ascii=True))
        return 2

    prompt = build_prompt(str(payload.get("prompt") or ""), workspace)
    command = _claude_command(env, workspace, prompt)
    timeout_s = int(float(payload.get("timeout_s") or os.environ.get("CKL_CLAUDE_TIMEOUT_S") or 300))
    completed = subprocess.run(
        command, cwd=workspace, env=env,
        text=True, capture_output=True, timeout=timeout_s,
    )
    text = extract_text(completed.stdout)
    usage = _extract_usage(completed.stdout)
    if source_workspace:
        sync_workspace(workspace, source_workspace)
    output = {
        "text": text,
        "returncode": completed.returncode,
        "workspace": str(workspace),
        "usage": usage,
        "stderr_tail": completed.stderr.strip()[-2000:],
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if completed.returncode == 0 else completed.returncode


def _claude_env() -> dict[str, str]:
    env = os.environ.copy()
    api_key = _first_env(env, KEY_ENVS)
    base_url = _first_env(env, BASE_URL_ENVS) or _deepseek_anthropic_url(env)
    model = _first_env(env, MODEL_ENVS)
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if model:
        env["ANTHROPIC_MODEL"] = model
    env.setdefault("CLAUDE_CODE_SIMPLE", "1")
    return env


def _missing_env(env: dict[str, str]) -> str:
    if not env.get("ANTHROPIC_API_KEY"):
        return "missing one of: " + ", ".join(KEY_ENVS)
    if not env.get("ANTHROPIC_BASE_URL") and env.get("CKL_CLAUDE_REQUIRE_BASE_URL", "1") != "0":
        return "missing Anthropic-format base URL: set CKL_CLAUDE_ANTHROPIC_BASE_URL or ANTHROPIC_BASE_URL"
    return ""


def _claude_command(env: dict[str, str], workspace: Path, prompt: str) -> list[str]:
    command = shlex.split(env.get("CKL_CLAUDE_COMMAND", "claude"))
    command.extend(
        [
            "--bare", "--print", "--output-format",
            env.get("CKL_CLAUDE_OUTPUT_FORMAT", "json"),
            "--no-session-persistence", "--permission-mode",
            env.get("CKL_CLAUDE_PERMISSION_MODE", "acceptEdits"),
            "--add-dir", str(workspace),
        ]
    )
    model = env.get("CKL_CLAUDE_MODEL") or env.get("ANTHROPIC_MODEL")
    if model:
        command.extend(["--model", model])
    tools = env.get("CKL_CLAUDE_ALLOWED_TOOLS")
    if tools:
        command.extend(["--allowedTools", tools])
    command.append(prompt)
    return command


def _extract_usage(stdout: str) -> dict[str, int] | None:
    """Extract usage from Claude Code JSON output."""
    stripped = stdout.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if isinstance(usage, dict):
        return {
            "total_tokens": int(usage.get("total_tokens", 0)),
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
        }
    return None


def _first_env(env: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return ""


def _deepseek_anthropic_url(env: dict[str, str]) -> str:
    base = env.get("DSV4_BASE_URL", "").rstrip("/")
    if base == "https://api.deepseek.com":
        return "https://api.deepseek.com/anthropic"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
