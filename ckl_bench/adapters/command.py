from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import GenerateRequest, GenerateResponse

# Known CLI agents: when the command first token matches one of these, the
# adapter routes through the matching wrapper script so the user only needs to
# set the raw CLI name (e.g. "dsx") instead of "python scripts/dsx_wrapper.py".
_KNOWN_CLIS: dict[str, str] = {
    "dsx": "ckl_bench.wrappers.dsx",
    "codex": "ckl_bench.wrappers.codex",
    "claude": "ckl_bench.wrappers.claude_code",
}


class CommandAdapter:
    """Run any agent framework through a stdin/stdout JSON command contract."""

    name = "command"

    def __init__(self, config: dict[str, Any]):
        command = config.get("command")
        if not command:
            raise ValueError("command adapter requires config key 'command' or --command")
        # Auto-wrap known CLIs: if the command is a raw CLI name, route through
        # the matching wrapper script so the user only sees the CLI name.
        first_token = shlex.split(command)[0] if isinstance(command, str) else command[0]
        cli_name = Path(first_token).name
        # Display name is the raw CLI the user configured (e.g. "dsx"), so the
        # dashboard shows the real agent name instead of "command".
        self.display_name = cli_name
        if cli_name in _KNOWN_CLIS:
            command = f"{shlex.quote(sys.executable)} -m {_KNOWN_CLIS[cli_name]}"
        self.command = command
        self.shell = bool(config.get("shell", isinstance(command, str)))
        self.cwd = config.get("cwd")
        self.extra_env = config.get("env", {})

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        payload = {
            "case_id": request.case_id,
            "messages": request.messages,
            "prompt": request.prompt,
            "workspace_path": str(request.workspace_path) if request.workspace_path else None,
            "metadata": request.metadata,
            "timeout_s": request.timeout_s,
        }
        command = self.command
        if isinstance(command, str) and not self.shell:
            command = shlex.split(command)

        env = None
        if self.extra_env:
            env = os.environ.copy()
            env.update({str(key): str(value) for key, value in self.extra_env.items()})

        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=True),
            text=True,
            capture_output=True,
            shell=self.shell,
            cwd=self.cwd,
            env=env,
            timeout=request.timeout_s,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        raw = {
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if completed.returncode != 0:
            # The wrapper scripts always write a JSON object to stdout, even on
            # failure. Parse it to surface the real CLI error (stderr_tail)
            # instead of dumping raw JSON at the user.
            detail = stderr or stdout
            if stdout:
                try:
                    parsed = json.loads(stdout)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    tail = parsed.get("stderr_tail")
                    if isinstance(tail, str) and tail.strip():
                        detail = tail.strip()
            raise RuntimeError(
                "command adapter failed with exit code "
                f"{completed.returncode}: {detail}"
            )

        if not stdout:
            return GenerateResponse(text="", raw=raw)
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            return GenerateResponse(text=stdout, raw=raw)

        if isinstance(parsed, dict):
            # Extract usage from wrapper output for cost tracking.
            metadata: dict[str, Any] = {}
            usage = parsed.get("usage")
            if isinstance(usage, dict):
                metadata["usage"] = {
                    "total_tokens": int(usage.get("total_tokens", 0)),
                    "input_tokens": int(usage.get("input_tokens", 0)),
                    "output_tokens": int(usage.get("output_tokens", 0)),
                }
            # Command agents may write artifacts to a workspace; surface the
            # path so graders (e.g. code_test) can read files the agent created
            # instead of trying to extract code from the response text.
            ws = parsed.get("workspace")
            workspace_path = Path(ws) if isinstance(ws, str) and ws else None
            for key in ("text", "response", "output", "final", "answer"):
                value = parsed.get(key)
                if isinstance(value, str):
                    return GenerateResponse(text=value, raw=parsed, metadata=metadata, workspace_path=workspace_path)
            print(
                "warning: command output JSON did not contain a text field; using raw stdout",
                file=sys.stderr,
            )
            return GenerateResponse(text=stdout, raw=parsed, metadata=metadata, workspace_path=workspace_path)
