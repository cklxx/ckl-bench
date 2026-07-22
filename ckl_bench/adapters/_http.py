"""Shared JSON HTTP client with retries and strict outbound URL policy."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
_SENSITIVE_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key"})
_MAX_REDIRECTS = 10


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


def _resolve_target(url: str, *, trusted_local: bool) -> tuple[urllib.parse.SplitResult, str, int]:
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
        addresses = {
            str(item[4][0])
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise HTTPRequestError(f"could not resolve outbound host {parsed.hostname!r}") from exc
    if not addresses:
        raise HTTPRequestError(f"could not resolve outbound host {parsed.hostname!r}")
    if not trusted_local and any(not _is_public_address(address) for address in addresses):
        raise HTTPRequestError(f"outbound host {parsed.hostname!r} resolves to a non-public address")
    # Deterministic selection makes the validated address the address actually dialed.
    return parsed, sorted(addresses)[0], port


def validate_outbound_url(url: str, *, trusted_local: bool = False) -> str:
    """Validate URL syntax, scheme, credentials, and all resolved IP addresses."""
    _resolve_target(url, trusted_local=trusted_local)
    return url


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80)


class _PolicyRedirectHandler:
    """Compatibility helper for callers/tests that inspect redirect policy."""

    def __init__(self, trusted_local: bool):
        self.trusted_local = trusted_local

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        if code not in _REDIRECT_STATUS:
            return None
        target = urllib.parse.urljoin(req.full_url, newurl)
        validate_outbound_url(target, trusted_local=self.trusted_local)
        redirected = urllib.request.Request(
            target,
            data=None if code in {301, 302, 303} else req.data,
            method="GET" if code in {301, 302, 303} else req.get_method(),
            headers=dict(req.headers),
        )
        if _origin(req.full_url) != _origin(target):
            for key in list(redirected.headers):
                if key.lower() in _SENSITIVE_HEADERS:
                    redirected.remove_header(key)
        return redirected


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, approved_ip: str, port: int, timeout: float | None):
        super().__init__(host, port=port, timeout=timeout)
        self._approved_ip = approved_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._approved_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, approved_ip: str, port: int, timeout: float | None):
        self._ssl_context = ssl.create_default_context()
        super().__init__(host, port=port, timeout=timeout, context=self._ssl_context)
        self._approved_ip = approved_ip

    def connect(self) -> None:
        raw = socket.create_connection((self._approved_ip, self.port), self.timeout)
        self.sock = self._ssl_context.wrap_socket(raw, server_hostname=self.host)


def _request_once(
    url: str,
    *,
    data: bytes | None,
    headers: dict[str, str],
    method: str,
    timeout: float | None,
    trusted_local: bool,
) -> tuple[int, Any, bytes]:
    parsed, approved_ip, port = _resolve_target(url, trusted_local=trusted_local)
    connection_type = _PinnedHTTPSConnection if parsed.scheme.lower() == "https" else _PinnedHTTPConnection
    connection = connection_type(parsed.hostname or "", approved_ip, port, timeout)
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    try:
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.headers, response.read()
    finally:
        connection.close()


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
    """Request JSON with retry and address-pinned SSRF protection."""
    label = api_label if "://" not in api_label else safe_url_label(api_label)
    max_retries, base, cap = _retry_settings()
    attempt = 0
    while True:
        current_url = url
        current_data: bytes | None = data
        current_method = method
        current_headers = dict(headers)
        try:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                status, response_headers, body = _request_once(
                    current_url,
                    data=current_data,
                    headers=current_headers,
                    method=current_method,
                    timeout=timeout,
                    trusted_local=trusted_local,
                )
                if status not in _REDIRECT_STATUS:
                    if 200 <= status < 300:
                        return json.loads(body.decode("utf-8"))
                    detail = body.decode("utf-8", errors="replace")
                    message = f"HTTP {status} from {label}: {detail}"
                    if status not in RETRYABLE_STATUS or attempt >= max_retries:
                        raise HTTPRequestError(message, status=status, attempts=attempt + 1)
                    _sleep_for(attempt, base, cap, _retry_after_seconds(response_headers))
                    break
                if redirect_count >= _MAX_REDIRECTS:
                    raise HTTPRequestError("too many outbound redirects", attempts=attempt + 1)
                location = response_headers.get("Location")
                if not location:
                    raise HTTPRequestError("outbound redirect missing Location", status=status)
                target = urllib.parse.urljoin(current_url, location)
                # Resolve now for fail-fast policy; _request_once will use its own exact approved result.
                validate_outbound_url(target, trusted_local=trusted_local)
                if _origin(current_url) != _origin(target):
                    current_headers = {
                        key: value
                        for key, value in current_headers.items()
                        if key.lower() not in _SENSITIVE_HEADERS
                    }
                if status in {301, 302, 303}:
                    current_method, current_data = "GET", None
                current_url = target
            else:  # pragma: no cover - loop always returns, breaks, or raises
                raise HTTPRequestError("too many outbound redirects")
        except HTTPRequestError as exc:
            if exc.status not in RETRYABLE_STATUS or attempt >= max_retries:
                raise
            _sleep_for(attempt, base, cap, None)
        except (OSError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
            message = f"{type(exc).__name__} from {label}: {exc}"
            if attempt >= max_retries:
                raise HTTPRequestError(message, status=None, attempts=attempt + 1) from exc
            _sleep_for(attempt, base, cap, None)
        attempt += 1
