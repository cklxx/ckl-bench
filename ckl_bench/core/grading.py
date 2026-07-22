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

from ckl_bench.adapters.base import ModelAdapter

from .cases import EvalCase
from .paths import safe_join
from .sandbox import run_python_script

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

# Writing-quality dimensions for the `quality` expectation kind. Each entry is
# (machine key, Chinese label, English name, one-line description). The judge
# scores each dimension 0.0–1.0 and the overall score is the average.
_QUALITY_DIMENSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("clear", "清晰", "clarity",
     "Clear and easy to understand; ideas expressed without ambiguity."),
    ("coherent", "连贯", "coherence",
     "Flows logically; ideas connected in a sensible order."),
    ("concise", "简洁", "conciseness",
     "Free of redundancy, filler, and unnecessary words."),
    ("specific", "具体", "specificity",
     "Concrete and specific rather than vague or abstract."),
    ("accurate", "准确", "accuracy",
     "Factually correct and free of errors."),
    ("complete", "完整", "completeness",
     "Fully addresses the task; all required parts covered."),
    ("appropriate", "得体", "appropriateness",
     "Tone, register, and style fit the context and audience."),
)


def _build_quality_criteria(selected: list[str] | None) -> str:
    """Build the quality-rubric criteria string the judge will score against."""
    if selected:
        wanted = {str(s) for s in selected}
        dims = [d for d in _QUALITY_DIMENSIONS if d[0] in wanted]
    else:
        dims = list(_QUALITY_DIMENSIONS)
    lines = [
        "Evaluate the candidate response on these writing-quality dimensions.",
        "Score each dimension from 0.0 (fails entirely) to 1.0 (excellent).",
        "The overall score is the average of the dimension scores.",
        "",
    ]
    for _key, zh, en, desc in dims:
        lines.append(f"- {zh} ({en}): {desc}")
    lines.append("")
    lines.append("Average the dimension scores for the overall score.")
    return "\n".join(lines)


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
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
) -> GradeResult:
    checks = [
        _grade_expectation(
            case, expectation, response_text, workspace_path,
            judge_adapter, reviewer_adapter, verifier_adapter,
        )
        for expectation in case.expectations
    ]
    total_weight = sum(check.weight for check in checks) or 1.0
    score = sum(check.score for check in checks) / total_weight
    if "pass_threshold" in case.metadata:
        passed = score >= float(case.metadata["pass_threshold"])
    else:
        passed = all(check.passed for check in checks)
    return GradeResult(score=score, passed=passed, checks=checks)


def _grade_expectation(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
) -> CheckResult:
    kind = str(expectation["kind"])
    weight = float(expectation.get("weight", 1.0))
    try:
        outcome = _evaluate(
            case, kind, expectation, response_text, workspace_path,
            judge_adapter, reviewer_adapter, verifier_adapter,
        )
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
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
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
        if "pattern" not in expectation and "value" not in expectation:
            raise ValueError("regex expectation requires 'pattern' (or 'value')")
        pattern = str(expectation.get("pattern", expectation.get("value")))
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
        if "pattern" not in expectation and "value" not in expectation:
            raise ValueError("file_regex expectation requires 'pattern' (or 'value')")
        pattern = str(expectation.get("pattern", expectation.get("value")))
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
        return _judge_expectation(
            case, expectation, response_text, workspace_path,
            judge_adapter, reviewer_adapter, verifier_adapter,
        )
    if kind in {"quality", "writing_quality"}:
        return _quality_expectation(
            case, expectation, response_text, workspace_path,
            judge_adapter, reviewer_adapter, verifier_adapter,
        )
    raise ValueError(f"unknown expectation kind: {kind}")


def _bool_outcome(passed: bool, detail: str) -> _EvalOutcome:
    return _EvalOutcome(passed=passed, score_fraction=1.0 if passed else 0.0, detail=detail)


def _judge_expectation(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
) -> _EvalOutcome:
    criteria = str(expectation.get("criteria") or expectation.get("rubric") or "").strip()
    if not criteria:
        raise ValueError("judge expectation requires criteria or rubric")
    return _judge_with_criteria(
        case, criteria, expectation, response_text, workspace_path,
        judge_adapter, reviewer_adapter, verifier_adapter,
    )


def _quality_expectation(
    case: EvalCase,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
) -> _EvalOutcome:
    """Judge the response on the 7 writing-quality dimensions (清晰/连贯/简洁/
    具体/准确/完整/得体). Reuses the adversarial judge pipeline; the rubric is
    built from the selected dimensions (defaults to all seven)."""
    selected = expectation.get("dimensions")
    if selected is not None and not isinstance(selected, list):
        raise ValueError("quality 'dimensions' must be a list")
    criteria = _build_quality_criteria(selected if isinstance(selected, list) else None)
    return _judge_with_criteria(
        case, criteria, expectation, response_text, workspace_path,
        judge_adapter, reviewer_adapter, verifier_adapter,
    )


def _judge_with_criteria(
    case: EvalCase,
    criteria: str,
    expectation: dict[str, Any],
    response_text: str,
    workspace_path: Path | None,
    judge_adapter: ModelAdapter | None,
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
) -> _EvalOutcome:
    if judge_adapter is None:
        return _EvalOutcome(
            False, 0.0,
            f"{expectation['kind']} expectation requires --judge or CKL_JUDGE",
        )
    threshold = float(expectation.get("threshold", expectation.get("pass_threshold", 0.7)))
    timeout_s = float(expectation.get("timeout_s", case.timeout_s or 120))
    target_text = _target_text(expectation, response_text, workspace_path)

    from .judge import JudgeConfig, adversarial_judge

    verdict = adversarial_judge(
        case,
        criteria,
        target_text,
        judge_adapter=judge_adapter,
        reviewer_adapter=reviewer_adapter,
        verifier_adapter=verifier_adapter,
        config=JudgeConfig(threshold=threshold, timeout_s=timeout_s),
    )
    return _EvalOutcome(
        passed=verdict.score >= threshold,
        score_fraction=verdict.score,
        detail=verdict.detail,
    )


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
    return safe_join(workspace_path, str(expectation["path"]), label="workspace path")


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


def _extract_code(text: str) -> str | None:
    """Strip a single fenced code block (```lang ... ```) if present.

    Returns ``None`` when no fenced block is found so callers can distinguish
    "extracted code" from "fell back to raw text" (the latter is almost never
    valid Python for code_test checks).
    """
    fence = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, flags=re.S)
    return fence.group(1) if fence else None


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
        created_tmp = tempfile.mkdtemp(prefix="ckl-bench-codetest-")
        work = Path(created_tmp)
    try:
        for name, content in (expectation.get("files") or {}).items():
            _write_safe(work, str(name), str(content))
        response_file = expectation.get("response_file")
        if response_file:
            if expectation.get("extract_code"):
                payload = _extract_code(response_text)
                if payload is None:
                    # No fenced code block in the response. Command agents
                    # (e.g. dsx) write code to a file in the workspace instead
                    # of returning it in the text. If the expected file exists,
                    # use it; otherwise search the workspace for a .py file the
                    # agent may have written under a different name.
                    target = safe_join(work, str(response_file), label="code_test response path")
                    if target.exists():
                        payload = None
                    else:
                        found = _find_agent_file(work, ".py")
                        if found is not None:
                            shutil.copy2(found, target)
                            payload = None
                        else:
                            payload = response_text
            else:
                payload = response_text
            if payload is not None:
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


def _find_agent_file(work: Path, suffix: str) -> Path | None:
    """Find the first file with *suffix* in *work* (excluding caches).

    Command agents may write code under a name they chose (e.g. the function
    name) rather than the ``response_file`` the grader expects. This locates
    the agent's file so it can be copied to the expected name.
    """
    if not work.is_dir():
        return None
    candidates = sorted(
        p for p in work.rglob(f"*{suffix}")
        if p.is_file() and "__pycache__" not in p.parts
    )
    return candidates[0] if candidates else None


def _write_safe(root: Path, name: str, content: str) -> None:
    target = safe_join(root, name, label="code_test path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _load_python_grader(spec: str):
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr)
