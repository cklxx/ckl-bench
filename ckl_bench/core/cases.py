from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CaseValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EvalCase:
    id: str
    title: str
    type: str
    input: dict[str, Any]
    expectations: list[dict[str, Any]]
    capability: list[str]
    difficulty: str | None
    timeout_s: float | None
    metadata: dict[str, Any]
    source_path: Path
    source_line: int

    @property
    def messages(self) -> list[dict[str, str]]:
        messages = self.input.get("messages")
        if messages is not None:
            return [{"role": str(m["role"]), "content": str(m["content"])} for m in messages]
        prompt = self.prompt
        return [{"role": "user", "content": prompt}]

    @property
    def prompt(self) -> str:
        if "prompt" in self.input:
            return str(self.input["prompt"])
        messages = self.input.get("messages", [])
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return "\n".join(str(m.get("content", "")) for m in messages)


def discover_case_files(paths: Iterable[str | Path]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.is_file():
            files.append(path)
        else:
            raise CaseValidationError(f"case path does not exist: {path}")
    return files


def load_cases(paths: Iterable[str | Path]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: dict[str, Path] = {}
    for path in discover_case_files(paths):
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise CaseValidationError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
                case = _parse_case(payload, path, line_no)
                if case.id in seen:
                    raise CaseValidationError(
                        f"duplicate case id '{case.id}' in {path}:{line_no}; "
                        f"first seen in {seen[case.id]}"
                    )
                seen[case.id] = path
                cases.append(case)
    return cases


def _parse_case(payload: dict[str, Any], path: Path, line_no: int) -> EvalCase:
    if not isinstance(payload, dict):
        raise CaseValidationError(f"{path}:{line_no}: case must be a JSON object")
    case_id = _required_str(payload, "id", path, line_no)
    input_payload = payload.get("input")
    if not isinstance(input_payload, dict):
        raise CaseValidationError(f"{path}:{line_no}: 'input' must be an object")
    if "prompt" not in input_payload and "messages" not in input_payload:
        raise CaseValidationError(f"{path}:{line_no}: input needs 'prompt' or 'messages'")
    messages = input_payload.get("messages")
    if messages is not None:
        if not isinstance(messages, list) or not messages:
            raise CaseValidationError(f"{path}:{line_no}: input.messages must be a non-empty list")
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or "role" not in message or "content" not in message:
                raise CaseValidationError(
                    f"{path}:{line_no}: input.messages[{index}] needs role and content"
                )
    expectations = payload.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        raise CaseValidationError(f"{path}:{line_no}: 'expectations' must be a non-empty list")
    for index, expectation in enumerate(expectations):
        if not isinstance(expectation, dict) or "kind" not in expectation:
            raise CaseValidationError(f"{path}:{line_no}: expectations[{index}] needs kind")
        prefix = f"expectations[{index}]"
        kind = str(expectation["kind"])
        if "weight" in expectation:
            _validate_number(expectation["weight"], f"{prefix}.weight", path, line_no, positive=True)
        if kind in {"judge", "llm_judge", "quality", "writing_quality"}:
            for key in ("threshold", "pass_threshold"):
                if key in expectation:
                    _validate_number(
                        expectation[key], f"{prefix}.{key}", path, line_no, unit_interval=True
                    )
        if kind in {"numeric", "close"}:
            for key in ("abs_tol", "rel_tol", "tol"):
                if key in expectation:
                    _validate_number(
                        expectation[key], f"{prefix}.{key}", path, line_no, nonnegative=True
                    )
        if kind in {"judge", "llm_judge", "quality", "writing_quality", "code_test", "execute", "run"}:
            if "timeout_s" in expectation:
                _validate_number(
                    expectation["timeout_s"], f"{prefix}.timeout_s", path, line_no, nonnegative=True
                )

    capability = payload.get("capability", [])
    if isinstance(capability, str):
        capability = [capability]
    if not isinstance(capability, list):
        raise CaseValidationError(f"{path}:{line_no}: capability must be a string or list")

    timeout_s = payload.get("timeout_s")
    if timeout_s is not None:
        timeout_s = _validate_number(timeout_s, "timeout_s", path, line_no, nonnegative=True)

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise CaseValidationError(f"{path}:{line_no}: metadata must be an object")
    if "pass_threshold" in metadata:
        _validate_number(
            metadata["pass_threshold"], "metadata.pass_threshold", path, line_no, unit_interval=True
        )

    return EvalCase(
        id=case_id,
        title=str(payload.get("title", case_id)),
        type=str(payload.get("type", "chat")),
        input=input_payload,
        expectations=expectations,
        capability=[str(item) for item in capability],
        difficulty=str(payload["difficulty"]) if "difficulty" in payload else None,
        timeout_s=timeout_s,
        metadata=metadata,
        source_path=path,
        source_line=line_no,
    )


def _validate_number(
    value: Any,
    field: str,
    path: Path,
    line_no: int,
    *,
    positive: bool = False,
    nonnegative: bool = False,
    unit_interval: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CaseValidationError(f"{path}:{line_no}: {field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise CaseValidationError(f"{path}:{line_no}: {field} must be a finite number")
    if positive and number <= 0:
        raise CaseValidationError(f"{path}:{line_no}: {field} must be greater than 0")
    if nonnegative and number < 0:
        raise CaseValidationError(f"{path}:{line_no}: {field} must be nonnegative")
    if unit_interval and not 0 <= number <= 1:
        raise CaseValidationError(f"{path}:{line_no}: {field} must be between 0 and 1")
    return number


def _required_str(payload: dict[str, Any], key: str, path: Path, line_no: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CaseValidationError(f"{path}:{line_no}: '{key}' must be a non-empty string")
    return value


# ---------------------------------------------------------------------------
# Case serialization / CRUD helpers (used by the dashboard server)
# ---------------------------------------------------------------------------


def validate_case_dict(payload: dict[str, Any]) -> EvalCase:
    """Validate a case dict and return an :class:`EvalCase`.

    Reuses :func:`_parse_case` so the server and the file loader share the same
    schema rules.  Raises :class:`CaseValidationError` on bad input.
    """
    return _parse_case(payload, Path("<api>"), 0)


def case_to_dict(case: EvalCase) -> dict[str, Any]:
    """Serialize *case* back to the JSONL schema (without internal fields)."""
    payload: dict[str, Any] = {
        "id": case.id,
        "title": case.title,
        "type": case.type,
        "input": case.input,
        "expectations": case.expectations,
    }
    if case.capability:
        payload["capability"] = case.capability
    if case.difficulty is not None:
        payload["difficulty"] = case.difficulty
    if case.timeout_s is not None:
        payload["timeout_s"] = case.timeout_s
    if case.metadata:
        payload["metadata"] = case.metadata
    return payload


def write_cases(path: Path, cases: list[EvalCase]) -> Path:
    """Atomically write *cases* to *path* as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payloads = [case_to_dict(case) for case in cases]
    for payload in payloads:
        validate_case_dict(payload)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path
