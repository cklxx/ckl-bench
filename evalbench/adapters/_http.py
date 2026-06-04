"""Shared HTTP helper: stdlib urllib POST with retry, backoff, and jitter.

Every API adapter routes through ``request_json`` so transient failures
(429 rate limits, 5xx, connection resets, timeouts) survive a long live run
instead of zeroing a case. Retryable vs fatal is distinguished by status code,
``Retry-After`` is honored, and attempt counts are surfaced for evidence.

Tuning via environment (all optional):
- ``EVB_MAX_RETRIES``       default 3 (so up to 4 attempts)
- ``EVB_RETRY_BASE_DELAY``  default 0.5 (seconds, doubled each attempt)
- ``EVB_RETRY_MAX_DELAY``   default 20.0 (seconds, per-attempt cap)
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any

# Status codes worth retrying: request timeout, conflict, rate limit, and the
# transient 5xx family. Everything else (400/401/403/404/422) is fatal.
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class HTTPRequestError(RuntimeError):
    """Raised when a request ultimately fails. Carries status + attempt count."""

    def __init__(self, message: str, *, status: int | None = None, attempts: int = 1):
        super().__init__(message)
        self.status = status
        self.attempts = attempts


def _retry_settings() -> tuple[int, float, float]:
    max_retries = int(os.environ.get("EVB_MAX_RETRIES", "3"))
    base = float(os.environ.get("EVB_RETRY_BASE_DELAY", "0.5"))
    cap = float(os.environ.get("EVB_RETRY_MAX_DELAY", "20.0"))
    return max(0, max_retries), max(0.0, base), max(0.0, cap)


def _sleep_for(attempt: int, base: float, cap: float, retry_after: float | None) -> None:
    if retry_after is not None:
        time.sleep(min(retry_after, cap))
        return
    delay = min(cap, base * (2 ** attempt))
    # Full jitter avoids synchronized retries across concurrent workers.
    time.sleep(random.uniform(0.0, delay) if delay > 0 else 0.0)


def _retry_after_seconds(headers: Any) -> float | None:
    try:
        value = headers.get("Retry-After") if headers else None
    except AttributeError:
        return None
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def request_json(
    url: str,
    *,
    data: bytes,
    headers: dict[str, str],
    method: str = "POST",
    timeout: float | None = 120.0,
    api_label: str = "API",
) -> dict[str, Any]:
    """POST ``data`` to ``url`` and return parsed JSON, retrying transient errors.

    Raises ``HTTPRequestError`` on a fatal status or after exhausting retries.
    """
    max_retries, base, cap = _retry_settings()
    attempt = 0
    while True:
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code} from {api_label}: {detail}"
            if exc.code not in RETRYABLE_STATUS or attempt >= max_retries:
                raise HTTPRequestError(message, status=exc.code, attempts=attempt + 1) from exc
            _sleep_for(attempt, base, cap, _retry_after_seconds(exc.headers))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            message = f"{type(exc).__name__} from {api_label}: {exc}"
            if attempt >= max_retries:
                raise HTTPRequestError(message, status=None, attempts=attempt + 1) from exc
            _sleep_for(attempt, base, cap, None)
        attempt += 1
