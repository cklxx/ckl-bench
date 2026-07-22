#!/usr/bin/env python3
"""Synchronize checkout resources into the Python package."""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCE_ROOT = ROOT / "ckl_bench" / "resources"
RESOURCE_DIRS = ("cases", "configs", "registries")


def sync_resources(*, check: bool = False) -> list[str]:
    """Copy canonical root resources, or return their drift in check mode."""
    drift: list[str] = []
    for name in RESOURCE_DIRS:
        source = ROOT / name
        destination = RESOURCE_ROOT / name
        if check:
            drift.extend(_compare_trees(source, destination, name))
        else:
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination, ignore=_ignore_non_resources)
    return drift


def _ignore_non_resources(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name == "README.md" or name.startswith(".")}


def _compare_trees(source: Path, destination: Path, label: str) -> list[str]:
    source_files = _resource_files(source)
    destination_files = _resource_files(destination)
    drift = [f"missing packaged resource: {label}/{path}" for path in sorted(source_files - destination_files)]
    drift.extend(
        f"stale packaged resource: {label}/{path}"
        for path in sorted(destination_files - source_files)
    )
    drift.extend(
        f"changed packaged resource: {label}/{path}"
        for path in sorted(source_files & destination_files)
        if not filecmp.cmp(source / path, destination / path, shallow=False)
    )
    return drift


def _resource_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.name != "README.md" and not path.name.startswith(".")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if packaged resources differ")
    args = parser.parse_args(argv)
    drift = sync_resources(check=args.check)
    if drift:
        print("\n".join(drift), file=sys.stderr)
        print("run: python scripts/sync_resources.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
