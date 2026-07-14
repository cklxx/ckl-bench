#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

KEY_ENVS = ("CKL_CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "DSV4_API_KEY", "DEEPSEEK_API_KEY")
BASE_URL_ENVS = ("CKL_CLAUDE_ANTHROPIC_BASE_URL", "ANTHROPIC_BASE_URL", "DSV4_ANTHROPIC_BASE_URL")
MODEL_ENVS = ("CKL_CLAUDE_MODEL", "ANTHROPIC_MODEL", "DSV4_MODEL")


def main() -> int:
    payload = json.loads(sys.stdin.read())
    case_id = str(payload.get("case_id") or "case")
    source_workspace = Path(payload["workspace_path"]) if payload.get("workspace_path") else None
    inspect_workspace = _prepare_inspect_workspace(case_id, source_workspace)

    env = _claude_env()
    missing = _missing_env(env)
    if missing:
        print(json.dumps({"text": missing}, ensure_ascii=True))
        return 2

    command = _claude_command(env, inspect_workspace, _prompt(payload, inspect_workspace))
    timeout_s = int(float(payload.get("timeout_s") or os.environ.get("CKL_CLAUDE_TIMEOUT_S") or 300))
    completed = subprocess.run(
        command,
        cwd=inspect_workspace,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_s,
    )
    text = _extract_text(completed.stdout)
    if source_workspace:
        _sync_workspace(inspect_workspace, source_workspace)
    output = {
        "text": text,
        "returncode": completed.returncode,
        "workspace": str(inspect_workspace),
        "stderr_tail": completed.stderr.strip()[-2000:],
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if completed.returncode == 0 else completed.returncode


def _prepare_inspect_workspace(case_id: str, source_workspace: Path | None) -> Path:
    root = Path(os.environ.get("CKL_CLAUDE_WORKSPACE_DIR", ".tmp-runs/claude-code-workspaces"))
    target = root / _slug(case_id)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source_workspace:
        shutil.copytree(source_workspace, target)
    else:
        target.mkdir(parents=True)
    return target


def _sync_workspace(source: Path, destination: Path) -> None:
    for child in destination.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in source.iterdir():
        dest = destination / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)


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
            "--bare",
            "--print",
            "--output-format",
            env.get("CKL_CLAUDE_OUTPUT_FORMAT", "json"),
            "--no-session-persistence",
            "--permission-mode",
            env.get("CKL_CLAUDE_PERMISSION_MODE", "acceptEdits"),
            "--add-dir",
            str(workspace),
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


def _prompt(payload: dict[str, Any], workspace: Path) -> str:
    prompt = str(payload.get("prompt") or "")
    return (
        "You are being evaluated by ckl-bench as a command-line coding agent.\n"
        f"Work only inside this workspace: {workspace}\n"
        "Edit files directly in that workspace. Do not touch files outside it.\n"
        "When the task is complete, give a concise final answer. If the task asks "
        "you to print DONE, include DONE in the final answer.\n\n"
        f"Task:\n{prompt}\n"
    )


def _extract_text(stdout: str) -> str:
    stripped = stdout.strip()
    if not stripped:
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(data, dict):
        for key in ("result", "text", "response", "output", "final", "answer"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return stripped


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


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "case"


if __name__ == "__main__":
    raise SystemExit(main())
