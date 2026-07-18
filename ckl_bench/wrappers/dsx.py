#!/usr/bin/env python3
"""DSX CLI wrapper for ckl-bench command-agent evaluation."""
from __future__ import annotations

from .common import run_exec_wrapper


def main() -> int:
    return run_exec_wrapper("CKL_DSX", "dsx", "-m", ".tmp-runs/dsx-workspaces")


if __name__ == "__main__":
    raise SystemExit(main())
