from __future__ import annotations

import os
import re
from pathlib import Path

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvFileError(ValueError):
    pass


def load_default_env() -> list[str]:
    return load_env_file(Path(os.environ.get("EVB_ENV_FILE", ".env")))


def load_env_file(path: Path = Path(".env"), override: bool = False) -> list[str]:
    """Load simple KEY=VALUE pairs from a .env file without extra dependencies."""

    if not path.exists():
        return []
    loaded: list[str] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise EnvFileError(f"{path}:{line_no}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not ENV_NAME_RE.match(key):
            raise EnvFileError(f"{path}:{line_no}: invalid env var name {key!r}")
        parsed_value = _parse_env_value(value)
        if override or key not in os.environ:
            os.environ[key] = parsed_value
            loaded.append(key)
    return loaded


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0] == value[-1] and value[0] in {"'", '"'}:
        body = value[1:-1]
        if value[0] == '"':
            return bytes(body, "utf-8").decode("unicode_escape")
        return body
    return _strip_inline_comment(value).strip()


def _strip_inline_comment(value: str) -> str:
    escaped = False
    for index, char in enumerate(value):
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == "#" and not escaped and (index == 0 or value[index - 1].isspace()):
            return value[:index]
        escaped = False
    return value
