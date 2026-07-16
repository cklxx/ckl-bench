#!/usr/bin/env python3
"""dsx CLI wrapper for ckl-bench command-agent evaluation.

Reads a JSON payload from stdin (case_id, prompt, workspace_path, messages,
timeout_s), invokes the dsx CLI in an isolated workspace, and writes a JSON
response to stdout.

Configuration via env vars:
  CKL_DSX_COMMAND       dsx binary or full command (default: "dsx")
  CKL_DSX_MODEL         model name passed to -m
  CKL_DSX_TIMEOUT_S     per-case timeout in seconds (default: 300)
  CKL_DSX_WORKSPACE_DIR root for isolated workspaces (default: .tmp-runs/dsx-workspaces)
  CKL_DSX_EXTRA_ARGS    space-separated extra args passed to dsx
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _common import (
    build_exec_command,
    build_prompt,
    diagnose_stderr,
    extract_text,
    parse_usage_stderr,
    prepare_workspace,
    sync_workspace,
)


def main() -> int:
    payload = json.loads(sys.stdin.read())
    case_id = str(payload.get("case_id") or "case")
    source_workspace = Path(payload["workspace_path"]) if payload.get("workspace_path") else None
    workspace = prepare_workspace(
        case_id, source_workspace, "CKL_DSX_WORKSPACE_DIR", ".tmp-runs/dsx-workspaces"
    )

    prompt = build_prompt(str(payload.get("prompt") or ""), workspace)
    command = build_exec_command("CKL_DSX", "dsx", "-m", prompt)
    timeout_s = int(float(payload.get("timeout_s") or os.environ.get("CKL_DSX_TIMEOUT_S") or 300))

    completed = subprocess.run(
        command, cwd=workspace, env=os.environ.copy(),
        text=True, capture_output=True, timeout=timeout_s,
    )
    text = extract_text(completed.stdout)
    if source_workspace:
        sync_workspace(workspace, source_workspace)
    stderr_tail = diagnose_stderr(completed.stderr.strip()[-2000:])
    output = {
        "text": text,
        "returncode": completed.returncode,
        "workspace": str(workspace),
        "usage": parse_usage_stderr(completed.stderr),
        "stderr_tail": stderr_tail,
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if completed.returncode == 0 else completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
