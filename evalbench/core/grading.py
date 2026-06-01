from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cases import EvalCase


@dataclass
class CheckResult:
    kind: str
    passed: bool
    score: float
    weight: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "passed": self.passed,
            "score": self.score,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class GradeResult:
    score: float
    passed: bool
    checks: list[CheckResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "checks": [check.as_dict() for check in self.checks],
        }


def grade_case(case: EvalCase, response_text: str, workspace_path: Path | None) -> GradeResult:
    checks = [
        _grade_expectation(case, expectation, response_text, workspace_path)
        for expectation in case.expectations
    ]
    total_weight = sum(check.weight for check in checks) or 1.0
    score = sum(check.score for check in checks) / total_weight
    threshold = float(case.metadata.get("pass_threshold", 1.0))
    return GradeResult(score=score, passed=score >= threshold, checks=checks)


def _grade_expectation(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
) -> CheckResult:
    kind = str(expectation["kind"])
    weight = float(expectation.get("weight", 1.0))
    try:
        passed, detail = _evaluate(case, kind, expectation, response_text, workspace_path)
    except Exception as exc:  # noqa: BLE001 - grader errors must be recorded, not hidden.
        passed = False
        detail = f"grader error: {type(exc).__name__}: {exc}"
    return CheckResult(
        kind=kind,
        passed=passed,
        score=weight if passed else 0.0,
        weight=weight,
        detail=detail,
    )


def _evaluate(
    case: EvalCase,
    kind: str,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
) -> tuple[bool, str]:
    if kind == "contains":
        text = _target_text(expectation, response_text, workspace_path)
        value = str(expectation["value"])
        case_sensitive = bool(expectation.get("case_sensitive", True))
        haystack = text if case_sensitive else text.lower()
        needle = value if case_sensitive else value.lower()
        return needle in haystack, f"expected contains {value!r}"
    if kind == "not_contains":
        text = _target_text(expectation, response_text, workspace_path)
        value = str(expectation["value"])
        case_sensitive = bool(expectation.get("case_sensitive", True))
        haystack = text if case_sensitive else text.lower()
        needle = value if case_sensitive else value.lower()
        return needle not in haystack, f"expected not contains {value!r}"
    if kind == "exact":
        expected = str(expectation["value"])
        actual = _target_text(expectation, response_text, workspace_path).strip()
        return actual == expected, f"expected exact {expected!r}, got {actual!r}"
    if kind == "regex":
        text = _target_text(expectation, response_text, workspace_path)
        flags = re.IGNORECASE if expectation.get("ignore_case") else 0
        pattern = str(expectation["pattern"])
        return re.search(pattern, text, flags=flags) is not None, f"expected regex {pattern!r}"
    if kind == "json_path":
        data = json.loads(_target_text(expectation, response_text, workspace_path))
        actual = _extract_path(data, str(expectation["path"]))
        if "equals" in expectation:
            return actual == expectation["equals"], (
                f"expected {expectation['path']} == {expectation['equals']!r}, got {actual!r}"
            )
        if "contains" in expectation:
            expected = str(expectation["contains"])
            return expected in str(actual), f"expected {expectation['path']} contains {expected!r}"
        return actual is not None, f"expected path {expectation['path']} to exist"
    if kind == "file_exists":
        path = _workspace_file(workspace_path, expectation)
        return path.exists(), f"expected file {path.name} to exist"
    if kind == "file_contains":
        path = _workspace_file(workspace_path, expectation)
        value = str(expectation["value"])
        return value in path.read_text(encoding="utf-8"), f"expected {path.name} contains {value!r}"
    if kind == "file_regex":
        path = _workspace_file(workspace_path, expectation)
        pattern = str(expectation["pattern"])
        return (
            re.search(pattern, path.read_text(encoding="utf-8")) is not None,
            f"expected {path.name} matches {pattern!r}",
        )
    if kind == "python":
        fn = _load_python_grader(str(expectation["callable"]))
        result = fn(case=case, response_text=response_text, workspace_path=workspace_path, expectation=expectation)
        if isinstance(result, dict):
            return bool(result.get("passed")), str(result.get("detail", "python grader"))
        return bool(result), "python grader"
    raise ValueError(f"unknown expectation kind: {kind}")


def _target_text(expectation: dict[str, Any], response_text: str, workspace_path: Path | None) -> str:
    target = expectation.get("target", "text")
    if target == "text":
        return response_text
    if target == "file":
        return _workspace_file(workspace_path, expectation).read_text(encoding="utf-8")
    raise ValueError(f"unknown expectation target: {target}")


def _workspace_file(workspace_path: Path | None, expectation: dict[str, Any]) -> Path:
    if workspace_path is None:
        raise ValueError("workspace expectation used without workspace")
    relative = Path(str(expectation["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe workspace path: {relative}")
    return workspace_path / relative


def _extract_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _load_python_grader(spec: str):
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr)
