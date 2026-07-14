from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from typing import Any

from .base import GenerateRequest, GenerateResponse


class CommandAdapter:
    """Run any agent framework through a stdin/stdout JSON command contract."""

    name = "command"

    def __init__(self, config: dict[str, Any]):
        command = config.get("command")
        if not command:
            raise ValueError("command adapter requires config key 'command' or --command")
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
            raise RuntimeError(
                "command adapter failed with exit code "
                f"{completed.returncode}: {stderr or stdout}"
            )

        if not stdout:
            return GenerateResponse(text="", raw=raw)
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            return GenerateResponse(text=stdout, raw=raw)

        if isinstance(parsed, dict):
            for key in ("text", "response", "output", "final", "answer"):
                value = parsed.get(key)
                if isinstance(value, str):
                    return GenerateResponse(text=value, raw=parsed)
        print(
            "warning: command output JSON did not contain a text field; using raw stdout",
            file=sys.stderr,
        )
        return GenerateResponse(text=stdout, raw=parsed)
