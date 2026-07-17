from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def resource_path(relative: str, override: str | Path | None = None) -> Path:
    """Resolve an explicit path, checkout override, then packaged default."""
    if override is not None:
        path = Path(override)
        if path.exists():
            return path
    checkout = Path(relative)
    if checkout.exists():
        return checkout
    return Path(str(files("ckl_bench.resources").joinpath(relative)))
