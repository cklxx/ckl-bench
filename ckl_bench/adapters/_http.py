"""Shared JSON HTTP client with retries and strict outbound URL policy."""

from __future__ import annotations

import ipaddress
import json
import os
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
_SENSITIVE_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key"})


class HTTPRequestError(RuntimeError):
    """Raised when a request ultimately fails. Carries status + attempt count."""

    def __init__(self, message: str, *, status: int | None = None, attempts: int = 1):
        super().__init__(message)
        self.status = status
        self.attempts = attempts


def safe_url_label(url: str) -> str:
    """Return a log-safe URL without credentials, query parameters, or fragments."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or "invalid-host"
    if ":" in host:
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return urllib.parse.urlunsplit((parsed.scheme, f"{host}{port}", parsed.path or "/", "", ""))


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return ip.is_global


def validate_outbound_url(url: str, *, trusted_local: bool = False) -> str:
    """Validate URL syntax, scheme, credentials, and all resolved IP addresses."""
    parsed = urllib.parse.urlsplit(url)
    allowed_schemes = {"https"} | ({"http"} if trusted_local else set())
    if parsed.scheme.lower() not in allowed_schemes:
        raise HTTPRequestError("outbound URL must use HTTPS")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise HTTPRequestError("outbound URL must have a host and no embedded credentials")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise HTTPRequestError("outbound URL has an invalid port") from exc
    try:
        addresses = {str(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPRequestError(f"could not resolve outbound host {parsed.hostname!r}") from exc
    if not addresses:
        raise HTTPRequestError(f"could not resolve outbound host {parsed.hostname!r}")
    if not trusted_local and any(not _is_public_address(address) for address in addresses):
        raise HTTPRequestError(f"outbound host {parsed.hostname!r} resolves to a non-public address")
    return url


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80)


class _PolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, trusted_local: bool):
        super().__init__()
        self.trusted_local = trusted_local

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        if code not in _REDIRECT_STATUS:
            return None
        target = urllib.parse.urljoin(req.full_url, newurl)
        validate_outbound_url(target, trusted_local=self.trusted_local)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is None:
            return None
        if _origin(req.full_url) != _origin(target):
            for key in list(redirected.headers):
                if key.lower() in _SENSITIVE_HEADERS:
                    redirected.remove_header(key)
            for key in list(redirected.unredirected_hdrs):
                if key.lower() in _SENSITIVE_HEADERS:
                    redirected.remove_header(key)
        return redirected


def _retry_settings() -> tuple[int, float, float]:
    max_retries = int(os.environ.get("CKL_MAX_RETRIES", "3"))
    base = float(os.environ.get("CKL_RETRY_BASE_DELAY", "0.5"))
    cap = float(os.environ.get("CKL_RETRY_MAX_DELAY", "20.0"))
    return max(0, max_retries), max(0.0, base), max(0.0, cap)


def _sleep_for(attempt: int, base: float, cap: float, retry_after: float | None) -> None:
    if retry_after is not None:
        time.sleep(min(max(0.0, retry_after), cap))
        return
    delay = min(cap, base * (2 ** attempt))
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
    trusted_local: bool = False,
) -> dict[str, Any]:
    """Request JSON with retry and SSRF-safe URL/redirect validation."""
    validate_outbound_url(url, trusted_local=trusted_local)
    opener = urllib.request.build_opener(_PolicyRedirectHandler(trusted_local))
    label = api_label if "://" not in api_label else safe_url_label(api_label)
    max_retries, base, cap = _retry_settings()
    attempt = 0
    while True:
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code} from {label}: {detail}"
            if exc.code not in RETRYABLE_STATUS or attempt >= max_retries:
                raise HTTPRequestError(message, status=exc.code, attempts=attempt + 1) from exc
            _sleep_for(attempt, base, cap, _retry_after_seconds(exc.headers))
        except HTTPRequestError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            message = f"{type(exc).__name__} from {label}: {exc}"
            if attempt >= max_retries:
                raise HTTPRequestError(message, status=None, attempts=attempt + 1) from exc
            _sleep_for(attempt, base, cap, None)
        attempt += 1
