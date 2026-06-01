from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


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

    capability = payload.get("capability", [])
    if isinstance(capability, str):
        capability = [capability]
    if not isinstance(capability, list):
        raise CaseValidationError(f"{path}:{line_no}: capability must be a string or list")

    timeout_s = payload.get("timeout_s")
    if timeout_s is not None:
        timeout_s = float(timeout_s)

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise CaseValidationError(f"{path}:{line_no}: metadata must be an object")

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


def _required_str(payload: dict[str, Any], key: str, path: Path, line_no: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CaseValidationError(f"{path}:{line_no}: '{key}' must be a non-empty string")
    return value
