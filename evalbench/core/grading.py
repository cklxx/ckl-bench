from __future__ import annotations

import importlib
import json
import math
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evalbench.adapters.base import GenerateRequest, ModelAdapter

from .cases import EvalCase
from .sandbox import run_python_script

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


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


@dataclass(frozen=True)
class _EvalOutcome:
    passed: bool
    score_fraction: float
    detail: str


def grade_case(
    case: EvalCase,
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None = None,
) -> GradeResult:
    checks = [
        _grade_expectation(case, expectation, response_text, workspace_path, judge_adapter)
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
    judge_adapter: ModelAdapter | None,
) -> CheckResult:
    kind = str(expectation["kind"])
    weight = float(expectation.get("weight", 1.0))
    try:
        outcome = _evaluate(case, kind, expectation, response_text, workspace_path, judge_adapter)
    except Exception as exc:  # noqa: BLE001 - grader errors must be recorded, not hidden.
        outcome = _EvalOutcome(False, 0.0, f"grader error: {type(exc).__name__}: {exc}")
    score_fraction = min(max(outcome.score_fraction, 0.0), 1.0)
    return CheckResult(
        kind=kind,
        passed=outcome.passed,
        score=weight * score_fraction,
        weight=weight,
        detail=outcome.detail,
    )


def _evaluate(
    case: EvalCase,
    kind: str,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
) -> _EvalOutcome:
    if kind == "contains":
        text = _target_text(expectation, response_text, workspace_path)
        value = str(expectation["value"])
        case_sensitive = bool(expectation.get("case_sensitive", True))
        haystack = text if case_sensitive else text.lower()
        needle = value if case_sensitive else value.lower()
        return _bool_outcome(needle in haystack, f"expected contains {value!r}")
    if kind == "not_contains":
        text = _target_text(expectation, response_text, workspace_path)
        value = str(expectation["value"])
        case_sensitive = bool(expectation.get("case_sensitive", True))
        haystack = text if case_sensitive else text.lower()
        needle = value if case_sensitive else value.lower()
        return _bool_outcome(needle not in haystack, f"expected not contains {value!r}")
    if kind == "exact":
        expected = str(expectation["value"])
        actual = _target_text(expectation, response_text, workspace_path).strip()
        return _bool_outcome(actual == expected, f"expected exact {expected!r}, got {actual!r}")
    if kind == "regex":
        text = _target_text(expectation, response_text, workspace_path)
        flags = re.IGNORECASE if expectation.get("ignore_case") else 0
        pattern = str(expectation["pattern"])
        return _bool_outcome(re.search(pattern, text, flags=flags) is not None, f"expected regex {pattern!r}")
    if kind == "json_path":
        data = _loads_lenient(_target_text(expectation, response_text, workspace_path))
        actual = _extract_path(data, str(expectation["path"]))
        if "equals" in expectation:
            return _bool_outcome(
                actual == expectation["equals"],
                f"expected {expectation['path']} == {expectation['equals']!r}, got {actual!r}",
            )
        if "contains" in expectation:
            expected = str(expectation["contains"])
            return _bool_outcome(expected in str(actual), f"expected {expectation['path']} contains {expected!r}")
        return _bool_outcome(actual is not None, f"expected path {expectation['path']} to exist")
    if kind == "file_exists":
        path = _workspace_file(workspace_path, expectation)
        return _bool_outcome(path.exists(), f"expected file {path.name} to exist")
    if kind == "file_contains":
        path = _workspace_file(workspace_path, expectation)
        value = str(expectation["value"])
        return _bool_outcome(
            value in path.read_text(encoding="utf-8"),
            f"expected {path.name} contains {value!r}",
        )
    if kind == "file_regex":
        path = _workspace_file(workspace_path, expectation)
        pattern = str(expectation["pattern"])
        return _bool_outcome(
            re.search(pattern, path.read_text(encoding="utf-8")) is not None,
            f"expected {path.name} matches {pattern!r}",
        )
    if kind in {"numeric", "close"}:
        text = _target_text(expectation, response_text, workspace_path)
        expected = float(expectation["value"])
        abs_tol = float(expectation.get("abs_tol", expectation.get("tol", 1e-6)))
        rel_tol = float(expectation.get("rel_tol", 0.0))
        actual = _extract_number(text, expectation)
        if actual is None:
            return _EvalOutcome(False, 0.0, f"no number found in target for numeric check (got {text[:60]!r})")
        ok = math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol)
        return _bool_outcome(ok, f"expected ~{expected} (abs_tol={abs_tol}, rel_tol={rel_tol}), got {actual}")
    if kind in {"set_equals", "set_equal"}:
        text = _target_text(expectation, response_text, workspace_path)
        data = json.loads(text)
        if "path" in expectation:
            data = _extract_path(data, str(expectation["path"]))
        expected = expectation.get("values", expectation.get("value"))
        actual_set = _as_frozenset(data)
        expected_set = _as_frozenset(expected)
        return _bool_outcome(
            actual_set == expected_set,
            f"expected set of {len(expected_set)} items, got {len(actual_set)} "
            f"(missing={_preview(expected_set - actual_set)}, extra={_preview(actual_set - expected_set)})",
        )
    if kind in {"choice", "mcq"}:
        text = _target_text(expectation, response_text, workspace_path)
        value = str(expectation["value"])
        choices = [str(choice) for choice in expectation.get("choices", [value])]
        case_sensitive = bool(expectation.get("case_sensitive", False))
        selected = _extract_choice(text, choices, case_sensitive)
        expected = value if case_sensitive else value.lower()
        normalized = selected if (selected is None or case_sensitive) else selected.lower()
        return _bool_outcome(normalized == expected, f"expected choice {value!r}, got {selected!r}")
    if kind in {"code_test", "execute", "run"}:
        return _code_test(case, expectation, response_text, workspace_path)
    if kind == "python":
        fn = _load_python_grader(str(expectation["callable"]))
        result = fn(case=case, response_text=response_text, workspace_path=workspace_path, expectation=expectation)
        if isinstance(result, dict):
            passed = bool(result.get("passed"))
            score = float(result.get("score", 1.0 if passed else 0.0))
            return _EvalOutcome(passed, score, str(result.get("detail", "python grader")))
        return _bool_outcome(bool(result), "python grader")
    if kind in {"judge", "llm_judge"}:
        return _judge_expectation(case, expectation, response_text, workspace_path, judge_adapter)
    raise ValueError(f"unknown expectation kind: {kind}")


def _bool_outcome(passed: bool, detail: str) -> _EvalOutcome:
    return _EvalOutcome(passed=passed, score_fraction=1.0 if passed else 0.0, detail=detail)


def _judge_expectation(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
) -> _EvalOutcome:
    if judge_adapter is None:
        return _EvalOutcome(False, 0.0, "judge expectation requires --judge or EVB_JUDGE")
    criteria = str(expectation.get("criteria") or expectation.get("rubric") or "").strip()
    if not criteria:
        raise ValueError("judge expectation requires criteria or rubric")
    threshold = float(expectation.get("threshold", expectation.get("pass_threshold", 0.7)))
    target_text = _target_text(expectation, response_text, workspace_path)
    prompt = _judge_prompt(case, criteria, target_text)
    judge_response = judge_adapter.generate(
        GenerateRequest(
            case_id=f"{case.id}:judge",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict evaluation judge. Return JSON only with "
                        "keys score, passed, and reason. score must be between 0 and 1."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            prompt=prompt,
            metadata={"case_type": "judge", "judge_for": case.id},
            timeout_s=float(expectation.get("timeout_s", case.timeout_s or 120)),
        )
    )
    data = _parse_judge_json(judge_response.text)
    score = float(data.get("score", 1.0 if data.get("passed") else 0.0))
    score = min(max(score, 0.0), 1.0)
    passed = score >= threshold
    reason = str(data.get("reason") or data.get("detail") or "").strip()
    detail = f"judge score={score:.3f} threshold={threshold:.3f}"
    if reason:
        detail += f" | {reason}"
    return _EvalOutcome(passed=passed, score_fraction=score, detail=detail)


def _judge_prompt(case: EvalCase, criteria: str, target_text: str) -> str:
    return (
        f"Case id: {case.id}\n"
        f"Title: {case.title}\n\n"
        "Task prompt/messages:\n"
        f"{json.dumps(case.messages, ensure_ascii=False, indent=2)}\n\n"
        "Candidate response or artifact:\n"
        f"{target_text}\n\n"
        "Evaluation criteria:\n"
        f"{criteria}\n\n"
        "Return only JSON in this shape:\n"
        '{"score":0.0,"passed":false,"reason":"short reason"}'
    )


def _parse_judge_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError(f"judge returned non-JSON: {text[:200]}") from exc
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("judge JSON must be an object")
    return data


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


def _loads_lenient(text: str) -> Any:
    """Parse JSON, tolerating surrounding prose or a Markdown code fence.

    Strict parse first (so well-formed answers are unaffected); on failure, try a
    fenced block, then the last balanced object/array in the text. This keeps
    grading focused on the answer rather than on exact output formatting.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no parseable JSON found in response: {text[:120]!r}")


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


def _extract_number(text: str, expectation: dict[str, Any]) -> float | None:
    if "path" in expectation:
        try:
            value = _extract_path(json.loads(text), str(expectation["path"]))
            return float(value)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
            return None
    stripped = text.strip()
    try:
        return float(stripped)
    except ValueError:
        match = _NUMBER_RE.search(stripped)
        return float(match.group(0)) if match else None


def _as_frozenset(items: Any) -> frozenset[str]:
    if not isinstance(items, (list, tuple, set, frozenset)):
        raise ValueError(f"set check needs a list/array, got {type(items).__name__}")
    return frozenset(json.dumps(item, sort_keys=True, ensure_ascii=True) for item in items)


def _preview(values: frozenset[str], limit: int = 4) -> str:
    items = sorted(values)[:limit]
    suffix = "..." if len(values) > limit else ""
    return "{" + ", ".join(items) + suffix + "}"


def _extract_choice(text: str, choices: list[str], case_sensitive: bool) -> str | None:
    """Return the choice token that appears LAST in the text (models conclude
    with their answer), or None if no choice token is present."""
    flags = 0 if case_sensitive else re.IGNORECASE
    best: str | None = None
    best_pos = -1
    for choice in choices:
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(choice)}(?![A-Za-z0-9_])"
        for match in re.finditer(pattern, text, flags):
            if match.start() >= best_pos:
                best_pos = match.start()
                best = choice
    return best


def _extract_code(text: str) -> str:
    """Strip a single fenced code block (```lang ... ```) if present."""
    fence = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, flags=re.S)
    return fence.group(1) if fence else text


def _code_test(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
) -> _EvalOutcome:
    test = str(expectation.get("test", expectation.get("code", "")))
    if not test:
        raise ValueError("code_test requires 'test' (or 'code')")
    setup = str(expectation.get("setup", ""))
    script = f"{setup}\n{test}" if setup else test
    timeout_s = float(expectation.get("timeout_s", case.timeout_s or 15))
    memory_mb = int(expectation.get("memory_mb", 512))

    created_tmp: str | None = None
    work = workspace_path
    if work is None:
        created_tmp = tempfile.mkdtemp(prefix="evalbench-codetest-")
        work = Path(created_tmp)
    try:
        for name, content in (expectation.get("files") or {}).items():
            _write_safe(work, str(name), str(content))
        response_file = expectation.get("response_file")
        if response_file:
            payload = _extract_code(response_text) if expectation.get("extract_code") else response_text
            _write_safe(work, str(response_file), payload)
        result = run_python_script(script, cwd=work, timeout_s=timeout_s, memory_mb=memory_mb)
    finally:
        if created_tmp:
            shutil.rmtree(created_tmp, ignore_errors=True)

    passed = result.ok
    detail = f"exit={result.returncode} time={result.duration_ms}ms"
    if result.timed_out:
        detail += " (timed out)"
    if not passed:
        tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        if tail:
            detail += " | " + " / ".join(line.strip() for line in tail)
    return _EvalOutcome(passed, 1.0 if passed else 0.0, detail)


def _write_safe(root: Path, name: str, content: str) -> None:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe code_test path: {name}")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _load_python_grader(spec: str):
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr)
