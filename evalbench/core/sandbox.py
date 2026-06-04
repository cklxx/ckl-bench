"""Run candidate code in a subprocess with a timeout, for execution-based grading.

The strongest agent benchmarks (SWE-bench, LiveCodeBench, HumanEval) do not
grade code by string matching -- they *run* it against tests and check the exit
status. This module provides a minimal, stdlib-only way to do that: write a
script next to the candidate's files and execute it in the workspace with a wall
clock timeout and best-effort resource limits.

Security note: this executes the case's test code and the candidate's edited
files. Cases are trusted local content, but agent-produced files are only as
trustworthy as the agent. For untrusted agents, run the whole evaluation inside
a container or VM; this module is a guardrail, not a jail.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


# Environment variables worth preserving for a Python subprocess. Everything
# else (API keys, tokens) is dropped so candidate code cannot read credentials.
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")


def _child_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})
    return env


def _limit_resources(cpu_seconds: int, memory_mb: int):
    """Return a preexec_fn that caps CPU and address space, or None off POSIX."""
    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return None

    def _apply() -> None:  # pragma: no cover - runs in the child process
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        except (ValueError, OSError):
            pass
        if memory_mb > 0:
            limit = memory_mb * 1024 * 1024
            for name in ("RLIMIT_AS", "RLIMIT_DATA"):
                rlimit = getattr(resource, name, None)
                if rlimit is not None:
                    try:
                        resource.setrlimit(rlimit, (limit, limit))
                    except (ValueError, OSError):
                        pass

    return _apply


def run_python_script(
    script: str,
    *,
    cwd: Path | None = None,
    timeout_s: float = 15.0,
    memory_mb: int = 512,
    extra_env: dict[str, str] | None = None,
    executable: str | None = None,
) -> ExecResult:
    """Execute ``script`` as Python in ``cwd`` with a timeout.

    The script is written to a temporary file inside ``cwd`` (when given) so that
    ``import`` statements resolve against the candidate's workspace files. The
    file is removed afterward. ``cwd`` defaults to a throwaway temp directory.
    """
    interpreter = executable or sys.executable or "python3"
    cleanup_dir: tempfile.TemporaryDirectory | None = None
    if cwd is None:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="evalbench-sandbox-")
        work = Path(cleanup_dir.name)
    else:
        work = Path(cwd)

    fd, tmp_name = tempfile.mkstemp(prefix="_evalbench_exec_", suffix=".py", dir=str(work))
    script_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script)
        started = time.perf_counter()
        timed_out = False
        try:
            # No -I/-P: the script lives in the workspace, so the workspace is
            # sys.path[0] and the test can ``import`` the candidate's files.
            # Credentials are isolated via the scrubbed environment instead.
            completed = subprocess.run(
                [interpreter, str(script_path)],
                cwd=str(work),
                env=_child_env(extra_env),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_limit_resources(int(timeout_s) + 1, memory_mb),
            )
            returncode = completed.returncode
            stdout, stderr = completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = -1
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\n[timed out after {timeout_s}s]"
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return ExecResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass
        if cleanup_dir is not None:
            cleanup_dir.cleanup()
