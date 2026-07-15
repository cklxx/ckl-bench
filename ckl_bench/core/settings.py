"""Persistent settings for the ckl-bench dashboard.

Settings live in ``~/.ckl_bench/settings.json`` and bridge the UI config to
environment variables consumed by the wrapper scripts (claude_code_wrapper.py,
codex_wrapper.py, dsx_wrapper.py).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

#: Directory for persistent settings.
SETTINGS_DIR = Path(os.environ.get("CKL_BENCH_HOME", Path.home() / ".ckl_bench"))

#: Settings file path.
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

#: Default run options.
DEFAULT_DEFAULTS: dict[str, Any] = {
    "repeat": 1,
    "concurrency": 1,
    "seed": 0,
    "judge": "",
}

#: Default adapter configs — the command is the raw CLI binary; the
#: CommandAdapter auto-routes through the matching wrapper script internally.
DEFAULT_ADAPTER_CONFIGS: dict[str, dict[str, Any]] = {
    "claude-code": {
        "command": "claude",
        "model": "",
    },
    "codex": {
        "command": "codex",
        "model": "",
    },
    "dsx": {
        "command": "dsx",
        "model": "",
    },
}

#: Map of UI adapter key → env var names consumed by the wrapper scripts.
#: Each value maps a config key (e.g. "api_key") to an env var name.
ADAPTER_ENV_MAP: dict[str, dict[str, str]] = {
    "claude-code": {
        "command": "CKL_CLAUDE_COMMAND",
        "api_key": "CKL_CLAUDE_API_KEY",
        "base_url": "CKL_CLAUDE_ANTHROPIC_BASE_URL",
        "model": "CKL_CLAUDE_MODEL",
        "workspace_dir": "CKL_CLAUDE_WORKSPACE_DIR",
    },
    "codex": {
        "command": "CKL_CODEX_COMMAND",
        "model": "CKL_CODEX_MODEL",
        "workspace_dir": "CKL_CODEX_WORKSPACE_DIR",
    },
    "dsx": {
        "command": "CKL_DSX_COMMAND",
        "model": "CKL_DSX_MODEL",
        "workspace_dir": "CKL_DSX_WORKSPACE_DIR",
    },
}

#: Keys whose values should be masked when returning settings to the UI.
SECRET_KEYS = {"api_key", "token", "key", "secret"}


@dataclass
class Settings:
    """Persistent dashboard settings."""

    adapters: dict[str, dict[str, Any]] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_DEFAULTS))
    active_adapters: list[str] = field(default_factory=list)


def settings_from_dict(raw: dict[str, Any]) -> Settings:
    """Merge a raw settings dict with defaults and return a Settings object.

    Adapters are merged with :data:`DEFAULT_ADAPTER_CONFIGS` so the wrapper
    script commands are available out of the box. Used by both
    :func:`load_settings` (disk) and the server's settings update endpoint.
    """
    adapters = copy.deepcopy(DEFAULT_ADAPTER_CONFIGS)
    stored = raw.get("adapters", {})
    if isinstance(stored, dict):
        for name, cfg in stored.items():
            if isinstance(cfg, dict):
                adapters.setdefault(name, {})
                adapters[name].update(cfg)
    defaults = copy.deepcopy(DEFAULT_DEFAULTS)
    defaults.update(raw.get("defaults", {}) or {})
    active = raw.get("active_adapters", [])
    if not isinstance(active, list):
        active = []
    return Settings(adapters=adapters, defaults=defaults, active_adapters=active)


def load_settings() -> Settings:
    """Load settings from disk, falling back to defaults."""
    if not SETTINGS_FILE.exists():
        return settings_from_dict({})
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("could not read settings: %s", exc)
        return settings_from_dict({})
    return settings_from_dict(raw)


def save_settings(settings: Settings, existing: Settings | None = None) -> None:
    """Persist settings to disk.

    Merges with *existing* settings (or on-disk values when *existing* is
    ``None``) so masked secrets (``****last4``) don't overwrite the real
    stored values.
    """
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    if existing is None:
        existing = load_settings()
    # Merge adapters: preserve stored secrets when UI sends masked values.
    merged_adapters: dict[str, dict[str, Any]] = {}
    for name, cfg in settings.adapters.items():
        merged = dict(existing.adapters.get(name, {}))
        for key, value in cfg.items():
            if key in SECRET_KEYS and isinstance(value, str) and value.startswith("****"):
                # Masked value — keep the stored secret if present.
                if key in merged:
                    continue
            merged[key] = value
        merged_adapters[name] = merged
    # Also keep adapters that were removed from UI but exist on disk?
    # No — only save what the UI sends. Removed adapters are dropped.
    raw = {
        "adapters": merged_adapters,
        "defaults": settings.defaults,
        "active_adapters": settings.active_adapters,
    }
    SETTINGS_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def apply_settings(settings: Settings) -> None:
    """Set env vars from settings so wrapper scripts pick them up.

    Only sets keys that are present; does not unset existing shell env vars.
    """
    for name, cfg in settings.adapters.items():
        env_map = ADAPTER_ENV_MAP.get(name, {})
        for key, value in cfg.items():
            env_var = env_map.get(key)
            if env_var and value is not None and str(value) != "":
                os.environ[env_var] = str(value)


def mask_secrets(settings: Settings) -> Settings:
    """Return a copy of settings with secret values masked to ``****last4``."""
    masked = copy.deepcopy(settings)
    for cfg in masked.adapters.values():
        for key, value in cfg.items():
            if key in SECRET_KEYS and isinstance(value, str) and value:
                if len(value) > 4:
                    cfg[key] = "****" + value[-4:]
                else:
                    cfg[key] = "****"
    return masked


def test_adapter(adapter_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build an adapter and run a ping request to verify it works.

    Returns ``{ok, output, error}``. Uses a short timeout so the UI test
    button does not spin forever.
    """
    import shlex
    import subprocess
    import tempfile
    from pathlib import Path as _Path

    from ckl_bench.adapters import build_adapter
    from ckl_bench.adapters.base import GenerateRequest

    # Quick pre-check: for command adapters, verify the command exists and is
    # executable before running the full (slower) ping test.
    if adapter_name == "command":
        command = config.get("command", "")
        if command:
            try:
                first_token = shlex.split(command)[0]
            except (ValueError, IndexError):
                first_token = command
            import shutil
            if "/" not in first_token and shutil.which(first_token) is None:
                return {
                    "ok": False,
                    "output": "",
                    "error": f"command not found: {first_token!r} (check PATH or use full path)",
                }

    try:
        adapter = build_adapter(adapter_name, config)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": "", "error": f"build failed: {exc}"}

    # Use a temp workspace so the test does not copy the entire repo.
    with tempfile.TemporaryDirectory(prefix="ckl-test-") as tmp:
        request = GenerateRequest(
            case_id="ping",
            messages=[{"role": "user", "content": "PONG"}],
            prompt="Reply with the word PONG.",
            workspace_path=_Path(tmp),
            timeout_s=10,
        )
        try:
            response = adapter.generate(request)
            text = response.text[:500] if response.text else ""
            return {"ok": True, "output": text, "error": ""}
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "output": "",
                "error": "timed out after 10s — the command may not speak the "
                "JSON stdin/stdout contract. Use a wrapper script "
                "(scripts/*_wrapper.py) or a command that reads JSON from stdin "
                "and writes JSON to stdout.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "output": "", "error": str(exc)}
