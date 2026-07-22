"""Dashboard server: HTTP REST API + WebSocket for live progress.

The server is split into two cooperating pieces:

* :class:`BenchServer` owns the HTTP server (stdlib ``http.server``) and an
  optional WebSocket server (``websockets`` library, optional dependency).
* :class:`BenchAPIHandler` routes HTTP requests to REST endpoints.

When ``websockets`` is not installed, the server still works — the frontend
falls back to polling ``/api/runs/{id}/progress``.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ckl_bench.core.cases import (
    CaseValidationError,
    EvalCase,
    case_to_dict,
    load_cases,
    validate_case_dict,
    write_cases,
)
from ckl_bench.core.providers import load_namespaces, load_provider
from ckl_bench.core.reporting import _render_react_page
from ckl_bench.core.run_manager import RunManager
from ckl_bench.core.settings import (
    Settings,
    apply_settings,
    load_settings,
    mask_secrets,
    save_settings,
    settings_from_dict,
    test_adapter,
)

_log = logging.getLogger(__name__)

#: Default case file for newly created cases.
DEFAULT_CASE_FILE = "custom.jsonl"
MAX_BODY_BYTES = 1024 * 1024
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
BUILTIN_DASHBOARD_ADAPTERS = {"mock"}
CONFIGURED_ADAPTER_KEYS = {"claude-code", "codex", "dsx"}
IMMUTABLE_ADAPTER_CONFIG_KEYS = {"command", "endpoint", "base_url", "workspace_dir", "cache_dir"}
EDITABLE_ADAPTER_CONFIG_KEYS = {"api_key", "model"}
EDITABLE_DEFAULT_KEYS = {"repeat", "concurrency", "seed", "judge"}


class RequestTooLargeError(ValueError):
    pass


class BenchServer:
    """Run the HTTP API and optional WebSocket server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        runs_dir: str | Path = "runs",
        cases_dir: str | Path = "cases",
        token: str | None = None,
        origin: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(32)
        self.origin = origin or f"http://{host}:{port}"
        self.runs_dir = Path(runs_dir)
        self.cases_dir = Path(cases_dir)
        self.manager = RunManager(
            self.runs_dir,
            self.cases_dir,
            db_path=self.runs_dir / "ckl-bench.db",
        )
        self._http_server: ThreadingHTTPServer | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_loop: Any = None  # asyncio event loop for the WS server
        self._stop_event = threading.Event()
        self._case_lock = threading.Lock()
        # Load and apply persistent settings (env vars for wrapper scripts).
        self.settings: Settings = load_settings()
        apply_settings(self.settings)

    def start(self, blocking: bool = True) -> None:
        """Start the server. *blocking=False* runs it in a background thread."""
        handler = _make_handler(self)
        self._http_server = ThreadingHTTPServer((self.host, self.port), handler)

        # Try to start WebSocket server (best-effort).
        self._start_ws()

        addr = f"http://{self.host}:{self.port}"
        _log.info("ckl-bench server running at %s", addr)
        print(f"ckl-bench dashboard: {addr}")
        ws_port = self.port + 1
        _log.info("WebSocket at ws://%s:%s/ws", self.host, ws_port)

        if blocking:
            try:
                self._http_server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.shutdown()
        else:
            thread = threading.Thread(
                target=self._http_server.serve_forever,
                name="ckl-http",
                daemon=True,
            )
            thread.start()

    def _start_ws(self) -> None:
        """Start the WebSocket server in a background thread if available."""
        try:
            import asyncio

            import websockets  # type: ignore[import-untyped]
        except ImportError:
            _log.info("websockets not installed; live progress disabled (polling fallback)")
            return

        manager = self.manager
        token = self.token
        token_protocol = "ckl-bench-token." + base64.urlsafe_b64encode(
            token.encode("utf-8")
        ).decode("ascii").rstrip("=")
        allowed_origin = self.origin
        ws_port = self.port + 1  # WS on next port over to avoid path conflicts

        async def ws_handler(websocket):  # type: ignore[no-untyped-def]
            """Authenticate and forward progress events to same-origin clients."""
            request = getattr(websocket, "request", None)
            path = getattr(request, "path", None) or getattr(websocket, "path", "")
            headers = getattr(request, "headers", None) or getattr(websocket, "request_headers", {})
            parsed = urlparse(path)
            origin = headers.get("Origin") if headers is not None else None
            protocols = headers.get("Sec-WebSocket-Protocol", "") if headers is not None else ""
            offered = {item.strip() for item in protocols.split(",") if item.strip()}
            if (
                parsed.path != "/ws"
                or parsed.query
                or origin != allowed_origin
                or "ckl-bench" not in offered
                or not any(hmac.compare_digest(item, token_protocol) for item in offered)
            ):
                await websocket.close(code=1008, reason="unauthorized")
                return

            def listener(event: dict[str, Any]) -> None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        websocket.send(json.dumps(event, default=str)),
                        loop,
                    )
                except Exception:  # noqa: BLE001
                    pass

            manager.add_listener(listener)
            try:
                # Send initial snapshot.
                await websocket.send(json.dumps({"type": "connected", "ws_port": ws_port}))
                async for _ in websocket:
                    pass  # keep connection open until client disconnects
            except Exception:  # noqa: BLE001
                pass
            finally:
                manager.remove_listener(listener)

        loop = asyncio.new_event_loop()
        self._ws_loop = loop
        self._ws_stop: Any = None  # asyncio.Event, set inside run_ws

        async def run_ws() -> None:
            stop_event = asyncio.Event()
            self._ws_stop = stop_event
            async with websockets.serve(
                ws_handler,
                self.host,
                ws_port,
                subprotocols=["ckl-bench"],
            ):
                _log.info("WebSocket server running at ws://%s:%d", self.host, ws_port)
                await stop_event.wait()  # run until shutdown sets the event

        def _thread_main() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_ws())
            except asyncio.CancelledError:
                pass
            finally:
                loop.close()

        self._ws_thread = threading.Thread(target=_thread_main, name="ckl-ws", daemon=True)
        self._ws_thread.start()

    def shutdown(self) -> None:
        """Gracefully shut down the server."""
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
        # Signal the WebSocket loop to exit cleanly (lets run_ws complete and
        # the async with block close the server before the loop is closed).
        if self._ws_loop is not None and self._ws_stop is not None:
            try:
                self._ws_loop.call_soon_threadsafe(self._ws_stop.set)
            except Exception:  # noqa: BLE001 - loop may already be closed
                pass
        self._stop_event.set()
        if self._ws_thread is not None:
            self._ws_thread.join(timeout=5)
            self._ws_thread = None
        self.manager.close(timeout=5)
        try:
            from ckl_bench.core.logging_config import shutdown_logging
            shutdown_logging()
        except Exception:  # noqa: BLE001
            _log.exception("logging shutdown failed")


def _int_field(body: dict[str, Any], name: str, default: int, minimum: int | None = None) -> int:
    value = body.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _optional_str(body: dict[str, Any], name: str) -> str | None:
    value = body.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _make_handler(server: BenchServer) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to *server*."""

    class Handler(BenchAPIHandler):
        bench_server = server

    return Handler


class BenchAPIHandler(BaseHTTPRequestHandler):
    """REST API + static file handler."""

    bench_server: BenchServer  # set by _make_handler

    # Silence default request logging; use logging module instead.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        _log.debug("api %s", format % args)

    # -- Response helpers ---------------------------------------------------

    def _request_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin == self.bench_server.origin

    def _authenticated(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(
            supplied,
            self.bench_server.token,
        )

    def _authorize_api(self) -> bool:
        if not self._request_origin_allowed():
            self._error(403, "forbidden origin")
            return False
        if not self._authenticated():
            self._error(401, "unauthorized")
            return False
        return True

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin == self.bench_server.origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status=status)

    def _read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0:
            raise ValueError("invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise RequestTooLargeError(f"request body exceeds {MAX_BODY_BYTES} bytes")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
        return body

    # -- CORS preflight -----------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._request_origin_allowed():
            self._error(403, "forbidden origin")
            return
        if not self._authenticated():
            self._error(401, "unauthorized")
            return
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    # -- Routing ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        # Static: serve the React app.
        if path == "/" or path == "/index.html":
            self._serve_app()
            return

        # API routes.
        if path.startswith("/api/") and not self._authorize_api():
            return
        try:
            if path == "/api/cases":
                self._list_cases(query)
            elif path.startswith("/api/cases/"):
                self._get_case(unquote(path.rsplit("/", 1)[-1]))
            elif path == "/api/runs":
                self._list_runs()
            elif path.startswith("/api/runs/") and path.endswith("/progress"):
                run_id = path.split("/")[3]
                self._get_progress(run_id)
            elif path.startswith("/api/runs/"):
                self._get_run(unquote(path.rsplit("/", 1)[-1]))
            elif path == "/api/providers":
                self._list_providers()
            elif path == "/api/config":
                self._get_config()
            elif path == "/api/settings":
                self._get_settings()
            else:
                self._error(404, "not found")
        except Exception:  # noqa: BLE001
            _log.exception("GET %s failed", path)
            self._error(500, "internal server error")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/api/") and not self._authorize_api():
            return

        try:
            body = self._read_body()
            if path == "/api/cases":
                self._create_case(body)
            elif path == "/api/runs":
                self._launch_run(body)
            elif path.startswith("/api/runs/") and path.endswith("/cancel"):
                self._cancel_run(unquote(path.split("/")[3]))
            elif path == "/api/settings/test":
                self._test_settings_adapter(body)
            else:
                self._error(404, "not found")
        except RequestTooLargeError as exc:
            self._error(413, str(exc))
        except CaseValidationError as exc:
            self._error(400, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception:  # noqa: BLE001
            _log.exception("POST %s failed", path)
            self._error(500, "internal server error")

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/api/") and not self._authorize_api():
            return

        try:
            body = self._read_body()
            if path.startswith("/api/cases/"):
                self._update_case(unquote(path.rsplit("/", 1)[-1]), body)
            elif path == "/api/settings":
                self._update_settings(body)
            else:
                self._error(404, "not found")
        except RequestTooLargeError as exc:
            self._error(413, str(exc))
        except CaseValidationError as exc:
            self._error(400, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception:  # noqa: BLE001
            _log.exception("PUT %s failed", path)
            self._error(500, "internal server error")

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/api/") and not self._authorize_api():
            return

        try:
            if path.startswith("/api/cases/"):
                self._delete_case(unquote(path.rsplit("/", 1)[-1]))
            else:
                self._error(404, "not found")
        except Exception:  # noqa: BLE001
            _log.exception("DELETE %s failed", path)
            self._error(500, "internal server error")

    # -- Static serving -----------------------------------------------------

    def _serve_app(self) -> None:
        """Serve the React SPA in app mode."""
        try:
            html = _render_react_page(
                {
                    "page": "app",
                    "ws_port": self.bench_server.port + 1,
                    "api_token": self.bench_server.token,
                }
            )
        except FileNotFoundError:
            self._error(500, "web template not found; build the frontend first")
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -- Cases API ----------------------------------------------------------

    def _all_cases(self) -> list[EvalCase]:
        return load_cases([str(self.bench_server.cases_dir)])

    def _list_cases(self, query: dict[str, list[str]]) -> None:
        pack = query.get("pack", [None])[0]
        cases = self._all_cases()
        if pack:
            # Filter by pack directory name (e.g. "chat", "agent").
            pack_path = self.bench_server.cases_dir / pack
            cases = [c for c in cases if str(c.source_path).startswith(str(pack_path))]
        result = [
            {
                "id": c.id,
                "title": c.title,
                "type": c.type,
                "capability": c.capability,
                "difficulty": c.difficulty,
                "timeout_s": c.timeout_s,
                "source": f"{c.source_path}:{c.source_line}",
            }
            for c in cases
        ]
        self._json(result)

    def _get_case(self, case_id: str) -> None:
        for case in self._all_cases():
            if case.id == case_id:
                self._json(case_to_dict(case))
                return
        self._error(404, f"case not found: {case_id}")

    def _create_case(self, body: dict[str, Any]) -> None:
        case = validate_case_dict(body)
        pack = body.get("pack")
        with self.bench_server._case_lock:
            if any(existing.id == case.id for existing in self._all_cases()):
                self._error(409, f"case id already exists: {case.id}")
                return
            if pack:
                # Validate pack name to prevent path traversal.
                if not isinstance(pack, str) or "/" in pack or ".." in pack or pack.startswith("."):
                    self._error(400, f"invalid pack name: {pack}")
                    return
                pack_dir = self.bench_server.cases_dir / pack
                if not pack_dir.is_dir():
                    self._error(400, f"pack does not exist: {pack}")
                    return
                target = pack_dir / DEFAULT_CASE_FILE
            else:
                target = self.bench_server.cases_dir / DEFAULT_CASE_FILE
            existing = load_cases([str(target)]) if target.exists() else []
            write_cases(target, [*existing, case])
        self._json(case_to_dict(case), status=201)

    def _update_case(self, case_id: str, body: dict[str, Any]) -> None:
        if "id" in body and body["id"] != case_id:
            self._error(409, "case id does not match URL")
            return
        updated = validate_case_dict({**body, "id": case_id})
        with self.bench_server._case_lock:
            target_case = next((c for c in self._all_cases() if c.id == case_id), None)
            if target_case is None:
                self._error(404, f"case not found: {case_id}")
                return
            file_cases = load_cases([str(target_case.source_path)])
            write_cases(
                target_case.source_path,
                [updated if c.id == case_id else c for c in file_cases],
            )
        self._json(case_to_dict(updated))

    def _delete_case(self, case_id: str) -> None:
        with self.bench_server._case_lock:
            target_case = next((c for c in self._all_cases() if c.id == case_id), None)
            if target_case is None:
                self._error(404, f"case not found: {case_id}")
                return
            file_cases = load_cases([str(target_case.source_path)])
            write_cases(target_case.source_path, [c for c in file_cases if c.id != case_id])
        self._json({"deleted": case_id})

    # -- Runs API -----------------------------------------------------------

    def _list_runs(self) -> None:
        runs = self.bench_server.manager.list_runs()
        self._json(runs)

    def _get_run(self, run_id: str) -> None:
        run = self.bench_server.manager.get_run(run_id)
        if run is None:
            self._error(404, f"run not found: {run_id}")
            return
        if run.get("status") in TERMINAL_RUN_STATUSES:
            run["results"] = self.bench_server.manager.get_run_results(run_id)
        self._json(run)

    def _get_progress(self, run_id: str) -> None:
        run = self.bench_server.manager.get_run(run_id)
        if run is None:
            self._error(404, f"run not found: {run_id}")
            return
        self._json({"run_id": run_id, "status": run["status"], "progress": run.get("progress", {})})

    def _trusted_provider(self, target: str) -> dict[str, Any] | None:
        provider = load_provider(target)
        if provider is None:
            return None
        adapter = provider.get("adapter")
        if not isinstance(adapter, str) or ":" in adapter:
            return None
        from ckl_bench.adapters.registry import BUILT_INS

        return provider if adapter in BUILT_INS else None

    def _configured_adapter(self, key: str) -> tuple[str, dict[str, Any]] | None:
        if key not in CONFIGURED_ADAPTER_KEYS:
            return None
        config = dict(self.bench_server.settings.adapters.get(key, {}))
        if not config.get("command"):
            return None
        return "command", config

    def _launch_run(self, body: dict[str, Any]) -> None:
        requested = body.get("adapter_target") or body.get("adapter")
        if not isinstance(requested, str) or not requested:
            raise ValueError("adapter must be a non-empty trusted target")
        if body.get("adapter_config") or body.get("config"):
            raise ValueError("adapter_config is not accepted by the dashboard")
        if any(body.get(name) is not None for name in ("cache_dir", "reviewer", "verifier")):
            raise ValueError("dashboard run contains unsupported execution options")

        adapter_name: str | None = None
        adapter_target: str | None = None
        adapter_config: dict[str, Any] = {}
        configured = self._configured_adapter(requested)
        if configured is not None:
            adapter_name, adapter_config = configured
        elif requested in BUILTIN_DASHBOARD_ADAPTERS:
            adapter_name = requested
        elif self._trusted_provider(requested) is not None:
            adapter_target = requested
        else:
            raise ValueError(f"untrusted dashboard adapter: {requested}")

        case_ids = body.get("case_ids")
        case_paths = body.get("case_paths")
        if case_ids is not None and (
            not isinstance(case_ids, list) or not all(isinstance(item, str) for item in case_ids)
        ):
            raise ValueError("case_ids must be a list of strings")
        if case_paths is not None:
            if not isinstance(case_paths, list) or not all(isinstance(item, str) for item in case_paths):
                raise ValueError("case_paths must be a list of strings")
            trusted_packs = {
                str(path.resolve())
                for path in self.bench_server.cases_dir.iterdir()
                if path.is_dir()
            } if self.bench_server.cases_dir.is_dir() else set()
            resolved_paths = []
            for raw_path in case_paths:
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = self.bench_server.cases_dir.parent / candidate
                resolved = str(candidate.resolve())
                if resolved not in trusted_packs:
                    raise ValueError(f"untrusted case path: {raw_path}")
                resolved_paths.append(resolved)
            case_paths = resolved_paths

        repeat = _int_field(body, "repeat", 1, minimum=1)
        concurrency = _int_field(body, "concurrency", 1, minimum=1)
        seed = _int_field(body, "seed", 0)
        judge_target = _optional_str(body, "judge")
        if judge_target and judge_target not in {"same", "self"} and self._trusted_provider(judge_target) is None:
            raise ValueError(f"untrusted judge target: {judge_target}")

        run_id = self.bench_server.manager.start_run(
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            adapter_target=adapter_target,
            case_paths=case_paths,
            case_ids=case_ids,
            repeat=repeat,
            concurrency=concurrency,
            seed=seed,
            judge_target=judge_target,
        )
        self._json({"run_id": run_id, "status": "running"}, status=202)

    def _cancel_run(self, run_id: str) -> None:
        run = self.bench_server.manager.get_run(run_id)
        if run is None:
            self._error(404, f"run not found: {run_id}")
            return
        if run.get("status") not in {"pending", "running", "cancellation_requested"}:
            self._error(409, f"run is already terminal: {run_id}")
            return
        self.bench_server.manager.cancel_run(run_id)
        self._json({"run_id": run_id, "status": "cancellation_requested"}, status=202)

    # -- Providers / Config -------------------------------------------------

    def _list_providers(self) -> None:
        namespaces = load_namespaces()
        result = [
            {
                "namespace": ns["namespace"],
                "aliases": ns["aliases"],
                "default": ns.get("default", ""),
            }
            for ns in namespaces
        ]
        self._json(result)

    def _get_config(self) -> None:
        # Available case packs (subdirectories of cases/).
        cases_dir = self.bench_server.cases_dir
        packs = sorted(
            p.name for p in cases_dir.iterdir() if p.is_dir()
        ) if cases_dir.is_dir() else []
        # Available adapters.
        from ckl_bench.adapters.registry import BUILT_INS

        adapters = sorted(BUILT_INS.keys())
        self._json(
            {
                "case_packs": packs,
                "adapters": adapters,
                "runs_dir": str(self.bench_server.runs_dir),
                "cases_dir": str(self.bench_server.cases_dir),
                "ws_port": self.bench_server.port + 1,
            }
        )

    # -- Settings API -------------------------------------------------------

    def _get_settings(self) -> None:
        masked = mask_secrets(self.bench_server.settings)
        self._json(
            {
                "adapters": masked.adapters,
                "defaults": masked.defaults,
                "active_adapters": masked.active_adapters,
            }
        )

    def _update_settings(self, body: dict[str, Any]) -> None:
        adapters = body.get("adapters", {})
        defaults = body.get("defaults", {})
        active = body.get("active_adapters", self.bench_server.settings.active_adapters)
        if not isinstance(adapters, dict) or not isinstance(defaults, dict) or not isinstance(active, list):
            raise ValueError("invalid settings shape")
        if any(key not in CONFIGURED_ADAPTER_KEYS for key in adapters):
            raise ValueError("unknown dashboard adapter")
        if any(key not in EDITABLE_DEFAULT_KEYS for key in defaults):
            raise ValueError("unsupported default setting")
        if any(key not in CONFIGURED_ADAPTER_KEYS for key in active):
            raise ValueError("unknown active adapter")
        safe_adapters: dict[str, dict[str, Any]] = {}
        for name, config in adapters.items():
            if not isinstance(config, dict):
                raise ValueError("adapter settings must be objects")
            forbidden = set(config) & IMMUTABLE_ADAPTER_CONFIG_KEYS
            if forbidden:
                raise ValueError("dashboard cannot edit executable or endpoint settings")
            unknown = set(config) - EDITABLE_ADAPTER_CONFIG_KEYS
            if unknown:
                raise ValueError("unsupported adapter setting")
            safe_adapters[name] = dict(config)
        requested = settings_from_dict(
            {"adapters": safe_adapters, "defaults": defaults, "active_adapters": active}
        )
        save_settings(requested, existing=self.bench_server.settings)
        canonical = load_settings()
        apply_settings(canonical)
        self.bench_server.settings = canonical
        masked = mask_secrets(canonical)
        self._json(
            {
                "adapters": masked.adapters,
                "defaults": masked.defaults,
                "active_adapters": masked.active_adapters,
            }
        )

    def _test_settings_adapter(self, body: dict[str, Any]) -> None:
        key = body.get("adapter_name")
        if not isinstance(key, str) or key not in CONFIGURED_ADAPTER_KEYS:
            raise ValueError("unknown dashboard adapter")
        supplied = body.get("config", {}) or {}
        if not isinstance(supplied, dict):
            raise ValueError("config must be an object")
        if set(supplied) & IMMUTABLE_ADAPTER_CONFIG_KEYS:
            raise ValueError("dashboard cannot test executable or endpoint overrides")
        if set(supplied) - EDITABLE_ADAPTER_CONFIG_KEYS:
            raise ValueError("unsupported adapter setting")
        config = dict(self.bench_server.settings.adapters.get(key, {}))
        config.update(supplied)
        result = test_adapter("command", config)
        status = 200 if result["ok"] else 400
        self._json(result, status=status)
