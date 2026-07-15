"""Dashboard server: HTTP REST API + WebSocket for live progress.

The server is split into two cooperating pieces:

* :class:`BenchServer` owns the HTTP server (stdlib ``http.server``) and an
  optional WebSocket server (``websockets`` library, optional dependency).
* :class:`BenchAPIHandler` routes HTTP requests to REST endpoints.

When ``websockets`` is not installed, the server still works — the frontend
falls back to polling ``/api/runs/{id}/progress``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import signal
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ckl_bench.core.cases import (
    CaseValidationError,
    EvalCase,
    case_to_dict,
    load_cases,
    validate_case_dict,
    write_cases,
)
from ckl_bench.core.providers import load_namespaces, load_provider, redacted_namespace
from ckl_bench.core.run_manager import RunManager, collect_runs
from ckl_bench.core.reporting import _render_react_page
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


class BenchServer:
    """Run the HTTP API and optional WebSocket server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        runs_dir: str | Path = "runs",
        cases_dir: str | Path = "cases",
    ) -> None:
        self.host = host
        self.port = port
        self.runs_dir = Path(runs_dir)
        self.cases_dir = Path(cases_dir)
        self.manager = RunManager(self.runs_dir, self.cases_dir)
        self._http_server: ThreadingHTTPServer | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_loop: Any = None  # asyncio event loop for the WS server
        self._stop_event = threading.Event()
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
        ws_port = self.port + 1  # WS on next port over to avoid path conflicts

        async def ws_handler(websocket):  # type: ignore[no-untyped-def]
            """Register a RunManager listener that forwards progress events."""

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
            async with websockets.serve(ws_handler, self.host, ws_port):
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
        # Signal the WebSocket loop to exit cleanly (lets run_ws complete and
        # the async with block close the server before the loop is closed).
        if self._ws_loop is not None and self._ws_stop is not None:
            try:
                self._ws_loop.call_soon_threadsafe(self._ws_stop.set)
            except Exception:  # noqa: BLE001 - loop may already be closed
                pass
        self._stop_event.set()


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

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status=status)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc

    # -- CORS preflight -----------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json({})

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
        try:
            if path == "/api/cases":
                self._list_cases(query)
            elif path.startswith("/api/cases/"):
                self._get_case(path.rsplit("/", 1)[-1])
            elif path == "/api/runs":
                self._list_runs()
            elif path.startswith("/api/runs/") and path.endswith("/progress"):
                run_id = path.split("/")[3]
                self._get_progress(run_id)
            elif path.startswith("/api/runs/"):
                self._get_run(path.rsplit("/", 1)[-1])
            elif path == "/api/providers":
                self._list_providers()
            elif path == "/api/config":
                self._get_config()
            elif path == "/api/settings":
                self._get_settings()
            else:
                self._error(404, "not found")
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            body = self._read_body()
            if path == "/api/cases":
                self._create_case(body)
            elif path == "/api/runs":
                self._launch_run(body)
            elif path == "/api/settings/test":
                self._test_settings_adapter(body)
            else:
                self._error(404, "not found")
        except CaseValidationError as exc:
            self._error(400, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            body = self._read_body()
            if path.startswith("/api/cases/"):
                self._update_case(path.rsplit("/", 1)[-1], body)
            elif path == "/api/settings":
                self._update_settings(body)
            else:
                self._error(404, "not found")
        except CaseValidationError as exc:
            self._error(400, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path.startswith("/api/cases/"):
                self._delete_case(path.rsplit("/", 1)[-1])
            else:
                self._error(404, "not found")
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")

    # -- Static serving -----------------------------------------------------

    def _serve_app(self) -> None:
        """Serve the React SPA in app mode."""
        try:
            html = _render_react_page({"page": "app", "ws_port": self.bench_server.port + 1})
        except FileNotFoundError:
            self._error(500, "web template not found; build the frontend first")
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        # Write to the default case file.
        target = self.bench_server.cases_dir / DEFAULT_CASE_FILE
        existing: list[EvalCase] = []
        if target.exists():
            existing = load_cases([str(target)])
        if any(c.id == case.id for c in existing):
            self._error(409, f"case id already exists: {case.id}")
            return
        existing.append(case)
        write_cases(target, existing)
        self._json(case_to_dict(case), status=201)

    def _update_case(self, case_id: str, body: dict[str, Any]) -> None:
        # Ensure the id matches.
        body["id"] = case_id
        updated = validate_case_dict(body)
        all_cases = self._all_cases()
        target_case = next((c for c in all_cases if c.id == case_id), None)
        if target_case is None:
            self._error(404, f"case not found: {case_id}")
            return
        source_path = target_case.source_path
        # Read current file, replace the case, write back.
        file_cases = load_cases([str(source_path)])
        new_cases = [updated if c.id == case_id else c for c in file_cases]
        write_cases(source_path, new_cases)
        self._json(case_to_dict(updated))

    def _delete_case(self, case_id: str) -> None:
        all_cases = self._all_cases()
        target_case = next((c for c in all_cases if c.id == case_id), None)
        if target_case is None:
            self._error(404, f"case not found: {case_id}")
            return
        source_path = target_case.source_path
        file_cases = load_cases([str(source_path)])
        remaining = [c for c in file_cases if c.id != case_id]
        write_cases(source_path, remaining)
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
        # Include results for completed runs.
        if run.get("status") == "completed":
            run["results"] = self.bench_server.manager.get_run_results(run_id)
        self._json(run)

    def _get_progress(self, run_id: str) -> None:
        run = self.bench_server.manager.get_run(run_id)
        if run is None:
            self._error(404, f"run not found: {run_id}")
            return
        self._json({"run_id": run_id, "status": run["status"], "progress": run.get("progress", {})})

    def _launch_run(self, body: dict[str, Any]) -> None:
        adapter_name = body.get("adapter", "mock")
        adapter_config = body.get("adapter_config") or body.get("config") or {}
        case_paths = body.get("case_paths")
        case_ids = body.get("case_ids")
        repeat = int(body.get("repeat", 1))
        concurrency = int(body.get("concurrency", 1))
        seed = int(body.get("seed", 0))
        judge_target = body.get("judge")
        cache_dir = body.get("cache_dir")

        try:
            run_id = self.bench_server.manager.start_run(
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                case_paths=case_paths,
                case_ids=case_ids,
                repeat=repeat,
                concurrency=concurrency,
                seed=seed,
                judge_target=judge_target,
                cache_dir=cache_dir,
            )
        except CaseValidationError as exc:
            self._error(400, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")
            return

        self._json({"run_id": run_id, "status": "running"}, status=202)

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
        settings = settings_from_dict(body)
        save_settings(settings, existing=self.bench_server.settings)
        apply_settings(settings)
        self.bench_server.settings = settings
        self._json({"ok": True})

    def _test_settings_adapter(self, body: dict[str, Any]) -> None:
        adapter_name = body.get("adapter_name", "mock")
        config = body.get("config", {}) or {}
        result = test_adapter(adapter_name, config)
        status = 200 if result["ok"] else 400
        self._json(result, status=status)
