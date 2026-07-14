from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path("registries/models")
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ProviderRegistryError(ValueError):
    pass


def load_namespaces(
    registry_dir: Path = REGISTRY_DIR,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not registry_dir.exists():
        return []
    env = environ or os.environ
    namespaces: dict[str, dict[str, Any]] = {}
    for path in sorted(registry_dir.glob("*.jsonl")):
        for record in _load_jsonl(path, env):
            namespace = _merge_record(namespaces, record)
            if not namespace.get("default"):
                namespace["default"] = namespace["targets"][0]["id"]
    return list(namespaces.values())


def load_namespace(
    namespace_id: str,
    registry_dir: Path = REGISTRY_DIR,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    for namespace in load_namespaces(registry_dir=registry_dir, environ=environ):
        if namespace_id == namespace.get("namespace") or namespace_id in namespace.get("aliases", []):
            return namespace
    return None


def load_providers(
    registry_dir: Path = REGISTRY_DIR,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    return [
        provider
        for namespace in load_namespaces(registry_dir=registry_dir, environ=environ)
        for provider in namespace_providers(namespace)
    ]


def load_provider(
    provider_id: str,
    registry_dir: Path = REGISTRY_DIR,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    namespace_id, target_id = _split_provider_id(provider_id)
    namespace = load_namespace(namespace_id, registry_dir=registry_dir, environ=environ)
    if namespace is None:
        return None
    target = _select_target(namespace, target_id)
    if target is None:
        return None
    return _provider_from_target(namespace, target)


def namespace_providers(namespace: dict[str, Any]) -> list[dict[str, Any]]:
    return [_provider_from_target(namespace, target) for target in _targets(namespace)]


def provider_probe_target(provider: dict[str, Any]) -> dict[str, Any]:
    probe = provider.get("probe", {})
    return {
        "target": provider["id"],
        "kind": provider.get("kind", "api"),
        "adapter": provider.get("adapter", "openai"),
        "config": dict(provider.get("config", {})),
        "case_set": probe.get("case_set", "chat"),
        "limit": int(probe.get("limit", 1)),
        "required_env": list(provider.get("required_env", [])),
        "required_env_any": list(provider.get("required_env_any", [])),
    }


def redacted_provider(provider: dict[str, Any]) -> dict[str, Any]:
    return _redact(provider)


def redacted_namespace(namespace: dict[str, Any]) -> dict[str, Any]:
    return _redact(namespace)


def _load_jsonl(path: Path, environ: Mapping[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProviderRegistryError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ProviderRegistryError(f"{path}:{line_no}: expected a JSON object")
        expanded = _expand_env(raw, environ)
        expanded["_registry_path"] = str(path)
        expanded["_registry_line"] = line_no
        records.append(expanded)
    return records


def _merge_record(namespaces: dict[str, dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
    namespace_id = str(record.get("namespace", "")).strip()
    if not namespace_id:
        raise ProviderRegistryError(f"{record.get('_registry_path', '<registry>')}: missing namespace")
    target_id = str(record.get("target") or record.get("id") or "default")
    namespace = namespaces.setdefault(
        namespace_id,
        {
            "namespace": namespace_id,
            "aliases": [],
            "default": None,
            "targets": [],
            "_registry_path": record.get("_registry_path", ""),
        },
    )
    for alias in _as_list(record.get("aliases", [])):
        if alias not in namespace["aliases"]:
            namespace["aliases"].append(alias)
    if record.get("default") is True:
        namespace["default"] = target_id
    elif isinstance(record.get("default"), str) and record["default"]:
        namespace["default"] = record["default"]

    target = dict(record)
    target["id"] = target_id
    namespace["targets"].append(target)
    return namespace


def _provider_from_target(namespace: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    namespace_id = str(namespace.get("namespace", ""))
    target_id = str(target.get("id") or target.get("target") or namespace.get("default") or "default")
    provider_id = namespace_id if target_id == namespace.get("default", target_id) else f"{namespace_id}:{target_id}"
    api_key_env = _as_list(target.get("api_key_env", namespace.get("api_key_env", [])))
    return {
        "id": provider_id,
        "namespace": namespace_id,
        "target": target_id,
        "aliases": _as_list(namespace.get("aliases", [])),
        "label": target.get("label", target_id),
        "kind": target.get("kind", namespace.get("kind", "api")),
        "adapter": target.get("adapter", namespace.get("adapter", "openai")),
        "config": {
            "base_url": target.get("base_url", namespace.get("base_url", "")),
            "api_key_envs": api_key_env,
            "model": target.get("model", namespace.get("model", "")),
            "temperature": target.get("temperature", namespace.get("temperature", 0)),
            "max_tokens": target.get("max_tokens", namespace.get("max_tokens", 512)),
            "headers": target.get("headers", namespace.get("headers", {})),
            "extra_body": target.get("extra_body", namespace.get("extra_body", {})),
        },
        "probe": target.get("probe", namespace.get("probe", {"case_set": "chat", "limit": 1})),
        "required_env": _as_list(target.get("required_env", namespace.get("required_env", []))),
        "required_env_any": _as_list(target.get("required_env_any", api_key_env)),
        "notes": _as_list(target.get("notes", namespace.get("notes", []))),
        "_registry_path": namespace.get("_registry_path", ""),
    }


def _targets(namespace: dict[str, Any]) -> list[dict[str, Any]]:
    targets = namespace.get("targets", {})
    if isinstance(targets, dict):
        return [{"id": key, **value} for key, value in targets.items()]
    if isinstance(targets, list):
        return [dict(target) for target in targets]
    return []


def _select_target(namespace: dict[str, Any], target_id: str | None) -> dict[str, Any] | None:
    selected = target_id or namespace.get("default")
    targets = _targets(namespace)
    if selected is None and targets:
        return targets[0]
    for target in targets:
        if target.get("id") == selected:
            return target
    return None


def _split_provider_id(value: str) -> tuple[str, str | None]:
    for sep in (":", "/"):
        if sep in value:
            namespace_id, target_id = value.split(sep, 1)
            return namespace_id, target_id
    return value, None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _expand_env(value: Any, environ: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: environ.get(match.group(1), match.group(2) or ""), value)
    if isinstance(value, list):
        return [_expand_env(item, environ) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item, environ) for key, item in value.items()}
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = key.lower()
            if key_lower in {"api_key", "authorization", "secret", "token"}:
                redacted[key] = "***" if item else item
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
