#!/usr/bin/env python3
"""dsx CLI wrapper for ckl-bench command-agent evaluation.

Reads a JSON payload from stdin (case_id, prompt, workspace_path, messages,
timeout_s), invokes the dsx CLI in an isolated workspace, and writes a JSON
response to stdout.

Configuration via env vars:
  CKL_DSX_COMMAND       dsx binary or full command (default: "dsx")
  CKL_DSX_MODEL         model name passed to -m/--model
  CKL_DSX_TIMEOUT_S     per-case timeout in seconds (default: 300)
  CKL_DSX_WORKSPACE_DIR root for isolated workspaces (default: .tmp-runs/dsx-workspaces)
  CKL_DSX_EXTRA_ARGS    space-separated extra args passed to dsx
"""
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


def main() -> int:
    payload = json.loads(sys.stdin.read())
    case_id = str(payload.get("case_id") or "case")
    source_workspace = Path(payload["workspace_path"]) if payload.get("workspace_path") else None
    inspect_workspace = _prepare_workspace(case_id, source_workspace)

    command = _dsx_command(inspect_workspace, _prompt(payload, inspect_workspace))
    timeout_s = int(float(payload.get("timeout_s") or os.environ.get("CKL_DSX_TIMEOUT_S") or 300))

    completed = subprocess.run(
        command,
        cwd=inspect_workspace,
        env=os.environ.copy(),
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
        "usage": _parse_usage(completed.stderr),
        "stderr_tail": completed.stderr.strip()[-2000:],
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if completed.returncode == 0 else completed.returncode


def _prepare_workspace(case_id: str, source_workspace: Path | None) -> Path:
    root = Path(os.environ.get("CKL_DSX_WORKSPACE_DIR", ".tmp-runs/dsx-workspaces"))
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


def _dsx_command(workspace: Path, prompt: str) -> list[str]:
    command = shlex.split(os.environ.get("CKL_DSX_COMMAND", "dsx"))
    command.extend(["exec", "--skip-git-repo-check"])
    model = os.environ.get("CKL_DSX_MODEL")
    if model:
        command.extend(["-m", model])
    extra = os.environ.get("CKL_DSX_EXTRA_ARGS")
    if extra:
        command.extend(shlex.split(extra))
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


def _parse_usage(stderr: str) -> dict[str, int] | None:
    """Parse token usage from dsx stderr (e.g. 'tokens used\\n423')."""
    m = re.search(r"tokens used\s*\n\s*(\d+)", stderr)
    if m:
        total = int(m.group(1))
        return {"total_tokens": total, "input_tokens": 0, "output_tokens": 0}
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "case"


if __name__ == "__main__":
    raise SystemExit(main())
