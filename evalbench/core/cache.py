"""Content-addressed response cache so reruns are free and deterministic.

promptfoo, Inspect, and DeepEval all cache model calls: it makes iterating on
graders, reports, and case selection free (no repeated API spend) and makes a
suite reproducible when the upstream model is non-deterministic. This is a
stdlib-only implementation -- one JSON file per request, keyed by a stable hash
of everything that can change the answer.

The cache is keyed on the *request*, never on wall-clock time, so the same
(adapter, model, params, messages) always maps to the same file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(parts: dict[str, Any]) -> str:
    """Stable SHA-256 over a canonical JSON encoding of ``parts``.

    Keys are sorted and separators fixed so the digest is independent of dict
    ordering or incidental whitespace.
    """
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResponseCache:
    """A tiny on-disk cache. Sharded by key prefix to keep directories small."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
        tmp.replace(path)  # atomic on POSIX and Windows


class NullCache:
    """A cache that never hits -- used when caching is disabled."""

    def get(self, key: str) -> dict[str, Any] | None:  # noqa: D102 - trivial
        return None

    def put(self, key: str, value: dict[str, Any]) -> None:  # noqa: D102 - trivial
        return None
