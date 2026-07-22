from __future__ import annotations

import os
import shutil
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a path escapes its trusted root or traverses a symlink."""


def safe_relative_path(value: str | os.PathLike[str], *, label: str = "path") -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafePathError(f"unsafe {label}: {path}")
    return path


def safe_join(
    root: Path,
    value: str | os.PathLike[str],
    *,
    label: str = "path",
    allow_missing: bool = True,
) -> Path:
    """Resolve a relative path below *root*, rejecting symlink traversal."""
    root = Path(root).resolve(strict=True)
    relative = safe_relative_path(value, label=label)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if current.is_symlink():
            raise UnsafePathError(f"unsafe {label}: symlink component {current}")
        if current.exists():
            resolved = current.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise UnsafePathError(f"unsafe {label}: {relative}")
            current = resolved
        elif not allow_missing and index == len(relative.parts) - 1:
            raise UnsafePathError(f"missing {label}: {relative}")
    if not current.is_relative_to(root):
        raise UnsafePathError(f"unsafe {label}: {relative}")
    return current


def validate_owned_path(root: Path, candidate: Path, *, label: str = "path") -> Path:
    """Return a resolved existing candidate only when it is inside root."""
    resolved_root = Path(root).resolve(strict=True)
    resolved = Path(candidate).resolve(strict=True)
    if resolved == resolved_root or resolved.is_relative_to(resolved_root):
        return resolved
    raise UnsafePathError(f"unsafe {label}: {candidate} is outside {resolved_root}")


def copy_tree_safely(source: Path, destination: Path) -> None:
    """Copy a tree without following or retaining symlinks."""
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise UnsafePathError(f"workspace is not a directory: {source}")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise UnsafePathError(f"copy destination already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    for current, dirs, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        safe_dirs: list[str] = []
        for name in dirs:
            child = current_path / name
            if child.is_symlink():
                continue
            safe_dirs.append(name)
            (destination / relative / name).mkdir(exist_ok=True)
        dirs[:] = safe_dirs
        for name in files:
            child = current_path / name
            if child.is_symlink():
                continue
            target = destination / relative / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
