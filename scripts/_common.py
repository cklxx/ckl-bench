#!/usr/bin/env python3
"""Shared helpers for ckl-bench CLI wrapper scripts (dsx, codex, claude-code).

These wrappers read a JSON payload from stdin, invoke a coding CLI in an
isolated workspace, and write a JSON response to stdout.  The workspace
setup, prompt building, output parsing, and usage extraction are identical
across wrappers, so they live here once.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
from pathlib import Path

#: Dict keys tried, in order, when extracting text from a JSON agent output.
TEXT_KEYS = ("result", "text", "response", "output", "final", "answer")


def prepare_workspace(
    case_id: str,
    source_workspace: Path | None,
    root_env: str,
    default_root: str,
) -> Path:
    """Create an isolated workspace for a case, optionally seeded from a source."""
    root = Path(os.environ.get(root_env, default_root))
    target = root / slug(case_id)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source_workspace:
        shutil.copytree(source_workspace, target)
    else:
        target.mkdir(parents=True)
    return target


def sync_workspace(source: Path, destination: Path) -> None:
    """Mirror *source* into *destination* (full overwrite, no merge)."""
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


def build_prompt(prompt: str, workspace: Path) -> str:
    """Build the evaluation prompt that bounds the agent to its workspace."""
    return (
        "You are being evaluated by ckl-bench as a command-line coding agent.\n"
        f"Work only inside this workspace: {workspace}\n"
        "Edit files directly in that workspace. Do not touch files outside it.\n"
        "When the task is complete, give a concise final answer. If the task asks "
        "you to print DONE, include DONE in the final answer.\n\n"
        f"Task:\n{prompt}\n"
    )


def extract_text(stdout: str) -> str:
    """Extract the agent's text answer from raw stdout (JSON or plain)."""
    stripped = stdout.strip()
    if not stripped:
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(data, dict):
        for key in TEXT_KEYS:
            value = data.get(key)
            if isinstance(value, str):
                return value
    return stripped


def parse_usage_stderr(stderr: str) -> dict[str, int] | None:
    """Parse token usage from a stderr line such as ``tokens used\\n423``."""
    m = re.search(r"tokens used\s*\n\s*(\d+)", stderr)
    if m:
        total = int(m.group(1))
        return {"total_tokens": total, "input_tokens": 0, "output_tokens": 0}
    return None


def build_exec_command(
    prefix: str,
    default_command: str,
    model_flag: str,
    prompt: str,
) -> list[str]:
    """Build a dsx/codex-style ``exec`` command from ``CKL_<PREFIX>_*`` env vars."""
    command = shlex.split(os.environ.get(f"{prefix}_COMMAND", default_command))
    command.extend(["exec", "--skip-git-repo-check"])
    model = os.environ.get(f"{prefix}_MODEL")
    if model:
        command.extend([model_flag, model])
    extra = os.environ.get(f"{prefix}_EXTRA_ARGS")
    if extra:
        command.extend(shlex.split(extra))
    command.append(prompt)
    return command


def slug(value: str) -> str:
    """Turn an arbitrary case id into a filesystem-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "case"
